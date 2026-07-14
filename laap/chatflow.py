"""
chatflow — 把 /v1/chat/completions 的使用者輸入餵進 psi（對話流真正接上心臟）。

問題：作者的 chat handler → process_with_laap → bridge.process 這條認知管線很重、
可能慢甚至卡死整個 process，且不保證餵 psi。agency 的聯想種子需要源源不絕的真對話，
不能依賴這條管線。

做法：monkey-patch aiohttp 的路由註冊，把 /v1/chat/completions 的 handler 包一層 —
請求進入的第一時間（作者 handler 執行之前）就抽 user_msg 餵 psi，不阻塞、不改作者碼、
不管作者管線成敗。aiohttp 的 request.json() 會快取 body，包一層不影響作者 handler 再讀。

install 掛在 startup_all（早於作者 app.router.add_post 註冊，patch 在 class 層級）。
NEURALIS_CHATFLOW=off 可關。
"""
from __future__ import annotations

import logging
import asyncio
import os
import time
import uuid

logger = logging.getLogger("laap.chatflow")

_CHAT_PATH = "/v1/chat/completions"
# 作者的 process_with_laap 是同步阻塞函式，卸載到 executor 後才不會凍結 event loop。
# 逾時降級（executor 版本下 wait_for 有效，因 event loop 沒被阻塞）。
_CHAT_TIMEOUT_S = float(os.environ.get("NEURALIS_CHAT_TIMEOUT_S", 25))


def _extract_user_msg(body: dict) -> str:
    for m in reversed(body.get("messages", []) or []):
        if m.get("role") == "user":
            return (m.get("content", "") or "")[:500]
    return ""


def _feed(user_msg: str) -> None:
    """餵 psi + 重置 consolidation 睡眠窗。任一沒起就 no-op，絕不擋作者 handler。"""
    if not user_msg:
        return
    try:
        from laap.startup import get_psi_core, get_consolidation
        psi = get_psi_core()
        if psi is not None:
            psi.process_input(user_msg)
        cons = get_consolidation()
        if cons is not None:
            cons.note_interaction()
    except Exception as e:
        logger.debug(f"[chatflow] feed 跳過: {e}")


def _build_response(content: str, engine: str, model: str, prompt_chars: int) -> dict:
    """複製作者 handle_chat_completions 的非 streaming OpenAI response 格式。"""
    return {
        "id": f"laap-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0,
                     "message": {"role": "assistant", "content": content},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": prompt_chars // 4,
                  "completion_tokens": len(content) // 4, "total_tokens": 0},
        "engine": engine,
    }


def _make_chat_handler(orig_handler):
    """包住作者 chat handler：(1) 餵 psi (2) 非 streaming 走 executor 卸載 + timeout
    （治 event loop 阻塞隱患）。streaming 走作者原 handler（少數，保留其 SSE 邏輯）。"""
    from aiohttp import web

    async def handler(request):
        try:
            body = await request.json()   # aiohttp 快取 body，作者/executor 再讀無虞
        except Exception as e:
            logger.debug(f"[chatflow] body 解析失敗，交回作者: {e}")
            return await orig_handler(request)

        _feed(_extract_user_msg(body))

        # streaming：保留作者 SSE 實作（同步阻塞風險僅限這條少數路徑）
        if body.get("stream"):
            return await orig_handler(request)

        # 非 streaming：把同步的 process_with_laap 丟 executor，不凍結 event loop
        model = body.get("model", "laap-core")
        messages = body.get("messages", [])
        prompt_chars = sum(len(m.get("content", "")) for m in messages)
        try:
            import laap_brain_api as api   # 執行時已載入（runpy 起 API 後）
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, api.process_with_laap, messages, model),
                timeout=_CHAT_TIMEOUT_S)
            content = result.get("content", "")
            engine = result.get("engine", "laap-core")
        except asyncio.TimeoutError:
            logger.warning(f"[chatflow] 認知管線逾時 {_CHAT_TIMEOUT_S}s → 降級回應")
            content = "（認知管線處理逾時，本次降級回應。狀態未受影響。）"
            engine = "laap-timeout"
        except Exception as e:
            logger.debug(f"[chatflow] executor 路徑失敗，交回作者 handler: {e}")
            return await orig_handler(request)
        return web.json_response(_build_response(content, engine, model, prompt_chars))

    return handler


def install() -> bool:
    """patch aiohttp add_post，包住 chat completions handler。冪等。回是否安裝。"""
    if os.environ.get("NEURALIS_CHATFLOW", "on").lower() in ("off", "0", "false"):
        return False
    try:
        from aiohttp.web_urldispatcher import UrlDispatcher
    except Exception as e:
        logger.warning(f"[chatflow] aiohttp 不可用，跳過: {e}")
        return False
    if getattr(UrlDispatcher.add_post, "_laap_chatflow", False):
        return True  # 已裝
    orig = UrlDispatcher.add_post

    def patched(self, path, handler, **kw):
        if path == _CHAT_PATH:
            handler = _make_chat_handler(handler)
            logger.info(f"[chatflow] 已包住 {path} — 餵 psi + executor 卸載（防 event loop 阻塞）")
        return orig(self, path, handler, **kw)

    patched._laap_chatflow = True
    UrlDispatcher.add_post = patched
    return True
