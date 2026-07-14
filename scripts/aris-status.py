#!/usr/bin/env python3
"""
aris-status — 一頁式 Aris 狀態儀表（讀 status.json + tail 三審計檔）。

用法:
    python3 scripts/aris-status.py          # 印當前狀態
    python3 scripts/aris-status.py --json    # 原始 JSON
    watch -n5 python3 scripts/aris-status.py # 每 5 秒刷新
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "status.json"


def _tail(path: Path, n: int = 3) -> list:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def main():
    if not STATUS.exists():
        print("status.json 不存在 — API 沒在跑，或 NEURALIS_STATUS=off")
        return
    data = json.loads(STATUS.read_text(encoding="utf-8"))

    if "--json" in sys.argv:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    age = time.time() - data.get("ts", 0)
    fresh = "🟢" if age < 90 else "🔴 (stale)"
    print(f"═══ Aris 狀態 @ {data.get('iso', '?')} {fresh} ({age:.0f}s 前) ═══")

    psi = data.get("psi")
    if psi and "error" not in psi:
        e = psi["emotion"]
        print(f"❤️  心跳 tick={psi['tick']} | 主導需求={psi['dominant_need']} "
              f"(drive={psi['dominant_drive']}) | 注意力={psi['attention']}")
        print(f"    情緒 valence={e['valence']:+.2f} arousal={e['arousal']:.2f} | "
              f"最近輸入: {psi['last_input'] or '(無)'}")

    ag = data.get("agency")
    if ag:
        print(f"🔄 自主行動 累計={ag['actions_total']} (跳過空轉={ag.get('skipped_stale', 0)}) | "
              f"近一小時={ag['actions_last_hour']}/{ag['max_per_hour']} | 閾值={ag['drive_threshold']}")

    co = data.get("consolidation")
    if co:
        sleep = "😴 睡眠中" if co["asleep"] else f"👁 清醒 (閒置 {co['seconds_since_interaction']:.0f}s)"
        print(f"🧹 固化 passes={co['passes_total']} | {sleep}")

    mem = data.get("memory", {})
    if "laap_layers" in mem:
        L = mem["laap_layers"]
        print(f"🧠 記憶 全腦={mem['gbrain_total']} | laap: "
              f"episodic={L['episodic']} core={L['core']} archive={L['archive']}")

    # 最近自主行動 + 固化
    acts = _tail(ROOT / "agency-audit.jsonl", 3)
    if acts:
        print("── 最近自主行動 ──")
        for a in acts:
            print(f"   [{a.get('need')}] {a.get('tool')}({str(a.get('prompt'))[:32]}) "
                  f"ok={a.get('ok')}")
    denies = _tail(ROOT / "safety-audit.jsonl", 2)
    if denies:
        print("── 最近安全閘 DENY ──")
        for d in denies:
            print(f"   {d.get('tool')}: {str(d.get('denied'))[:50]}")


if __name__ == "__main__":
    main()
