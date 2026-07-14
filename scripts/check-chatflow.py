#!/usr/bin/env python3
"""對話流攔截自檢：user_msg 抽取 / patch 冪等 / body 快取不破壞作者 handler / 餵 psi。
用法: PYTHONPATH=.:../laap-AGI ../laapenv/bin/python scripts/check-chatflow.py"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from laap.chatflow import _extract_user_msg, _wrap, install


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

    # C. wrap 攔截餵 psi + body 快取不破壞作者 handler
    fed = {}

    class FakeReq:
        def __init__(self, b):
            self._b = b
            self.reads = 0
        async def json(self):
            self.reads += 1
            return self._b

    async def author_handler(req):
        # 作者 handler 再讀一次 body（模擬 process_with_laap）
        b = await req.json()
        return {"ok": True, "saw": _extract_user_msg(b)}

    # 攔截前先 patch _feed 觀測
    import laap.chatflow as cf
    orig_feed = cf._feed
    cf._feed = lambda msg: fed.update(msg=msg)
    try:
        wrapped = _wrap(author_handler)
        req = FakeReq({"messages": [{"role": "user", "content": "餵我進 psi"}]})
        res = asyncio.run(wrapped(req))
        assert fed.get("msg") == "餵我進 psi", f"應攔截餵 psi: {fed}"
        assert res["saw"] == "餵我進 psi", "作者 handler 仍應讀到 body"
        assert req.reads == 2, f"body 讀 2 次（wrapper + handler）都成功: {req.reads}"
    finally:
        cf._feed = orig_feed
    print("C. 攔截餵 psi + 作者 handler 仍讀得到 body: OK")

    # D. 真餵 psi（若 psi 起得來）
    from laap.psi_core import PsiCore, NeedType
    from laap.agi.cognitive_bus import CognitiveBus
    import laap.startup as st
    st._psi_core = PsiCore(bus=CognitiveBus(agent_name="check"), interval=0.5)
    before = st._psi_core.needs.values[NeedType.RELATEDNESS]
    cf._feed("謝謝你陪我一起想")
    after = st._psi_core.needs.values[NeedType.RELATEDNESS]
    assert after > before, "餵 psi 應提升 relatedness"
    assert st._psi_core.last_input == "謝謝你陪我一起想"
    print(f"D. 真餵 psi: OK — relatedness {before:.3f}→{after:.3f}, last_input 已設")

    print("ALL CHATFLOW CHECKS PASSED")


if __name__ == "__main__":
    main()
