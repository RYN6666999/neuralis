#!/usr/bin/env bash
# start.sh — 啟動 LAAP Brain API + PsiCore 自動心跳
#
# 用法:
#   source ~/neuralis/scripts/start.sh
#
# 這會:
#   1. 疊加 neuralis 到 PYTHONPATH
#   2. 啟動 PsiCore 認知引擎（Aris 的心跳）
#   3. 啟動 LAAP Brain API server
#
# 不需要修改作者任何程式碼。

NEURALIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 1. 疊加 PYTHONPATH
if [[ ":$PYTHONPATH:" != *":$NEURALIS_DIR:"* ]]; then
    export PYTHONPATH="$NEURALIS_DIR:$PYTHONPATH"
fi

# 2. 切到 laap-AGI 目錄
cd "$NEURALIS_DIR/../laap-AGI" || {
    echo "[neuralis] ❌ 找不到 laap-AGI 目錄 (預期在 $NEURALIS_DIR/../laap-AGI)"
    exit 1
}

# 3. 啟動 venv
source .venv/bin/activate || {
    echo "[neuralis] ❌ 無法載入 .venv"
    exit 1
}

# 4. 用 Python 先起 PsiCore，再起 API server
echo "[neuralis] ❤️ 啟動 PsiCore + LAAP Brain API..."
echo ""

python3 -c "
import sys
sys.path.insert(0, '.')
from laap.startup import ensure_psi_core
psi = ensure_psi_core()
if psi:
    state = psi.get_state()
    print(f'[neuralis] ✅ PsiCore 啟動成功')
    print(f'[neuralis]    需求主導: {state[\"dominant_need\"]}')
    print(f'[neuralis]    情緒效價: {state[\"emotion\"][\"valence\"]}')
else:
    print(f'[neuralis] ⚠️ PsiCore 未啟動 (降級模式)')
"

echo ""
echo "[neuralis] 🚀 啟動 LAAP Brain API on :11530..."
python aris_brain/laap_brain_api.py --port 11530