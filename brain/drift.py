#!/usr/bin/env python3
"""drift.py — 上游漂移偵測：不是我的東西，動了沒？

neuralis 依賴兩個「不是 Ryan 的」上游：
  - LIUTod/scream-code        身體（CLI + 工具）
  - lorryjovens-hub/laap-AGI  laap-core / PSI 引擎

他們一 push，這裡可能靜默壞掉。topology.yaml 的 probe 測「邊通不通」，
測不出「上游偷偷往前跑了」——因為當下還是通的，壞的是未來。

這支就是那個「往外看」的眼睛。純唯讀、純網路查詢，不改任何東西。

用法：
    drift.py            # 人看
    drift.py --json     # 機器讀
    drift.py --quiet    # 只有漂移時才輸出（給 cron）

exit 1 = 有漂移。exit 2 = 查不到（網路/API 問題，不算漂移）。
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

TIMEOUT = 10

CHECKS = [
    {
        "id": "scream",
        "label": "Scream（身體）",
        "kind": "npm",
        "pkg": "scream-code",
        "installed_at": "/opt/homebrew/lib/node_modules/scream-code/package.json",
        "repo": "LIUTod/scream-code",
        "owner": "LIUTod（不是你）",
        "note": "npm 全域安裝，非原始碼。~/Developer/neuralis/scream-code/ 只是 mcp.json 設定。",
    },
    {
        "id": "laap",
        "label": "laap-AGI（PSI 引擎源頭）",
        "kind": "git",
        "local": Path.home() / "Developer/laap-AGI",
        "repo": "lorryjovens-hub/laap-AGI",
        "branch": "main",
        "owner": "lorryjovens-hub（不是你）",
    },
]


def _get(url: str):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "neuralis-drift"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.load(r)
    except Exception as e:
        return {"_error": str(e)}


def _vtuple(v: str):
    try:
        return tuple(int(x) for x in v.strip().lstrip("v").split(".")[:3])
    except Exception:
        return (0,)


def check_npm(c: dict) -> dict:
    out = {"id": c["id"], "label": c["label"], "repo": c["repo"], "owner": c["owner"]}
    p = Path(c["installed_at"])
    if not p.exists():
        return {**out, "status": "unknown", "detail": f"找不到 {p}"}
    try:
        local = json.loads(p.read_text()).get("version", "?")
    except Exception as e:
        return {**out, "status": "unknown", "detail": str(e)}

    reg = _get(f"https://registry.npmjs.org/{c['pkg']}")
    if "_error" in reg:
        return {**out, "local": local, "status": "unknown", "detail": reg["_error"]}

    latest = reg.get("dist-tags", {}).get("latest", "?")
    versions = sorted(reg.get("versions", {}), key=_vtuple)
    behind = 0
    if local in versions and latest in versions:
        behind = versions.index(latest) - versions.index(local)

    out.update({"local": local, "latest": latest, "behind": behind,
                "note": c.get("note")})
    out["status"] = "ok" if behind <= 0 else ("drift" if behind < 5 else "stale")
    out["detail"] = f"本地 {local} · 最新 {latest} · 落後 {behind} 版"
    return out


def _remote_gone(repo: str) -> bool:
    """遠端 repo 是否已不存在（404）。改名 / 轉私有 / 刪除都會是 404。

    2026-08-20：`lorryjovens-hub/laap-AGI` 就是這樣消失的，而本檔當時把它印成
    「✅ 全部同步」exit 0 —— 偵測器在它存在的全部理由所對應的最壞情況下印綠燈。
    """
    r = _get(f"https://api.github.com/repos/{repo}")
    return "_error" in r and "404" in str(r["_error"])


def check_git(c: dict) -> dict:
    out = {"id": c["id"], "label": c["label"], "repo": c["repo"], "owner": c["owner"]}
    local_dir = Path(c["local"])
    if not (local_dir / ".git").exists():
        # 本地沒 checkout **不代表**不用查遠端。舊版在這裡就早退，
        # 所以在 CI／新機器上永遠不會發現上游整個消失了。
        if _remote_gone(c["repo"]):
            return {**out, "status": "gone",
                    "detail": f"上游 repo 不存在（404）—— 改名、轉私有或已刪除。"
                              f"本地也沒有 {local_dir}，沒有任何可重現的基準"}
        return {**out, "status": "unknown", "detail": f"{local_dir} 不是 git repo"}

    def git(*a):
        r = subprocess.run(["git", "-C", str(local_dir), *a],
                           capture_output=True, text=True, timeout=TIMEOUT)
        return r.stdout.strip() if r.returncode == 0 else ""

    sha = git("rev-parse", "HEAD")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    dirty = bool(git("status", "--porcelain"))

    up = _get(f"https://api.github.com/repos/{c['repo']}/commits/{c['branch']}")
    if "_error" in up:
        # 404 = 東西不見了（要叫）；其他錯誤 = 網路／限流（不該假紅）。
        # 這兩件事的正確行動完全不同，不能共用一個 status。
        if "404" in str(up["_error"]) and _remote_gone(c["repo"]):
            return {**out, "local_sha": sha[:7], "branch": branch, "status": "gone",
                    "detail": f"上游 repo 不存在（404）—— 改名、轉私有或已刪除。"
                              f"本地 {branch}@{sha[:7]} 成了唯一的來源"}
        return {**out, "local_sha": sha[:7], "branch": branch,
                "status": "unknown", "detail": up["_error"]}

    up_sha = up.get("sha", "")
    up_date = (up.get("commit", {}).get("committer", {}) or {}).get("date", "?")
    same = sha == up_sha

    out.update({"local_sha": sha[:7], "upstream_sha": up_sha[:7],
                "branch": branch, "upstream_branch": c["branch"],
                "upstream_date": up_date, "dirty": dirty})
    if same:
        out["status"] = "ok"
        out["detail"] = f"與 upstream/{c['branch']} 同步"
    else:
        out["status"] = "drift"
        out["detail"] = (f"本地 {branch}@{sha[:7]} ≠ "
                         f"upstream/{c['branch']}@{up_sha[:7]}（{up_date[:10]}）")
        if branch != c["branch"]:
            out["detail"] += f" · 且不在 {c['branch']} 分支"
    return out


MARK = {"ok": "🟢", "drift": "🟡", "stale": "🔴", "gone": "💀", "unknown": "⚪"}
# 會讓 exit != 0 的狀態。`gone` 必須在裡面 —— 上游整個消失是最壞情況，
# 偵測器在最壞情況下不出聲就沒有存在意義。`unknown` 刻意不在裡面：
# 那涵蓋離線與 API 限流，算失敗會製造假紅，而 guard.yml 已經寫過
# 「假紅比沒有更糟 —— 人會學會無視紅燈」。
FAIL_STATUS = ("drift", "stale", "gone")


def main() -> int:
    args = sys.argv[1:]
    results = [check_npm(c) if c["kind"] == "npm" else check_git(c) for c in CHECKS]

    if "--json" in args:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        drifted = [r for r in results if r["status"] in FAIL_STATUS]
        if "--quiet" in args and not drifted:
            return 0
        print("\n" + "=" * 56)
        print("  上游漂移偵測 — 不是你的東西，動了沒？")
        print("=" * 56)
        for r in results:
            print(f"\n{MARK[r['status']]} {r['label']}")
            print(f"   {r['repo']}  [{r['owner']}]")
            print(f"   {r['detail']}")
            if r.get("dirty"):
                print("   ⚠️  本地有未提交變更")
            if r.get("note"):
                print(f"   💬 {r['note']}")
        gone = [r for r in results if r["status"] == "gone"]
        if gone:
            print(f"\n💀 {len(gone)} 個上游已不存在（404）。")
            print("   這不是漂移，是基準消失：你沒有可重現的上游可以疊。")
            for r in gone:
                print(f"   · {r['repo']} —— README / ROADMAP / topology.yaml 的宣稱都指向這裡")
        if drifted and not gone:
            print(f"\n⚠️  {len(drifted)} 個上游已漂移。")
            print("   漂移不等於壞掉，但代表：上游修過的 bug 你沒拿到，")
            print("   而且你們的行為差異會越拉越大。")
        elif not drifted:
            unknown = [r for r in results if r["status"] == "unknown"]
            if unknown:
                print(f"\n⚪ {len(unknown)} 個查不到（離線／限流／本地無 checkout）—— 不是綠燈，是沒驗到。")
            else:
                print("\n✅ 全部同步")
        print()

    # 三態 exit（docstring 第 18 行本來就這樣承諾，但實作一直只有 0/1）：
    #   1 = 有漂移／上游消失 —— 要行動
    #   2 = 查不到（離線／限流／本地無 checkout）—— **不是綠燈，也不是失敗**
    #   0 = 真的驗過且同步
    # 為什麼 unknown 需要自己的 code 而不是併進 1：併進去就是假紅，而
    # guard.yml 寫過「假紅比沒有更糟 —— 人會學會無視紅燈」。但併進 0 是
    # 把「沒驗到」講成「沒問題」，自動化讀不出差別。所以要第三個值。
    # CI 建議：exit 2 當 warning（不擋 pipeline），exit 1 當 failure。
    if any(r["status"] in FAIL_STATUS for r in results):
        return 1
    return 2 if any(r["status"] == "unknown" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
