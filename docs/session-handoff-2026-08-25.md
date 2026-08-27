# Aris Full Power — 接線圖與下一步

## 當前 18428 狀態（2026-08-25）

18428 running at port 18428。
啟動：`cd ~/Developer/neuralis/scripts && /opt/homebrew/bin/python3 aris_tulpa_api.py 18428`

DB：`~/Developer/neuralis/data/tulpa_memory.db`
規格書：`~/Developer/neuralis/docs/tulpa-spec-v0.3.md`

## 11 個端點

| 端點 | 用途 |
|------|------|
| `GET /health` | 健康 + 即時警報 |
| `GET /audit` | 完整稽核（9 類警報） |
| `GET /blindspot` | 周哈里窗盲點報告 |
| `GET /convergence` | 習慣收斂曲線 |
| `GET /state` | tulpa 權重 |
| `GET /migration` | 認知遷移時序 |
| `GET /prune` | 去蕪存菁 + 結構同構 |
| `GET /observer` | 第三位置觀察者洞見 |
| `GET /timeaxis` | 時間軸競爭（過去/現在/未來） |
| `GET,POST /experiment` | 實驗/創造者（分裂合併） |
| `GET,POST /cognitive` | 主認知 API |

## 三層架構

```
競合者（六個 tulpa + 領域樹）
   → 競爭誰進 context
觀察者（第三位置）
   → 發現 conflict/contradiction/MOTW mismatch
實驗/創造者（meta-tulpa）
   → 根據觀察結果提出分裂/合併/跨域建議
```

## 核心哲學

- 周哈里窗擴展 = 湧現
- 競合（競爭+整合）≠ 概率機
- 行動變化 = 聰明，非文字生成
- 八項敷衍已修復（spec §9）
- 不靜默降級、不假裝有信心
- 高耦合在感知層，低耦合在執行層

## 下一步（待實作）

1. Rust tulpa-engine — copy PsiEngine `engine.rs` + `runtime.rs`
2. 分層頻率：fast(weight drift) → medium(prune) → slow(cross-table mining)
3. 自省結論也競爭（insight compete）
4. 無輸入時自我審視，等使用者回來主動提出


---

# 今日實作流水（2026-08-25 後半）— 18428 認知引擎修復與閉環

> 本段由 Prime-agent＋Ryan 協作實作並 live 驗證。所有改動皆經重啟 18428 實測。

## 🎯 核心病根（今天抓到的）
系統把「結構偽影」誤判成「能力失敗」，AUDIT 是幫兇。
- `愛` keyword 103 miss = 匱乏不存在，非 bug
- 合併建議 sim 0.8 = detect_isomorphism 只看樹形不看語意
- conflict 分數近 = 預設權重接近，無真實分歧
- 未來 tulpa 0/10 = 計分器結構性壟斷，非能力衰退

## ✅ 今日已落地（全部 live 驗證）

### 1. prediction ground truth（死→生）
- 舊：predicted_path 算完即死，無存無消費
- 今：`prediction_events` 表 + `_settle_prediction` 跨輪結算 + session 結束標 expired（自然死亡，非 timeout）
- 端點：`GET /predictions`、`GET /feedback`、audit 含 settled/unsettled/expired

### 2. Bug① 結算串位
- 舊：取最新 pending 硬對 current actual → 錯位
- 今：匹配式 `predicted == actual_path`，其餘 pending 留待

### 3. Bug② 預測寬域
- 舊：抓所有 current||'/%' 兄弟比頻率 → 跟催被陌生拜訪頂替
- 今：限定「同分支直接下一跳」（depth+1），不再亂猜

### 4. observer→experiment 閉環（全收無門檻）
- `_observe_third_position` 產出 conflict → 全收進 `pending_suggestions`
- 信心度排序（GET /experiment）+ 審議（POST action=review approve/reject）
- 學習閉環：`_learned_confidence` 依同型歷史 approve/reject 調整新建議信心 → `/feedback` 可查
- 特性：不靜默降級（Ryan 拍板），全收+標信心，雜事排序

### 5. 領域樹「生」機制（keyword 生命週期閉環）
- 生：jieba 分詞 + 累計候選 + 閘門（同路≥4 或跨路≥4）→ pending_suggestions → 人核准 → 寫入該節點 keywords + `domain_keyword_additions` 持久化 + 啟動 overlay
- 死（既有）：prune_cycle 50 miss → 移除
- 復活（既有）：移除後出現 → 自動加回
- 實證：斡旋無→有，核准寫入【帶看】+【簽約/成交】兩節點，重啟 overlay 生效 → 單字「斡旋」route 命中領域樹

## 🔴 目前進程
PID 99059（latest），session 新，DB `~/Developer/neuralis/data/tulpa_memory.db`
啟動：`cd ~/Developer/neuralis/scripts && /opt/homebrew/bin/python3 aris_tulpa_api.py 18428`（**注意：必須用 /opt/homebrew，laapenv 無 aiohttp**）

## gap list（今日校正後）
| 缺口 | 狀態 |
|------|------|
| keyword 生（領域樹） | ✅ 已補 |
| prediction cleanup | ✅ 已補 |
| Bug① 結算串位 | ✅ 已補 |
| Bug② 預測寬域 | ✅ 已補 |
| observer→experiment | ✅ 全收無門檻+信心排序 |
| tulpa flat keyword 新生 | ❌ 只有領域樹有，六個 tulpa 手刻死 |
| _suggest_split 死碼 | ❌ 無人呼叫 |
| blindspot/convergence/observer 產出不被消費 | ❌ 只供人讀 |
| 外部事實接入 | ❌ 只能吃內部路徑名 |
| 11551 記憶雙 DB | ❌ 18428 不讀 11551 |
| 主動預警 | ❌ 被動指標 only |

## 下次建議
1. tulpa flat keyword 新生（領域樹有、tulpa 沒有，不對稱）— 可複用現有 jieba+閘門架構
2. 每輪 observer insight 是否值得自動升級成大範圍動作（審慎）
3. 外部事實（房多多 C 單/LINE/通話）接 ground truth

## 湧現基準（Ryan 2026-08-25 界定）
18428 = 實驗湧現的機器，不是湧現本身。
湧現 = 微觀依賴 + 宏觀自主 + 跨尺度穩健（Anderson/Chalmers/Bedau/Hoel）。實質 = 因果壓縮。

### 今天「生」在哪層
jieba 累計 → 斡旋加詞 = 底層生成。宏觀自主 ❌、跨尺度穩健 ❌ → 統計關聯 + 人核准，非湧現。別用「湧現」撐場。

### 真湧現實驗命題（北極星）
1. **自組織新節點**：從統計長出「新節奏點」→ 預測力 > 手刻，非人先標。
2. **跨尺度穩健**：底層微調，宏觀規律仍穩。
兩者都過 + 可 predict → 才算「宏觀自主」出現。

### 下顆螺帽意義重估
tulpa flat keyword 新生 = 補對稱（六個 tulpa 也學詞）= 有用底層採集，不追湧現。

## ✅ 收尾追加（2026-08-25 晚）

### contradiction 已接進 pending（observer 四感 → conflict/contradiction 兩感能說話）
- `_observe_third_position` contradiction → `pending_suggestions`（suggested_action=flag_tulpa，標記待觀察/調 weight）
- 用 `_learned_confidence("contradiction", 0.5)`：人長期審議會調整這型的優先權（學習閉環）
- 驗證：寫入路徑單測通過（flag_tulpa + confidence + pending）

### opportunity / motw_mismatch 真正堵點（誠實記）
- **opportunity**：`_suggest_cross_domain` 需 ≥2 棵領域樹才觸發，`ALL_DOMAINS=[CLIENT_TREE]` 只有一棵 → 目前實質不產出。等第二棵樹出現再活化。
- **motw_mismatch**：舊 MOTW 比較器已退役（if False 凍結塊已刪），`_settle_prediction` 跨輪結算 + `_global_prediction_accuracy` 全域迴授 是唯一準確率來源。motw 型不再產生新數據，只留 audit 讀歷史。

### 凍結塊退役完成（有出口的凍結）
- 刪除 if False MOTW 凍結塊（43 行死碼），`_settle_prediction` + C 全域迴授正式接棒
- prediction_accuracy 舊表不再寫入；motw_mismatch 不再產新假警報
- 驗證：跨輪結算正確（客戶經營→預測帶看→實際帶看→settled correct=1，6 筆全對）


---

# ═════════ 今日收檔（2026-08-25 18:07）═════════

## 18428 現況
- PID 26226（latest），Session s20260825_180721
- 6 tulpas alive、權重 0.98~1.5 正常
- 健康：0 contradiction/motw_failure（舊系統已退休）、9 expired（正常清理）、3 unresolved conflicts、1 inactive keyword（愛的 legacy）、1 pending_merge

## 今日 10 大改動（全部 live）
| 改動 | 層級 | 驗證 |
|------|------|------|
| FD leak WeakSet | Hermes | ✅ 沒再爆 |
| FD 壓力監測 | Hermes | ✅ 80%警告 |
| prediction ground truth | 18428 | ✅ /predictions |
| Bug①②③ 結算+cleanup | 18428 | ✅ settled/expired 正常 |
| observer→experiment 閉環 | 18428 | ✅ pending 可用 |
| keyword 生(領域樹+tulpa) | 18428 | ✅ 斡旋+暢快驗證 |
| 全域學習迴授 A→B→C | 18428 | ⏳ 等 20 samples 啟動 |
| PSI 雙向 | 18428→PSI | ✅ FIFO 寫入不崩（無外部 meter） |
| contradiction pipeline | 18428 | ✅ 已接 pending |
| 湧現框(2/3 判準) | 架構 | ⏳ 等 learning loop 樣本足 |

## 閉環待續（若需先接）
- 全域迴授 learning loop：等 settled samples ≥20 自動啟動（已新增 :참 audit learning_loop 可視化）
- 11551/18428 記憶互通：低必要性（延後）
- 房多多/LINE 外部事實：無源（延後）
- PSI 吃到與否無外部 meter（需 daemon 側加 events counter）— 誠實標記，不假裝已證

## 開工教訓（Ryan 界定）
「開工先問湧現軸」＝用「這在往哪條主軸長」當大門，過濾要動哪些、往深挖還是放著。白天是看到洞就補（發散），傍晚湧現框進場後才收斂（窄深）。
