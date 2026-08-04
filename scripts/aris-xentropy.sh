#!/usr/bin/env bash
# aris-xentropy — 交叉熵損失計算
# 衡量我的分類判斷 vs Ryan 矯正之間的差距
# H(p,q) = -Σ p(x) * log(q(x))
set -euo pipefail

LOG="${HOME}/.scream-code/tmp/xentropy-log.jsonl"

show_stats() {
    if [[ ! -f "$LOG" ]]; then
        echo "尚無交叉熵數據"
        exit 0
    fi
    python3 << 'PYEOF'
import json, math, os, sys
from datetime import datetime

log_path = os.path.expanduser("~/.scream-code/tmp/xentropy-log.jsonl")
events = []
with open(log_path) as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except: pass

if not events:
    print("尚無交叉熵數據")
    sys.exit(0)

losses = []
for e in events:
    # p = 我當初的信心（0-1），q = ground truth（矯正後是 1）
    p = float(e.get("confidence", 0.5))
    q = 1.0  # 矯正後 = ground truth
    # H = -p * log(q + ε) — 但當 q=1, log(1)=0, H=0 沒意義
    # 改用：H = -log(p)  — 信心越低 loss 越高
    # p=0.9 → H=0.1, p=0.5 → H=0.69, p=0.1 → H=2.3
    eps = 1e-10
    h = -math.log(max(p, eps))
    losses.append(h)

avg = sum(losses) / len(losses)
trend = "↗️ 惡化" if len(losses) >= 3 and losses[-1] > losses[-3] else "↘️ 改善" if len(losses) >= 3 else "—"

# ── Threshold 觸發 ──
DEBRIEF_NOTE = os.path.expanduser("~/.scream-code/tmp/debrief-note.txt")
COG_SHIFT = os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun/Aris/認知遷移.md")
triggers = []

# H < 0.5: normal — 沒事
if avg < 0.5:
    pass

# H 0.5–1.0: attention — flag to debrief-note.txt
if 0.5 <= avg < 1.0:
    note = f"[xentropy] H={avg:.3f} 進入注意區間（0.5-1.0）"
    with open(DEBRIEF_NOTE, 'w') as f:
        f.write(note)
    triggers.append(f"⚠️ 注意: H={avg:.3f} → debrief-note.txt flagged")

# H > 1.0: alarm — auto-write cognitive shift
if avg >= 1.0:
    entry = f"\n\n## [{datetime.now().strftime('%Y-%m-%d %H:%M')}] ⚠️ 交叉熵警報 (H={avg:.3f})\n\n**舊認知：** 我的分類邏輯沒有問題。\n**觸發：** 交叉熵損失 H={avg:.3f} 超過警報線 1.0。\n**新認知：** 我的分類判斷正在偏離 Ryan 的矯正。需要檢查分類邏輯。\n**類型：** auto-alarm\n"
    with open(COG_SHIFT, 'a') as f:
        f.write(entry)
    triggers.append(f"🔴 警報: H={avg:.3f} → 認知遷移已寫入")

# 連續 3 次矯正 H 都上升 → trend warning
corrections = [e for e in events if e.get("type") == "correction"]
if len(corrections) >= 3:
    recent = corrections[-3:]
    h_vals = []
    for c in recent:
        p = float(c.get("confidence", 0.5))
        h_vals.append(-math.log(max(p, 1e-10)))
    if h_vals[0] < h_vals[1] < h_vals[2]:
        snap = os.path.expanduser("~/Developer/neuralis/aris-snapshot.md")
        warning = "\n⚠️ [bootstrap] 警告：最近 3 次矯正 H 持續上升 — 分類邏輯可能偏移\n"
        # Append warning to snapshot if not already there
        txt = open(snap).read()
        if warning.strip() not in txt:
            txt += warning
            open(snap, 'w').write(txt)
        triggers.append(f"📈 趨勢警告: 連續 3 次矯正 H 上升 → snapshot 已註記")

print(f"=== 交叉熵損失 ===")
print(f"  事件數: {len(events)}")
print(f"  平均損失: {avg:.3f}")
print(f"  趨勢: {trend}")
if triggers:
    print(f"  ── 觸發 ──")
    for t in triggers:
        print(f"  {t}")
print(f"  最近事件:")
for e in events[-5:]:
    p = e.get("confidence", 0.5)
    h = -math.log(max(p, 1e-10))
    print(f"    [{e.get('section','?')}] p={p:.2f} H={h:.3f} — {e.get('content','')[:40]}")
PYEOF
}

record() {
    # aris-xentropy record "內容" --section "偏好" --confidence 0.8
    local content=""
    local section=""
    local confidence=0.5
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --section) section="$2"; shift 2 ;;
            --confidence) confidence="$2"; shift 2 ;;
            *) content="$1"; shift ;;
        esac
    done
    if [[ -z "$content" ]]; then
        echo "usage: aris-xentropy record '內容' --section X --confidence N"
        exit 1
    fi
    local ts
    ts=$(date +%s)
    echo "{\"ts\":$ts,\"content\":\"${content::60}\",\"section\":\"$section\",\"confidence\":$confidence}" >> "$LOG"
    echo "✅ 已記錄 (confidence=$confidence)"
}

correct() {
    # aris-xentropy correct "原始內容" --old-section X --new-section Y
    local content=""
    local old_section=""
    local new_section=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --old-section) old_section="$2"; shift 2 ;;
            --new-section) new_section="$2"; shift 2 ;;
            *) content="$1"; shift ;;
        esac
    done
    if [[ -z "$content" ]]; then
        echo "usage: aris-xentropy correct '內容' --old-section X --new-section Y"
        exit 1
    fi
    local ts
    ts=$(date +%s)
    echo "{\"ts\":$ts,\"content\":\"${content::60}\",\"old_section\":\"$old_section\",\"new_section\":\"$new_section\",\"type\":\"correction\"}" >> "$LOG"
    echo "✅ 矯正已記錄: $old_section → $new_section"
    echo "   這會計入下一次 stats 的交叉熵"
}

case "${1:-stats}" in
    stats|status) show_stats ;;
    record) shift; record "$@" ;;
    correct) shift; correct "$@" ;;
    *)
        echo "Usage: aris-xentropy [stats|record|correct]"
        echo "  stats    — 顯示交叉熵統計"
        echo "  record '內容' --section X --confidence N — 記錄一次分類"
        echo "  correct '內容' --old-section X --new-section Y — 記錄矯正"
        ;;
esac