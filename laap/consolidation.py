"""
ConsolidationLoop — Phase 5：記憶固化循環（睡眠）。

「記憶有存取、缺睡眠」（docs/research/external-feedback.md #1）。
agency loop 每天自主寫入 episodic 記憶，只進不出會把腦庫變垃圾場 —
這個迴路是消化系統。零 LLM：去重靠 normalized hash、升層靠情緒/重複度、
摘要是萃取式（不生成）。

睡眠窗：arousal 低 + 一段時間無互動才跑（不在對話中打掃）。

安全邊界（硬規則）：只動 `laap/memory/` namespace 下的頁，其他 slug 一律不碰。
每 pass 突變上限 MAX_MUTATIONS，審計 JSONL 全記錄。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("laap.consolidation")

_NS = "laap/memory/"
_EPI = "laap/memory/episodic/"
_CORE = "laap/memory/core/"
_ARCHIVE = "laap/memory/archive/"

MAX_PAGES_PER_PASS = 30
MAX_MUTATIONS_PER_PASS = 5
PROMOTE_EMOTION = 0.5     # 情緒強度 ≥ 此值 → 升 core
PROMOTE_SEEN = 3          # 重複出現 ≥ 此次數 → 升 core
STALE_DAYS = 30           # 超過此天數且低重要/低情緒 → 歸檔
STALE_IMPORTANCE = 0.35
STALE_EMOTION = 0.2
AUDIT_PATH = Path(__file__).resolve().parents[1] / "consolidation-audit.jsonl"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _f(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _age_days(created_at: str) -> float:
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    except Exception:
        return 0.0


class ConsolidationLoop:
    """背景執行緒：睡眠窗內對 laap/memory/episodic/* 做去重、升層、歸檔。"""

    def __init__(self, psi=None,
                 interval: Optional[float] = None,
                 idle_s: Optional[float] = None,
                 arousal_max: Optional[float] = None):
        self.psi = psi
        self.interval = interval if interval is not None else _env_float("NEURALIS_CONSOLIDATION_INTERVAL", 1800.0)
        self.idle_s = idle_s if idle_s is not None else _env_float("NEURALIS_CONSOLIDATION_IDLE_S", 600.0)
        self.arousal_max = arousal_max if arousal_max is not None else _env_float("NEURALIS_CONSOLIDATION_AROUSAL_MAX", 0.5)
        self._last_interaction = time.time()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self.passes_total = 0

    # ── 生命週期 ──

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(f"[Consolidation] 排程啟動 interval={self.interval}s idle={self.idle_s}s")

    def stop(self) -> None:
        self._running = False

    def note_interaction(self) -> None:
        """有互動就重置閒置計時（memory_bridge 餵 psi 時順手呼叫）。"""
        self._last_interaction = time.time()

    def _loop(self) -> None:
        while self._running:
            time.sleep(self.interval)
            try:
                if self._asleep():
                    self.run_pass()
            except Exception as e:
                logger.warning(f"[Consolidation] pass 失敗: {e}")

    def _asleep(self) -> bool:
        if time.time() - self._last_interaction < self.idle_s:
            return False
        if self.psi is not None:
            try:
                if self.psi.emotion.to_dict()["arousal"] > self.arousal_max:
                    return False
            except Exception:
                pass
        return True

    # ── 固化 pass ──

    def run_pass(self) -> dict:
        """一輪固化。回傳統計 dict（供自檢/審計）。"""
        try:
            from gbrain_client import get_client
            client = get_client()
        except Exception:
            client = None
        if client is None:
            return {"skipped": "gbrain 不可用"}

        pages = client.call("list_pages", {"limit": 100})
        epi = [p for p in pages if p.get("slug", "").startswith(_EPI)][:MAX_PAGES_PER_PASS]

        stats = {"scanned": len(epi), "merged": 0, "promoted": 0, "archived": 0}
        mutations = 0
        seen: dict = {}  # normalized-hash → survivor info

        for p in epi:
            if mutations >= MAX_MUTATIONS_PER_PASS:
                break
            page = client.call("get_page", {"slug": p["slug"]})
            body = (page.get("compiled_truth") or "").strip()
            fm = page.get("frontmatter") or {}
            info = {
                "slug": p["slug"],
                "body": body,
                "importance": _f(fm.get("importance"), 0.5),
                "emotion": _f(fm.get("emotion_intensity")),
                "seen_count": int(_f(fm.get("seen_count"), 1)),
                "age_days": _age_days(page.get("created_at", "")),
                "tags": [],
            }
            key = hashlib.md5(_normalize(body).encode()).hexdigest()

            if key in seen:
                # 去重合併：留最早那頁，seen_count 累加、importance 取大，刪這頁
                surv = seen[key]
                surv["seen_count"] += info["seen_count"]
                surv["importance"] = max(surv["importance"], info["importance"])
                surv["emotion"] = max(surv["emotion"], info["emotion"])
                surv["dirty"] = True
                self._delete(client, info["slug"])
                stats["merged"] += 1
                mutations += 1
            else:
                info["dirty"] = False
                seen[key] = info

        for surv in seen.values():
            if mutations >= MAX_MUTATIONS_PER_PASS:
                break
            promote = surv["emotion"] >= PROMOTE_EMOTION or surv["seen_count"] >= PROMOTE_SEEN
            stale = (surv["age_days"] > STALE_DAYS
                     and surv["importance"] < STALE_IMPORTANCE
                     and surv["emotion"] < STALE_EMOTION)
            if promote:
                self._move(client, surv, _CORE, layer="core")
                stats["promoted"] += 1
                mutations += 1
            elif stale:
                self._move(client, surv, _ARCHIVE, layer="archive")
                stats["archived"] += 1
                mutations += 1
            elif surv["dirty"]:
                self._rewrite(client, surv, surv["slug"], layer="episodic")
                mutations += 1

        self.passes_total += 1
        entry = {"ts": time.time(), "pass": self.passes_total, **stats}
        try:
            with AUDIT_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[Consolidation] 審計寫入失敗: {e}")
        logger.info(f"[Consolidation] pass#{self.passes_total} {stats}")
        return stats

    # ── 突變原語（全部帶 namespace 硬檢查） ──

    @staticmethod
    def _guard(slug: str) -> None:
        assert slug.startswith(_NS), f"固化只准動 {_NS}*，拒絕 {slug}"

    def _delete(self, client, slug: str) -> None:
        self._guard(slug)
        client.call("delete_page", {"slug": slug})

    def _rewrite(self, client, surv: dict, slug: str, layer: str) -> None:
        self._guard(slug)
        mem_id = slug.rsplit("/", 1)[-1]
        content = (
            f"---\n"
            f"title: laap memory {mem_id}\n"
            f"importance: {round(surv['importance'], 3)}\n"
            f"layer: {layer}\n"
            f"emotion_intensity: {round(surv['emotion'], 3)}\n"
            f"seen_count: {surv['seen_count']}\n"
            f"source: laap-consolidation\n"
            f"---\n\n"
            f"{surv['body']}\n"
        )
        client.call("put_page", {"slug": slug, "content": content}, timeout=30.0)

    def _move(self, client, surv: dict, dst_prefix: str, layer: str) -> None:
        old = surv["slug"]
        self._guard(old)
        mem_id = old.rsplit("/", 1)[-1]
        self._rewrite(client, surv, f"{dst_prefix}{mem_id}", layer=layer)
        self._delete(client, old)
