#!/usr/bin/env python3
"""Stabilize Scream footer status line to reduce viewport jitter.

Rewrites buildStatusLine in dist/app-*.mjs to remove animated spinner + elapsed
time churn. This keeps footer text width and content stable while streaming.

Safe behavior:
- keep one backup (*.stable-footer-bak)
- validate with node --check
- auto-restore backup on syntax error
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path


DIST = Path("/opt/homebrew/lib/node_modules/scream-code/dist")
MARK = "stable-footer v1"


def _rewrite(content: str) -> tuple[str, bool]:
    pattern = re.compile(
        r"function buildStatusLine\(streamingPhase, streamingStartTime\) \{.*?\n\}\nfunction formatFooterGitBadge",
        re.DOTALL,
    )
    replacement = (
        "function buildStatusLine(streamingPhase, streamingStartTime) {\n"
        "        // stable-footer v1: fixed-width, non-animated footer status\n"
        "        if (streamingPhase === \"idle\") return t(\"status.idle\");\n"
        "        if (streamingPhase === \"tool\") return t(\"status.tool\");\n"
        "        if (streamingPhase === \"waiting\") return t(\"status.waiting\");\n"
        "        if (streamingPhase === \"thinking\") return t(\"status.thinking\");\n"
        "        if (streamingPhase === \"composing\") return t(\"status.composing\");\n"
        "        return \"\";\n"
        "}\n"
        "function formatFooterGitBadge"
    )
    out, n = pattern.subn(replacement, content, count=1)
    return out, n == 1


def main() -> int:
    targets = sorted(DIST.glob("app-*.mjs"))
    if not targets:
        print(f"❌ {DIST} 找不到 app-*.mjs")
        return 1

    target = targets[0]
    backup = Path(str(target) + ".stable-footer-bak")
    content = target.read_text("utf-8")

    if MARK in content:
        print("✅ stable-footer v1 已套用，跳過")
        return 0

    patched, ok = _rewrite(content)
    if not ok:
        print("⚠️ 找不到 buildStatusLine 區塊，scream 版本可能變更，需人工對齊")
        return 1

    if not backup.exists():
        shutil.copy2(target, backup)

    target.write_text(patched, "utf-8")

    check = subprocess.run(["node", "--check", str(target)], capture_output=True, text=True)
    if check.returncode != 0:
        shutil.copy2(backup, target)
        print(f"❌ node --check 失敗，已還原備份:\n{check.stderr[:400]}")
        return 1

    print(f"✅ stable footer 已套用（{target.name}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
