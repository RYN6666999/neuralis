"""E1.2 下游效用信號 — agency 寫的記憶後續有沒有被 recall 用到。

取代 len/500 假信號的『真』品質信號：延遲、不可作弊（長度騙不了未來被想起）。
批准預設：二元（有/無被 recall）、7 天窗、下游獎勵權重 0.7。

三個 ledger（jsonl，~/.gbrain/）：
  provenance: mem_id → {need, tool, angle}（agency 寫記憶時記）
  recall:     mem_id 被 recall 的 ts（recall 路徑記）
  credited:   已發過延遲獎勵的 mem_id（防重複發）

流程：tag_memory（寫時）→ record_recall（被想起時）→ pending_rewards（sweep：
7 天內被 recall 且未 credited → 回 (need,angle,tool) 給 agency 發延遲獎勵）→
mark_credited。base 參數化讓測試 hermetic。
ponytail: 二元起步；次數×新鮮度加權是升級路徑。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

WINDOW_S = 7 * 86400
DOWNSTREAM_REWARD = 0.7          # E1.2-c：下游獎勵權重
_DIR = Path.home() / ".gbrain"
_PROV = "memory-provenance.jsonl"
_RECALL = "memory-recall.jsonl"
_CREDITED = "memory-credited.jsonl"


def _p(name: str, base: Optional[str]) -> Path:
    return (Path(base) if base else _DIR) / name


def tag_memory(mem_id: str, need: str, tool: str, angle: str = "",
               when: Optional[float] = None, base: Optional[str] = None) -> None:
    """agency 寫記憶時記 provenance（哪個 need/tool/angle 產生了這條記憶）。"""
    if not mem_id:
        return
    _append(_p(_PROV, base), {"mem_id": mem_id, "need": need, "tool": tool,
                              "angle": angle,
                              "ts": when if when is not None else time.time()})


def record_recall(mem_id: str, when: Optional[float] = None,
                  base: Optional[str] = None) -> None:
    """recall 路徑命中 agency 記憶時記一筆（= 這條記憶被用到了）。"""
    if not mem_id:
        return
    _append(_p(_RECALL, base),
            {"mem_id": mem_id, "ts": when if when is not None else time.time()})


def pending_rewards(now: Optional[float] = None, base: Optional[str] = None) -> list:
    """7 天內被 recall、未 credited 的 agency 記憶 → [{mem_id,need,angle,tool,reward}]。
    呼叫端據此發延遲獎勵，成功後 mark_credited。"""
    now = now if now is not None else time.time()
    prov_map = {e["mem_id"]: e for e in _load(_p(_PROV, base))}
    recalled = {e["mem_id"] for e in _load(_p(_RECALL, base))
                if now - e.get("ts", 0) <= WINDOW_S}
    credited = {e["mem_id"] for e in _load(_p(_CREDITED, base))}
    out = []
    for mem_id in recalled:
        if mem_id in credited or mem_id not in prov_map:
            continue
        p = prov_map[mem_id]
        out.append({"mem_id": mem_id, "need": p.get("need", ""),
                    "angle": p.get("angle", ""), "tool": p.get("tool", ""),
                    "reward": DOWNSTREAM_REWARD})
    return out


def mark_credited(mem_id: str, base: Optional[str] = None) -> None:
    _append(_p(_CREDITED, base), {"mem_id": mem_id, "ts": time.time()})


def _append(path: Path, obj: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _load(path: Path) -> list:
    out = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return out
    for line in lines:
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out
