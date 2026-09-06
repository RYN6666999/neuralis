#!/usr/bin/env bash
# pre-commit hook — 自動跑 risk-scorer 對每個暫存的 .py 檔
# 安裝: ln -sf ../../scripts/pre-commit-risk.sh .git/hooks/pre-commit
# 或直接: cp scripts/pre-commit-risk.sh .git/hooks/pre-commit
set -uo pipefail

REPO_ROOT="$(python3 -c "import os; print(os.path.dirname(os.path.realpath('$0')))" 2>/dev/null)"
REPO_ROOT="$(cd "$REPO_ROOT/.." && pwd -P)"
RISK_SCRIPT="$REPO_ROOT/scripts/risk-scorer.py"
RED=0
SCORES=()

# 取得暫存中的 .py 檔
STAGED=$(git diff --cached --name-only --diff-filter=ACM | grep '\.py$' || true)
if [[ -z "$STAGED" ]]; then
    exit 0
fi

echo "🔍 risk-scorer pre-commit 檢查..."

for f in $STAGED; do
    FILEPATH="$REPO_ROOT/$f"
    if [[ ! -f "$FILEPATH" ]]; then
        continue
    fi

    RESULT=$(python3 "$RISK_SCRIPT" --file "$FILEPATH" 2>/dev/null)
    SCORE=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('score',0))" 2>/dev/null)
    LEVEL=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('level','🟢'))" 2>/dev/null)

    if [[ "$SCORE" -ge 9 ]]; then
        echo "  $LEVEL $f — score $SCORE/24 (高風險)"
        RED=1
    elif [[ "$SCORE" -ge 5 ]]; then
        echo "  $LEVEL $f — score $SCORE/24 (中風險)"
    else
        echo "  🟢 $f — score $SCORE/24"
    fi
    SCORES+=("$f: $LEVEL $SCORE")
done

if [[ "$RED" -eq 1 ]]; then
    echo ""
    echo "⚠️  有高風險檔案（score ≥ 9）。執行詳細檢查："
    for s in "${SCORES[@]}"; do
        echo "  $s"
    done
    echo ""
    # 沒有 TTY（Hermes 背景/Hook 自動化）→ 直接擋下
    if [[ ! -t 0 ]]; then
        echo "❌ commit 中止 — 高風險，非互動環境自動拒絕"
        exit 1
    fi
    echo "要跳過 risk-scorer 檢查嗎？(y/N)"
    read -r SKIP < /dev/tty
    if [[ "$SKIP" != "y" && "$SKIP" != "Y" ]]; then
        echo "❌ commit 中止 — 請先處理高風險項目後再提交"
        echo "   執行: python3 scripts/risk-scorer.py --file <檔名>"
        exit 1
    fi
fi

exit 0