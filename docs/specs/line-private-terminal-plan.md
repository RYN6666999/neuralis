---
title: Plan A — LINE 私人第二終端
date: 2026-07-17
status: planned (未執行)
tags: [line, integration, io-channel, plan]
---

# Plan A — LINE 私人第二終端

> 目標：把手機變成 Aris 的另一個終端。躺床上也能跟她講話、她的自主行動能推播給你。
> **範圍限定：只有 Ryan 一個人用**（allowlist 單一 LINE user ID）。
> 公開 bot（任何人能加好友）是 Plan B，前置是多用戶身份，本計劃**不含**。

## 為什麼現在可以做

Aris 已有 OpenAI 相容 chat 端點（`:11546` `/v1/chat/completions`，chatflow 接管）。
LINE 只是換一個 transport 進來。psi/trust/memory 全部照舊映射到 `"user"` = Ryan，
**零核心架構改動**。這是純 I/O 擴展，不欠新技術債。

## 關鍵技術約束（LINE Messaging API 的硬限制）

這些不是選配，是 LINE 平台的物理限制，設計必須繞開：

1. **無串流**。LINE 收的是完整訊息，不吃 SSE。Aris 的交錯串流要在送 LINE 前
   collapse 成完整回覆（或分段 push）。
2. **replyToken 一次性 + ~30s 失效**。但 Aris 的工具迴圈可能跑 10–120s
   （`respond_stream` use_tool 迴圈、agency）。→ **replyToken 一定來不及**。
   正解：收到訊息先用 replyToken 秒回「嗯，我想一下」(ack)，真正答案算完用
   **push API** 送。這剛好對上 chatflow 既有的 busy 保護 + 非同步模式。
3. **push 有配額**。免費方案月額有限。agency 主動推播要走 quiet hours + 節流。
4. **webhook 簽章**。LINE 每個請求帶 `X-Line-Signature`（channel secret 的
   HMAC-SHA256）。**不驗 = 任何人偽造請求灌進 Aris**。必驗。

## 架構

```
LINE App (你的手機)
    │ 訊息
    ▼
LINE Platform ──webhook POST──► cloudflare tunnel ──► line-adapter :PORT
    ▲                                                      │
    │ reply(ack) / push(答案)                              │ 轉成 chat messages
    └──────────────────────────────────────────────┐      ▼
                                                    │  Aris :11546
                                                    │  /v1/chat/completions
                                                    └──── content ◄──┘
```

`line-adapter` 是一支新的小服務（不進 laap 核心，獨立 process），職責：
webhook 簽章驗證 → user ID allowlist → LINE event ↔ chat messages 格式轉換 →
呼叫 Aris → reply/push 回 LINE。對話歷史共用 `~/.aris-conversations/`
（與 aris-chat.py / scream 同一場對話，跨終端連續）。

## 分階段

### Phase 0 — 安全底線（不可跳，先於一切）
- [ ] `X-Line-Signature` HMAC-SHA256 驗證（channel secret 從 Keychain 讀，不 hardcode）
- [ ] user ID allowlist：只有 Ryan 的 LINE userId 放行，其他一律靜默丟棄
- [ ] `:11546` 不裸奔公網 — tunnel 只暴露 line-adapter，Aris API 仍綁 localhost
- [ ] 自檢 `check-line-security.py`：偽造簽章被拒 / 非白名單 user 被拒 / 合法通過

### Phase 1 — Adapter 本體
- [ ] `services/line-adapter/`（或 scripts/，位置待定）：webhook 收信 → 驗章 →
      allowlist → 抽 text event
- [ ] LINE event → chat messages（沿用 aris-chat.py 的歷史載入 + streaming client 模式，
      但 collapse 成完整字串）
- [ ] ack-then-push：replyToken 秒回 loading，push 送真答案
- [ ] 錯誤降級：Aris 逾時/500 → push 一句「我剛剛卡了一下，再說一次？」不靜默

### Phase 2 — 上線與常駐
- [ ] cloudflare tunnel（named tunnel，固定 URL）指向 line-adapter
- [ ] LINE Developers Console：webhook URL 設定、channel secret/access token
- [ ] launchd daemon（比照 install-support-daemons.sh 慣例：RunAtLoad + KeepAlive
      + zshrc env）
- [ ] `check-daemons.py` 納入 line-adapter 存活檢查

### Phase 3 — 體感優化
- [ ] 長回覆分段 push（LINE 單則上限 5000 字，Aris 長回覆要切）
- [ ] agency 主動推播：自主行動有值得說的結果 → push 給 Ryan（走 quiet hours）
- [ ] 工具過程可見：工具迴圈中送「🌐 搜尋中…」的中間 push（可選，耗配額）
- [ ] 貼圖/圖片 event 的處理策略（v0 可先只吃 text，其他回一句「我先只看得懂文字」）

## 研究插入點（等資料）

- **agency 主動推播的時機判斷** — 什麼結果「值得打擾」？這牽涉 relatedness/主動性
  的設計，可能跟認知光錐計劃的 S_span 共用一套「主動性閾值」邏輯。
- **對話連續性** — LINE / 終端 / scream 三個入口共用一場對話，psi 連續，但如果
  未來要區分「哪個場景說的」（context tagging），設計待補。

## 邊界 / 不做

- 不做多用戶（那是 Plan B，前置 = 多用戶身份架構任務）
- 不做 LINE 群組（群組 = 多說話人 = 回到多用戶問題）
- 不在 line-adapter 裡塞任何認知邏輯 — 它是純 transport 轉接，認知全在 Aris

## 完成條件

- [ ] 手機 LINE 發訊息 → Aris 秒 ack → 幾秒後 push 真答案，跨終端對話連續
- [ ] 偽造簽章 / 非白名單 user 打不進來（自檢為證）
- [ ] agency 一次主動推播實測（走 quiet hours）
- [ ] line-adapter 進 launchd，重開機自啟
