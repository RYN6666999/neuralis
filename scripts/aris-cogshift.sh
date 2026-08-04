#!/usr/bin/env bash
# aris-cogshift — detect cognitive shifts from aris-memory + append to 認知遷移.md
# Runs as part of aris-autoupdate.sh (cron), or standalone.
# Detects:
#   1. New contradiction_journal entries (Rope 1/2 conflicts = cognitive dissonance)
#   2. Memories that flipped confidence (green→red = belief correction)
#   3. High-salience decision/state_change events
set -euo pipefail

VAULT="${HOME}/Library/Mobile Documents/iCloud~md~obsidian/Documents"
SHIFT_FILE="${VAULT}/Fun/Aris/認知遷移.md"
CURSOR="/tmp/aris-cogshift-cursor.txt"

last_id=$(cat "$CURSOR" 2>/dev/null || echo 0)

python3 << 'PYEOF' 2>/dev/null || true
import json, os, sqlite3, time
from datetime import datetime

db_path = os.path.expanduser("~/.aris-memory.db")
shift_path = os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun/Aris/認知遷移.md")
cursor_path = "/tmp/aris-cogshift-cursor.txt"

if not os.path.exists(db_path):
    exit(0)

try:
    last_id = int(open(cursor_path).read().strip()) if os.path.exists(cursor_path) else 0
except:
    last_id = 0

conn = sqlite3.connect(db_path)
max_id = last_id
appends = []

# Source 1: contradiction_journal — emotional conflict = cognitive dissonance
rows = conn.execute(
    "SELECT id, mem_id, rope, reason, created_at FROM contradiction_journal WHERE id > ? ORDER BY id",
    (last_id,)
).fetchall()

for r in rows:
    if r[0] > max_id: max_id = r[0]
    ts = datetime.fromtimestamp(r[4]).strftime('%Y-%m-%d %H:%M') if r[4] else 'unknown'
    # Fetch the conflicting memory content
    mem = conn.execute("SELECT content, emotion_tag FROM memories WHERE id=?", (r[1],)).fetchone()
    content = mem[0][:80] if mem else '?'
    emo = mem[1] if mem else '?'
    rope_label = "情緒衝突" if r[2] == "rope1" else "時間矛盾"
    appends.append(f"""
### [{ts}] 自動偵測：{rope_label}
- **舊認知**：（記憶 #{r[1]}：{content}）
- **觸發**：{rope_label} — {r[3]}
- **新認知**：需要人工確認
- **類型**：correction
- **壓縮**：
""")

# Source 2: memories that hit confidence=red via contradiction
rows2 = conn.execute(
    "SELECT m.id, m.content, m.confidence, m.created_at, m.emotion_tag "
    "FROM memories m WHERE m.confidence='red' AND m.id > ? AND m.id NOT IN "
    "(SELECT mem_id FROM contradiction_journal) ORDER BY m.id LIMIT 20",
    (last_id,)
).fetchall()

for r in rows2:
    if r[0] > max_id: max_id = r[0]
    ts = datetime.fromtimestamp(r[3]).strftime('%Y-%m-%d %H:%M') if r[3] else 'unknown'
    appends.append(f"""
### [{ts}] 自動偵測：信心降級（red）
- **舊認知**：（記憶 #{r[0]}：{r[1][:80]}）
- **觸發**：confidence 被標 red（違反四繩驗證）
- **新認知**：需要人工確認
- **類型**：correction
- **壓縮**：
""")

if appends:
    with open(shift_path, 'a', encoding='utf-8') as f:
        f.write('\n'.join(appends))
    print(f"cogshift: {len(appends)} new shifts appended")

if max_id > last_id:
    with open(cursor_path, 'w') as f:
        f.write(str(max_id))

conn.close()
PYEOF

# Also sync to gbrain
python3 -c "
import sys, json
sys.path.insert(0, '$HOME/Developer/neuralis')
from gbrain_client import get_client
c = get_client()
if c:
    content = open('$SHIFT_FILE', encoding='utf-8').read()
    c.call('put_page', {'slug': 'aris-cognitive-shifts', 'content': content[:4000]})
    print('gbrain cognitive-shifts synced')
" 2>/dev/null || true

exit 0