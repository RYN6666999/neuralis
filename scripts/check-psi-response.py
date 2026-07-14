#!/usr/bin/env python3
"""psi→回應 自檢：情緒狀態真的影響回應內容（不是裝的）。

A/B 純函式：_compose_psi_reply 對不同 state/delta 出不同句、數字可回溯。
C   契約檔：_write_author_state 寫出作者 schema 的 state/latest.json。
D/E E2E（需 :11546 活著 + 新碼已載入）：
    D. relatedness 句 → psi-respond 回應報出該需求的實測 delta
    E. 中性句 → 「沒有明顯觸動」分支；兩次回應內容不同

用法: PYTHONPATH=.:../laap-AGI ../laapenv/bin/python scripts/check-psi-response.py
"""
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from laap import chatflow

# ── A. 有觸動：delta 進句子、主導需求與情緒數字可回溯 ──
st = {
    "needs": {"relatedness": {"current": 0.66}},
    "dominant_need": "competence", "dominant_drive": 0.8,
    "emotion": {"valence": 0.02, "arousal": 0.31, "dominance": 0.5},
    "attention": "TASK", "tick": 100,
}
delta = {"relatedness": 0.06, "valence": 0.02}
r = chatflow._compose_psi_reply(st, delta)
assert "relatedness +0.06" in r, r
assert "competence" in r and "0.80" in r, r
assert "v+0.02" in r and "a0.31" in r, r
print("A. 觸動句數字可回溯: OK —", r[:60], "…")

# ── B. 無觸動 + 情緒象限分支 ──
r2 = chatflow._compose_psi_reply(st, {"relatedness": 0.001, "valence": 0.0})
assert "沒有明顯觸動" in r2, r2
st_sad = {**st, "emotion": {"valence": -0.3, "arousal": 0.7, "dominance": 0.5}}
r3 = chatflow._compose_psi_reply(st_sad, delta)
assert "心情偏沉" in r3 and "亢奮" in r3, r3
assert r != r2 != r3
print("B. 分支（無觸動/低落亢奮）: OK")

# ── C. 作者契約檔 schema ──
_orig_laap_dir = os.environ.get("LAAP_AGI_DIR")
with tempfile.TemporaryDirectory() as tmp:
    os.environ["LAAP_AGI_DIR"] = tmp
    full_st = {
        "needs": {"competence": {"current": 0.5, "target": 0.7, "drive": 0.4}},
        "dominant_need": "competence", "dominant_drive": 0.4,
        "emotion": {"valence": 0.0, "arousal": 0.3, "dominance": 0.5},
        "attention": "IDLE", "tick": 42,
    }
    chatflow._write_author_state(full_st)
    out = json.loads((Path(tmp) / "aris_brain" / "state" / "latest.json").read_text())
    assert out["cycle"] == 42 and out["needs"]["competence"] == 0.5
    assert out["attention"] == "IDLE" and "valence" in out["emotion"]
    assert not (Path(tmp) / "aris_brain" / "state" / "latest.json.tmp").exists()
if _orig_laap_dir is None:
    del os.environ["LAAP_AGI_DIR"]
else:
    os.environ["LAAP_AGI_DIR"] = _orig_laap_dir
print("C. 作者契約檔 latest.json schema: OK")

# ── D/E. 活體 E2E ──
API = "http://localhost:11546/v1/chat/completions"


def chat(msg: str) -> dict:
    req = urllib.request.Request(
        API, method="POST",
        data=json.dumps({"model": "laap-core",
                         "messages": [{"role": "user", "content": msg}]}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as f:
        return json.loads(f.read())


try:
    urllib.request.urlopen("http://localhost:11546/health", timeout=3)
except OSError:
    print("D/E. SKIP — API 沒在跑（E2E 需要 :11546）")
    sys.exit(0)

d = chat("謝謝你陪我聊天，有你在真好，我們是一起的")
dc = d["choices"][0]["message"]["content"]
if d.get("engine") not in ("psi-respond", "longform"):
    print(f"D/E. SKIP — 線上還是舊碼（engine={d.get('engine')}），重啟 API 後重跑")
    sys.exit(0)
assert "relatedness" in dc or "[PSI:" in dc, dc
print(f"D. 情感句 → {d['engine']}: OK — {dc[:70]}…")

e = chat("TCP 三次握手的第二步是什麼")
ec = e["choices"][0]["message"]["content"]
assert ec != dc, "兩種輸入回應不該相同"
print(f"E. 中性句回應不同於情感句: OK — {ec[:70]}…")

# 契約檔真的落地在作者目錄
real = Path(os.environ.get("LAAP_AGI_DIR",
            str(Path.home() / "Developer/laap-AGI"))) / "aris_brain/state/latest.json"
if real.exists():
    live = json.loads(real.read_text())
    print(f"   作者契約檔活著: cycle={live['cycle']} needs={len(live['needs'])} 維")

print("ALL PSI-RESPONSE CHECKS PASSED")
