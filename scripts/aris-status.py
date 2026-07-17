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
        af = psi.get("affective")
        if af:
            b = af.get("biases", {})
            print(f"    5維 mood={af['mood']} | 偏差 risk={b.get('risk_seeking', 0):+.2f} "
                  f"narrow={b.get('attention_narrowing', 0):+.2f} "
                  f"creat={b.get('creativity', 0):+.2f} | 事件={af.get('events_total', 0)}")

    ag = data.get("agency")
    if ag:
        eff = ag.get('effective_interval_s', ag['interval_s'])
        trust = ag.get('trust', {})
        trust_str = f"信任={trust.get('user', 0):.2f}" if trust else ""
        rpe = f"RPE avg={ag.get('rpe_avg', 0):+.4f} exp={ag.get('exploration_rate', 0.15):.2f}" if ag.get('rpe_count', 0) else ""
        print(f"🔄 自主行動 累計={ag['actions_total']} (跳過空轉={ag.get('skipped_stale', 0)}) | "
              f"近一小時={ag['actions_last_hour']}/{ag['max_per_hour']} | 閾值={ag['drive_threshold']}"
              f" | interval={eff}s"
              + (f" | {trust_str}" if trust_str else "")
              + (f" | {rpe}" if rpe else ""))
        agentos_tools = ag.get('agentos_tools_used', [])
        if agentos_tools:
            print(f"    AgentOS 工具: {', '.join(agentos_tools)}")
        pending = ag.get('pending_approvals', 0)
        if pending:
            print(f"    待批工具: {pending}")

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
            rpe = f"rpe={a.get('rpe', 0):+.3f}" if "rpe" in a else ""
            print(f"   [{a.get('need')}] {a.get('tool')}({str(a.get('prompt'))[:32]}) "
                  f"ok={a.get('ok')}" + (f" {rpe}" if rpe else ""))
    denies = _tail(ROOT / "safety-audit.jsonl", 2)
    if denies:
        print("── 最近安全閘 DENY ──")
        for d in denies:
            print(f"   {d.get('tool')}: {str(d.get('denied'))[:50]}")

    # watchdog：崩過幾次是運維第一時間要看的
    wd = _tail(ROOT / "watchdog-audit.jsonl", 200)
    restarts = [e for e in wd if e.get("event") in ("restart_ok", "restart_failed")]
    if restarts:
        last = restarts[-1]
        ago = (time.time() - last.get("ts", 0)) / 60
        loop = " 🚨 CRASH-LOOP 已停手" if any(e.get("event") == "crashloop" for e in wd[-5:]) else ""
        print(f"🛡️  watchdog 重啟 {len(restarts)} 次 | 最近: {last['event']} "
              f"({ago:.0f} 分鐘前){loop}")


if __name__ == "__main__":
    main()
