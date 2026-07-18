"""C-a：gbrain 經驗快取當規劃器（安全脊椎 Stage 4，§4 路 C）。

決策前先問快取『gbrain 有沒有相關經驗/知識可導這個決定』：
  hit → 用它當種子（零 LLM，gbrain-first）
  miss → 走探索（C-b 會在此委派 Scream 前瞻）
每次決策記 hit/miss，累計真實命中率 —— 校準 backtest 的粗略 65%。

⚠️ 命中定義用『詞相關』不用『原始分數』。backtest 教訓：gbrain hybrid 對亂碼
查詢的 top hit 也 0.84，分數尺度分不出有用/沒用。所以要求查詢與命中內容真的
共享有意義的詞。ponytail: 詞重疊是粗略相關代理；語義相關（無 LLM 的 rerank）
是升級路徑。base/now 參數化讓測試 hermetic。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

_DIR = Path.home() / ".gbrain"
_LEDGER = "cache-hitrate.jsonl"
_STOP = set("的 了 是 在 我 你 他 和 與 也 都 就 而 及 test query".split())


def _tokens(s: str) -> set:
    return {t for t in re.split(r"[\s，。、/_\-]+", (s or "").lower())
            if len(t) >= 2 and t not in _STOP}


def is_relevant(query: str, hit: dict) -> bool:
    """查詢與命中是否真的詞相關（非分數門檻）。"""
    content = (hit.get("chunk_text") or hit.get("title") or "") + " " + str(hit.get("slug", ""))
    return bool(_tokens(query) & _tokens(content))


def lookup(query: str, hits: list) -> dict:
    """在 gbrain hits 裡找相關命中。回 {hit, experience, slug}。
    hits = hybrid_hits 的結果（caller 先查好，方便測試/共用連線）。"""
    for h in hits:
        if is_relevant(query, h):
            exp = " ".join((h.get("chunk_text") or h.get("title") or "").split())
            return {"hit": True, "experience": exp[:200], "slug": h.get("slug", "")}
    return {"hit": False, "experience": None, "slug": ""}


def record(hit: bool, need: str = "", when: Optional[float] = None,
           base: Optional[str] = None) -> None:
    p = (Path(base) if base else _DIR) / _LEDGER
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": when if when is not None else time.time(),
                                "hit": bool(hit), "need": need}) + "\n")
    except Exception:
        pass


def hit_rate(base: Optional[str] = None, window_s: Optional[float] = None,
             now: Optional[float] = None) -> dict:
    """回 {rate, hits, total}。window_s 給就只算窗內。"""
    p = (Path(base) if base else _DIR) / _LEDGER
    now = now if now is not None else time.time()
    hits = total = 0
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {"rate": 0.0, "hits": 0, "total": 0}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if window_s is not None and now - e.get("ts", 0) > window_s:
            continue
        total += 1
        if e.get("hit"):
            hits += 1
    return {"rate": (hits / total if total else 0.0), "hits": hits, "total": total}
