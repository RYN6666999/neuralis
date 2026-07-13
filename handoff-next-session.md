# neuralis — 繼續補全任務

## 當前狀態

neuralis repo 已建立（`~/neuralis/`），已 push 到 GitHub：`github.com/RYN6666999/neuralis`

包含 33 個檔案，1 個 commit。

## 下一個 AI 的入口文件

**請先閱讀 `docs/specs/neuralis-handoff.md`** 獲取完整架構分析、缺口矩陣、優先級列表。

## 快速啟動

```bash
cd ~/laap-AGI && source .venv/bin/activate
source ~/neuralis/scripts/activate.sh
python aris_brain/laap_brain_api.py
```

## P1 優先任務

1. 升級 `laap/agi/world_model.py` → 真正的語意圖引擎
2. 升級 `laap/agi/causal.py` → 接受 `quantum_dim` 參數
3. 升級 `laap/agi/analogical.py` → 接受 `name` 參數
4. 建立 `aris_brain/aris_generator.py` → 解鎖論文生成
5. 調查 `psilang_v2` import 問題 (agi_kernel.py)