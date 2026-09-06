#!/usr/bin/env python3
"""
label-adapter.py — 把「真人/真實工具回饋」接成世界模型可消費的 structured label（A 核心）

原理：學習迴路斷在「label 沒人餵」。這支不自己判對錯（那會污染訓練資料），
而是從「已有真實真值的地方」把訊號接出來，寫進 mistake_outcome / verification_log。

三條 label 源（都不靠 LLM 自證，靠外部真值）：
  1. mistake_outcome.avoided — 你確認「這類錯後來沒再犯了」→ 正向 label
  2. mistake_outcome.recurred  — 你標記「這類錯又犯了」→ 負向 label（def trigger）
  3. verification_log verdict  — 接住原本孤兒 _verify_claim 找不到的 judge，
                                把「tool log 證據」跟「human 裁定」都寫進 verdict

安全性鐵則（breed 陷阱11 三態驗證 + 責任邊界）：
  - label 只能來自「外部可觀察的動作/你明確的確認」，不來自 LLM 自述
  - 舉例：某錯「又犯了」必須有 tool log / 你的話佐證，不能是系統自己說
  - unverifiable 是合法的 label —— 寧可標「無法驗」也不猜

用法：
  python3 label-adapter.py verdict-from-tools           # 掃 tool log，有證據的判 pending claims
  python3 label-adapter.py mark --mistake-id 5 --outcome avoided --evidence "RM-測試後行為符合"
  python3 label-adapter.py mark --mistake-id 1 --outcome recurred --evidence "又犯了一樣領域錯"
  python3 label-adapter.py stats                         # 看 label 狀態
"""
import argparse, sqlite3, datetime, json
from pathlib import Path

HOME = Path.home()
TULPA_DB = HOME / "Developer/neuralis/data/tulpa_memory.db"
# D1 2026-09-06：不再以死檔當真值源。TOOL_LOG/TOOL_LOGS 僅留作歷史紀錄，
# 實際判定已改為「只信真人/外部即時證據」，見 _tool_evidence_exists()。
# (原真值源 /tmp/laap-tool-status.json 停在 9/3、cognitive-hook.log 不存在)
TOOL_LOG = Path("/tmp/laap-tool-status.json")
TOOL_LOGS = [
    Path("/tmp/laap-tool-status.json"),
    Path(HOME / ".hermes/logs/cognitive-hook.log"),
]


def _conn():
    c = sqlite3.connect(TULPA_DB)
    c.row_factory = sqlite3.Row
    return c


def _now():
    return datetime.datetime.now().isoformat()


def cmd_mark(mistake_id, outcome, evidence):
    """把一筆錯標成 avoided/recurred/unverifiable。這是主要的真人 label 介面。"""
    if outcome not in ("avoided", "recurred", "unverifiable"):
        print(f"❌ outcome 必須是 avoided/recurred/unverifiable，不是 {outcome}")
        return 1
    db = _conn()
    # 確認 mistake 存在
    m = db.execute("SELECT id, error_type, input_pattern FROM mistake_catalog WHERE id=?", (mistake_id,)).fetchone()
    if not m:
        print(f"❌ mistake id {mistake_id} 不存在")
        db.close(); return 1
    db.execute(
        "INSERT INTO mistake_outcome (mistake_id, outcome, evidence, created_at) VALUES (?,?,?,?)",
        (mistake_id, outcome, evidence or "", _now()))
    db.commit()
    print(f"✅ 已標記 mistake#{mistake_id} [{m['error_type']}] → {outcome}")
    if evidence:
        print(f"   證據: {evidence}")
    db.close()
    return 0


def _tool_evidence_exists(claim: str) -> bool:
    """（D1 2026-09-06）不再掃死檔當真值源。

    原本掃 /tmp/laap-tool-status.json（停在 9/3）與不存在的 cognitive-hook.log，
    永遠拿到空 → verdict-from-tools 永遠只輸出 pending，製造「有在判」的假象。
    真值源只剩：真人裁定（POST /label / label-adapter mark）或即時外部證據。
    這裡固定回 False，逼 pending claims 走「需要真人裁定」，不再靠死檔自我安慰。
    """
    return False


def cmd_verdict_from_tools():
    """掃有工具證據的 pending claims，把它判 verified（有真值佐證才算）。"""
    db = _conn()
    pending = db.execute("SELECT * FROM verification_log WHERE verdict='pending'").fetchall()
    moved = 0
    for row in pending:
        if _tool_evidence_exists(row["claim"]):
            db.execute(
                "INSERT INTO verification_log (claim, round, found, method, verdict, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (row["claim"], row["round"] + 1, 1, "tool_log", "verified", _now()))
            moved += 1
    db.commit()
    print(f"✅ 從 tool log 找到證據的 claims: {moved}")
    still_pending = db.execute("SELECT count(*) c FROM verification_log WHERE verdict='pending'").fetchone()["c"]
    print(f"   仍然 pending（無外部證據，需真人裁定）: {still_pending}")
    db.close()
    return 0


def cmd_mark_many(ids, outcome, evidence):
    """批量標記多筆錯為同一 outcome（一次處理一整族教訓）。"""
    db = _conn()
    now = _now()
    n = 0
    for mid in ids:
        m = db.execute("SELECT id, error_type, input_pattern FROM mistake_catalog WHERE id=?", (mid,)).fetchone()
        if not m:
            print(f"  ⚠️ mistake#{mid} 不存在，跳過")
            continue
        db.execute(
            "INSERT INTO mistake_outcome (mistake_id, outcome, evidence, created_at) VALUES (?,?,?,?)",
            (mid, outcome, evidence or "", now))
        n += 1
    db.commit()
    db.close()
    print(f"✅ 批量標記 {n} 筆 → {outcome}")
    return 0


def cmd_stats():
    db = _conn()
    print("=" * 50); print("label 狀態（學習迴路的訊號健康度）"); print("=" * 50)
    rows = db.execute("SELECT outcome, count(*) c FROM mistake_outcome GROUP BY outcome").fetchall()
    if not rows:
        print("\n⚠️ mistake_outcome 空 —— 還沒有人類/工具 label 進來")
        print("  → learning rate 虛位在等，這個空就是根因的眼下症狀")
    else:
        for r in rows:
            print(f"\n  [{r['outcome']}] {r['c']} 筆")
    # 每筆錯的標記狀態
    print("\n  ── 每筆錯的驗收狀態 ──")
    ms = db.execute("SELECT id, error_type, input_pattern FROM mistake_catalog").fetchall()
    for m in ms:
        o = db.execute("SELECT outcome, evidence FROM mistake_outcome WHERE mistake_id=? ORDER BY id DESC LIMIT 1",
                       (m["id"],)).fetchone()
        st = f"→ {o['outcome']}" if o else "→ (未labelled)"
        print(f"    #{m['id']} [{m['error_type']:18}] {m['input_pattern'][:30]:32} {st}")
    print("\n  ── verification_log verdict 分布 ──")
    v = db.execute("SELECT verdict, count(*) c FROM verification_log GROUP BY verdict").fetchall()
    for r in v:
        print(f"    {r['verdict']}: {r['c']}")
    db.close()
    return 0


def main():
    ap = argparse.ArgumentParser(description="Label adapter: 接真人/工具回饋給世界模型")
    sub = ap.add_subparsers(dest="cmd")
    m = sub.add_parser("mark", help="把一筆錯標成 avoided/recurred")
    m.add_argument("--mistake-id", type=int, required=True)
    m.add_argument("--outcome", required=True, choices=["avoided", "recurred", "unverifiable"])
    m.add_argument("--evidence", default="")
    mm = sub.add_parser("mark-many", help="批量標記多筆錯為同一 outcome")
    mm.add_argument("--ids", type=int, nargs="+", required=True)
    mm.add_argument("--outcome", required=True, choices=["avoided", "recurred", "unverifiable"])
    mm.add_argument("--evidence", default="")
    sub.add_parser("verdict-from-tools", help="掃有可 track 的 pending claims")
    sub.add_parser("stats", help="看 label 健康度")
    args = ap.parse_args()
    if args.cmd == "mark":
        return cmd_mark(args.mistake_id, args.outcome, args.evidence)
    if args.cmd == "mark-many":
        return cmd_mark_many(args.ids, args.outcome, args.evidence)
    if args.cmd == "verdict-from-tools":
        return cmd_verdict_from_tools()
    if args.cmd == "stats" or not args.cmd:
        return cmd_stats()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())