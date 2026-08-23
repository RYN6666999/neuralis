"""失敗痕跡 —— 「靜默失敗」的共用解藥。

## 為什麼需要這支

2026-08-21：我們花一整天分析一份 `agency-audit.jsonl`，最後發現寫它的進程跑的
是 22 小時前的舊碼。接下來的計畫是「重啟 Aris，累積 300 筆新資料測學習」。

但有兩處寫入失敗時只印一行 `logger.warning`：

    laap/agency.py       _audit()          審計寫入失敗 → warning
    laap/consolidation.py _loop()          pass 失敗     → warning

**如果寫入靜默失敗，我們會再等一次永遠不會來的 300 筆。** 而 log 裡那行 warning
沒有人會看 —— 它跟成功的執行混在同一份 log 裡，而且沒有任何地方會告訴你
「你以為在累積的東西其實沒有在累積」。

這跟 `check-*.py` 那條線修的是同一個病：**把一種狀態（失敗）偽裝成另一種
（沒事）**。`_check_verdict.py` 的解法是讓腳本輸出一行機器可讀的結論；
這裡的對應解法是：**失敗必須留下一個事後查得到、而且看得出是失敗的痕跡。**

## 設計

1. **獨立的 sentinel 檔** `audit-failures.jsonl`（與被寫壞的那份分開）。
   為什麼分開：主 audit 寫入失敗時，同一個檔案可能就是壞的來源
   （磁碟滿、權限、路徑消失），把失敗記錄寫回同一個檔案等於沒記。
2. **這個檔案存在本身就是訊號。** 正常運作時它不該存在 —— 所以
   「有沒有這個檔」是一個零成本的健康檢查（`aris-status.py` / morning-brief
   可以只看存在性）。
3. **in-process 計數器** `failure_count()`：同一個 process 內問得到「失敗幾次」，
   不用去讀檔。狀態端點可以直接曝這個數。
4. **最後手段寫 stderr。** 連 sentinel 都寫不進去時（真的磁碟滿），
   stderr 至少會進 launchd 的 StandardErrorPath。**不再有一條完全無聲的路徑。**

## 刻意不做的

- **不 raise。** 呼叫端是決策迴圈與 daemon 執行緒；讓審計失敗炸掉決策迴圈
  會把「記錄壞了」升級成「Aris 停止工作」，那比原病更糟。
  **要吵，但不要致命。**
- **不重試。** 寫入失敗的原因通常是持續性的（權限、磁碟滿），重試只會讓
  決策迴圈變慢。sentinel 記下來，由人處理。
- **不改成功路徑。** 成功時這支完全不參與 —— 硬要求：成功路徑行為不變。
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]

# 刻意與 agency-audit.jsonl / consolidation-audit.jsonl 分開：
# 主檔寫不進去時，它自己就是不可信的地方。
FAILURE_PATH = ROOT / "audit-failures.jsonl"

_lock = threading.Lock()
_counts: dict[str, int] = {}


def record(kind: str, error: BaseException | str, **context) -> None:
    """記一次失敗。**永不 raise** —— 呼叫端是決策迴圈，不能被審計問題打斷。

    `kind` 是失敗的種類（例如 `agency_audit_write` / `consolidation_pass`），
    用來讓事後分析分得出「哪一種東西在壞」。
    """
    with _lock:
        _counts[kind] = _counts.get(kind, 0) + 1
        n = _counts[kind]

    # 連錯誤格式化本身都可能炸（例如 __str__ 壞掉的例外物件）。
    # 這支的契約是「永不 raise」，所以連 repr 都要包起來。
    try:
        if isinstance(error, BaseException):
            err_text = f"{type(error).__name__}: {error}"
        else:
            err_text = str(error)
    except Exception:
        try:
            err_text = f"{type(error).__name__}: <格式化失敗>"
        except Exception:
            err_text = "<無法描述的失敗>"

    entry = {
        "ts": time.time(),
        "kind": str(kind),
        "error": err_text,
        "count_this_process": n,
        "pid": os.getpid(),
        "exe": sys.executable or "",
    }
    entry.update(context)

    try:
        with FAILURE_PATH.open("a", encoding="utf-8") as f:
            # default=repr：context 可能帶不可序列化的物件，
            # 那不該讓失敗記錄本身失敗。
            f.write(json.dumps(entry, ensure_ascii=False, default=repr) + "\n")
    except Exception as e:
        # 最後手段：連 sentinel 都寫不進去（磁碟滿／唯讀 FS）。
        # stderr 會進 launchd 的 StandardErrorPath —— 不留無聲的路徑。
        try:
            print(f"[failure_trail] 連失敗記錄都寫不進去 ({e})；"
                  f"原始失敗 kind={kind} error={entry['error']}",
                  file=sys.stderr, flush=True)
        except Exception:
            pass


def failure_count(kind: Optional[str] = None) -> int:
    """本 process 到目前為止的失敗次數。狀態端點可以直接曝這個數。"""
    with _lock:
        if kind is None:
            return sum(_counts.values())
        return _counts.get(kind, 0)


def failure_kinds() -> dict:
    """各種類的失敗次數快照。"""
    with _lock:
        return dict(_counts)


def has_failures() -> bool:
    """這個 process 有沒有記到失敗。

    注意：**這只反映本 process。** 跨進程／跨重啟要看 `FAILURE_PATH` 存不存在
    —— 那個檔案存在本身就是訊號（正常運作時不該有）。
    """
    return failure_count() > 0
