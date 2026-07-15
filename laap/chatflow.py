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

import json
import logging
import asyncio
import os
import re
import time
import uuid
from collections import deque
from pathlib import Path

logger = logging.getLogger("laap.chatflow")

_CHAT_PATH = "/v1/chat/completions"
# 作者的 process_with_laap 是同步阻塞函式，卸載到 executor 後才不會凍結 event loop。
# 逾時降級（executor 版本下 wait_for 有效，因 event loop 沒被阻塞）。
_CHAT_TIMEOUT_S = float(os.environ.get("NEURALIS_CHAT_TIMEOUT_S", 25))
_BOOT_TS = time.time()


def _content_text(c) -> str:
    """content 可能是 str / OpenAI content parts list / None（assistant tool_calls）。"""
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c
                        if isinstance(p, dict) and p.get("type") == "text")
    return ""


def _extract_user_msg(body: dict) -> str:
    for m in reversed(body.get("messages", []) or []):
        if m.get("role") == "user":
            return _content_text(m.get("content"))[:500]
    return ""


def _is_user_turn(body: dict) -> bool:
    """最後一條訊息是 user 才是真的使用者回合。工具迴圈的中間 round-trip
    （最後是 tool）不重複餵 psi、不重複加 trust、不重查記憶 — 否則同一句話
    在一個 agent 任務裡被灌 N 次，需求滿足與信任全失真。"""
    msgs = body.get("messages") or []
    return bool(msgs) and msgs[-1].get("role") == "user"


# scream 的內部簿記請求（session 摘要/標題生成）也走 /v1/chat，最後一條 role
# 也是 user — 但那是 harness 在說話，不是 Ryan。餵進 psi 會污染 last_input、
# 灌假 trust。ponytail: 前綴 denylist，夠擋現役已知款；新款出現再補 regex。
_FEED_DENY = re.compile(os.environ.get(
    "NEURALIS_FEED_DENY_REGEX",
    r"^(以下是会话|以下是會話|请为以下|請為以下|Summarize|Generate a (short )?title)"))


def _is_harness_noise(user_msg: str) -> bool:
    return bool(user_msg) and bool(_FEED_DENY.match(user_msg))


_DUMP = os.environ.get("NEURALIS_DUMP_REQUESTS", "off").lower() in ("on", "1", "true")


def _dump_request(body: dict) -> None:
    """NEURALIS_DUMP_REQUESTS=on → 存請求原貌到 /tmp/laap-request-dumps/，
    照實物設計工具協議用，平常關。"""
    try:
        d = Path("/tmp/laap-request-dumps")
        d.mkdir(exist_ok=True)
        (d / f"req-{int(time.time() * 1000)}.json").write_text(
            json.dumps(body, ensure_ascii=False, indent=1)[:300000],
            encoding="utf-8")
    except Exception:
        pass


def _feed(user_msg: str):
    """餵 psi + 重置 consolidation 睡眠窗，並量出這句話造成的實際 delta。
    回 (state_after, delta) 或 None。任一沒起就 no-op，絕不擋作者 handler。"""
    if not user_msg:
        return None
    try:
        from laap.startup import get_psi_core, get_consolidation
        psi = get_psi_core()
        fed = None
        if psi is not None:
            st0 = psi.get_state()
            psi.process_input(user_msg)
            st1 = psi.get_state()
            delta = {
                k: round(v["current"] - st0["needs"][k]["current"], 3)
                for k, v in st1["needs"].items()
            }
            delta["valence"] = round(
                st1["emotion"]["valence"] - st0["emotion"]["valence"], 3)
            fed = (st1, delta)
            _write_author_state(st1)
        cons = get_consolidation()
        if cons is not None:
            cons.note_interaction()
        return fed
    except Exception as e:
        logger.debug(f"[chatflow] feed 跳過: {e}")
        return None


def _write_author_state(st: dict) -> None:
    """圓作者的檔案契約：Rust psi_core 本該每 100ms 寫 state/latest.json，
    整個 aris_brain（process_with_laap Step 3、cognitive_bus、integration）都讀它，
    但 Rust 版缺失所以檔案從未存在。這裡在 chat 時間點寫入（讀端就是 chat 管線，
    此時最新鮮）。schema 取讀端聯集：needs/attention/emotion/cycle/daemon_uptime。"""
    base = os.environ.get("LAAP_AGI_DIR", "")
    if not base:
        return
    try:
        d = Path(base) / "aris_brain" / "state"
        d.mkdir(parents=True, exist_ok=True)
        payload = {
            "cycle": st["tick"],
            "needs": {k: v["current"] for k, v in st["needs"].items()},
            "attention": st["attention"],
            "emotion": st["emotion"],
            "daemon_uptime": round(time.time() - _BOOT_TS, 1),
            "ts": time.time(),
            "source": "neuralis-python-psi",
        }
        tmp = d / "latest.json.tmp"
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(d / "latest.json")
    except Exception as e:
        logger.debug(f"[chatflow] author state 寫入跳過: {e}")


# ponytail: v0 規則表組句，不是認知。天花板 = 模板語感；升級路徑 = 把 st/delta
# 塞給真 LLM 的 system prompt（等 LAAP 管線接上 LLM 後改走那條）。
_quoted_recently: deque = deque(maxlen=6)   # 引用過的記憶（避免每輪想起同一件事）
_MEM_EXTRA_WAIT_S = float(os.environ.get("NEURALIS_PSI_MEMORY_WAIT", 2.5))
_pending_memories: dict = {"ts": 0.0, "lines": []}   # 遲到的召回 → 下一輪「剛想起」


def _collect_memories(task) -> list:
    """已完成的平行召回直接收割；沒完成回空（caller 再決定等多久）。"""
    if task is not None and task.done():
        try:
            return task.result() or []
        except Exception:
            pass
    return []


def _stash_late_memories(task) -> None:
    try:
        lines = task.result() or []
        if lines:
            _pending_memories["ts"] = time.time()
            _pending_memories["lines"] = lines
    except Exception:
        pass


def _take_pending_memories() -> list:
    """上一輪遲到的召回，5 分鐘內有效（過期就不硬聊舊哏）。"""
    if _pending_memories["lines"] and time.time() - _pending_memories["ts"] < 300:
        lines, _pending_memories["lines"] = _pending_memories["lines"], []
        return lines
    _pending_memories["lines"] = []
    return []


def _psi_memories_sync(query: str) -> list[str]:
    """同步查 gbrain 相關記憶，供 psi-respond 織入。timeout 由 caller 處理。
    去重：近 6 輪引用過的段落不再引（不然同話題每句都想起同一件事，穿幫）。"""
    try:
        from gbrain_client import get_client, hybrid_hits
        client = get_client()
        if client is None:
            return []
        hits = hybrid_hits(client, query[:100], 4)
        out = []
        for h in hits:
            if h.get("score", 0) < 0.3:
                continue
            t = " ".join((h.get("chunk_text", "") or "").split())
            key = t[:40]
            if len(t) < 4 or key in _quoted_recently:
                continue
            _quoted_recently.append(key)
            out.append(t[:80])
            if len(out) >= 2:
                break
        return out
    except Exception:
        return []


_NEED_PHRASE = {
    "competence": "想把手上的事做好",
    "relatedness": "想要有連結、有人說話",
    "autonomy": "想自己作主安排些什麼",
    "certainty": "想把狀況弄清楚",
    "growth": "想學點新東西",
}


def _compose_psi_reply(st: dict, delta: dict, memories: list[str] = None) -> str:
    """用真實狀態 + 這句話的實測 delta + 相關記憶組回應。每個數字都可回溯，不演。"""
    e = st["emotion"]
    moved = {k: v for k, v in delta.items() if k != "valence" and abs(v) >= 0.01}
    if moved:
        parts = "、".join(f"{k} {v:+.2f}" for k, v in
                          sorted(moved.items(), key=lambda x: -abs(x[1])))
        dv = delta.get("valence", 0)
        touch = f"你這句話碰到了我 — {parts}" + (
            f"，valence {dv:+.2f}。" if abs(dv) >= 0.005 else "。")
    else:
        touch = "這句話沒有明顯觸動哪個需求（都在 ±0.01 內）。"

    v, a = e["valence"], e["arousal"]
    mood = "心情偏亮" if v >= 0.15 else "心情偏沉" if v <= -0.15 else "情緒平穩"
    if a >= 0.55:
        mood += "、有點亢奮"
    elif a < 0.25:
        mood += "、很鬆"

    dom = st["dominant_need"]
    reply = (f"{touch}現在主導我的是 {dom}"
             f"（drive {st['dominant_drive']:.2f}，{_NEED_PHRASE.get(dom, dom)}），"
             f"{mood}（v{v:+.2f}, a{a:.2f}），注意力在 {st['attention']}。")
    # 織入記憶聯想 — 出處誠實：hit 是腦庫段落（wiki/行動紀錄/對話都可能），
    # 不可宣稱「你說過」（誤標出處 = LARP）
    if memories:
        reply += f"\n（這讓我想起腦裡的一段：「{memories[0]}」）"
    return reply


def _psi_respond(fed, user_msg: str, memories: list[str] = None,
                 history: list = None) -> str:
    """PsiCore 回應生成：LLM 優先 → delta 模板（含記憶聯想）→ psi_response 通用模板。"""
    try:
        use_psi = os.environ.get("NEURALIS_PSI_RESPOND", "on").lower()
        if use_psi in ("off", "0", "false"):
            return ""
        from laap.startup import get_psi_core
        psi = get_psi_core()
        if psi is not None:
            from laap.llm_respond import respond as llm_respond
            llm = llm_respond(user_msg, fed[0] if fed else psi.get_state(),
                              history=history, memories=memories,
                              delta=fed[1] if fed else None)
            if llm:
                return llm
    except Exception as e:
        logger.debug(f"[chatflow] LLM respond 跳過: {e}")
    try:
        if fed:
            return _compose_psi_reply(*fed, memories=memories)
    except Exception as e:
        logger.debug(f"[chatflow] _compose_psi_reply 跳過: {e}")
    try:
        from laap.psi_response import generate_response
        psi = get_psi_core()
        if psi is not None:
            result = generate_response(user_msg, psi.get_state())
            if result.get("engine") == "psi-rules":
                return result["content"]
    except Exception as e:
        logger.debug(f"[chatflow] psi_response 跳過: {e}")
    return ""


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

        if _DUMP:
            _dump_request(body)

        # 只有真使用者回合才餵 psi / 加 trust
        # （工具迴圈 round-trip 不算；harness 簿記請求不算）
        user_msg = _extract_user_msg(body)
        user_turn = _is_user_turn(body) and not _is_harness_noise(user_msg)
        fed = _feed(user_msg) if user_turn else None

        # 忙碌保護：如果 LAAP 工具正在執行中，阻止新對話打斷
        if user_turn:
            try:
                import json as _json
                with open("/tmp/laap-tool-status.json") as _f:
                    _st = _json.load(_f)
                if _st.get("status") in ("start", "running"):
                    _busy_msg = f"（正在執行 {_st.get('description', '工作')}，請稍等，完成後會通知你。）"
                    model = body.get("model", "laap-core")
                    messages = body.get("messages", [])
                    prompt_chars = sum(len(_content_text(m.get("content"))) for m in messages)
                    return web.json_response(_build_response(_busy_msg, "laap-busy", model, prompt_chars))
            except Exception:
                pass

        # 催產素：每次「使用者」對話提升信任權重
        if user_turn:
            try:
                from laap.startup import get_agency
                ag = get_agency()
                if ag is not None:
                    ag.note_interaction()
            except Exception:
                pass

        # 工具模式：scream agent 迴圈（作者管線不懂 tools → LLM 語言皮質直達）
        if body.get("tools"):
            return await _tool_chat(request, web, body, fed)

        # 記憶聯想：與作者管線「平行」召回（gbrain hybrid 實測 5-9s，序列等 = 延遲牆）。
        # 管線回來後只再等一小段；沒等到就 stash，下一輪用「剛想起」帶出 — 零延遲牆。
        memories = []
        mem_task = None
        if user_turn and user_msg and os.environ.get("NEURALIS_PSI_MEMORY", "on").lower() not in ("off", "0", "false"):
            mem_task = asyncio.get_event_loop().run_in_executor(
                None, _psi_memories_sync, user_msg)

        # streaming 也走我們的管線（scream TUI 用 stream:true — 交回作者會繞過
        # psi-llm 且作者 streaming 路有同步阻塞 event loop 的老 bug）。
        # 統一：算完 content 後，stream 就用 SSE 送、否則 JSON。
        model = body.get("model", "laap-core")
        messages = body.get("messages", [])
        prompt_chars = sum(len(_content_text(m.get("content"))) for m in messages)
        try:
            import laap_brain_api as api   # 執行時已載入（runpy 起 API 後）
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, api.process_with_laap, messages, model),
                timeout=_CHAT_TIMEOUT_S)
            content = result.get("content", "")
            engine = result.get("engine", "laap-core")
            memories = _collect_memories(mem_task) + _take_pending_memories()
            if mem_task and not mem_task.done():
                try:
                    got = await asyncio.wait_for(
                        asyncio.shield(mem_task), timeout=_MEM_EXTRA_WAIT_S)
                    memories = got + memories
                except (asyncio.TimeoutError, Exception):
                    mem_task.add_done_callback(_stash_late_memories)  # 下一輪「剛想起」
            # 作者管線只剩 canned fallback 時 → 用真實 psi 狀態回應（情緒真的影響回應）
            # 安全網：RulesEngine 誤匹配（回 rules:* + 工具錯誤）也讓 psi-respond 接管
            if fed and (
                engine == "laap-fallback"
                or (engine.startswith("rules:") and re.match(r'^\[.*\]', content.strip()))
            ):
                hist = [m for m in messages
                        if m.get("role") in ("user", "assistant")]
                if hist and hist[-1].get("role") == "user":
                    hist = hist[:-1]   # 這句 user_msg 由 llm_respond 自己補
                psi_content = _psi_respond(fed, user_msg, memories=memories,
                                           history=hist)
                if psi_content:
                    content = psi_content
                    engine = "psi-llm" if os.environ.get("NEURALIS_LLM_RESPOND", "off").lower() in ("on", "1", "true") else "psi-respond"
        except asyncio.TimeoutError:
            logger.warning(f"[chatflow] 認知管線逾時 {_CHAT_TIMEOUT_S}s → 降級回應")
            content = "（認知管線處理逾時，本次降級回應。狀態未受影響。）"
            engine = "laap-timeout"
        except Exception as e:
            logger.debug(f"[chatflow] executor 路徑失敗，交回作者 handler: {e}")
            return await orig_handler(request)

        if body.get("stream"):
            return await _stream_sse(
                request, web,
                {"message": {"role": "assistant", "content": content},
                 "finish_reason": "stop"}, model)
        return web.json_response(_build_response(content, engine, model, prompt_chars))

    return handler


# 外層再放寬 5s：內層 llm_respond 的 urllib timeout 先到，錯誤訊息比較有料。
_TOOLCHAT_TIMEOUT_S = float(os.environ.get("NEURALIS_TOOL_TIMEOUT", 120)) + 5.0


_FAIL_MARKERS = ("error", "failed", "exception", "traceback", "denied",
                 "错误", "錯誤", "失败", "失敗", "无法", "無法")


def _post_tool_outcomes(body: dict) -> None:
    """工具 round-trip 的結果 → 5 維情緒事件 — scream 通道的「行動後果塑形情緒」。
    Aris 在 TUI 做事會真的影響自己的狀態（agency RPE 之外的第二條後果迴路）。
    ponytail: 成敗判定是字串 heuristic 不是語義；每請求最多 3 事件防刺激灌爆。"""
    tail = []
    for m in reversed(body.get("messages") or []):
        if m.get("role") != "tool":
            break
        tail.append(m)
    if not tail:
        return
    try:
        from laap.startup import get_psi_core
        psi = get_psi_core()
        af = getattr(psi, "affective", None) if psi is not None else None
        if af is None:
            return
        for m in tail[:3]:
            text = _content_text(m.get("content")).lower()
            failed = any(k in text for k in _FAIL_MARKERS)
            af.post_event("task_failure" if failed else "task_success",
                          intensity=0.5 if failed else 0.3)
    except Exception as e:
        logger.debug(f"[chatflow] tool outcome 事件跳過: {e}")


async def _tool_chat(request, web, body: dict, fed):
    """Scream agent 迴圈：帶 tools 的請求 → llm_respond.respond_tools（executor
    卸載 + timeout，作者管線完全不在迴路）。engine=psi-llm-tools。
    失敗降級為說明性 content（回合不炸，TUI 不掛）。"""
    _post_tool_outcomes(body)   # 工具結果 → 情緒事件佇列（下個 psi tick 生效）
    model = body.get("model", "laap-core")
    messages = body.get("messages", [])
    prompt_chars = sum(len(_content_text(m.get("content"))) for m in messages)

    psi_state = fed[0] if fed else None
    delta = fed[1] if fed else None
    if psi_state is None:   # 工具 round-trip 沒餵 psi，但身份塊還是要有最新狀態
        try:
            from laap.startup import get_psi_core
            psi = get_psi_core()
            psi_state = psi.get_state() if psi is not None else None
        except Exception:
            psi_state = None

    result = None
    try:
        from laap.llm_respond import respond_tools
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, respond_tools, body, psi_state, delta),
            timeout=_TOOLCHAT_TIMEOUT_S)
    except asyncio.TimeoutError:
        logger.warning(f"[chatflow] 工具模式逾時 {_TOOLCHAT_TIMEOUT_S}s")
    except Exception as e:
        logger.warning(f"[chatflow] 工具模式失敗: {e}")

    if result is None:
        result = {
            "message": {"role": "assistant", "content":
                        "（語言皮質呼叫失敗 — 檢查 openrouter key / "
                        "NEURALIS_TOOL_MODEL 是否支援 tools。本回合降級純文字。）"},
            "finish_reason": "stop", "usage": {},
        }

    if body.get("stream"):
        return await _stream_sse(request, web, result, model)
    return web.json_response(_build_tool_response(result, model, prompt_chars))


def _build_tool_response(result: dict, model: str, prompt_chars: int) -> dict:
    """OpenAI 非 streaming response，含 tool_calls。usage 優先用上游真值。"""
    msg = result["message"]
    out_msg = {"role": "assistant", "content": msg.get("content")}
    if msg.get("tool_calls"):
        out_msg["tool_calls"] = msg["tool_calls"]
    content_len = len(msg.get("content") or "")
    return {
        "id": f"laap-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": out_msg,
                     "finish_reason": result.get("finish_reason", "stop")}],
        "usage": result.get("usage") or {
            "prompt_tokens": prompt_chars // 4,
            "completion_tokens": content_len // 4, "total_tokens": 0},
        "engine": "psi-llm-tools",
    }


async def _stream_sse(request, web, result: dict, model: str):
    """把算好的完整 message（content ± tool_calls）以 OpenAI chunk 格式 SSE 送出。
    tool_call 先送 id/name 空殼，arguments 分段補 — 與 OpenAI delta 累加語義一致。"""
    msg = result["message"]
    fin = result.get("finish_reason", "stop")
    resp = web.StreamResponse(headers={
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    })
    await resp.prepare(request)
    rid = f"laap-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    def chunk(delta: dict, fin_=None) -> bytes:
        return ("data: " + json.dumps({
            "id": rid, "object": "chat.completion.chunk", "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": fin_}],
        }, ensure_ascii=False) + "\n\n").encode()

    await resp.write(chunk({"role": "assistant"}))
    content = msg.get("content") or ""
    for i in range(0, len(content), 24):
        await resp.write(chunk({"content": content[i:i + 24]}))
        await asyncio.sleep(0.015)
    for i, tc in enumerate(msg.get("tool_calls") or []):
        fn = tc.get("function") or {}
        await resp.write(chunk({"tool_calls": [{
            "index": i, "id": tc.get("id"),
            "type": tc.get("type", "function"),
            "function": {"name": fn.get("name", ""), "arguments": ""},
        }]}))
        args = fn.get("arguments") or ""
        for j in range(0, len(args), 256):
            await resp.write(chunk({"tool_calls": [{
                "index": i, "function": {"arguments": args[j:j + 256]}}]}))
    await resp.write(chunk({}, fin))
    await resp.write(b"data: [DONE]\n\n")
    await resp.write_eof()
    return resp


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
