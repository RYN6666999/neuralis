#!/usr/bin/env python3
"""C-a 驗證 backtest v2 — gbrain 經驗快取能扛下多少決策（誠實版）。

v1 壞了：gbrain 原始分數永遠高（亂碼查詢都 0.84），且循環（查到決策自己寫的記憶）。
v2 兩條誠實信號：
  A. gbrain 相關命中率：排掉「自己 + 未來」的記憶，且要求詞真的相關（非分數門檻）。
  B. audit-only：這決定之前，有沒有「同 need + 好結果」的先前經驗（純真實 outcome，
     零 gbrain 查詢、零循環）。這是最乾淨的方向讀數。

⚠️ 兩條都是方向性（92 筆小樣本、need 層粗粒度），做 go/no-go 夠，不做精算。
用法: source ~/.zshrc; PYTHONPATH=.:../laap-AGI python scripts/backtest-c-a.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
AUDIT = ROOT / "agency-audit.jsonl"
GO_BAR = 0.40

decisions = []
for line in AUDIT.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        d = json.loads(line)
    except json.JSONDecodeError:
        continue
    if d.get("prompt") and d.get("ts"):
        decisions.append(d)
decisions.sort(key=lambda x: x["ts"])
print(f"回放 {len(decisions)} 筆決策（按時間排序）\n")

_STOP = set("的 了 是 在 我 你 他 和 與 也 都 就 而 及 test query".split())


def toks(s: str) -> set:
    return {t for t in re.split(r"[\s，。、/_\-]+", s.lower())
            if len(t) >= 2 and t not in _STOP}


# ── 信號 B：audit-only 同 need 先前好經驗（最乾淨）──
b_hits = 0
seen_good_need = {}      # need -> 是否已有好經驗
for d in decisions:
    need = d.get("need", "")
    if seen_good_need.get(need):
        b_hits += 1       # 這決定之前已有同 need 好經驗 = 快取可導
    if d.get("outcome", 0) >= 0.6:
        seen_good_need[need] = True
b_rate = b_hits / len(decisions) if decisions else 0

# ── 信號 A：gbrain 相關命中（排自己+未來、要詞相關）──
a_rate = None
try:
    from gbrain_client import get_client, hybrid_hits
    client = get_client()
    if client is not None:
        a_hits = 0
        for d in decisions:
            q = d["prompt"][:100]
            ts_n = d["ts"]
            qtok = toks(q)
            hit = False
            for h in hybrid_hits(client, q, 10):
                slug = str(h.get("slug", ""))
                # 排掉 agency 自己寫的經驗記憶（循環）+ 未來記憶 + 內部狀態頁
                m = re.search(r"mem-(\d+)", slug)
                if m and int(m.group(1)) >= int(ts_n) - 5:
                    continue          # 自己或未來
                if slug.startswith("laap/memory/") or "_internal" in slug:
                    continue
                # 要求詞真的相關（非分數門檻）
                ctext = (h.get("chunk_text") or h.get("title") or "")
                if qtok & toks(ctext + " " + slug):
                    hit = True
                    break
            if hit:
                a_hits += 1
        a_rate = a_hits / len(decisions) if decisions else 0
except Exception as e:
    print(f"（信號 A 跳過：{e}）")

print("=== 兩條信號 ===")
if a_rate is not None:
    print(f"A. gbrain 相關命中（排自己+未來、要詞相關）: {a_rate:.0%}")
print(f"B. audit 同 need 先前好經驗（最乾淨）:        {b_rate:.0%}")

lead = a_rate if a_rate is not None else b_rate
print(f"\n=== 判決（go/no-go bar {GO_BAR:.0%}）===")
if lead >= GO_BAR:
    print(f"✅ GO — 主信號 {lead:.0%} ≥ {GO_BAR:.0%}。快取扛得住，C 值得建。")
elif lead >= 0.20:
    print(f"🟡 灰色 — 主信號 {lead:.0%}（20–40%）。半吊子，需人判。")
else:
    print(f"❌ NO-GO — 主信號 {lead:.0%} < 20%。連這都低，C 退化成貴版 B，重想。")
