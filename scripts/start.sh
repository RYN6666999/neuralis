#!/usr/bin/env bash
# start.sh — 啟動 LAAP Brain API + PsiCore 心跳（同一個 process）
#
# 用法:
#   ~/Developer/neuralis/scripts/start.sh [PORT]      # 預設 11546（與 scream-code/mcp.json 一致）
#
# 這會:
#   1. 疊加 neuralis 到 PYTHONPATH（neuralis 在前，laap-AGI 在後）
#   2. 在 API server 的同一個 Python process 內先起 PsiCore（心跳跟 API 同生命週期），
#      再載入 laap_brain_api — 心跳不會隨啟動器行程退出而死
#   3. 前景執行（要背景跑用 scripts/start-laap-api.sh）
#
# 不修改作者任何程式碼。
set -u

PORT="${1:-11546}"
NEURALIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAAP="${LAAP_AGI_DIR:-$NEURALIS_DIR/../laap-AGI}"

if [[ ! -d "$LAAP/aris_brain" ]]; then
    echo "[neuralis] ❌ 找不到 laap-AGI（預期 $LAAP，可用 LAAP_AGI_DIR 覆蓋）"
    return 1 2>/dev/null || exit 1   # 被 source 時不殺使用者 shell
fi

# venv 偵測：LAAP_VENV > 同層 laapenv > laap-AGI/.venv
VENV=""
for CAND in "${LAAP_VENV:-}" "$NEURALIS_DIR/../laapenv" "$LAAP/.venv"; do
    [[ -n "$CAND" && -x "$CAND/bin/python" ]] && VENV="$CAND" && break
done
if [[ -z "$VENV" ]]; then
    echo "[neuralis] ❌ 找不到 venv（試過 \$LAAP_VENV、../laapenv、laap-AGI/.venv）"
    return 1 2>/dev/null || exit 1
fi

export PYTHONPATH="$NEURALIS_DIR:$LAAP"
export LAAP_AGI_DIR="$LAAP"
echo "[neuralis] ❤️ PsiCore + LAAP Brain API :$PORT (venv=$VENV)"

exec "$VENV/bin/python" -u - "$PORT" <<'PYEOF'
import os
import runpy
import sys

port = sys.argv[1]

# 1. PsiCore 心跳 — 與 API server 同 process、同生命週期
from laap.startup import startup_all
bus, psi, tools = startup_all()
if psi:
    st = psi.get_state()
    print(f"[neuralis] ✅ PsiCore 心跳中 — 主導需求={st['dominant_need']} "
          f"效價={st['emotion']['valence']}")
else:
    print("[neuralis] ⚠️ PsiCore 未啟動（降級模式），API 照常起")
if tools:
    print(f"[neuralis] 🛠️ ToolExecutor: {len(tools.list_tools())} 工具")

# 2. 以作者的 __main__ 入口起 API（同 process，argv 傳 port）
api = os.path.join(os.environ["LAAP_AGI_DIR"], "aris_brain", "laap_brain_api.py")
sys.path.insert(0, os.path.dirname(api))   # 作者 bare imports 需要 aris_brain 在 path 首
sys.argv = ["laap_brain_api.py", "--port", port]
runpy.run_path(api, run_name="__main__")
PYEOF
