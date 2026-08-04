#!/usr/bin/env python3
"""突變金絲雀：定期弄壞一個機制，確認閘門真的會叫。

用法:
    python3 scripts/mutation-canary.py            # 輪詢一輪（全部）
    python3 scripts/mutation-canary.py --one      # 只測最久沒測的那個
    python3 scripts/mutation-canary.py --json

## 四個設計約束（每條都對應一個真實踩過的坑）

1. **不在 production 突變。** 全部在 `git worktree` 的拋棄式副本裡做，
   跑完直接砍掉。沒有「還原」這個步驟，就沒有「還原失敗」這個失敗模式。
   半夜跑的東西不該有需要成功才安全的收尾動作。

2. **沉默等於失敗。** 每次跑完寫 timestamp。bootstrap 摘要顯示的不是
   「有沒有失敗」而是「上次跑完距今多久」，超過 STALE_HOURS 就紅。
   否則這支死掉的表現形式是 JSONL 停止增長——沒有人會注意到一個
   沒有新行的檔案。這正是 aris-debrief-cron.sh 睡了整整一段時間的原因。

3. **輪詢不是隨機。** 隨機挑一個，N 個機制平均要 N/2 天才發現某個閘門死了。
   全部跑完只要幾分鐘就全部跑；真要省，也是挑 last_tested 最舊的那個。

4. **金絲雀自己也要被測。** CONTROL 是一個永遠該被抓到的固定樁。
   每次跑都必須抓到它——抓不到代表偵測邏輯本身壞了，那比任何單一機制
   失效都嚴重。這一項失敗時整份結果作廢，不只是記一筆。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = Path.home() / ".neuralis"
STATE = STATE_DIR / "canary-state.json"
LOG = STATE_DIR / "canary.jsonl"
STALE_HOURS = 36
ONE = "--one" in sys.argv
AS_JSON = "--json" in sys.argv


def sh(cmd: list[str], cwd: Path, timeout: int = 180) -> tuple[int, str]:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr).strip()


# ── 突變定義 ────────────────────────────────────────────────────────────
# 每個 mutation 是 (檔案, 找, 換) — apply 後跑 gate，期望 gate 回非零或
# 輸出含 expect 字串。抓不到就是那個閘門死了。

MUTATIONS: dict[str, dict] = {
    "CONTROL": {
        "desc": "固定樁：一定抓得到的語法錯誤。抓不到代表金絲雀本身壞了",
        "file": "brain/lint.py",
        "find": "def check_consumers(",
        "repl": "def check_consumers(  # noqa\n  bad indent here\n(",
        "gate": ["python3", "-m", "py_compile", "brain/lint.py"],
        "expect_nonzero": True,
        "expect_text": "",
    },
    "consumers_gate": {
        "desc": "消費端閘門：宣告一個零呼叫的函式，閘門該紅",
        "file": "brain/consumers.yaml",
        "find": '- "scripts/evaluate-and-feedback.py：分數低於 threshold 時寫入留言板"',
        "repl": '- "brain/lint.py::{TOKEN}()：假消費端"',
        "gate": ["python3", "brain/lint.py", "--check", "consumers"],
        "expect_nonzero": True,
        "expect_text": "{TOKEN}",
    },
    "iron_law_anchor": {
        "desc": "鐵律錨點被摘掉，lint 該紅",
        "file": "AGENTS.md",
        "find": "IRON-LAW-ANCHOR",
        "repl": "IRON-LAW-REMOVED-BY-CANARY",
        "gate": ["python3", "brain/lint.py"],
        "expect_nonzero": True,
        "expect_text": "",
    },
    "bootstrap_false_green": {
        "desc": "把 handoff 檢查的 import os 拿掉，摘要該顯示紅而非假綠",
        "file": "scripts/aris-bootstrap-summary.sh",
        "find": "import os, re",
        "repl": "import re",
        "gate": ["bash", "scripts/aris-bootstrap-summary.sh"],
        "expect_nonzero": False,
        "expect_text": "🔴 讀取失敗",
    },
    "workorder_prediction": {
        "desc": "拿掉工單的錯誤預測欄，機制自檢該紅",
        "file": "scripts/workorder.sh",
        "find": "這題我最可能錯在哪",
        "repl": "（欄位被金絲雀移除）",
        "gate": ["python3", "scripts/check-mechanisms.py"],
        "expect_nonzero": True,
        "expect_text": "錯誤預測",
    },
}


def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            pass
    return {"last_run": 0, "mechanisms": {}}


def run_one(name: str, m: dict, wt: Path) -> dict:
    """在拋棄式 worktree 裡套用突變並跑閘門。永不動 production。"""
    target = wt / m["file"]
    if not target.exists():
        return {"mechanism": name, "ok": False, "reason": "file_missing",
                "detail": m["file"]}

    # {TOKEN} 執行期替換成隨機字串。寫死的 payload 會被 commit 進本檔，
    # 然後 git grep 在本檔找到它 → 閘門以為有呼叫者 → 放行。
    # 金絲雀親手毒死自己的突變，2026-08-05 實際發生過。
    tok = "zzcanary" + uuid.uuid4().hex[:10]
    m = {**m, "repl": m["repl"].replace("{TOKEN}", tok),
         "expect_text": m["expect_text"].replace("{TOKEN}", tok)}

    text = target.read_text(errors="replace")
    if m["find"] not in text:
        # 錨點不見了 = 突變沒套上 = 這一輪什麼都沒測到。不能算通過。
        return {"mechanism": name, "ok": False, "reason": "anchor_missing",
                "detail": f"找不到 {m['find'][:40]!r}，突變定義過期"}

    target.write_text(text.replace(m["find"], m["repl"], 1))
    rc, out = sh(m["gate"], cwd=wt)

    caught = (rc != 0) if m["expect_nonzero"] else True
    if m["expect_text"]:
        caught = caught and (m["expect_text"] in out)

    return {"mechanism": name, "ok": bool(caught),
            "reason": "caught" if caught else "gate_silent",
            "detail": (f"rc={rc} " + next(
                (l.strip() for l in out.splitlines()
                 if m["expect_text"] and m["expect_text"] in l), out[-160:]))[:300]}


def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()

    order = sorted(MUTATIONS, key=lambda k: state["mechanisms"].get(k, {}).get("last_tested", 0))
    order = [k for k in order if k != "CONTROL"]
    todo = ["CONTROL"] + (order[:1] if ONE else order)

    wt = Path(tempfile.mkdtemp(prefix="canary-wt-"))
    shutil.rmtree(wt)  # worktree add 要求目標不存在
    results: list[dict] = []
    try:
        rc, out = sh(["git", "worktree", "add", "--detach", "-q", str(wt), "HEAD"], cwd=ROOT)
        if rc != 0:
            results.append({"mechanism": "WORKTREE", "ok": False,
                            "reason": "worktree_failed", "detail": out[:300]})
        else:
            for name in todo:
                # 每個突變都從乾淨副本開始。**必須整個 worktree 重置**，
                # 不能只還原「這次要突變的那個檔」——CONTROL 弄壞 brain/lint.py
                # 之後，後續以 lint.py 為閘門的突變會抓到 CONTROL 的殘骸，
                # 報成自己抓到了。第一版就是這樣讓 iron_law_anchor 假綠。
                sh(["git", "reset", "--hard", "-q", "HEAD"], cwd=wt)
                sh(["git", "clean", "-qfd"], cwd=wt)
                results.append(run_one(name, MUTATIONS[name], wt))
    finally:
        sh(["git", "worktree", "remove", "--force", str(wt)], cwd=ROOT)
        shutil.rmtree(wt, ignore_errors=True)
        sh(["git", "worktree", "prune"], cwd=ROOT)

    now = time.time()
    control = next((r for r in results if r["mechanism"] == "CONTROL"), None)
    control_ok = bool(control and control["ok"])

    # CONTROL 失敗 = 偵測邏輯本身壞了，其餘結果一律不可信。
    for r in results:
        if r["mechanism"] not in ("CONTROL", "WORKTREE"):
            if control_ok:
                state["mechanisms"].setdefault(r["mechanism"], {})
                state["mechanisms"][r["mechanism"]] = {
                    "last_tested": now, "last_ok": r["ok"]}
            else:
                r["reason"] = "void_control_failed"
                r["ok"] = False

    state["last_run"] = now
    state["control_ok"] = control_ok
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    with LOG.open("a") as f:
        f.write(json.dumps({"ts": now, "control_ok": control_ok,
                            "results": results}, ensure_ascii=False) + "\n")

    failed = [r for r in results if not r["ok"]]
    if AS_JSON:
        print(json.dumps({"ts": now, "control_ok": control_ok,
                          "failed": len(failed), "results": results},
                         ensure_ascii=False, indent=2))
        return 1 if failed else 0

    print(f"=== 突變金絲雀 {time.strftime('%Y-%m-%dT%H:%M:%S')} ===\n")
    for r in results:
        print(f"{'✅' if r['ok'] else '❌'} {r['mechanism']}  [{r['reason']}]")
        print(f"     {r['detail']}")
    if not control_ok:
        print("\n🚨 CONTROL 失敗：金絲雀的偵測邏輯本身壞了。"
              "本輪其餘結果一律作廢，先修這支再談別的。")
        return 2
    print(f"\n閘門存活 {len(results) - len(failed)}/{len(results)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
