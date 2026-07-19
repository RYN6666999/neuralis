#!/usr/bin/env python3
"""scream-timeout tool timeout 補丁（npm update 後需要重跑）。

問題：DEFAULT_TIMEOUT_S=60s 太短，複雜操作（grep 大檔、curl 慢 API）常被掐掉。

修法：提高到 120s，減少 Connect timeout。
"""
import shutil
import subprocess
import sys
from pathlib import Path

DIST = Path("/opt/homebrew/lib/node_modules/scream-code/dist")
MARK = "scream-timeout v1"
OLD = "const DEFAULT_TIMEOUT_S = 60;"
NEW = "const DEFAULT_TIMEOUT_S = 120;  /* scream-timeout v1 */"


def main() -> int:
    targets = sorted(DIST.glob("app-*.mjs"))
    if not targets:
        print(f"❌ {DIST} 找不到 app-*.mjs")
        return 1
    target = targets[0]
    backup = Path(str(target) + ".timeout-bak")
    content = target.read_text("utf-8")

    if MARK in content:
        print("✅ 已是 scream-timeout v1 補丁，跳過")
        return 0
    if OLD not in content:
        print("⚠️ 找不到 DEFAULT_TIMEOUT_S=60 錨點 — scream 改版了，人工對齊")
        return 1

    if not backup.exists():
        shutil.copy2(target, backup)

    target.write_text(content.replace(OLD, NEW, 1), "utf-8")

    check = subprocess.run(["node", "--check", str(target)],
                           capture_output=True, text=True)
    if check.returncode != 0:
        shutil.copy2(backup, target)
        print(f"❌ node --check 失敗，已還原備份:\n{check.stderr[:400]}")
        return 1
    print(f"✅ scream-timeout v1 補丁已套用（60s → 120s）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
