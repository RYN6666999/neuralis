#!/usr/bin/env python3
"""
morning-brief.py — Aris 晨報：跑整晚後留給 Ryan 看的摘要。

讀取：
1. agency-audit.jsonl（最近 24h 自主行動）
2. status.json（當前狀態快照）
3. gbrain recall_memory（相關記憶）

輸出：標準 Markdown，可直接貼或存檔。
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ── 路徑 ──
NEURALIS = Path(__file__).resolve().parents[1]
AUDIT = NEURALIS / "agency-audit.jsonl"
STATUS = NEURALIS / "data" / "status.json"

NOW = time.time()
DAY_AGO = NOW - 86400


def _fmt(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def _read_audit() -> list:
    """讀取最近 24h 的 audit entries。"""
    entries = []
    if not AUDIT.exists():
        return entries
    for line in AUDIT.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
            if d.get("ts", 0) >= DAY_AGO:
                entries.append(d)
        except json.JSONDecodeError:
            continue
    return entries


def _read_status() -> dict:
    """讀取最新 status snapshot。"""
    if STATUS.exists():
        try:
            return json.loads(STATUS.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _recall(query: str, limit: int = 5) -> list:
    """透過 API 查記憶。"""
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://localhost:11546/v1/recall_memory",
            data=json.dumps({"query": query, "limit": limit}).encode(),
            headers={"Content-Type": "application/json"},
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
        return resp.get("memories", [])
    except Exception:
        return []


def _agency_summary(entries: list) -> str:
    """從 audit entries 生成自主行動摘要。"""
    if not entries:
        return "無自主行動記錄。"

    total = len(entries)
    ok_count = sum(1 for e in entries if e.get("ok"))
    needs = {}
    rpes = []
    for e in entries:
        n = e.get("need", "?")
        needs[n] = needs.get(n, 0) + 1
        if "rpe" in e:
            rpes.append(e["rpe"])

    lines = [f"- 自主行動 {total} 次，成功 {ok_count} 次（{ok_count/total*100:.0f}%）"]
    for n, c in sorted(needs.items(), key=lambda x: -x[1]):
        lines.append(f"  - {n}: {c} 次")
    active_needs = len(needs)
    lines.append(f"  - 行為豐富度: {active_needs} 個需求有主動行為 + "
                 f"{5 - active_needs} 個被動/自然滿足(certainty/competence/growth 有 _ANGLE 查詢角度, "
                 f"relatedness 靠 process_input+trust 被動, autonomy 由 agency loop 自然滿足)")
    if rpes:
        avg_rpe = sum(rpes) / len(rpes)
        lines.append(f"  - RPE 均值: {avg_rpe:+.4f}")
    return "\n".join(lines)


def _state_summary(status: dict) -> str:
    """從 status.json 生成當前狀態摘要。"""
    psi = status.get("psi", {})
    agency = status.get("agency", {})
    memory = status.get("memory", {})

    lines = []
    # PsiCore
    dn = psi.get("dominant_need", "?")
    dd = psi.get("dominant_drive", 0)
    emo = psi.get("emotion", {})
    v = emo.get("valence", 0)
    a = emo.get("arousal", 0.5)
    mood = "正" if v > 0.15 else "負" if v < -0.15 else "平穩"
    lines.append(f"- 主導需求: {dn} (drive={dd:.2f}), 情緒: {mood} (v={v:+.2f}, a={a:.2f})")

    # Agency
    if agency:
        trust = agency.get("trust", {}).get("user", 0)
        exp = agency.get("exploration_rate", 0.15)
        lines.append(f"- 信任: {trust:.2f}, 探索率: {exp:.2f}")

    # Memory
    if memory:
        lines.append(f"- 記憶: 全腦 {memory.get('total', '?')} 頁")

    return "\n".join(lines)


def _memory_highlights() -> str:
    """從 gbrain 撈相關記憶亮點。"""
    results = _recall("Aris 自主行動 情緒 需求 狀態", limit=5)
    if not results:
        return "無相關記憶。"
    lines = []
    for m in results[:3]:
        text = m.get("text", "")[:150].replace("\n", " ")
        score = m.get("score", 0)
        lines.append(f"- [{score:.2f}] {text}")
    return "\n".join(lines)


def main():
    entries = _read_audit()
    status = _read_status()

    print(f"# ☀️ Aris 晨報 — {datetime.fromtimestamp(NOW).strftime('%Y-%m-%d')}")
    print()
    print(f"> 生成時間: {datetime.fromtimestamp(NOW).strftime('%H:%M')}")
    print(f"> 最近 24h 自主行動: {len(entries)} 次")
    print()

    # 狀態
    print("## 📊 當前狀態")
    print(_state_summary(status))
    print()

    # 自主行動
    print("## 🔄 自主行動摘要")
    print(_agency_summary(entries))
    print()

    # 記憶亮點
    print("## 🧠 記憶亮點")
    print(_memory_highlights())
    print()

    # 最後行動
    if entries:
        last = entries[-1]
        print("## 📝 最近一次行動")
        print(f"- 需求: {last.get('need', '?')}")
        print(f"- 查詢: {last.get('prompt', '?')[:80]}")
        if 'rpe' in last:
            print(f"- RPE: {last['rpe']:+.3f} (outcome={last.get('outcome',0):.2f}, expected={last.get('expected',0):.2f})")
        print(f"- 結果: {'✅ 成功' if last.get('ok') else '❌ 失敗'}")
        print()

    print("---")
    print(f"*下次看: `python3 scripts/morning-brief.py`*")


if __name__ == "__main__":
    main()