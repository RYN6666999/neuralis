#!/usr/bin/env python3
"""
aris-wiring — 接線稽查：誰繞過主幹，自己拉線到底層？

為什麼存在：
  這套系統沒有主幹。每個接入點（Hermes、proxy、relay、cron、autoupdate、
  各種 shell 腳本）都自己往底層拉一條線拿「狀態」和「記憶」。
  七條線 → 七份答案 → 任何人修好一條都「看起來像修好了」。
  今天一天就示範了三次：修 DB 沒變、修排序沒變、修 healthy() 端點還是舊值。

  在沒有主幹的系統裡，「做到位」在物理上不可能——因為沒有一個地方
  能同時代表全部。這支工具的作用是：把所有繞過主幹的線列出來，
  讓「片面完成」無法偽裝成「完成」。

判準（違規＝直接碰底層，而不是問主幹）：
  A. 直讀 PSI 狀態檔      rust-latest.json / latest.json / quantum_output.json
  B. 自己造 PSI 實例      PsiCore() / RustPsiBackend() / PythonPsiBackend()
  C. 自己開記憶後端        MemoryStore() / laap_semantic_memory / get_client()
  D. 硬寫服務埠            11546 / 11547 / 11550 / 11551

設計約束（今天踩過的坑，全部避開）：
  - 不用 pgrep（非 UTF-8 cmdline 會讓它靜默回空 → 「沒有」是假的）
  - 不依賴 rg（該指令在某些 shell 被 alias 成 grep，行為不同）
  - 讀檔一律 errors='replace'，本機確實存在非 UTF-8 內容
  - 掃描失敗要出現在報告裡，不准偽裝成「沒有違規」

用法：
  aris-wiring.py             # 人看
  aris-wiring.py --json      # 機器看
  aris-wiring.py --by-file   # 按檔案聚合（決定「這個檔要不要接主幹」時用）
exit code: 有違規=1，乾淨=0
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOTS = [
    Path("/Users/ryan/Developer/neuralis"),
    Path("/Users/ryan/Developer/laap-AGI"),
    Path("/Users/ryan/.hermes/hermes-agent"),
    Path("/Users/ryan/agent-sandbox/scripts"),
]

SCAN_EXT = {".py", ".sh", ".zsh", ".bash", ".ts", ".js"}

# 排除：不是「接線」的東西（測試、備份、快取、產物、文件、session log）
SKIP_DIR = {
    ".git", "__pycache__", "node_modules", "target", "graphify-out",
    "sessions", ".venv", "venv", "site-packages", ".claude", "backups",
    "tests", "test",
}
SKIP_NAME_RE = re.compile(r"(\.bak|-legacy|\.orig|\.tmp)")

# 主幹本身 + 稽查工具本身，不算違規（它們就是被授權碰底層的）
TRUNK_FILES = {
    "psi_backend.py",      # PSI 後端實作本身
    "startup.py",          # 唯一被授權建 PsiCore 的地方
    "memory_store.py",     # 記憶後端實作本身
    "gbrain_client.py",    # gbrain 客戶端實作本身
    "psi_adapter.py",      # rust→latest 的官方轉接
    "aris-truth.py",       # 真相稽查（唯讀）
    "aris-wiring.py",      # 本檔
}

RULES = [
    ("A. 直讀 PSI 狀態檔",
     re.compile(r"rust-latest\.json|[\"'/]latest\.json|quantum_output\.json")),
    ("B. 自己造 PSI 實例",
     re.compile(r"\b(PsiCore|RustPsiBackend|PythonPsiBackend)\s*\(")),
    # 註：原本 C 規則含裸的 `get_client(`，誤抓 Slack/飛書自己的同名函式
    # （slack/adapter.py 一支就假報 37 處）。判準必須綁定 gbrain/記憶語境。
    ("C. 自己開記憶後端",
     re.compile(r"\bMemoryStore\s*\(|laap_semantic_memory|gbrain_client"
                r"|memory_bridge|(from|import)\s+memory_store"
                r"|gbrain[_-]?client\.get_client|subprocess.*\bgbrain\b")),
    ("D. 硬寫服務埠",
     re.compile(r"\b(11546|11547|11550|11551)\b")),
]

ERRORS: list[str] = []


def iter_files():
    for root in ROOTS:
        if not root.exists():
            ERRORS.append(f"掃描根目錄不存在（此範圍未涵蓋）: {root}")
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIR and not d.startswith(".")]
            for fn in filenames:
                if Path(fn).suffix not in SCAN_EXT:
                    continue
                if SKIP_NAME_RE.search(fn):
                    continue
                yield Path(dirpath) / fn


def scan() -> list[dict]:
    hits = []
    for f in iter_files():
        if f.name in TRUNK_FILES:
            continue
        try:
            # errors='replace'：本機有非 UTF-8 內容，硬解會拋例外→被吞→假裝沒違規
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            ERRORS.append(f"讀檔失敗（此檔未稽查）: {f} — {type(e).__name__}")
            continue
        for i, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            if s.startswith("#") or s.startswith("//"):
                continue          # 註解不算接線
            for rule, pat in RULES:
                if pat.search(line):
                    hits.append({
                        "rule": rule,
                        "file": str(f),
                        "line": i,
                        "text": s[:110],
                    })
                    break
    return hits


def main() -> int:
    hits = scan()

    if "--json" in sys.argv:
        print(json.dumps({
            "violations": hits,
            "count": len(hits),
            "files": len({h["file"] for h in hits}),
            "scan_errors": ERRORS,
        }, ensure_ascii=False, indent=2))
        return 1 if hits else 0

    by_file: dict[str, list[dict]] = {}
    by_rule: dict[str, int] = {}
    for h in hits:
        by_file.setdefault(h["file"], []).append(h)
        by_rule[h["rule"]] = by_rule.get(h["rule"], 0) + 1

    print("aris-wiring — 繞過主幹的接線\n")
    print(f"違規 {len(hits)} 處，散在 {len(by_file)} 個檔\n")

    print("按類型：")
    for rule, n in sorted(by_rule.items(), key=lambda x: -x[1]):
        print(f"  {n:>4}  {rule}")

    if "--by-file" in sys.argv:
        print("\n按檔案（違規最多的在前 —— 這就是接主幹的優先順序）：")
        for f, hs in sorted(by_file.items(), key=lambda x: -len(x[1]))[:30]:
            rules = sorted({h["rule"][0] for h in hs})
            print(f"  {len(hs):>3} 處 [{''.join(rules)}]  {f}")
    else:
        print("\n違規最多的 15 個檔（--by-file 看完整）：")
        for f, hs in sorted(by_file.items(), key=lambda x: -len(x[1]))[:15]:
            rules = sorted({h["rule"][0] for h in hs})
            print(f"  {len(hs):>3} 處 [{''.join(rules)}]  {Path(f).name}")
            print(f"        {f}")

    if ERRORS:
        print("\n⚠️  掃描失敗（以下範圍未稽查，結果不完整）：")
        for e in ERRORS:
            print(f"  - {e}")

    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
