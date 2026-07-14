#!/usr/bin/env python3
"""對話流攔截自檢：user_msg 抽取 / patch 冪等 / body 快取不破壞作者 handler / 餵 psi。
用法: PYTHONPATH=.:../laap-AGI ../laapenv/bin/python scripts/check-chatflow.py"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from laap.chatflow import _extract_user_msg, install


def main():
    # A. user_msg 抽取（取最後一則 user）
    body = {"messages": [{"role": "user", "content": "舊"},
                         {"role": "assistant", "content": "回"},
                         {"role": "user", "content": "最新問題"}]}
    assert _extract_user_msg(body) == "最新問題"
    assert _extract_user_msg({"messages": []}) == ""
    print("A. user_msg 抽取（取最後 user）: OK")

    # B. install 冪等
    from aiohttp.web_urldispatcher import UrlDispatcher
    install()
    first = UrlDispatcher.add_post
    install()
    assert UrlDispatcher.add_post is first, "重複 install 不該再包"
    assert getattr(UrlDispatcher.add_post, "_laap_chatflow", False)
    print("B. install 冪等: OK")

    # D. 真餵 psi（先設好 psi，供 C 的 handler 用）
    from laap.psi_core import PsiCore, NeedType
    from laap.agi.cognitive_bus import CognitiveBus
    import laap.startup as st
    import laap.chatflow as cf
    st._psi_core = PsiCore(bus=CognitiveBus(agent_name="check"), interval=0.5)
    before = st._psi_core.needs.values[NeedType.RELATEDNESS]
    cf._feed("謝謝你陪我一起想")
    after = st._psi_core.needs.values[NeedType.RELATEDNESS]
    assert after > before, "餵 psi 應提升 relatedness"
    assert st._psi_core.last_input == "謝謝你陪我一起想"
    print(f"D. 真餵 psi: OK — relatedness {before:.3f}→{after:.3f}, last_input 已設")

    # C. executor 卸載證明：慢的同步 process_with_laap 不凍結 event loop
    #    mock laap_brain_api.process_with_laap 成 sleep(1.5s)，在 chat handler 跑的同時
    #    另一個 async task 持續計數 — 若 event loop 被阻塞，計數會停。
    import types
    fake_api = types.ModuleType("laap_brain_api")

    def slow_process(messages, model="laap-core"):
        time.sleep(1.5)  # 同步阻塞（模擬作者慢管線）
        return {"content": "慢管線回應", "engine": "test"}

    fake_api.process_with_laap = slow_process
    sys.modules["laap_brain_api"] = fake_api

    fed = {}
    orig_feed = cf._feed
    cf._feed = lambda msg: fed.update(msg=msg)

    class FakeReq:
        def __init__(self, b):
            self._b = b
        async def json(self):
            return self._b

    async def author_handler(req):  # 不該被非 streaming 走到
        return "AUTHOR-FALLBACK"

    def mkreq():
        return FakeReq({"messages": [{"role": "user", "content": "跑慢管線"}], "stream": False})

    async def run_c():
        handler = cf._make_chat_handler(author_handler)
        t0 = time.time()
        # 兩個慢 chat 併發。executor 卸載 → 並行 ~1.5s；阻塞 event loop → 序列化 ~3s
        resps = await asyncio.gather(handler(mkreq()), handler(mkreq()))
        return resps, time.time() - t0

    try:
        import json as _json
        resps, elapsed = asyncio.run(run_c())
        assert fed.get("msg") == "跑慢管線", f"應餵 psi: {fed}"
        assert elapsed < 2.5, f"event loop 被阻塞了！兩個慢 chat 序列化 {elapsed:.2f}s（executor 卸載失敗）"
        content = _json.loads(resps[0].body.decode())["choices"][0]["message"]["content"]
        assert content == "慢管線回應", f"應回 executor 結果: {content}"
    finally:
        cf._feed = orig_feed
        del sys.modules["laap_brain_api"]
    print(f"C. executor 卸載不阻塞 event loop: OK — 2 個 1.5s 慢 chat 併發僅 {elapsed:.2f}s（非 3s 序列化）")

    # E. timeout 降級：超時回降級 response，不 hang
    fake_api2 = types.ModuleType("laap_brain_api")
    fake_api2.process_with_laap = lambda m, model="x": (time.sleep(3), {"content": "太慢"})[1]
    sys.modules["laap_brain_api"] = fake_api2
    cf._CHAT_TIMEOUT_S = 0.5
    try:
        handler = cf._make_chat_handler(author_handler)
        req = FakeReq({"messages": [{"role": "user", "content": "會逾時"}]})
        resp = asyncio.run(handler(req))
        eng = _json.loads(resp.body.decode())["engine"]
        assert eng == "laap-timeout", f"應降級 engine=laap-timeout: {eng}"
    finally:
        del sys.modules["laap_brain_api"]
    print("E. 逾時降級（不 hang）: OK")

    print("ALL CHATFLOW CHECKS PASSED")


if __name__ == "__main__":
    main()
