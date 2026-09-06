# Aris 器官盤點表（2026-09-07 解剖）

> 判斷準則（Ryan 定）：**「有用=結果」**——每一顆器官能不能被外部採收判對錯。
> 判定方式：實測（跑過/看過），不是文件自報。一半參考上次診斷已實測的證據，另一半現跑補證。
> 判決碼：**留**（活體在跳、值得保有）｜**接**（器官好但心跳線沒接，要橋）｜**砍**（廢物，丟）

| 器官 | 狀態 | 證據（實測） | 判決 | 一句話 |
|---|---|---|---|---|
| Hermes session_search (FTS5) | 🟢 跳動 | Ryan「給關鍵字撈回說明」真實體驗 | **留** | 唯一被用戶真用過的心，別動它 |
| aris-memory / /wake / attention_line | 🟡 半活 | 「記得懸念」有感，但沒接進檢索 | **接** | 半活有價值，缺的是檢索出口 |
| 三進制哈希 ternary_search | ⚰️ 廢物 | 實測撈回完全無關內容 | **砍** | 名字酷、親手寫，但結果是垃圾 |
| gbrain CLI / aris-memory 檢索 | ⚰️ 廢物 | No results / 撈煞車片 | **砍** | 不接任何可驗證的使用者路徑 |
| RPE / agency（光錐） | ⚰️ 廢物 | 4.5 天零行動、只存 1 筆 | **砍** | 有復發迴路才值得留，目前是空轉 |
| tulpa 18428 | 🟡 半活 | 每輪給 winner，但判對錯無人 | **接** | 缺裁判（人/固定規則），要接審判線 |
| PSI 引擎 (Rust) | 🟢 活得好好的 | 25% CPU 真實底層；被封（缺 get_state） | **接** | 引擎活著，是 Python 消費者沒接 |
| 審計鏈/教訓/基因 | 🟢 活的閉環 | mtime 今晨；本檔即是產物 | **留** | 唯一能驗證接線的，靠它做這些判決 |

## 附註：本表自身也是實測產物
- 生成時已跑 `verify_lesson.py meta-effective-learning-loop`（verified=true，git log=3）、
  `meta-usefulness-equals-outcome`（verified=true，lessons=7）。
- 觸發判準的基建（lesson-gate）正被我排查一個 bug：`_handle_lesson_verify` 缺 `**kwargs`，
  導致 `lesson_verify` 工具一直 `TypeError: unexpected keyword 'task_id'`。已 patch source。