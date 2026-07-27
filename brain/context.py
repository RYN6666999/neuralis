#!/usr/bin/env python3
"""context.py — 把散在八個地方的真相，合成一份 AI 冷啟動簡報。

問題：知識散在 topology.yaml / causal.yaml / status.json / 留言板 / Obsidian…
      每個 AI 都要自己拼，拼錯就產生幻覺。

解法：一個入口，全部合成。但——

  ⚠️ 產出的 CONTEXT.md 是「衍生品」不是「真相」。
     手改它 = 白改，下次重跑就沒了。要改請改上游來源。

這個設計是刻意的：本專案有 _現況.md 說謊的前科（宣稱 relay 雙寫，
實查該 commit 不存在）。唯一的解法就是讓「人看的文件」永遠是生成的，
沒有人能手動在裡面塞一句假話而不被下次重跑洗掉。

用法：
    context.py                    # 印到 stdout
    context.py -o brain/CONTEXT.md
    context.py --live             # 加跑 drift.py + 探服務（慢，但是真的）
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("需要 pyyaml：pip install pyyaml")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BOARD = (Path.home() / "Library/Mobile Documents/iCloud~md~obsidian"
         / "Documents/Fun/Aris/留言板.md")
PORTS = {11546: "Aris API", 11550: "relay", 11551: "aris-memory"}


def _load(p: Path):
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _ping(port: int) -> str:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as r:
            return "🟢" if r.status == 200 else f"🟡 {r.status}"
    except Exception:
        return "🔴"


def build(live: bool = False) -> str:
    causal = _load(HERE / "causal.yaml") or {}
    topo = _load(ROOT / "topology.yaml") or {}
    L: list[str] = []
    add = L.append

    add("<!-- 本檔由 brain/context.py 生成。勿手改 —— 下次重跑就沒了。 -->")
    add("<!-- 要改請改上游：topology.yaml / brain/causal.yaml -->")
    add("")
    add("# NEURALIS — AI 冷啟動簡報")
    add("")
    add(f"生成於 {datetime.now(timezone.utc).astimezone():%Y-%m-%d %H:%M %Z}"
        f"　·　模式：{'live 實測' if live else 'static 靜態'}")
    add("")
    add("## 先讀這三條")
    add("")
    add("1. **文件會說謊，probe 不會。** 前科：`_現況.md` 宣稱 relay 雙寫"
        "（commit `3b966ae`），實查該 hash 不在 repo。"
        "要知道現在通不通 → 跑 `scripts/probe.py`，別讀文件。")
    add("2. **`laap/**` 是 path-DENY 紅線**，任何 agent 不得寫入。")
    add("3. **Aris = 大腦，Scream = 身體。** 2026-07-25 定版，別再重新討論。")
    add("")
    add("## 系統一句話")
    add("")
    add("```")
    add("LB-arcanum(記憶) → neuralis(大腦/Aris) ⇄ scream(身體)")
    add("                          ⇅")
    add("                   agentOS(38 工具)")
    add("```")
    add("")

    # 樞紐
    add("## 五個樞紐節點")
    add("")
    add("| id | 角色 | repo | 自有 |")
    add("|---|---|---|---|")
    for h in causal.get("hubs") or []:
        own = "✅" if h.get("owned") else "⚠️ **上游**"
        add(f"| `{h['id']}` | {h.get('role','')} | `{h.get('repo') or '?'}` | {own} |")
    add("")
    add("> ⚠️ `scream` 與 `laap-upstream` **不是 Ryan 的**。"
        "他們一改可能靜默弄壞系統 → 用 `brain/drift.py` 監測。")
    add("")

    # 執行期
    if live:
        add("## 執行期（實測）")
        add("")
        for port, name in PORTS.items():
            add(f"- {_ping(port)} `:{port}` {name}")
        add("")
        try:
            r = subprocess.run([sys.executable, str(HERE / "drift.py"), "--json"],
                               capture_output=True, text=True, timeout=40)
            for d in json.loads(r.stdout):
                mark = {"ok": "🟢", "drift": "🟡", "stale": "🔴"}.get(d["status"], "⚪")
                add(f"- {mark} **{d['label']}** — {d['detail']}")
        except Exception as e:
            add(f"- ⚪ drift 查詢失敗：{e}")
        add("")

    # 槓桿
    add("## 最高槓桿（blast.py 算的，非人工排序）")
    add("")
    try:
        r = subprocess.run([sys.executable, str(HERE / "blast.py"), "--json"],
                           capture_output=True, text=True, timeout=20)
        nodes = json.loads(r.stdout)["nodes"]

        def down(nid, seen=None):
            seen = seen or {nid}
            n = 0
            for t in nodes.get(nid, {}).get("blocks") or []:
                if t not in seen:
                    seen.add(t)
                    n += 1 + down(t, seen)
            return n

        rank = sorted(((down(k), k) for k, v in nodes.items()
                       if v.get("status") in ("not_started", "partial", "sealed")),
                      reverse=True)
        for i, (cnt, nid) in enumerate([x for x in rank if x[0]][:5], 1):
            n = nodes[nid]
            m = {"partial": "🟡", "not_started": "🔴", "sealed": "🔒"}.get(n.get("status"), "·")
            fire = " 🔥" if i == 1 else ""
            add(f"{i}. {m} **`{nid}`** — {n.get('label','')} → 解鎖 {cnt} 個下游{fire}")
        add("")
        add("**要動手就從第 1 名開始，投報率最高。**")
    except Exception as e:
        add(f"（blast 查詢失敗：{e}）")
    add("")

    # 風險
    add("## 風險")
    add("")
    add("| | 風險 | 說明 |")
    add("|---|---|---|")
    for r_ in causal.get("risks") or []:
        s = {"high": "🔴", "medium": "🟡", "low": "🔵"}.get(r_.get("severity"), "·")
        add(f"| {s} | `{r_['id']}` | {str(r_.get('what','')).strip()} |")
    add("")

    # 封印
    add("## 封印中（能開但刻意沒開）")
    add("")
    for s in causal.get("sealed") or []:
        add(f"- 🔒 **{s.get('label', s['id'])}** — {str(s.get('why','')).strip()[:90]}")
    add("")

    # topology
    add("## 執行期拓樸（topology.yaml）")
    add("")
    edges = topo.get("edges") or []
    fails = [e for e in edges if e.get("expect") == "fail"]
    add(f"{len(topo.get('nodes') or [])} 節點 · {len(edges)} 條邊"
        f"（{len(fails)} 條 `expect: fail`）")
    add("")
    if fails:
        add("已知紅（預期內，不是新 bug）：")
        for e in fails:
            add(f"- `{e['id']}`：{str(e.get('contract',''))[:70]}")
    add("")
    add("**驗證：`python3 scripts/probe.py`** —— 這才是唯一可信的現況。")
    add("")

    # 留言板
    if BOARD.exists():
        add("## 留言板")
        add("")
        try:
            n = len(BOARD.read_text(encoding="utf-8").splitlines())
            add(f"`Aris/留言板.md` · {n} 行 · "
                f"最後更新 {datetime.fromtimestamp(BOARD.stat().st_mtime):%Y-%m-%d %H:%M}")
            add("")
            add("跨 session 永久通訊頻道。開工前先讀最新幾則。")
        except Exception:
            pass
        add("")

    add("## 工具")
    add("")
    add("```bash")
    add("./brain/blast.py              # 因果總覽 + 槓桿排行")
    add("./brain/blast.py <id>         # 動它會炸到誰")
    add("./brain/blast.py <id> --why   # 它被誰卡住")
    add("./brain/drift.py              # 上游漂移偵測")
    add("./brain/context.py --live -o brain/CONTEXT.md   # 重新生成本檔")
    add("python3 scripts/probe.py      # 執行期真實現況")
    add("```")
    add("")
    add("---")
    add("*生成物。改上游來源，不要改這裡。*")
    return "\n".join(L)


def main() -> int:
    args = sys.argv[1:]
    out = build(live="--live" in args)
    if "-o" in args:
        p = Path(args[args.index("-o") + 1])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(out + "\n", encoding="utf-8")
        print(f"✅ 已寫入 {p}（{len(out.splitlines())} 行）")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
