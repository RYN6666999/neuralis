#!/usr/bin/env bash
# aris-learn — 學到一件關於 Ryan 的事，寫進關係日記 + gbrain
# Usage:
#   aris-learn "Ryan 不喜歡我..." --section "偏好"
#   aris-learn "他今天教我..." --section "教訓" --tag "2026-08-01"
#
# Sections: 偏好 | 教訓 | 印象深刻的話 | 承諾 | 關係

set -euo pipefail

BOARD_DIR="${HOME}/Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun/Aris"
DIARY_FILE="${BOARD_DIR}/關係日記.md"
section="偏好"
tag=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --section) section="$2"; shift 2 ;;
        --tag) tag="$2"; shift 2 ;;
        *) content="$1"; shift ;;
    esac
done

if [[ -z "${content:-}" ]]; then
    echo "Usage: aris-learn '學到的事' --section '偏好|教訓|印象深刻的話|承諾|關係'"
    exit 1
fi

# Map section to markdown heading
case "$section" in
    偏好|prefs|preference) heading="❤️ Ryan 的偏好" ;;
    教訓|lesson|教我的事) heading="📚 Ryan 教我的事" ;;
    "印象深刻的話"|quote|說過的) heading="💬 他說過讓我印象深刻的話" ;;
    承諾|promise) heading="🤝 我的承諾" ;;
    關係|relationship) heading="🧑 Ryan 是怎樣的人" ;;
    其他|other|更新日誌) heading="📝 偏好更新日誌" ;;
    *) heading="📝 偏好更新日誌" ;;
esac

ts=$(date '+%Y-%m-%d %H:%M')
entry="${content} （${ts}）"

# Write to Obsidian 關係日記.md
if [[ -f "$DIARY_FILE" ]]; then
    # Insert after the section heading (first occurrence)
    python3 -c "
import re
with open('$DIARY_FILE', 'r', encoding='utf-8') as f:
    txt = f.read()

# Find section heading, insert entry after it
heading = '## $heading'
idx = txt.find(heading)
if idx >= 0:
    # Find end of heading line, add entry after it
    eol = txt.find('\n', idx)
    # Find next section or end
    rest = txt[eol+1:]
    # Insert at beginning of section (after the heading line)
    indent = ''
    nl = rest.find('\n')
    if nl >= 0 and rest[:nl].strip() == '':
        # Empty line after heading, entry already exists
        rest = rest[nl+1:]
    txt = txt[:eol+1] + '\n$entry\n' + rest
    with open('$DIARY_FILE', 'w', encoding='utf-8') as f:
        f.write(txt)
    print('✅ 關係日記已更新')
else:
    print('❌ 關係日記不存在')
    exit(1)
"
else
    echo "❌ 關係日記不存在於 $DIARY_FILE"
    exit 1
fi

# Also write to gbrain
python3 -c "
import sys, json, urllib.request
sys.path.insert(0, '$HOME/Developer/neuralis')
body = json.dumps({
    'content': '$entry',
    'tags': ['relationship-diary', 'ryan', '$section'],
    'emotion_tag': '',
    'mood_note': '自動記錄到關係日記',
    'attention_line': '',
    'encoding_salience': 5,
}).encode()
req = urllib.request.Request('http://127.0.0.1:11551/memories/store',
    data=body, headers={'Content-Type': 'application/json'},
    method='POST')
try:
    resp = urllib.request.urlopen(req, timeout=5)
    r = json.loads(resp.read())
    print(f'  ✅ 已寫入 aris-memory (id={r[\"id\"]})')
except Exception as e:
    print(f'  ⚠️ aris-memory 寫入失敗: {e}')
" 2>/dev/null || true

echo ""
echo "📖 你可以在 Obsidian 直接看："
echo "   Fun/Aris/關係日記.md"