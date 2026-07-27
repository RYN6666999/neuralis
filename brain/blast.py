#!/usr/bin/env python3
"""blast.py — 影響半徑查詢：動一個東西，會炸到誰。

topology.yaml 回答「現在通不通」（probe.py 跑）。
這支回答「我改這個，誰會跟著動」（靜態走圖）。

沒有魔法：讀 causal.yaml，沿 blocks 邊做 BFS，照深度印出來。
沒有狀態、沒有 DB、沒有網路。跑壞了重跑，不會弄丟任何東西。

用法：
    blast.py                 # 全域總覽 + 槓桿排行
    blast.py <id>            # 動這個會炸到誰（下游）
    blast.py <id> --why      # 這個被誰卡住（上游）
    blast.py --risks         # 只列風險
    blast.py --json          # 機器讀

exit 1 = 查無此 id。
"""
from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("需要 pyyaml：pip install pyyaml")

CAUSAL = Path(__file__).resolve().parent / "causal.yaml"

MARK = {
    "done": "✅",
    "partial": "🟡",
    "not_started": "🔴",
    "sealed": "🔒",
}
SEV = {"high": "🔴", "medium": "🟡", "low": "🔵"}


def load() -> dict:
    if not CAUSAL.exists():
        sys.exit(f"找不到 {CAUSAL}")
    with CAUSAL.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def index(data: dict) -> dict:
    """把 blockers + sealed 併成一張表，並補出反向邊。

    causal.yaml 只要求寫 blocks 或 blocked_by 其中一邊（人比較好寫），
    這裡自動補齊另一邊，之後走圖就不用管方向了。
    """
    nodes: dict[str, dict] = {}
    for b in data.get("blockers") or []:
        nodes[b["id"]] = {**b, "kind": "blocker"}
    for s in data.get("sealed") or []:
        nodes[s["id"]] = {
            **s,
            "kind": "sealed",
            "status": "sealed",
            "blocks": s.get("blocks_unseal_of", []),
        }

    # 補反向邊
    for nid, n in nodes.items():
        for tgt in n.get("blocks") or []:
            if tgt in nodes:
                nodes[tgt].setdefault("blocked_by", [])
                if nid not in nodes[tgt]["blocked_by"]:
                    nodes[tgt]["blocked_by"].append(nid)
        for src in n.get("blocked_by") or []:
            if src in nodes:
                nodes[src].setdefault("blocks", [])
                if nid not in nodes[src]["blocks"]:
                    nodes[src]["blocks"].append(nid)
    return nodes


def bfs(nodes: dict, start: str, edge: str) -> list[tuple[str, int]]:
    """沿 edge 方向走，回傳 [(id, 幾跳), ...]。走過的不重複走。"""
    if start not in nodes:
        return []
    seen = {start}
    out: list[tuple[str, int]] = []
    q = deque([(start, 0)])
    while q:
        cur, d = q.popleft()
        for nxt in nodes[cur].get(edge) or []:
            if nxt in seen or nxt not in nodes:
                continue
            seen.add(nxt)
            out.append((nxt, d + 1))
            q.append((nxt, d + 1))
    return out


def show(nodes: dict, nid: str, upstream: bool = False) -> int:
    if nid not in nodes:
        print(f"❌ 查無 '{nid}'\n\n可用 id：")
        for k in sorted(nodes):
            print(f"   {k}")
        return 1

    n = nodes[nid]
    edge = "blocked_by" if upstream else "blocks"
    verb = "被這些卡住" if upstream else "動了會炸到"

    print(f"\n{MARK.get(n.get('status'), '·')} {nid} — {n.get('label', '')}")
    if n.get("kind") == "sealed":
        print(f"   封印原因：{n.get('why', '')}")
        if n.get("hard_blocker"):
            print(f"   ⛔ 硬阻塞：{n['hard_blocker']}")
        if n.get("unseal_risk"):
            print(f"   ⚠️  解封風險：{n['unseal_risk']}（成本 {n.get('unseal_cost', '?')}）")
        if n.get("gate_required"):
            print(f"   需先過閘：{', '.join(n['gate_required'])}")
    else:
        if n.get("done"):
            print(f"   已完成：{', '.join(map(str, n['done']))}")
        if n.get("missing"):
            print(f"   缺：{', '.join(map(str, n['missing']))}")
    if n.get("src"):
        print(f"   出處：{n['src']}")

    hits = bfs(nodes, nid, edge)
    print(f"\n   {verb}：", end="")
    if not hits:
        print("（無）\n")
        return 0
    print()
    for tgt, depth in sorted(hits, key=lambda x: (x[1], x[0])):
        t = nodes[tgt]
        hop = "直接" if depth == 1 else f"{depth} 跳"
        print(f"     {'  ' * (depth - 1)}→ {MARK.get(t.get('status'), '·')} {tgt} ({hop})")

    direct = sum(1 for _, d in hits if d == 1)
    print(f"\n   共 {len(hits)} 個（直接 {direct}）")
    if not upstream and len(hits) >= 3:
        print("   🔥 高槓桿：解開這個能連帶鬆開多個下游")
    if n.get("note"):
        print(f"   💬 {n['note']}")
    print()
    return 0


def overview(data: dict, nodes: dict) -> None:
    print("\n" + "=" * 58)
    print("  NEURALIS 腦域 — 因果總覽")
    print(f"  causal.yaml v{data.get('version')} · {data.get('updated')}")
    print("=" * 58)

    print("\n【樞紐節點】粗神經節，動它們全身震")
    for h in data.get("hubs") or []:
        own = "自有" if h.get("owned") else "⚠️ 上游（不是你的）"
        print(f"  ● {h['id']:<14} {h.get('role', '')}")
        print(f"    {h.get('repo') or '(repo 待確認)'}  [{own}]")
        if h.get("risk"):
            print(f"    ⚠️  {h['risk']}")

    print("\n【槓桿排行】解開一個，連帶鬆開幾個")
    rank = []
    for nid in nodes:
        if nodes[nid].get("status") in ("not_started", "partial", "sealed"):
            n_down = len(bfs(nodes, nid, "blocks"))
            if n_down:
                rank.append((n_down, nid))
    for i, (cnt, nid) in enumerate(sorted(rank, reverse=True), 1):
        n = nodes[nid]
        flag = " 🔥" if i == 1 else ""
        print(f"  {i}. {MARK.get(n.get('status'), '·')} {nid:<18} 解鎖 {cnt} 個下游{flag}")

    print("\n【風險】探測不到但會咬人")
    for r in data.get("risks") or []:
        print(f"  {SEV.get(r.get('severity'), '·')} {r['id']}：{r.get('what', '')}")
        if r.get("fix"):
            print(f"     修法：{r['fix']}")

    print("\n" + "-" * 58)
    print("  ./brain/blast.py <id>        看動它會炸到誰")
    print("  ./brain/blast.py <id> --why  看它被誰卡住")
    print("-" * 58 + "\n")


def main() -> int:
    data = load()
    nodes = index(data)
    args = sys.argv[1:]

    if "--json" in args:
        print(json.dumps({"nodes": nodes, "hubs": data.get("hubs"),
                          "risks": data.get("risks")},
                         ensure_ascii=False, indent=2))
        return 0

    if "--risks" in args:
        for r in data.get("risks") or []:
            print(f"{SEV.get(r.get('severity'), '·')} {r['id']}: {r.get('what', '')}")
        return 0

    if not args:
        overview(data, nodes)
        return 0

    return show(nodes, args[0], upstream="--why" in args)


if __name__ == "__main__":
    sys.exit(main())
