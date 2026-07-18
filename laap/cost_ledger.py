"""agency 算力預算 ledger（安全脊椎 Stage 2）— 委派/前瞻的成本閘。

記 token 花費、滑動小時窗；超預算 → 呼叫端該降頻（E2-b 預設「降頻不硬停」，
由呼叫端決定，ledger 只回 within_budget）。便宜的 Aris 不可無限觸發昂貴的
Scream/LLM（成本反轉防線）。env NEURALIS_AGENCY_HOURLY_TOKEN_BUDGET 預設 200000。

ponytail: token 數由呼叫端估/傳；精準計費（真實 usage 回填）是升級路徑。
path/now 參數化讓測試 hermetic。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

_DEFAULT_PATH = Path.home() / ".gbrain" / "agency-cost.jsonl"
_WINDOW = 3600.0


def _budget() -> int:
    return int(os.environ.get("NEURALIS_AGENCY_HOURLY_TOKEN_BUDGET", 200000))


def _path(path: Optional[str]) -> Path:
    return Path(path) if path else _DEFAULT_PATH


def record(tokens: int, source: str = "", when: Optional[float] = None,
           path: Optional[str] = None) -> None:
    p = _path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": when if when is not None else time.time(),
                                "tokens": int(tokens), "source": source},
                               ensure_ascii=False) + "\n")
    except Exception:
        pass


def spent_last_hour(now: Optional[float] = None, path: Optional[str] = None) -> int:
    p = _path(path)
    now = now if now is not None else time.time()
    total = 0
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if now - e.get("ts", 0) <= _WINDOW:
            total += int(e.get("tokens", 0))
    return total


def within_budget(want: int = 0, now: Optional[float] = None,
                  path: Optional[str] = None, budget: Optional[int] = None) -> bool:
    """想再花 want token 會不會超這小時預算。呼叫端 False 時應降頻。"""
    b = budget if budget is not None else _budget()
    return spent_last_hour(now=now, path=path) + int(want) <= b
