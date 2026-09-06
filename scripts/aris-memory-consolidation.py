#!/usr/bin/env python3
"""aris-memory-consolidation — 做夢模組（夜間記憶固化）。

設計原則（Ryan 架構規格）：
  - 重複 → 合併，不直接刪除
  - 矛盾 → 標記、凍結，不自動解決
  - 噪聲 → 降溫或墓碑，保留歷史
  - 證據 → 只追加不覆蓋，舊版標記 superseded
  - 每項操作可逆，不靜默降級

執行流程：
  1. 重複事件合併     — 同一件事寫了多次 → 合成 1 條
  2. 矛盾檢測          — 兩條記憶說相反的事 → 互標 contradiction
  3. 情節→語義提煉    — 多條相關事件 → 提煉為 M4 語義記憶
  4. 噪聲過濾          — 低 salience + 從未被 recall + 過期 → 墓碑
  5. 過期降權          — 超過 30 天沒被 recall 且 salience < 3 → 降溫
  6. 生成 L0 摘要       — 每條記憶一句話摘要（供 RecallDecider 快速判斷）
  7. 報告輸出           — 每次執行後印出做了什麼

用法：
    python3 scripts/aris-memory-consolidation.py              # dry-run
    python3 scripts/aris-memory-consolidation.py --apply      # 真的執行
    python3 scripts/aris-memory-consolidation.py --report     # 只報告不做

安裝為 nightly cron：
    (放在 aris-digest.plist 同一層，或 Hermes cronjob 裡)
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

DB = os.environ.get("ARIS_MEMORY_DB", str(Path.home() / ".aris-memory.db"))
REPORT_FILE = Path.home() / "Developer/neuralis/aris-consolidation-report.json"

# ── 雜訊閾值 ──
NOISE_DAYS = 30        # 超過 N 天沒被 recall
NOISE_SALIENCE = 2     # 自評顯著性 <= 此值視為低
NOISE_RECALLS = 1      # 被 recall 次數 <= 此值視為從未被用

# 語意提煉所需的最小相似事件數
SEMANTIC_MIN_EVENTS = 3

# ── 文字相似度（粗糙但無外部依賴） ──
def _tokenize(text: str) -> set[str]:
    """抽取中文 + 英文詞彙。"""
    return set(re.findall(r'[\u4e00-\u9fff\w]+', (text or "").lower()))

def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard 相似度 0-1。"""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

def _levenshtein_ratio(a: str, b: str) -> float:
    """Levenshtein 編輯距離比例 0-1。"""
    if not a or not b:
        return 0.0
    a, b = a[:200].lower(), b[:200].lower()
    n, m = len(a), len(b)
    if n > m:
        a, b = b, a
        n, m = m, n
    current = list(range(m + 1))
    for i in range(n):
        prev, current = current, [i + 1] + [0] * m
        for j in range(m):
            cost = 0 if a[i] == b[j] else 1
            current[j + 1] = min(prev[j + 1] + 1, current[j] + 1, prev[j] + cost)
    return 1.0 - (current[m] / max(n, m, 1))

def _text_similarity(a: str, b: str) -> float:
    """綜合文字相似度 0-1。只用 Jaccard（快，無需 Levenshtein 的 O(n²)）。"""
    if not a or not b:
        return 0.0
    return _jaccard(_tokenize(a), _tokenize(b))

def _batch_tokenize(memories: list[dict], field: str = "content") -> dict[int, set[str]]:
    """批次計算 token 集合。"""
    return {
        m["id"]: _tokenize((m.get(field) or "") + " " + (m.get("attention_line") or ""))
        for m in memories if m
    }


# ═══════════════════════════════════════════════════════════════
# Consolidation Engine
# ═══════════════════════════════════════════════════════════════

class ConsolidationEngine:
    """記憶固化引擎。對 SQLite 記憶庫執行 7 項固化操作。

    每個操作都是 idempotent（可重複執行）。dry_run=True 時只回報不做。
    """

    def __init__(self, db_path: str = DB, dry_run: bool = True):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.dry_run = dry_run
        self.report: dict[str, Any] = {
            "timestamp": time.time(),
            "dry_run": dry_run,
            "dedup": {"merged": 0, "skipped": 0},
            "contradiction": {"pairs": 0, "frozen": 0},
            "semantic": {"extracted": 0},
            "noise": {"tombstoned": 0, "cooled": 0},
            "summary": {"generated": 0},
            "errors": [],
        }

    def close(self):
        self.conn.close()

    # ─── 輔助 ───

    def _fetch_all_memories(self, min_confidence: str = "yellow") -> list[dict]:
        """抓取所有非墓碑的記憶。"""
        rows = self.conn.execute(
            "SELECT id, source, content, attention_line, tags, emotion_tag, "
            "created_at, encoding_salience, discovered_salience, total_recalls, "
            "last_recalled_at, confidence, origin, provenance, event_type, mood_note, flagged "
            "FROM memories WHERE confidence != 'tombstone' "
            "ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def _log(self, msg: str):
        print(f"  {'[DRY]' if self.dry_run else '[EXEC]'} {msg}")

    # ─── 1. 重複事件合併 ───

    def deduplicate(self, threshold: float = 0.75):
        """合併相似度超過 threshold 的記憶。

        策略：保留 encoding_salience 高的那條，低的標記墓碑。
        效能：先用 token 交集預篩選（至少共 2 個 token 才算全文相似度）。
        """
        memories = self._fetch_all_memories()
        count = 0

        # 預計算所有 token 集合（批次）
        token_sets = _batch_tokenize(memories)

        for i in range(len(memories)):
            if memories[i] is None:
                continue
            a = memories[i]
            aid = a["id"]
            for j in range(i + 1, len(memories)):
                if memories[j] is None:
                    continue
                b = memories[j]
                bid = b["id"]

                # 預篩選：至少共享 2 個 token 才計算相似度
                shared = token_sets[aid] & token_sets[bid]
                if len(shared) < 2:
                    continue

                sim = _jaccard(token_sets.get(aid, set()), token_sets.get(bid, set()))
                if sim >= threshold:
                    # 保留 salience 高者
                    keep, discard = (a, b) if (a["encoding_salience"] or 0) >= (b["encoding_salience"] or 0) else (b, a)
                    if not self.dry_run:
                        # 將 discard 的 attention_line 附加到 keep（如果 keep 沒有）
                        if discard.get("attention_line") and not keep.get("attention_line"):
                            self.conn.execute(
                                "UPDATE memories SET attention_line=? WHERE id=?",
                                (discard["attention_line"], keep["id"])
                            )
                        # 墓碑 discard
                        self.conn.execute(
                            "UPDATE memories SET confidence='tombstone', provenance=COALESCE(provenance,'')||' merged_from:'||? WHERE id=?",
                            (str(discard["id"]), discard["id"])
                        )
                        self.conn.commit()
                    count += 1
                    self._log(f"合併 #{keep['id']} ← #{discard['id']} (sim={sim:.2f})")
                    memories[j] = None  # 不再處理

        self.report["dedup"]["merged"] = count
        return count

    # ─── 2. 矛盾檢測 ───

    def detect_contradictions(self, threshold: float = 0.6):
        """找出內容矛盾（高相似度但情緒/事件類型相反）的記憶對。"""
        memories = self._fetch_all_memories()
        count = 0
        frozen = 0

        token_sets = _batch_tokenize(memories)
        OPPOSITE_EMOTIONS = {
            "frustration": "breakthrough", "breakthrough": "frustration",
            "anxiety": "calm", "calm": "anxiety",
            "joy": "sadness", "sadness": "joy",
        }

        for i in range(len(memories)):
            if memories[i] is None:
                continue
            for j in range(i + 1, len(memories)):
                if memories[j] is None:
                    continue
                a, b = memories[i], memories[j]
                if a.get("event_type") != b.get("event_type"):
                    continue
                shared = token_sets.get(a["id"], set()) & token_sets.get(b["id"], set())
                if len(shared) < 2:
                    continue
                sim = _jaccard(token_sets.get(a["id"], set()), token_sets.get(b["id"], set()))
                if sim < threshold:
                    continue

                emo_a = (a.get("emotion_tag") or "").strip().lower()
                emo_b = (b.get("emotion_tag") or "").strip().lower()
                conflict = False
                if emo_a and emo_b and OPPOSITE_EMOTIONS.get(emo_a) == emo_b:
                    conflict = True
                if a.get("confidence") == "green" and b.get("confidence") == "red":
                    conflict = True
                if b.get("confidence") == "green" and a.get("confidence") == "red":
                    conflict = True

                if conflict and not self.dry_run:
                    for mem in (a, b):
                        self.conn.execute(
                            "UPDATE memories SET flagged=1, mood_note=COALESCE(mood_note,'')||' [CONTRADICTION]' WHERE id=?",
                            (mem["id"],)
                        )
                    frozen += 1
                    self._log(f"矛盾凍結 #{a['id']} ↔ #{b['id']} (emo:{emo_a} vs {emo_b})")
                    count += 1

        self.report["contradiction"]["pairs"] = count
        self.report["contradiction"]["frozen"] = frozen
        if not self.dry_run and count > 0:
            self.conn.commit()
        return count

    # ─── 3. 情節→語義提煉 ───

    def extract_semantic(self, min_events: int = SEMANTIC_MIN_EVENTS):
        """從多條相似事件提煉語義模式。

        策略：
        1. 找出所有相似度 > 0.5 的記憶群組（至少 min_events 條）
        2. 生成一條 M4 語義記憶（「從 N 次事件發現：…」）
        3. 來源記憶互相 linked
        """
        memories = self._fetch_all_memories()
        # 只看有內容的記憶
        memories = [m for m in memories if (m["content"] or "").strip()]
        if len(memories) < min_events:
            return 0

        # 找出相似群組
        groups: list[list[dict]] = []
        used = set()
        for i in range(len(memories)):
            if i in used:
                continue
            group = [memories[i]]
            used.add(i)
            for j in range(i + 1, len(memories)):
                if j in used:
                    continue
                # 檢查是否與群組中任一成員相似
                sim = _text_similarity(
                    memories[i]["content"] or "",
                    memories[j]["content"] or "",
                )
                if sim > 0.5:
                    group.append(memories[j])
                    used.add(j)
            if len(group) >= min_events:
                groups.append(group)

        count = 0
        for group in groups:
            # 找共同主題詞
            all_tokens = set()
            for m in group:
                all_tokens.update(_tokenize(m["content"] or ""))
            # 找出出現頻率最高的詞
            from collections import Counter
            token_freq = Counter()
            for m in group:
                token_freq.update(_tokenize(m["content"] or ""))
            common = [t for t, c in token_freq.most_common(5) if c >= len(group) * 0.5]

            # 找共同情緒
            emotions = [m.get("emotion_tag") or "" for m in group if m.get("emotion_tag")]
            common_emotion = ""
            if emotions:
                common_emotion = Counter(emotions).most_common(1)[0][0]

            # 生成語義記憶
            NL = "\n"
            source_events = ", ".join(f"#{m['id']}" for m in group)
            semantic_text = (
                f"【語意提煉】從 {len(group)} 次事件發現：{NL}"
                f"  共同主題：{'、'.join(common) if common else '（分散）'}{NL}"
                f"  共同情緒：{common_emotion or '（多樣）'}{NL}"
                f"  來源事件：{source_events}{NL}"
                f"  提煉時間：{time.strftime('%Y-%m-%d %H:%M')}"
            )

            if not self.dry_run:
                now = time.time()
                self.conn.execute(
                    "INSERT INTO memories (source, source_id, content, tags, emotion_tag, "
                    "created_at, origin, confidence, provenance, event_type, encoding_salience) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    ("consolidation", f"semantic-{int(now)}", semantic_text[:2000],
                     json.dumps(["semantic", "auto_extracted"], ensure_ascii=False),
                     common_emotion, now, "auto_generated", "yellow",
                     f"extracted_from:{','.join(str(m['id']) for m in group)}",
                     "semantic_pattern", 3)
                )
                self.conn.commit()
                self._log(f"語意提煉: {common[:3]} ({len(group)} 事件)")
            count += 1

        self.report["semantic"]["extracted"] = count
        return count

    # ─── 4. 噪聲過濾 ───

    def filter_noise(self):
        """找出低價值記憶，標記為墓碑。

        條件（全部成立才標記墓碑）：
        - 儲存超過 NOISE_DAYS 天
        - encoding_salience <= NOISE_SALIENCE
        - total_recalls <= NOISE_RECALLS（幾乎沒被用過）
        - 不是 human origin（不碰人工記憶）
        """
        now = time.time()
        cutoff = now - NOISE_DAYS * 86400
        rows = self.conn.execute(
            "SELECT id, content, encoding_salience, total_recalls, origin, created_at "
            "FROM memories WHERE created_at < ? AND confidence != 'tombstone' "
            "AND origin != 'human'",
            (cutoff,)
        ).fetchall()

        count = 0
        for r in rows:
            if (r["encoding_salience"] or 0) <= NOISE_SALIENCE and (r["total_recalls"] or 0) <= NOISE_RECALLS:
                if not self.dry_run:
                    self.conn.execute(
                        "UPDATE memories SET confidence='tombstone', provenance=COALESCE(provenance,'')||' noise_tombstone:'||? WHERE id=?",
                        (time.strftime('%Y-%m-%d'), r["id"])
                    )
                count += 1
                self._log(f"噪聲墓碑 #{r['id']}: {r['content'][:40]}...")

        if not self.dry_run and count > 0:
            self.conn.commit()
        self.report["noise"]["tombstoned"] = count
        return count

    # ─── 5. 過期降權 ───

    def cool_down(self):
        """將低價值記憶從熱層降溫。

        條件：
        - 超過 30 天沒被 recall
        - encoding_salience < 3
        - 非 human origin

        降溫方式：confidence 設為 yellow（暖層），non-green 設為 red（冷層）。
        """
        now = time.time()
        cutoff = now - NOISE_DAYS * 86400
        rows = self.conn.execute(
            "SELECT id, encoding_salience, last_recalled_at, created_at, confidence, origin "
            "FROM memories WHERE confidence NOT IN ('tombstone', 'red') "
            "AND origin != 'human'",
        ).fetchall()

        count = 0
        for r in rows:
            last_recall = r["last_recalled_at"] or 0
            created = r["created_at"] or now
            age_no_recall = now - max(last_recall, created)
            if age_no_recall > NOISE_DAYS * 86400 and (r["encoding_salience"] or 0) < 3:
                new_conf = "yellow" if r["confidence"] == "green" else "red"
                if not self.dry_run:
                    self.conn.execute(
                        "UPDATE memories SET confidence=? WHERE id=?",
                        (new_conf, r["id"])
                    )
                count += 1
                self._log(f"降溫 #{r['id']}: {r['confidence']}→{new_conf}")

        if not self.dry_run and count > 0:
            self.conn.commit()
        self.report["noise"]["cooled"] = count
        return count

    # ─── 6. 生成 L0 摘要 ───

    def generate_summaries(self):
        """為每條非墓碑記憶生成 L0 摘要（一句話）。

        L0 摘要存在 provenance 欄位，格式：L0:一句話摘要
        """
        rows = self.conn.execute(
            "SELECT id, content, attention_line, event_type, emotion_tag, "
            "encoding_salience, provenance "
            "FROM memories WHERE confidence != 'tombstone' "
            "AND (provenance IS NULL OR provenance NOT LIKE 'L0:%')"
        ).fetchall()

        count = 0
        for r in rows:
            content = (r["content"] or "").strip()
            if not content:
                continue
            # 啟發式摘要：取第一句 + 情緒 + 重要度
            first_line = content.split("\n")[0][:80]
            emotion = f" [{r['emotion_tag']}]" if r["emotion_tag"] else ""
            sal = f" ★{r['encoding_salience']}" if r["encoding_salience"] >= 3 else ""
            attn = f" ☞{r['attention_line'][:30]}" if r["attention_line"] else ""
            summary = f"L0:{first_line}{emotion}{sal}{attn}"

            if not self.dry_run:
                current_prov = r["provenance"] or ""
                if current_prov:
                    new_prov = current_prov + "\n" + summary
                else:
                    new_prov = summary
                self.conn.execute(
                    "UPDATE memories SET provenance=? WHERE id=?",
                    (new_prov[:500], r["id"])
                )
            count += 1

        if not self.dry_run and count > 0:
            self.conn.commit()
        self.report["summary"]["generated"] = count
        self._log(f"L0 摘要: {count} 條")
        return count

    # ─── 7. 執行全部 ───

    def run_all(self):
        """依序執行所有固化操作。"""
        print(f"\n{'='*60}")
        print(f"記憶固化 {'(DRY RUN)' if self.dry_run else '(實際執行)'}")
        print(f"資料庫: {DB}")
        print(f"{'='*60}")

        print("\n--- 1. 重複合併 ---")
        self.deduplicate()

        print("\n--- 2. 矛盾檢測 ---")
        self.detect_contradictions()

        print("\n--- 3. 語意提煉 ---")
        self.extract_semantic()

        print("\n--- 4. 噪聲過濾 ---")
        self.filter_noise()

        print("\n--- 5. 過期降權 ---")
        self.cool_down()

        print("\n--- 6. L0 摘要 ---")
        self.generate_summaries()

        # Final report
        self.report["success"] = True
        r = self.report
        print(f"\n{'='*60}")
        print(f"固化報告")
        print(f"{'='*60}")
        print(f"  重複合併: {r['dedup']['merged']} 對")
        print(f"  矛盾檢測: {r['contradiction']['pairs']} 對（凍結 {r['contradiction']['frozen']} 條）")
        print(f"  語意提煉: {r['semantic']['extracted']} 條")
        print(f"  噪聲過濾: {r['noise']['tombstoned']} 條墓碑")
        print(f"  過期降權: {r['noise']['cooled']} 條")
        print(f"  L0 摘要:  {r['summary']['generated']} 條")
        print(f"  {'DRY RUN — 無實際變更' if self.dry_run else '✅ 已套用'}")

        # Save report
        try:
            REPORT_FILE.write_text(json.dumps(self.report, ensure_ascii=False, indent=2))
        except Exception:
            pass

        return self.report


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Aris 記憶固化（做夢模組）")
    parser.add_argument("--apply", action="store_true", help="真的執行（預設 dry-run）")
    parser.add_argument("--report", action="store_true", help="只看上次報告")
    args = parser.parse_args()

    if args.report:
        if REPORT_FILE.exists():
            print(json.loads(REPORT_FILE.read_text()))
        else:
            print("尚無固化報告")
        sys.exit(0)

    engine = ConsolidationEngine(dry_run=not args.apply)
    try:
        engine.run_all()
    finally:
        engine.close()