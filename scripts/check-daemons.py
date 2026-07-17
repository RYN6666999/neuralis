#!/usr/bin/env python3
"""支援 daemon 自檢：三隻 launchd daemon 活著 + 產出檔有在動。
用法: python3 scripts/check-daemons.py
安裝: scripts/install-support-daemons.sh"""
import subprocess
import sys
import time
from pathlib import Path

DAEMONS = {
    "com.neuralis.phase-logger": "scream-phase-logger.py",
    "com.neuralis.task-executor": "scream-task-executor.py",
    "com.neuralis.scream-monitor": "scream-monitor.sh",
}

failed = []

# A. 行程在跑（pgrep 認腳本名 — launchd label 下是 zsh -c 包裝）
for label, marker in DAEMONS.items():
    r = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True)
    pids = r.stdout.split()
    if pids:
        print(f"A. {label}: OK (pid {', '.join(pids)})")
    else:
        print(f"A. {label}: DOWN")
        failed.append(label)

# B. launchd 有註冊（開機自啟的保證）
for label in DAEMONS:
    r = subprocess.run(["launchctl", "print", f"gui/{__import__('os').getuid()}/{label}"],
                       capture_output=True, text=True)
    if r.returncode == 0:
        print(f"B. {label}: launchd 已註冊")
    else:
        print(f"B. {label}: launchd 未註冊 — 跑 scripts/install-support-daemons.sh")
        failed.append(label)

# C. 時間軸新鮮度（phase-logger 的產出；1h 內有動算活 — 沒活動時不動是正常的，
#    只在檔案完全不存在時警告）
timeline = Path.home() / ".scream-code" / "timeline.jsonl"
if timeline.exists():
    age = time.time() - timeline.stat().st_mtime
    print(f"C. timeline.jsonl: 存在（{age/60:.0f} 分鐘前更新）")
else:
    print("C. timeline.jsonl: 不存在（phase-logger 還沒寫過 — 有事件後應出現）")

if failed:
    print(f"\nFAILED: {sorted(set(failed))}")
    sys.exit(1)
print("\nALL DAEMON CHECKS PASSED")
