# -*- coding: utf-8 -*-
"""GT 可信度檢查工具 — 測「標籤有沒有標對」，不是測量。

做法: 同一批 (input→expected_memory) 由同一人再標一輪(重測,test-retest)，
     比對兩輪是否一致 → 算一致率 + Cohen's kappa。
使用時機: 標完一批 GT 後跑這一支，過不了閾值就剔/重標，別硬收 100 筆。

用法:
  python3 gt_check.py ls                 # 列出目前 GT 檔案
  python3 gt_check.py new demo.json      # 建立範例 GT(帶 label_a)
  python3 gt_check.py redo demo.json     # 互動重標(產生第二輪 label_b)
  python3 gt_check.py check demo.json    # 算一致率 + κ + 低一致條目
"""
import sys, json, os, re
from collections import Counter

def _norm(s: str) -> str:
    if not s: return ""
    s = s.strip().lower()
    s = re.sub(r"[\s\W]+", "", s)
    return s

def _load(path):
    rows = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line: continue
        rows.append(json.loads(line))
    return rows

def _save(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def cohen_kappa(a, b):
    """a,b 兩份 label list，算 Cohen's kappa。"""
    assert len(a) == len(b)
    n = len(a)
    if n == 0: return 1.0, 1.0
    cats = set(a) | set(b)
    # 觀察一致率 Po
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    # 期望一致率 Pe
    ca = Counter(a); cb = Counter(b)
    pe = sum((ca.get(c, 0)/n) * (cb.get(c, 0)/n) for c in cats)
    denom = 1 - pe
    kappa = (po - pe) / denom if denom != 0 else 1.0
    return round(po, 3), round(kappa, 3)

def cmd_new(path):
    # 建立一筆有 label A 的真值範例，讓使用者覆寫成自己的
    rows = [
        {"input": "V12 引擎的檔名是什麼?", "expected_memory": "aris_v12_dense_kernel.py", "label_a": "aris_v12_dense_kernel.py"},
        {"input": "把客戶 A 的簽約進度拉出來", "expected_memory": "客戶A.簽約", "label_a": None},
        {"input": "產品庫存剩多少", "expected_memory": "庫存.產品", "label_a": None},
    ]
    _save(path, rows)
    print(f"[new] {path} 已建立({len(rows)} 筆)。請編輯 label_a 填真實標記，label_b 留空待重標。")

def cmd_redo(path):
    rows = _load(path)
    print(f"[redo] 重標 {len(rows)} 筆(第二次標注 → label_b)。首行已預填 label_a 顯示。")
    for i, r in enumerate(rows):
        old = r.get("label_a") or "(空)"
        # 顯示 input + 別讓「預期答案」偷看，重標的人只看 input
        ans = input(f"  {i+1}/{len(rows)}  input: {r['input']}\n     (你第一輪標: {old}) 標二:「該召回哪條?」> ").strip()
        r["label_b"] = ans
    _save(path, rows)
    print("[redo] label_b 已存回，跑 check。")

def cmd_check(path):
    rows = _load(path)
    a = [_norm(r.get("label_a","")) for r in rows]
    b = [_norm(r.get("label_b","")) for r in rows]
    na = sum(1 for x in a if x)
    nb = sum(1 for y in b if y)
    assert na > 0, "label_a 全空，先填 expect 再跑 redo"
    if nb < na:
        print(f"[check] label_b 只有 {nb} 筆 < label_a {na} 筆。先跑 redo 補完。")
        return
    po, k = cohen_kappa(a, b)
    print(f"[check] {path}")
    print(f"  條目數        : {len(rows)}")
    print(f"  一致性(po)    : {po}")
    print(f"  Cohen's κ     : {k}")
    print(f"  判讀 (κ): 0.8↑=可信 0.4~0.8=中等 0.4↓=不可信")
    print("  低一致條目:")
    bad = [r for r, x, y in zip(rows, a, b) if x != y]
    if not bad:
        print("   (無)")
    else:
        for r in bad:
            print(f"    - {r.get('input')}  a={r.get('label_a')}  b={r.get('label_b')}   ← 批區級檢查")
    return k

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    cmd, path = sys.argv[1], sys.argv[2]
    {
        "new": cmd_new,
        "redo": cmd_redo,
        "check": cmd_check,
    }[cmd](path)
