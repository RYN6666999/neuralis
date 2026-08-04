#!/usr/bin/env bash
# aris-remember — Scream Code 端快速寫入對話記憶
# Usage:
#   aris-remember "Ryan 說的話" --emotion "frustration" --mood "覺得踏實"
#   aris-remember "Ryan 說..." --tag "trust" --tag "機器人女友" --salience 4
#
# 自動附加：PSI 情緒狀態、時間戳
# 寫入：aris-memory HTTP API (port 11551) + gbrain 雙備份

set -euo pipefail

ARIS_MEMORY_URL="${ARIS_MEMORY_URL:-http://127.0.0.1:11551}"
PSI_STATE_FILE="${HOME}/Developer/laap-AGI/aris_brain/state/rust-latest.json"

# ── 參數解析 ──
content=""
emotion_tag=""
mood_note=""
tags='["conversational","scream-code"]'
salience=3
source="scream"
source_id=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --emotion) emotion_tag="$2"; shift 2 ;;
        --mood) mood_note="$2"; shift 2 ;;
        --tag) tags=$(echo "$tags" | python3 -c "import sys,json; t=json.load(sys.stdin); t.append('$2'); print(json.dumps(t))"); shift 2 ;;
        --salience) salience="$2"; shift 2 ;;
        --source) source="$2"; shift 2 ;;
        --id) source_id="$2"; shift 2 ;;
        *) content="$1"; shift ;;
    esac
done

if [[ -z "$content" ]]; then
    echo "Usage: aris-remember <content> [--emotion tag] [--mood note] [--tag t] [--salience 1-5]"
    exit 1
fi

# ── 讀 PSI 狀態 ──
psi_json="{}"
if [[ -f "$PSI_STATE_FILE" ]]; then
    psi_json=$(python3 -c "
import json
with open('$PSI_STATE_FILE') as f:
    s = json.load(f)
print(json.dumps({
    'pleasure': s.get('affect', {}).get('pleasure', 0),
    'arousal': s.get('affect', {}).get('arousal', 0),
    'dominance': s.get('affect', {}).get('dominance', 0.5),
    'dominant_need': max(s.get('needs', {}), key=lambda k: s['needs'].get(k, 0)) if s.get('needs') else 'unknown',
    'needs': s.get('needs', {}),
    'drives': s.get('drives', {}),
}))
")
fi

# ── 寫入 aris-memory ──
payload=$(python3 -c "
import json
p = {
    'source': '$source',
    'content': '''$content''',
    'tags': $tags,
    'emotion_tag': '$emotion_tag',
    'mood_note': '''$mood_note''',
    'encoding_salience': $salience,
    'psi_state': $psi_json,
    'origin': 'human',
    'confidence': 'yellow',
    'provenance': 'scream-session-$(date +%s)',
}
print(json.dumps(p, ensure_ascii=False))
")

resp=$(curl -s -X POST "$ARIS_MEMORY_URL/memories/store" \
    -H "Content-Type: application/json" \
    -d "$payload" 2>/dev/null)

if echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'id' in d, str(d)" 2>/dev/null; then
    mem_id=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
    echo "✅ 對話記憶已寫入 (id=$mem_id)"
    echo "   情緒: $emotion_tag | 顯著性: $salience"
    echo "   PSI: $(echo "$psi_json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"pleasure={d['pleasure']:.2f} arousal={d['arousal']:.2f} need={d['dominant_need']}\")" 2>/dev/null || echo 'unknown')"
else
    echo "⚠️ aris-memory 寫入失敗: $resp"
    echo "   (用 MemoryWrite 降級)"
fi