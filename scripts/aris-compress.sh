#!/usr/bin/env bash
# aris-compress — 壓縮認知遷移紀錄 → 高層級 Pattern
# 找出重複出現的遷移類型、關鍵字、關聯性，抽象成 Pattern
# 執行：每週一次或手動
set -euo pipefail

SHIFT_FILE="${HOME}/Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun/Aris/認知遷移.md"

python3 << 'PYEOF'
import os, re, json
from collections import Counter
from datetime import datetime

path = os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun/Aris/認知遷移.md")
txt = open(path, encoding='utf-8').read()

# Parse all shift entries
# Format: ### [date] title\n content...
entries = re.findall(r'### \[([^\]]+)\] ([^\n]+)\n(.*?)(?=\n### |\Z)', txt, re.DOTALL)

print(f"=== 認知遷移統計 ===")
print(f"總遷移數：{len(entries)}")
print()

types = Counter()
triggers = []
keywords = []

for ts, title, body in entries:
    # Extract type
    m = re.search(r'\*\*類型\*\*：(\w+)', body)
    t = m.group(1) if m else 'unknown'
    types[t] += 1
    # Extract old belief keywords
    old = re.search(r'\*\*舊認知\*\*：([^\n]*)', body)
    new = re.search(r'\*\*新認知\*\*：([^\n]*)', body)
    trigger = re.search(r'\*\*觸發\*\*：([^\n]*)', body)
    if old: keywords.extend(re.findall(r'[\u4e00-\u9fff\w]{2,}', old.group(1)))
    if trigger: triggers.append(trigger.group(1))

print("=== 按類型分佈 ===")
for t, c in types.most_common():
    print(f"  {t}: {c}")

print()
print("=== 高頻關鍵詞（舊認知中出現的） ===")
common = Counter(k for k in keywords if len(k) >= 2).most_common(15)
for k, c in common:
    print(f"  {k}: {c}")

print()
print("=== 重複觸發模式 ===")
trigger_counter = Counter(triggers).most_common(5)
for t, c in trigger_counter:
    print(f"  [{c}x] {t[:60]}")

# Generate new patterns from repeated correction type
corrections = [e for e in entries if 'correction' in e[2]]
if len(corrections) >= 3:
    print()
    print("=== 建議新 Pattern（>=3 條 correction 自動建議） ===")
    # Group corrections by title keywords
    keywords = []
    for ts, title, body in corrections:
        words = set(re.findall(r'[\u4e00-\u9fff]{2,}', title))
        keywords.append((words, ts, title))
    
    # Find clusters by Jaccard similarity
    clusters = []
    for i, (ws1, ts1, t1) in enumerate(keywords):
        found = False
        for c in clusters:
            ws2 = c[0]
            jaccard = len(ws1 & ws2) / max(len(ws1 | ws2), 1)
            if jaccard > 0.1:
                c[1].append((ts1, t1))
                found = True
                break
        if not found:
            clusters.append([ws1, [(ts1, t1)]])
    
    for ws, items in clusters:
        if len(items) >= 2:
            print(f"  Cluster ({len(items)} 條): {items[0][1][:50]}...")
            for ts, title in items:
                print(f"    - [{ts}] {title[:50]}")

print()
print("建議：執行 aris-learn 或在認知遷移.md 手動填入 Pattern 區塊")
PYEOF