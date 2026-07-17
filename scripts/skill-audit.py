#!/usr/bin/env python3
"""每週技能使用盤點 — 從 Scream Code session + agency audit + memory 統計

Output: Markdown report to stdout + append to ~/Developer/neuralis/data/skill-audit-log.md
"""
import json, subprocess, sqlite3
from pathlib import Path
from collections import Counter
from datetime import datetime

HOME = Path.home()
SCREAM_SESSIONS = HOME / '.scream-code/sessions'
MEMORY_DB = HOME / '.scream-code/memory/memos.sqlite'
AGENCY_AUDIT = HOME / 'Developer/neuralis/agency-audit.jsonl'
OUTPUT = HOME / 'Developer/neuralis/data/skill-audit-log.md'


def count_skill_calls():
    """從 wire.jsonl 搜尋 Skill 工具呼叫"""
    counts = Counter()
    if not SCREAM_SESSIONS.exists():
        return counts
    result = subprocess.run(
        ['grep', '-roh', '"skill":"[^"]*"', str(SCREAM_SESSIONS)],
        capture_output=True, text=True, timeout=30
    )
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith('"skill":"'):
            name = line.split('"')[3]
            if name and not name.startswith('_'):
                counts[name] += 1
    return counts


def count_agency_actions():
    """從 agency audit 統計自主行動使用的工具"""
    counts = Counter()
    total = 0
    if AGENCY_AUDIT.exists():
        for line in AGENCY_AUDIT.read_text().splitlines():
            if not line.strip(): continue
            try:
                d = json.loads(line)
                tool = d.get('tool', 'unknown')
                counts[tool] += 1
                total += 1
            except: pass
    return counts, total


def count_memory_tags():
    """從記憶庫統計標籤頻率"""
    tags = Counter()
    try:
        db = sqlite3.connect(str(MEMORY_DB))
        rows = db.execute('SELECT tags, user_need FROM memos').fetchall()
        db.close()
        for tags_str, need in rows:
            try:
                t = json.loads(tags_str) if isinstance(tags_str, str) else tags_str
                if isinstance(t, list):
                    for tag in t: tags[tag] += 1
            except: pass
    except: pass
    return tags


def main():
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    skill_calls = count_skill_calls()
    agency_counts, agency_total = count_agency_actions()
    mem_tags = count_memory_tags()

    lines = [f"\n## 📊 技能使用盤點 @ {now}\n"]

    lines.append("### Scream Code Skill 呼叫（top 10）")
    if skill_calls:
        for name, cnt in skill_calls.most_common(10):
            lines.append(f"- `{name}`: {cnt}次")
    else:
        lines.append("（無紀錄）")

    lines.append(f"\n### Aris 自主行動（共 {agency_total} 次）")
    if agency_counts:
        for tool, cnt in agency_counts.most_common():
            lines.append(f"- `{tool}`: {cnt}次 ({cnt/agency_total*100:.0f}%)")

    lines.append("\n### 記憶庫熱門標籤（top 15）")
    for tag, cnt in mem_tags.most_common(15):
        lines.append(f"- `{tag}`: {cnt}次")

    lines.append("\n### 推薦註冊為 harness tool 的技能")
    hot = [name for name, cnt in skill_calls.most_common() if cnt >= 2]
    if hot:
        for name in hot:
            lines.append(f"- `{name}`（已呼叫 {skill_calls[name]} 次）")
    else:
        lines.append("（尚無足夠數據 — 先新增常用技能導航至 toolmode prompt）")

    report = "\n".join(lines)
    print(report)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, 'a') as f:
        f.write(report + "\n")


if __name__ == '__main__':
    main()