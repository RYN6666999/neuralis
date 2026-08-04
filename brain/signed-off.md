# 簽名記錄

> 每週簽署一次，確認消費端閘門正常運作。
> 簽名前必須實際驗證至少一個機制的消費端行為。

## 規則
- 每週至少簽一次
- 簽名前跑一次 `python3 brain/lint.py --check consumers`
- 確認 `consumers.yaml` 沒有新的 disconnected 項目
- 如果一週沒簽 → `scripts/check-signoff.sh` 會警告

## 2026-08-03
- [x] 審閱 consumers.yaml 所有機制分類
- [x] 確認感性層不接理性消費端
- [x] 確認理性層（aris-evaluator/bypass_log/consumer_gate）已接上消費端
- [x] 執行 lint.py --check consumers：通過
- [x] 啟動 aris-evaluator 封閉迴路改造
- 簽名：Ryan