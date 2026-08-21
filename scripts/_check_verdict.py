"""自檢腳本的三態結論 —— 「綠燈說謊」的共用解藥。

## 為什麼需要這支

`scripts/check-*.py` 存在的唯一理由是：**壞了要有人知道**。
但其中有一族腳本在「外部依賴不在」時的行為是：印一行 `SKIP`，
然後照樣印 `ALL CHECKS PASSED` 並 `exit 0`。

於是偵測器在它存在的全部理由所對應的最壞情況下 —— 什麼都沒驗到 ——
對外的訊號跟「全部驗過而且都好」完全一樣。自動化讀不出差別，人也讀不出。
`brain/drift.py` 就是這樣把上游 404 印成「✅ 全部同步」exit 0 的（見
`tests/test_drift_missing_upstream.py`）。

## 三態，不是兩態

根因不是少寫一個 if，是把三件事壓進同一個布林：

| 語義 | 對的行動 | exit |
|---|---|---|
| 驗過了，是好的 | 繼續 | 0 |
| 驗過了，是壞的 | 修 | 1 |
| **沒驗到** | 換個能驗的環境再驗；別當成驗過 | 2 |

第三態必須跟 0 分開，否則就是把「沒驗到」講成「沒問題」。
也必須跟 1 分開，否則就是假紅 —— `.github/workflows/guard.yml` 已經寫過
「假紅比沒有更糟 —— 人會學會無視紅燈」。離線、限流、環境本來就沒這個
依賴（沒有 gbrain binary、沒有 Rust daemon、`:11546` 不在、沒有 lsof），
這些都**不是 fail**。

CI 用法與 `brain/drift.py` 一致：exit 2 當 warning（不擋 pipeline），
exit 1 當 failure。

## 邊界（這支刻意不做的事）

- **`unknown` 不吃例外。** 未預期的例外是 `fail`，不是「沒驗到」——
  腳本自己炸掉是真問題。舊版 `check-rust-psi-backend.py` 把
  `FileNotFoundError` 吞進 `except Exception` 印一行就 exit 0，
  剩下所有檢查靜默消失，這正是要擋的。
- **`unknown` 不會蓋掉 `fail`。** 同時有兩者時 exit 1（要行動的優先）。
"""
from __future__ import annotations

import sys
from typing import List, Optional

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"        # 驗到了，是可接受的降級／非關鍵缺口 → 仍算綠（exit 0）
UNKNOWN = "UNKNOWN"  # 沒驗到（依賴不在／離線）→ 不是綠燈，也不是失敗（exit 2）

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_UNVERIFIED = 2

_ICON = {PASS: "✅", FAIL: "❌", WARN: "⚠️ ", UNKNOWN: "⚪"}


class Verdict:
    """收集各段結論，最後算出一個誠實的 exit code。"""

    def __init__(self, name: str) -> None:
        self.name = name
        self.results: List[dict] = []

    # ── 記錄 ──────────────────────────────────────────────────
    def _add(self, status: str, msg: str, detail: str = "") -> None:
        self.results.append({"status": status, "msg": msg, "detail": detail})
        print(f"{_ICON[status]} {msg}" + (f" — {detail}" if detail else ""))

    def ok(self, msg: str, detail: str = "") -> None:
        self._add(PASS, msg, detail)

    def fail(self, msg: str, detail: str = "") -> None:
        self._add(FAIL, msg, detail)

    def warn(self, msg: str, detail: str = "") -> None:
        self._add(WARN, msg, detail)

    def unknown(self, msg: str, detail: str = "") -> None:
        """依賴不在／環境沒有 → 這段沒驗到。**不是綠燈，也不算失敗。**"""
        self._add(UNKNOWN, msg, detail)

    # ── 查詢 ──────────────────────────────────────────────────
    def counts(self) -> dict:
        return {s: sum(1 for r in self.results if r["status"] == s)
                for s in (PASS, FAIL, WARN, UNKNOWN)}

    def exit_code(self) -> int:
        c = self.counts()
        if c[FAIL]:
            return EXIT_FAIL
        if c[UNKNOWN]:
            return EXIT_UNVERIFIED
        return EXIT_OK

    # ── 輸出 ──────────────────────────────────────────────────
    def summary(self) -> str:
        """摘要行。刻意讓三態各有一句**互相看不錯**的話。

        `ALL CHECKS PASSED` 只在真的全驗過時才印 —— 有任何一段沒驗到就不准印，
        因為 grep 那句話的人（和 CI）就是靠它判斷「這支綠了」。
        """
        c = self.counts()
        head = (f"{c[PASS]}/{len(self.results)} PASS, {c[FAIL]} FAIL, "
                f"{c[WARN]} WARN, {c[UNKNOWN]} 沒驗到")
        code = self.exit_code()
        if code == EXIT_FAIL:
            body = f"❌ {self.name}: 有 FAIL —— 這是真問題，要修。"
        elif code == EXIT_UNVERIFIED:
            body = (f"⚪ {self.name}: {c[UNKNOWN]} 段沒驗到（依賴不在／離線）"
                    f"—— **不是綠燈，是沒驗到**。exit 2。\n"
                    f"   沒驗到的：" + "、".join(
                        r["msg"] for r in self.results if r["status"] == UNKNOWN))
        elif c[WARN]:
            body = f"✅ {self.name}: ALL CHECKS PASSED（有 {c[WARN]} 項降級警告）"
        else:
            body = f"✅ {self.name}: ALL CHECKS PASSED"
        return f"\n{'=' * 56}\n{head}\n{body}\n"

    def finish(self) -> None:
        """印摘要並用正確的 code 退出。"""
        print(self.summary())
        sys.exit(self.exit_code())


def guard(v: Verdict, label: str):
    """context manager：段內未預期例外 → `fail`（不是 unknown、不是靜默 exit 0）。

    舊 `check-rust-psi-backend.py` 的 `except Exception: print(...)` 會把
    `FileNotFoundError` 吞掉、後面所有檢查一併消失、最後仍 exit 0。
    腳本自己炸掉是真問題，必須紅。
    """
    class _G:
        def __enter__(self_inner):
            return v

        def __exit__(self_inner, exc_type, exc, tb):
            if exc_type is None:
                return False
            if exc_type is SystemExit:
                return False
            if exc_type is AssertionError:
                v.fail(f"{label}: 斷言失敗", str(exc) or "(無訊息)")
                return True
            v.fail(f"{label}: 未預期例外 {exc_type.__name__}", str(exc))
            return True

    return _G()
