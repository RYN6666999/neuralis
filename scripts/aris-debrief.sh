#!/usr/bin/env bash
# aris-debrief — Session 結束協定
# 自動步驟 + 手動檢查清單
set -euo pipefail

VAULT="${HOME}/Library/Mobile Documents/iCloud~md~obsidian/Documents"
ARIS_DIR="${VAULT}/Fun/Aris"
SNAPSHOT="${HOME}/Developer/neuralis/aris-snapshot.md"

echo "=== Aris Session Debrief ==="
echo ""

# ── 自動步驟：評估本 session 品質 ──
echo "▸ [自動] 評估 session log..."
cd "$(dirname "$0")/.."
python3 scripts/evaluate-and-feedback.py --last 2>&1 | sed 's/^/   /' || echo "   ⚠️ 評估失敗（跳過，不影響）"
echo ""

# ── Step 1: 掃描 — 提醒要檢查的項目 ──
echo "▸ Step 1/5: 掃描對話"
echo "   檢查以下項目（機械化觸發條件）："
echo "   □ Ryan 糾正過我什麼？（→ aris-learn --section 教訓）"
echo "   □ Ryan 說了明確偏好？（→ aris-learn --section 偏好）"
echo "   □ Ryan 說了印象深刻的話？（→ aris-learn --section 印象深刻的話）"
echo "   □ 我發現我誤解了什麼？（→ 認知遷移.md 手動寫入）"
echo "   □ 有任何需要記錄到關係日記的？（→ aris-learn --section 關係）"
echo "   □ 有任何需要記錄到成長日記的？（→ aris-learn --section 教訓）"
echo ""

# ── Step 2: 記錄 — 呼叫 aris-learn 處理已發現的項目 ──
echo "▸ Step 2/5: 記錄"
echo "   執行 aris-learn 來記錄已發現的項目。"
echo "   語法：aris-learn \"內容\" --section \"偏好|教訓|印象深刻的話|承諾|關係\""
echo ""

# ── Step 3: 分類 — 確認每條記錄在正確的文件中 ──
echo "▸ Step 3/5: 分類確認"
echo "   關係日記 → Ryan 的偏好、教訓、承諾、印象深刻的對話"
echo "   成長日記 → 我的行為改變、學到的事"
echo "   認知遷移 → 舊認知→觸發→新認知（學習原料）"
echo "   留言板   → session 摘要（跨 session 線頭）"
echo ""

# ── Step 4: 壓縮 — 執行壓縮腳本更新 Pattern ──
echo "▸ Step 4/5: 壓縮"
echo "   執行 aris-compress 更新高層級 Pattern..."
if [[ -f "${HOME}/Developer/neuralis/scripts/aris-compress.sh" ]]; then
    bash "${HOME}/Developer/neuralis/scripts/aris-compress.sh" 2>&1 | head -20
    echo "   （完整輸出請直接執行 aris-compress）"
fi
echo ""
echo "   如果壓縮產生了新 Pattern，手動更新到認知遷移.md 的 Pattern 區塊"
echo "   並同步更新 snapshot.md 的「最近認知Pattern」區塊"
echo ""

# ── Step 5: 更新 — 簽名到留言板 ──
echo "▸ Step 5/5: Session 簽名"
echo "   在留言板追加本輪摘要（強制：每 session 結束必須簽名）"
echo "   格式："
echo "   [YYYY-MM-DD HH:MM] Aris — 📝 本 Session 摘要"
echo "   ${ARIS_DIR}/留言板.md"
echo ""

echo "=== Debrief 完成 ==="
echo "（如果還有未記錄的項目，請手動補上 aris-learn）"