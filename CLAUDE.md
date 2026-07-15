# CLAUDE.md — neuralis 長期開發規則

短期進度不放這裡（見 `AGENTS.md` 與 `handoff-next-session.md`）。
本檔只放不隨 roadmap 變動的規則。

1. neuralis 是獨立 overlay — 不直接修改 laap-AGI 上游 repo，透過
   PYTHONPATH 疊加。
2. Python `laap/psi_core.py` 是目前 PSI 行為的參考實作。新增非 Python
   PSI 後端前，必須先建立版本化的 backend 契約與 characterization tests。
3. 一個任務使用一個 branch/worktree，不直接在 main 上開發。
4. 沒有測試不得宣稱完成。「完成」必須指向實際檔案、pytest 或
   `scripts/check-*.py` 自檢。
5. 沒有 benchmark 不得宣稱效能提升。
6. 不得把 QRE / QuantumVM 描述為真正的量子運算 — 那是高維向量幾何的
   比喻（見 `docs/specs/quantum-engine-spec.md`）。
7. 安全閘必須先於能力：自主寫入、命令執行與 RSI 開放前，對應的
   safety/approval 閘必須先存在並通過自檢。
8. 高風險工具預設拒絕（`laap/safety_gate.py`）。不能為了測試方便降低
   預設安全性；測試用明確的環境變數或 fixture 隔離。
9. 修改核心狀態格式（`get_state()` / `format_state_injection()` /
   輸入事件）時，必須同步在 `tests/` 中新增對應的契約測試，
   明確標示行為變化。
10. 完工報告必須包含：commit SHA、測試結果（通過/失敗/skip 數）、
    已知限制、未完成項目。未執行或被 skip 的測試不得寫成通過。
11. 不提交 token、API key、密碼、本機絕對路徑或 runtime state 至版控。
    `.env`、`*-audit.jsonl`、`approved-tools.txt` 已列在 `.gitignore`。
12. 不做任務範圍外的重構 — 只改任務指定的檔案與其直接相依的介面。
    發現週邊問題時記錄在 handoff/已知限制，不順手修。
13. 不要把整份 ROADMAP 複製進 CLAUDE.md — 藍圖是 roadmap 的事，
    CLAUDE.md 只放不隨進度變動的長期規則。
