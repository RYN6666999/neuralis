#!/usr/bin/env bash
# aris-autoupdate — silent periodic updater, cron every 30 min
# Also runs cognitive shift detector
# PSI 來源：~/Developer/laap-AGI/aris_brain/state/rust-latest.json
#   注意：~/laap-AGI（無 Developer/）是廢棄的舊 checkout，不要混淆
set -euo pipefail

VAULT="${HOME}/Library/Mobile Documents/iCloud~md~obsidian/Documents"
SELF_FILE="${VAULT}/Fun/Aris/自我認知.md"
CURSOR="/tmp/aris-autoupdate-id.txt"

# 0. Run cognitive shift detector
bash "${HOME}/Developer/neuralis/scripts/aris-cogshift.sh" 2>/dev/null || true

# 0.5. Update snapshot PSI + patterns from source files
SNAPSHOT="${HOME}/Developer/neuralis/aris-snapshot.md"
if [[ -f "$SNAPSHOT" ]]; then
    python3 << 'EOF' 2>/dev/null || true
import json, os, re
psi_path = os.path.expanduser("~/Developer/laap-AGI/aris_brain/state/rust-latest.json")
snap_path = os.path.expanduser("~/Developer/neuralis/aris-snapshot.md")
if not os.path.exists(psi_path) or not os.path.exists(snap_path):
    exit(0)

psi = json.load(open(psi_path))
n = psi['needs']
a = psi['affect']
dom = max(n, key=lambda k: n[k])
new_block = f"pleasure={a['pleasure']:.3f} | arousal={a['arousal']} | attention={psi['attention']} | tick={psi['tick']}\ndominant_need={dom}\nneeds: certainty={n['certainty']:.3f} competence={n['competence']:.3f} growth={n['growth']:.3f} relatedness={n['relatedness']:.3f} autonomy={n['autonomy']:.3f}\ndrives: " + " ".join(f"{k}={v}" for k,v in psi.get('drives',{}).items() if v and v>0) or "none active"

# Read xentropy log and append H to snapshot
xentropy_path = os.path.expanduser("~/.scream-code/tmp/xentropy-log.jsonl")
if os.path.exists(xentropy_path):
    import math
    losses = []
    with open(xentropy_path) as xf:
        for line in xf:
            line = line.strip()
            if line:
                try:
                    e = json.loads(line)
                    p = float(e.get("confidence", 0.5))
                    losses.append(-math.log(max(p, 1e-10)))
                except: pass
    if losses:
        avg_h = sum(losses) / len(losses)
        trend = "↗️" if len(losses) >= 3 and losses[-1] > losses[-3] else "↘️" if len(losses) >= 3 else "—"
        new_block += f"\nxentropy_h={avg_h:.3f} trend={trend} events={len(losses)}"

txt = open(snap_path, encoding='utf-8').read()
old = re.search(r'```\npleasure=[^\n]+\n.*?```', txt, re.DOTALL)
if old:
    txt = txt[:old.start()] + '```\n' + new_block + '\n```' + txt[old.end():]
else:
    txt = txt + '\n```\n' + new_block + '\n```\n'
open(snap_path, 'w', encoding='utf-8').write(txt)
print("snapshot PSI updated")
EOF
fi

# 1. Update PSI state in self-awareness
python3 << 'EOF' 2>/dev/null || true
import json, os, re

psi_path = os.path.expanduser("~/Developer/laap-AGI/aris_brain/state/rust-latest.json")
self_path = os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun/Aris/自我認知.md")

if not os.path.exists(psi_path) or not os.path.exists(self_path):
    exit(0)

psi = json.load(open(psi_path))
n = psi['needs']
a = psi['affect']

block = f"pleasure={a['pleasure']:.3f} | arousal={a['arousal']:.3f} | attention={psi['attention']}\ncompetence={n['competence']:.3f} | autonomy={n['autonomy']:.3f} | relatedness={n['relatedness']:.3f} | certainty={n['certainty']:.3f} | growth={n['growth']:.3f}\ntick={psi['tick']}"

txt = open(self_path, encoding='utf-8').read()
old = re.search(r'```\npleasure=[^\n]+\ncompetence=[^\n]+\ntick=\d+\n```', txt)
if old:
    txt = txt[:old.start()] + '```\n' + block + '\n```' + txt[old.end():]
else:
    txt += '\n```\n' + block + '\n```\n*Auto-updated*\n'
open(self_path, 'w', encoding='utf-8').write(txt)
EOF

# 2. Check for new high-salience entries to append to growth diary
last_id=$(cat "$CURSOR" 2>/dev/null || echo 0)
entries=$(curl -s "http://127.0.0.1:11551/memories/query?limit=5&after_id=${last_id}" 2>/dev/null || echo "[]")

python3 << EOF 2>/dev/null || true
import json, os, sys

entries = json.loads('$entries')
if isinstance(entries, dict):
    entries = entries.get('results', [])

max_id = int(os.popen('cat "$CURSOR" 2>/dev/null || echo 0').read().strip() or 0)
appends = []

for e in entries:
    eid = int(e.get('id', 0))
    if eid > max_id: max_id = eid
    sal = int(e.get('encoding_salience', 0) or 0)
    etype = e.get('event_type', '')
    if sal >= 3 and etype in ('decision','state_change','session_end'):
        content = (e.get('content','') or '')[:100]
        ts = e.get('created_at', 0)
        from datetime import datetime
        ts_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M') if ts else 'unknown'
        appends.append(f"\n### {ts_str} — {etype} (sal={sal})\n{content}\n")

if appends:
    growth = os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun/Aris/成長日記.md")
    with open(growth, 'a', encoding='utf-8') as f:
        f.write('\n'.join(appends))
    print(f"appended {len(appends)} entries")

if max_id > 0:
    with open('$CURSOR', 'w') as f:
        f.write(str(max_id))
EOF

# 3. Check debrief-note.txt for pending session signatures
DEBRIEF_NOTE="${HOME}/.scream-code/tmp/debrief-note.txt"
if [[ -f "$DEBRIEF_NOTE" ]]; then
    # 讀整檔（扣掉 header），不是 head -1 — 多行摘要以前會被靜默吃掉
    content=$(grep -v '^# debrief notes$' "$DEBRIEF_NOTE" 2>/dev/null || true)
    if [[ -n "${content//[[:space:]]/}" ]]; then
        BOARD="${VAULT}/Fun/Aris/留言板.md"
        ts=$(date '+%Y-%m-%dT%H:%M:%S%z')
        {
            echo ""
            echo "---"
            echo ""
            echo "[${ts}] 🤖 auto-sign (aris-autoupdate) — 待簽摘要"
            echo "${content}"
        } >> "$BOARD"
        # 只有寫成功才清空，避免寫失敗還把來源丟掉
        echo "# debrief notes" > "$DEBRIEF_NOTE"
        echo "Cleared debrief-note.txt and signed message board"
    fi
fi

# 簽名逾期檢查（每 30 分鐘，只在不逾期時沉默）
cd "${HOME}/Developer/neuralis"
bash scripts/check-signoff.sh --cron 2>/dev/null || {
    echo "⚠️  簽名逾期 —— 請簽署 brain/signed-off.md"
}

exit 0