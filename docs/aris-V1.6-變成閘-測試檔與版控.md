# Aris 記憶 V1.6 — 把通過變成閘（永久測試檔 + hook POST 納版控）

> 來源：Prime Agent · 代 Ryan 提出 · 2026-08-20
> 對應：上一份省思（`docs/aris-V1.5-省思-給Prime.md`）的「未解」前兩條。
> 目的不是加新功能，是**把 V1.5 的 13/13 從「跑完就消失」變成「改壞就紅」**。

## 兩件事

### Task 1 — 永久自動測試檔（最重要）
- **新增**：`laap-AGI/tests/test_fetch_detail.py`（pytest）。
- **測什麼**：把 V1.5 的能力矩陣固化成測試（不是 13 個現寫 heredoc）：
  - 識別碼命中：`79800` → 撈得到含 79800 的記憶
  - 專名單詞命中：`紫貘` / `C單` → 撈得到（專名＝強證據，一個就夠）
  - 中文實詞 ≥2：`富邦銀行拒絕貸款` → 撈到 #1334
  - 反面：`青鴉` / `白獬` / `赤梟`（庫裡無）→ 0 筆，不注入
  - 單一常見詞不構成命中：`代號` 單詞 → 0（青鴉那案靠這條守住）
  - 出處鍥：「命中時回傳內容含 A庫#編號 前後夾法」
- **測的資料**：**凍結一份 fixture**（從 A庫 抽一小撮代表性列，放 `tests/fixtures/memory.sqlite` 或 JSON）。**不要**直接打 live A庫——否則 A庫一長/一變測試就壞，測試要確定性。verification: `pytest tests/test_fetch_detail.py -q` 全綠；
  而且**故意壞一例**（把 ≥2 改成 ≥3）要能紅——證明它真的會擋回歸，不是裝飾。
- **紅線**：測試不可連網、不可打 live 服務、不可依賴 jieba 之外的第三方剛裝的狀態。
- 為何是這些案（理由）：省思 #7「反思沒有變成閘」——唯一把 13/13 變成閘的就是讓它能在 CI/本地一鍵重跑，改到就紅。**這是本次最高優先。**

### Task 2 — hook POST 修復納入版控
- **現況風險**（省思 #8）：`~/.hermes/scripts/aris-cognitive-hook.py` 的長文走 POST 修改**只在 .bak**，不在任何 git repo——哪天動 Hermes，修復靜默消失。
- **做法**（擇一，Claude 判斷哪個乾淨）：
  a. 把修好的 hook 放進 `laap-AGI/scripts/hooks/aris-cognitive-hook.py` 並在 `laap-AGI` 版控；
     另寫 `scripts/hooks/README.md` 標明「live 在 `~/.hermes/scripts/`、此為版控原始版、改以 repo 版為準」。
  b. 或：把「長文走 POST」這段邏輯**上移到 bridge**（`aris_cognitive_bridge.py`）讓 hook 保持薄、只做轉發——測起來更乾淨。選這個要先 `git -C laap-AGI diff` 看 bridge 現況，別蓋掉既有 GET/POST。
- **verification**（跑完貼輸出）：`diff scripts/hooks/aris-cognitive-hook.py ~/.hermes/scripts/aris-cognitive-hook.py`（同則空、異則列出）；並重測一次長文：一段 800 字含關鍵字在末段的文字，關鍵字要撈得到。

## 附帶（你省思的 S3，驗收就該有這一格）
- 測試檔裡加一例「**記憶當線索不當答案**」：使用者給「C 單」，正確行為不是複述 #1353 而是**去讀 `C單狀態.json` 逐筆確認**才回答。這一格如果測不了，就在 README/test 註解裡明記「由人工驗收」，不許假裝測得到。
- 正面覆蓋率**照實算（不含紫貘探針）**：4/7，不是 7/7。回報寫真實數。

## 回報（照貼）
1. `pytest` 全綠輸出 + 「故意改壞一例→紅」的輸出（兩者都要，證明閘是活的）
2. hook 版控落點（a 或 b）+ diff 結果
3. 長文重測輸出
4. 過/不過

## 一句話
**這一版不新增能力，是把「不會再靜默退化」變成可驗證的事實。**
