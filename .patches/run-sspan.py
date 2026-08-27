#!/usr/bin/env python3
"""跑 S_span 判準 — 在 neuralis 根目錄執行：python3 run-sspan.py

需要先套 p1-fix.patch（提供 learning_verdict）。
audit 記錄裡沒有 "choice" 欄位，要先把 (need, tool) 映射成選擇 —— PI 的
verify-neuralis.sh 漏了這步，所以會 KeyError: 'choice'。
"""
import json
import sys
from pathlib import Path

# 這支可能被放在 .patches/ 之類的子目錄執行。Python 會把「腳本所在目錄」
# 放進 sys.path[0]（不是 cwd），所以從子目錄跑時 import laap 會失敗。
# 往上找出 repo 根目錄（有 laap/ 的那層），插到 sys.path 最前面。
_here = Path(__file__).resolve()
_root = next((p for p in (_here.parent, *_here.parents) if (p / "laap").is_dir()), None)
if _root is None:
    sys.exit("找不到 laap/ 目錄 —— 請把這支放在 neuralis repo 裡（或其子目錄）")
sys.path.insert(0, str(_root))

AUDIT = _root / "agency-audit.jsonl"
if not AUDIT.exists():
    sys.exit(f"找不到 {AUDIT}")

try:
    from laap.s_span_bench import learning_verdict, behavior_entropy
except ImportError as e:
    sys.exit(f"匯入 learning_verdict 失敗：{e}\n"
             f"（repo 根目錄判定為 {_root}）\n"
             "若 pytest 已是 352 passed，patch 是套好的，那這是路徑問題不是 patch 問題。")

recs = []
for line in AUDIT.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        recs.append(json.loads(line))
    except Exception:
        pass

# 關鍵一步：audit 沒有 choice 欄位，用 (need, tool) 當選擇
mapped = [{"choice": (r.get("need", "?"), r.get("tool", "?")),
           "outcome": r.get("outcome", 0)} for r in recs]

v = learning_verdict(mapped)
ent = behavior_entropy([m["choice"] for m in mapped])

print(f"筆數            = {v['n_records']}")
print(f"選擇種類        = {v['n_choices']}")
print(f"行為熵          = {ent:.2f} bits")
print(f"實現優勢        = {v['advantage']:+.4f}   ← 實際選擇比亂選好多少")
_p95 = v['null_p95']
print(f"亂選能拿到的上限 = "
      + (f"{_p95:+.4f}   ← 虛無分布 95 百分位" if _p95 is not None
         else "(算不出來 — 選擇種類少於 2)"))
print(f"樣本不足        = {v['underpowered']}")
print()
if v["underpowered"]:
    print(">>> 樣本不足，不下結論。需要 ≥100 筆（建議 300）。")
elif v["learned"]:
    print(f">>> ✅ 學了。實現優勢 {v['advantage']:+.4f} 超過亂選上限 {_p95:+.4f}。")
    print("    Aris 的工具/角度選擇確實偏向了高品質的選項，不是亂選。")
else:
    print(f">>> ❌ 沒學。實現優勢 {v['advantage']:+.4f} 沒超過亂選上限 {_p95:+.4f}。")
    print("    樣本足夠而測不出優勢 = 這是真結論，不是測不出來。")
