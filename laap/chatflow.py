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
import os

logger = logging.getLogger("laap.chatflow")

_CHAT_PATH = "/v1/chat/completions"


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


def _wrap(handler):
    async def wrapped(request):
        try:
            body = await request.json()   # aiohttp 快取 body，作者 handler 再讀無虞
            _feed(_extract_user_msg(body))
        except Exception as e:
            logger.debug(f"[chatflow] 攔截跳過: {e}")
        return await handler(request)     # 原封不動走作者 handler
    return wrapped


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
            handler = _wrap(handler)
            logger.info(f"[chatflow] 已包住 {path} — 對話流餵 psi")
        return orig(self, path, handler, **kw)

    patched._laap_chatflow = True
    UrlDispatcher.add_post = patched
    return True
