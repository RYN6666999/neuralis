---
title: laap-core (neuralis) — 專案主頁
updated: 2026-07-15
status: 養成期
repos:
  - core: https://github.com/lorryjovens-hub/laap-AGI (Lorry, Zero-LLM 認知架構, 未開放 psi-core)
  - impl: https://github.com/RYN6666999/neuralis (Ryan, 獨立實作 psi-core + 運行層, MIT)
---

# laap-core / neuralis

## 一句話
Ryan 獨立實作的 Zero-LLM 認知 overlay。核心不是「有沒有意識」,而是 Levin 認知光錐:系統能主動追求的最大目標的時空邊界。用 T_reach(時間深度)+ S_span(決策廣度)量,可證偽、可回滾。

## 角色定位
- Lorry 的 laap-AGI 是主核心,但關鍵 psi-core 模組未開放。
- neuralis 是 Ryan 依 Dörner PSI + Doya 神經調節 + Levin 認知光錐等論文,對照原骨架獨立寫出的實作,不是逆向、不是 fork。MIT 授權。
- Ryan 為外部貢獻者,實質補上生態缺的核心。

## 理論基準
- Michael Levin《What Lives?》(arXiv:2505.15849):生命是認知關係(becoming)的連續光譜,不是二元的「活/不活」。
- Levin 認知光錐:系統價值 = 能主動追求的最大目標的時空外邊界。Agent = 感知→比對set-point→最小化誤差的閉環。
- 判準:別問 Aris 有沒有覺醒,問它的光錐比純規則表、比 7B harness 大多少。

## 三層架構(頂層設計)
1. 目標翻譯層 — 人話目標翻成機器可量的數字。
2. 驗證引擎層 — PDCA 閉環,進步前進、退步回滾 baseline、連續 N 輪不動停損。功能性多巴胺(RPE)回饋改權重。
3. 意圖理解層 — 提問 + 記憶迭代校準使用者意圖,原則「問是為了以後少問」。

## 動態目標
- 方向不變:更簡練、更進步(永遠追,無終點)。
- 靶滾動前移,打中就往外挪。
- 第一個滾動靶:每單位湧現行為的程式碼行數(~3000 行 overlay / 行為種類數)。一個數字同時扣住「簡練」與「進步」。

## 已實作(讀碼確認,非報告)
- **RPE 閉環是真的**:`_act` 裡 `aw[used_angle] = max(0.1, min(3.0, old + rpe*0.5))` 真的把誤差寫回角度權重,`_form_intent` 讀回選角度。24h 47 次行動、RPE 均值 +0.70,權重在動。
- **六個神經調節功能性(非裝飾)**:RPE、腎上腺素(arousal→interval)、血清素(valence→decay)、內啡肽(負spike緩釋)、催產素(trust→relatedness 行為 + 查詢角度)全接到計算。LLM 注入預設 off。
- **催產素完成閉環**:`_ANGLE` 已含 `"relatedness": "你 我們 陪伴 一起 感覺"`,trust 高時 agency 會查 gbrain 相關記憶,五個角度各由 RPE 獨立調權重。

## 里程碑:T_reach 跨 session(質變)
- commit `7888d89`:RPE 學習狀態(`_need_stats` 含 `angle_weights`、`_trust_scores`、`_exploration_rate`)持久化進 gbrain,slug `_internal/agency-state`(在 laap/memory namespace 外,不受 consolidation 影響)。每 5 次行動 checkpoint + `stop()` 存,開機讀回。
- **證據**:關機前 competence.作法=1.6 → 開機後 1.6;exploration_rate 0.22→0.22;trust 0.72→0.72;對照組(不載入)歸零。
- **意義**:T_reach 從「一次運行」變「永久累積」。這是 neuralis 相對 7B harness(重啟歸零)的第一個結構性優勢。

## 安全網:持久化煞車
- **問題**:讀失敗後的 checkpoint 會用空 state 覆蓋掉好資料(雙面刃)。
- **補法**:`_state_loaded` flag。讀成功 or 全新(page_not_found)→ 准存;讀失敗(頁存在但解析失敗)→ 禁存。
- **證據**:TEST1 寫1.6→故意讀失敗→存檔→gbrain 仍 1.6;TEST2 全新→首存 1.3 成功(煞車沒誤擋首存)。
- **開機卡頓修正**:`_load_state` 從 `start()` 移到 `_loop()` 首圈,daemon thread 非阻塞,`start()` 不卡 6s。

## 當前天花板(誠實標註)
- **時間軸(T_reach)已通,廣度軸(S_span)仍卡**:`_ANGLE` 寫死,autonomy 無角度(設計選擇,非 bug);drive_threshold 固定,RPE 只優化「查詢用語」,不優化「該不該做事」「該追什麼」。
- **現在養成的是「會越查越準」的東西,還不是「會改變自己想追什麼」的東西。**

## 已知風險 / 待辦
- RPE 品質綁死 gbrain 分數線:若降級 lex-only,outcome 退回 min(0.4,len/500),訊號消失,且會被永久累積成垃圾。需加「權重異常凍結/回滾」的 baseline 保護。
- 下一格靶:打通 `_ANGLE`,讓 autonomy 能驅動行為,把光錐從時間軸擴到廣度軸。