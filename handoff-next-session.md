# 線頭 — 給下一手

這份**不記錄現況**。以前它是 686 行的流水帳，寫下的那一刻就開始腐敗
（鐵律一：事實只能推導，不能複製）。歷史全文在 `docs/history/handoff-2026-07-archive.md`，
當史料讀，不要當真相讀。

## 開場四步

```bash
git pull                              # 多 AI 平行作業，先對齊
bash ~/check-commitments.sh           # Step 0：跨對話承諾
python3 scripts/aris-status.py        # 一頁儀表：系統活著沒
python3 brain/lint.py                 # 宣稱與證據對不對得上（檢查項數以腳本輸出為準）
```

再讀 Obsidian `Fun/Aris/留言板.md` 的最後幾則 —— 那是唯一持續同步的線頭來源。

## 規則在哪，不在這裡

| 要什麼 | 去哪 |
|---|---|
| 鐵律（擋 commit 的那三條） | `CLAUDE.md`，法條正文在 `brain/lint.py` 檔頭 |
| 開發鐵則、啟動、驗證指令 | `AGENTS.md` |
| 系統長怎樣 | `SCREAM-ARIS-ARCHITECTURE.md` + `topology.yaml` |
| 還活著的設計 | `docs/specs/`（`docs/specs/parked/` 是凍結的，不代表現況） |
| 最近做了什麼 | `git log --oneline`，不要問文件 |

## 唯一該寫進這裡的東西

**還開著、但程式碼看不出來的線頭** —— 需要人拍板的、卡在別人身上的、
或「知道有這回事才不會踩」的。有證據能查的一律不寫，寫了就是製造抄本。

寫進來的每一條都該有到期日或收尾條件。收掉了就刪，不要留成歷史層。
