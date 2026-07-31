# CLAUDE.md — neuralis 長期開發規則

短期進度不放這裡（見 `AGENTS.md` 與 `handoff-next-session.md`）。
本檔只放不隨 roadmap 變動的規則。

## 鐵律（凌駕以下所有條款，違反直接擋 commit）

**鐵律一：事實只能推導，不能複製。**
抄一次 = 預約未來某天的一個謊。抄本不會跟著本體變，也沒人會回頭對。

**鐵律二：0 信心路由 — 任何開發行為預設第一次就有問題，換一條路驗過才算數。**
產出者不得自驗。用產出它的同一條路去驗，等於沒驗。

**鐵律三：debug 百科 —— 錯誤被抓到一次就收錄；未收尾的事也要記。**
錯誤會叫，未完成不會叫；不會叫的才會變成大患。

**鐵律零（不是拿來遵守的，是拿來找閘該放哪的）：**
Agent 會沿著「證據最容易製造」的方向走。架構的工作不是要求誠實，是讓造假比做對更貴。
前三條都是它的產物。

<!-- IRON-LAW-ANCHOR: 本段由 brain/lint.py 檢查 G 盯著，刪掉會擋 commit。 -->

| 範圍 | 正文在哪（唯一權威，此處不複述） |
|---|---|
| 鐵律一、二的**本專案實作** | `brain/lint.py` 檔頭 |
| 鐵律零～三的**跨專案正文與工具** | `RYN6666999/LB-oculus`（陰陽眼），本機 `~/Developer/LB-oculus` |

複述就是抄本，抄本會腐敗 —— 那正是鐵律一禁的事。

```bash
python3 brain/lint.py     # 本專案七道檢查，每道對應一個真實踩過的坑
dbp open                  # 未收尾清單（開場、收尾各跑一次）
dbp risk <檔案>           # 動手前：這個檔以前在哪摔過
```

1. neuralis 是獨立 overlay — 不直接修改 laap-AGI 上游 repo，透過
   PYTHONPATH 疊加。
2. Python `laap/psi_core.py` 是目前 PSI 行為的參考實作。新增非 Python
   PSI 後端前，必須先建立版本化的 backend 契約與 characterization tests。
3. 一個任務使用一個 branch/worktree，不直接在 main 上開發。
4. 沒有測試不得宣稱完成。「完成」必須指向實際檔案、pytest 或
   `scripts/check-*.py` 自檢。
5. 沒有 benchmark 不得宣稱效能提升。
6. 不得把 QRE / QuantumVM 描述為真正的量子運算 — 那是高維向量幾何的
   比喻（見 `docs/specs/parked/quantum-engine-spec.md`）。
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
14. **event loop 線程上不准任何同步等待。** 同步函式一律
    `run_in_executor` + `await wait_for`；thread → loop 的事件投遞用
    `loop.call_soon_threadsafe`，不在 thread 裡開新 event loop 對主 loop
    的 Queue 跑 `run_until_complete`（跨 loop put 會 RuntimeError）。
    阻塞在單請求測試下看不出來 — 改串流/工具管線後必須驗「串流進行中
    打 /health 回 200」。此坑已踩三次（`9b904a3`、gbrain recall、`4e7e952`），
    每次都讓 watchdog 誤殺行程。
15. 下「repo 裡沒有 X / 沒人做過 X」的結論前，先 `git branch -a` +
    `git log --all -- <path>`。單一分支的工作樹不是 repo 全貌；這類誤判的
    代價是叫下一手重做已完成的工作。
16. **🔴 習慣鏈路（強制・不可中斷・不問不等不拖）：**
    每次有效率的程式碼改動結束後，必須走完整條鏈：
    `git status` → `git add <目標檔案>` → `git commit -m "有意義的訊息"`
    → `git push` → **留言板回報（含 commit hash + 一句做完什麼）**
    → **MemoryWrite 存經驗**（含 whatWorked/whatFailed）。
    **中斷點 = 沒做完。** 不問「要不要 push」、不等確認、不跨 session 補。
    這條鏈的每一個環節都是原子操作的一部分 — 斷在哪裡就等於沒做完。
    例外條件：純閱讀/研究不寫 code、或 Ryan 明確說「先不要 commit」。
    
    同一條鏈的「前向」版本：開工前先 pull 最新 + 確認 branch 正確，
    不在過時的 baseline 上改。見 AGENTS.md「開工前先 git branch --show-current」。
