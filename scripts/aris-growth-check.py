#!/usr/bin/env python3
"""aris-growth-check.py — 成長路徑檢查。

三項指標：
1. PSI 引擎活著（/health 回 engines_loaded=true）
2. 記憶持續累積（aris-memory DB 筆數）
3. Probe 無非預期紅（最近一次 probe.py run 的結果）
"""
import json, os, sqlite3, subprocess, sys, urllib.request
from pathlib import Path

def check():
    results = []
    
    # 1. PSI health
    try:
        r = urllib.request.urlopen("http://localhost:11546/health", timeout=5)
        data = json.loads(r.read())
        ok = data.get("engines_loaded") == True
        results.append((ok, f"PSI health: engines_loaded={'✅' if ok else '❌'}"))
    except Exception as e:
        results.append((False, f"PSI health: ❌ {e}"))
    
    # 2. Memory count
    mem_db = Path(os.environ.get("ARIS_MEMORY_DB", str(Path.home() / ".aris-memory.db")))
    if mem_db.exists():
        try:
            conn = sqlite3.connect(f"file:{mem_db}?mode=ro", uri=True)
            count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            conn.close()
            results.append((True, f"記憶筆數: {count}"))
        except Exception as e:
            results.append((False, f"記憶讀取失敗: {e}"))
    else:
        results.append((False, f"記憶 DB 不存在: {mem_db}"))
    
    # 3. Check probe health — 只盯跟成長有關的核心邊
    _GROWTH_PROBES = [
        "rust_b1_read",     # Rust 引擎活著
        "rust_b2_write",    # 事件通道通著
        "relay_remembers_turn",  # 對話連續性
        "recall_not_selfinflated",  # 記憶誠實性
        "wake_reads_three", # 醒來三源合一
        "psi_evaluator_state", # PSI 狀態可讀
    ]
    try:
        r = subprocess.run(
            [sys.executable, "-c", f"""
import sys; sys.path.insert(0, 'scripts')
from probe import PROBES
probes = {_GROWTH_PROBES!r}
for k in probes:
    ok, msg = PROBES[k]()
    if not ok:
        print(f'FAIL {{k}}: {{msg}}')
        sys.exit(1)
print(f'OK: {{len(probes)}} growth probes green')
"""], capture_output=True, text=True, timeout=30, cwd=str(Path.home() / "Developer/neuralis"))
        ok = r.returncode == 0
        detail = r.stdout.strip().splitlines()[-1] if r.stdout else r.stderr[:80]
        results.append((ok, f"成長 probe: {'✅' if ok else '❌'} {detail}"))
    except Exception as e:
        results.append((False, f"Probe 執行失敗: {e}"))
    
    # Summary
    passed = sum(1 for ok, _ in results if ok)
    total = len(results)
    print(f"\n成長路徑檢查 ({passed}/{total} 通過):")
    for ok, msg in results:
        print(f"  {'✅' if ok else '❌'} {msg}")
    
    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(check())