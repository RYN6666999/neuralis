#!/usr/bin/env python3
"""記憶織入自檢：平行召回收割/遲到 stash/過期/去重/出處措辭。

用法: PYTHONPATH=.:../laap-AGI ../laapenv/bin/python scripts/check-memory-weave.py
"""
import os
import sys
import time
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 假 gbrain：hybrid_hits 回固定 hits（不碰真腦庫）
fake = types.ModuleType("gbrain_client")
fake.get_client = lambda: object()
_HITS = [
    {"score": 0.9, "chunk_text": "watchdog 三層守護鏈 launchd 到完整 Aris"},
    {"score": 0.8, "chunk_text": "情緒引擎五維耦合矩陣"},
    {"score": 0.1, "chunk_text": "低分雜訊不該出現"},
]
fake.hybrid_hits = lambda c, q, k: list(_HITS)
sys.modules["gbrain_client"] = fake

from laap import chatflow

# A. 召回 + 分數線 + 上限 2 條
chatflow._quoted_recently.clear()
got = chatflow._psi_memories_sync("watchdog")
assert len(got) == 2 and "watchdog" in got[0] and "雜訊" not in " ".join(got), got
print("A. 召回/分數線/上限: OK")

# B. 去重：同 hits 再查 → 空（近 6 輪引用過）
got2 = chatflow._psi_memories_sync("watchdog")
assert got2 == [], got2
print("B. 引用去重: OK")

# C. stash → take（5 分鐘內）→ 再 take 空
class DoneTask:
    def __init__(self, lines):
        self._lines = lines
    def result(self):
        return self._lines

chatflow._stash_late_memories(DoneTask(["遲到的記憶"]))
assert chatflow._take_pending_memories() == ["遲到的記憶"]
assert chatflow._take_pending_memories() == []
print("C. 遲到 stash/take: OK")

# D. 過期 stash 不帶出
chatflow._stash_late_memories(DoneTask(["過期的"]))
chatflow._pending_memories["ts"] = time.time() - 400
assert chatflow._take_pending_memories() == []
print("D. 5 分鐘過期: OK")

# E. _collect：done 收割、未完成回空、例外吞掉
class Pending:
    def done(self):
        return False

class Boom:
    def done(self):
        return True
    def result(self):
        raise RuntimeError("boom")

class Ok(Boom):
    def result(self):
        return ["x"]

assert chatflow._collect_memories(None) == []
assert chatflow._collect_memories(Pending()) == []
assert chatflow._collect_memories(Boom()) == []
assert chatflow._collect_memories(Ok()) == ["x"]
print("E. _collect 三態: OK")

# F. 出處措辭誠實：不宣稱「你說過」
st = {"needs": {}, "dominant_need": "competence", "dominant_drive": 0.5,
      "emotion": {"valence": 0.0, "arousal": 0.3}, "attention": "TASK", "tick": 1}
reply = chatflow._compose_psi_reply(st, {"valence": 0.0}, memories=["一段舊記憶"])
assert "想起" in reply and "你上次說過" not in reply and "你說過" not in reply, reply
print("F. 出處措辭（不 LARP）: OK")

print("ALL MEMORY-WEAVE CHECKS PASSED")
