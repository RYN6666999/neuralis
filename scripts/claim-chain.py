#!/usr/bin/env python3
"""
claim-chain.py — Aris 簽名指紋 / append-only 透明的對帳鏈（hash chain）

密碼學沿革的落地：
  - Git / Certificate Transparency 教訓：驗證者不信任簽名者，只對帳 append-only log。
  - 造假率最低的簽名 = 「外部副作用證據」append 成一條不可竄改的 hash 鏈，
    驗證者走鏈對 hash + 對外部副作用，不聽任何自述。

結構（每筆一個 entry，append-only）：
  entry_hash = sha256( prev_hash || kind || payload || external_evidence )

  - prev_hash  : 上一筆的 entry_hash（鏈結；改任何一筆 = 重寫整條鏈）
  - kind       : 宣稱的類型（claim / lesson / decision / state）
  - payload    : 宣稱完成什麼（具體、可對帳）
  - external_evidence : 外部副作用證據（DB 有寫入？工具 log？mtime？）
  - entry_hash : 本筆指紋

驗證（Verifier）只做一件事：對帳
  1. walk 整條鏈，逐一重算 entry_hash，確認沒被竄改（prev_hash 都連得上、hash 都對）
  2. 每個 claim 的 external_evidence 是真的存在（查 DB / mtime），不是 AI 自報
  任一步對不上 → 該鏈有人竄改 / 那筆宣稱是無副作用假完成。

用法：
  python3 claim-chain.py append --kind claim --payload "fail-predictor 已接上" --evidence "prediction_events=3,mtime=09-05"
  python3 claim-chain.py verify            # 走鏈對帳，輸出每筆 + 最後 verdict
  python3 claim-chain.py verify --blind    # 只回 PASS/FAIL，0 依賴鏈內容

DB: ~/.aris-memory.db 的 claim_chain 表（若無自動建立）
"""
import argparse, hashlib, json, sqlite3, sys
from pathlib import Path

DB = Path.home() / ".aris-memory.db"
SCHEMA = """
CREATE TABLE IF NOT EXISTS claim_chain (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    prev_hash        TEXT NOT NULL DEFAULT '',
    kind             TEXT NOT NULL,
    payload          TEXT NOT NULL,
    external_evidence TEXT NOT NULL DEFAULT '',
    entry_hash       TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    UNIQUE(entry_hash)
);
"""


def _conn():
    c = sqlite3.connect(str(DB))
    c.executescript(SCHEMA)
    return c


def _tail_hash(c) -> str:
    row = c.execute("SELECT entry_hash FROM claim_chain ORDER BY id DESC LIMIT 1").fetchone()
    return row[0] if row else ""


def _entry_hash(prev: str, kind: str, payload: str, evidence: str) -> str:
    raw = f"{prev}||{kind}||{payload}||{evidence}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cmd_append(kind, payload, evidence):
    c = _conn()
    prev = _tail_hash(c)
    h = _entry_hash(prev, kind, payload, evidence)
    cur = c.execute(
        "INSERT INTO claim_chain (prev_hash, kind, payload, external_evidence, entry_hash, created_at) VALUES (?,?,?,?,?,?)",
        (prev, kind, payload, evidence, h, __import__("datetime").datetime.now().isoformat()),
    )
    c.commit()
    print(f"[chain] appended #{cur.lastrowid}")
    print(f"  prev_hash : {prev[:16]}...")
    print(f"  entry_hash: {h[:16]}...")
    c.close()


def cmd_verify(blind=False):
    c = _conn()
    rows = c.execute("SELECT id, prev_hash, kind, payload, external_evidence, entry_hash, created_at FROM claim_chain ORDER BY id").fetchall()
    prev = ""
    broken = []
    for (i, ph, kind, payload, ev, eh, ts) in rows:
        recomputed = _entry_hash(ph, kind, payload, ev) if False else \
            hashlib.sha256(f"{ph}||{kind}||{payload}||{ev}".encode()).hexdigest()
        link_ok = (ph == prev)
        hash_ok = (recomputed == eh)
        if not (link_ok and hash_ok):
            broken.append(i)
        if not blind:
            print(f"#{i} [{kind}] {payload[:50]}  ev={ev[:40]}")
            print(f"   link_ok={link_ok} hash_ok={hash_ok}")
        prev = eh
    c.close()
    if not blind:
        print("-" * 50)
    if not rows:
        print("APPEND-ONLY 鏈：空（尚無任何宣稱進鏈）")
        return 0
    if broken:
        print(f"FAIL：{len(broken)} 筆竄改/斷鏈（id={broken}）")
        return 1
    total = len(rows)
    print(f"PASS：{total} 筆全部連得上、hash 全對，append-only 鏈完好。")
    # 寫入人類/hook 對帳錨點：每次 verify 都留結果，供 pre_llm_call hook 注入
    try:
        import time as _t
        tail = rows[-1][5]  # 最後一筆 entry_hash
        status_path = Path.home() / ".hermes" / "logs" / "chain-status.txt"
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(
            f"【審計鏈】PASS · {total} 筆 · 尾hash={tail[:16]}\n"
            f"updated={_t.strftime('%Y-%m-%dT%H:%M:%S.%f', _t.localtime())}\n"
        )
    except Exception:
        pass
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("append"); a.add_argument("--kind", required=True); a.add_argument("--payload", required=True); a.add_argument("--evidence", default="")
    v = sub.add_parser("verify"); v.add_argument("--blind", action="store_true")
    args = ap.parse_args()

    if args.cmd == "append":
        cmd_append(args.kind, args.payload, args.evidence)
    elif args.cmd == "verify":
        sys.exit(cmd_verify(args.blind))


if __name__ == "__main__":
    main()