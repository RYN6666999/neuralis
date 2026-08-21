#!/usr/bin/env python3
"""糾偏機制自檢：今天做的防呆是不是真的還在作用。

用法:
    python3 scripts/check-mechanisms.py            # 快檢（不重載 API）
    python3 scripts/check-mechanisms.py --deep     # 含重載與活體對話，約 60s
    python3 scripts/check-mechanisms.py --json

存在理由：這些檢查原本是三份 markdown 提示詞，貼給 agent 讓它逐條跑。
散文版每次都漏東西——漏題後把分母改小、用總結取代原始輸出、換量測單位。
那些不是它不聽話，是**分母和單位由被驗方決定**。寫成腳本，兩者都被寫死。

散文只該留給需要人類判讀的部分（根因、解法、取捨）。可機械判定的部分
就該是這支檔案。這是 scripts/check-*.py 家族的第 27 支，不是新發明。

所有突變測試跑在用完就丟的臨時 repo 或 try/finally 還原，最後驗這個 repo 沒被碰過。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import uuid
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT = (Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents/Fun")
DEEP = "--deep" in sys.argv
AS_JSON = "--json" in sys.argv

results: list[dict] = []


def record(name: str, ok: bool, evidence: str, note: str = "") -> None:
    results.append({"check": name, "ok": bool(ok), "evidence": evidence,
                    "note": note, "state": "pass" if ok else "fail"})


def skip(name: str, why: str) -> None:
    """未執行是第三種狀態，不是通過。

    把略過算成 ✅ 就是「漏題後改分子」——本檔第一版自己犯過，
    23/23 裡有 2 項根本沒跑。分母沒縮，分子灌水，同一個病。
    """
    results.append({"check": name, "ok": None, "evidence": why,
                    "note": "", "state": "skip"})


def sh(cmd: list[str] | str, cwd: Path = ROOT, timeout: int = 120) -> str:
    """跑指令，回 stdout+stderr 的合併文字。不吞錯誤——錯誤訊息本身就是證據。"""
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       shell=isinstance(cmd, str), timeout=timeout)
    return (r.stdout + r.stderr).strip()


# ── 1. 工單產生器 ───────────────────────────────────────────────────────
def check_workorder() -> None:
    out = sh(["bash", "scripts/workorder.sh", "自檢用"])

    n_bias = out.count("偏誤")
    record("workorder.偏誤區塊", n_bias >= 6, f"出現 {n_bias} 次（需 >= 6）")

    tail = out.split("完成前自檢", 1)[-1]
    n_self = len(re.findall(r"^\d+\.", tail, re.M))
    record("workorder.自檢題數", n_self >= 8, f"{n_self} 題（需 >= 8）")

    lines = out.splitlines()
    i_pred = next((i for i, l in enumerate(lines) if "最可能錯在哪" in l), -1)
    i_pass = next((i for i, l in enumerate(lines) if l.startswith("## 通過條件")), -1)
    record("workorder.錯誤預測在通過條件之前",
           0 <= i_pred < i_pass,
           f"預測欄第 {i_pred+1} 行，通過條件第 {i_pass+1} 行")

    for field in ("取樣範圍", "原始輸出", "我的解讀"):
        record(f"workorder.交件欄位.{field}", field in out,
               "有" if field in out else "缺")

    probe = sh(["bash", "scripts/workorder.sh", "--probe", "自檢用"])
    record("workorder.probe模式", "不准修任何東西" in probe,
           "尾段有查證型宣告" if "不准修任何東西" in probe else "缺")


# ── 2. pre-commit 語法閘 ────────────────────────────────────────────────
def check_syntax_gate() -> None:
    hook = ROOT / ".githooks" / "pre-commit"
    has = hook.exists() and "py_compile" in hook.read_text()
    record("語法閘.存在", has, "pre-commit 含 py_compile" if has else "缺")

    hooks_path = sh(["git", "config", "core.hooksPath"])
    record("語法閘.已掛載", hooks_path == ".githooks",
           f"core.hooksPath={hooks_path!r}（需 '.githooks'）")

    # 突變測試跑在**用完就丟的臨時 repo** 裡，不碰這個 repo。
    #
    # 2026-08-20：舊版在 ROOT 裡 `git add` + `git commit` 真的做提交，靠 hook 擋下來
    # 才沒事。但 hook 沒掛的機器上（.git/hooks 不進版控，重 clone / 換分支就沒了）
    # commit 會成功，而 finally 只 `git reset HEAD <file>` —— 那撤 index，不撤 commit。
    # 結果：壞檔案進了歷史，HEAD 多一個 "check-mechanisms probe"，而 git status
    # 看起來近乎乾淨。實測連踩兩次。
    #
    # 最惡毒的地方是它專打「閘已經死掉」的機器 —— 正是最需要跑這支自檢的時候。
    # 一個為了驗證安全機制而破壞工作區的檢查，會讓它之後所有的實跑結果都不可信。
    #
    # 臨時 repo 只需要 hook + 一個壞檔案就能驗「hook 會不會擋」，不需要真實歷史。
    hook_abs = str(hook.resolve())
    with tempfile.TemporaryDirectory(prefix="check-mech-") as tmp:
        def tsh(args: list[str]) -> str:
            r = subprocess.run(["git", "-C", tmp, *args],
                               capture_output=True, text=True)
            return (r.stdout + r.stderr).strip()

        tsh(["init", "-q"])
        tsh(["config", "user.email", "probe@localhost"])
        tsh(["config", "user.name", "check-mechanisms probe"])
        # 指向版控裡那份真 hook（用絕對路徑，因為 cwd 是臨時目錄）
        tsh(["config", "core.hooksPath", str(Path(hook_abs).parent)])
        (Path(tmp) / "_probe_bad.py").write_text("def f():\nreturn 1\n")
        tsh(["add", "_probe_bad.py"])
        out = tsh(["commit", "-m", "check-mechanisms probe"])
        blocked = "無法編譯" in out and "擋下" in out
        # 雙重確認：不只看訊息，直接問臨時 repo 有沒有生出 commit
        has_commit = tsh(["rev-parse", "--verify", "-q", "HEAD"]) != ""
        record("語法閘.實際會擋", blocked and not has_commit,
               next((l for l in out.splitlines() if "擋下" in l), out[:120])
               + ("" if not has_commit else " ← 且 commit 真的成立了"))

    # 這個 repo 從頭到尾沒被碰過，直接驗給你看（不再是「清乾淨了嗎」而是「有沒有碰」）
    dirty = sh(["git", "status", "--porcelain"])
    stray = [l for l in dirty.splitlines() if "_check_mechanisms_bad" in l or "_probe_bad" in l]
    head_now = sh(["git", "log", "-1", "--format=%s"])
    record("語法閘.未污染工作區",
           not stray and "check-mechanisms probe" not in head_now,
           f"無突變殘留；HEAD={head_now[:50]!r}" if not stray
           else f"殘留: {stray}")


# ── 3. bootstrap 摘要 ──────────────────────────────────────────────────
def _stale_line() -> str:
    out = sh(["bash", "scripts/aris-bootstrap-summary.sh"])
    return next((l for l in out.splitlines() if "進程碼" in l), "")


def check_bootstrap() -> None:
    out = sh(["bash", "scripts/aris-bootstrap-summary.sh"])

    guard = "說「不確定」之前" in out
    record("bootstrap.不確定守門", guard,
           next((l for l in out.splitlines() if "不確定" in l), "缺"))
    record("bootstrap.守門附可跑指令", out.count("git log") >= 2,
           f"git 指令出現 {out.count('git log')} 次（需 >= 2）")

    stale = _stale_line()
    record("bootstrap.進程碼欄存在", bool(stale), stale or "缺")
    record("bootstrap.進程碼非錯誤態", "無法判定" not in stale, stale)

    if not DEEP:
        skip("bootstrap.進程碼鑑別力", "需 --deep（含兩次重載，約 20s）")
        return

    # 綠 → touch → 紅 → 重載 → 綠。三值全同 = 沒有鑑別力。
    target = ROOT / "laap" / "chatflow.py"
    mtime = target.stat().st_mtime
    try:
        sh(["bash", "scripts/reload-aris.sh"])
        time.sleep(3)
        a = _stale_line()
        target.touch()
        b = _stale_line()
        sh(["bash", "scripts/reload-aris.sh"])
        time.sleep(3)
        c = _stale_line()
        ok = ("🟢" in a) and ("🔴" in b) and ("🟢" in c)
        record("bootstrap.進程碼鑑別力", ok,
               f"A={a.split()[-1] if a else '?'} / "
               f"B={'🔴' if '🔴' in b else '?'} / "
               f"C={'🟢' if '🟢' in c else '?'}",
               "三值全同代表機制無鑑別力")
    finally:
        import os
        os.utime(target, (mtime, mtime))


# ── 4. 消費端閘門（A/B 突變）────────────────────────────────────────────
def check_consumers_gate() -> None:
    yaml_p = ROOT / "brain" / "consumers.yaml"
    original = yaml_p.read_text()

    base = sh(["python3", "brain/lint.py", "--check", "consumers"])
    record("消費端閘門.基準乾淨", "情報層乾淨" in base,
           next((l for l in base.splitlines() if "情報層" in l), base[-120:]))

    marker = '- "scripts/evaluate-and-feedback.py：分數低於 threshold 時寫入留言板"'
    if marker not in original:
        record("消費端閘門.突變偵測", False,
               "consumers.yaml 找不到突變錨點，條目可能已改名",
               "更新本檢查的 marker")
        return
    # 函式名必須執行期隨機。寫死的 payload 一旦被 commit 進本檔，
    # git grep 就會在本檔找到它，閘門判定「有呼叫者」而放行——
    # 這支腳本會親手讓自己的突變測試失效。2026-08-05 實際發生過。
    token = "zzcanary" + uuid.uuid4().hex[:10]
    try:
        yaml_p.write_text(original.replace(
            marker, f'- "brain/lint.py::{token}()：假消費端"'))
        out = sh(["python3", "brain/lint.py", "--check", "consumers"])
        caught = token in out and "未被任何其他檔案呼叫" in out
        record("消費端閘門.突變偵測", caught,
               next((l.strip() for l in out.splitlines() if token in l),
                    "未觸發（閘門沒抓到零呼叫的假消費端）"))
    finally:
        yaml_p.write_text(original)
        record("消費端閘門.突變已還原", yaml_p.read_text() == original,
               "內容與突變前一致" if yaml_p.read_text() == original else "還原失敗")


# ── 5. ND 管線與乙的種子（活體）─────────────────────────────────────────
def _seed_count() -> int:
    out = sh(["sqlite3", str(Path.home() / ".aris-memory.db"),
              "select count(*) from memories where attention_line != '';"])
    return int(out) if out.isdigit() else -1


def check_nd_pipeline() -> None:
    if not DEEP:
        skip("ND管線.誤判防護", "需 --deep（會發一次真對話，約 30s）")
        skip("ND管線.走新路徑", "需 --deep")
        return

    log = ROOT / "laap-api.log"
    before_lines = len(log.read_text(errors="replace").splitlines()) if log.exists() else 0
    before = _seed_count()
    if before < 0:
        record("ND管線.誤判防護", False, "讀不到 aris-memory.db")
        return

    sh(["curl", "-s", "--max-time", "60", "-X", "POST",
        "http://localhost:11546/v1/chat/completions",
        "-H", "Content-Type: application/json",
        "-d", json.dumps({"model": "aris", "messages": [
            {"role": "user", "content": "今天天氣如何"}]})])
    after = _seed_count()

    # 「今天天氣如何」不含任何注意力關鍵字。DB 動了就是誤判復發。
    record("ND管線.誤判防護", before == after, f"DB {before} → {after}（應不變）")

    tail = "\n".join(log.read_text(errors="replace").splitlines()[before_lines:])
    record("ND管線.走新路徑", "✅ ND" in tail,
           next((l[-60:] for l in tail.splitlines() if "✅ ND" in l), "log 無 ND 行"))


# ── 6. 文件與互連 ──────────────────────────────────────────────────────
def check_docs() -> None:
    docs = {
        "對ai的幻覺驗證框架.md": VAULT / "對ai的幻覺驗證框架.md",
        "工程場景的驗證延伸.md": VAULT / "工程場景的驗證延伸.md",
        "派工單校準協定.md": VAULT / "Aris" / "派工單校準協定.md",
    }
    for name, p in docs.items():
        if not p.exists():
            record(f"文件.{name}", False, "不存在")
            continue
        text = p.read_text(errors="replace")
        links = text.count("[[")
        record(f"文件.{name}", links >= 1,
               f"{len(text.splitlines())} 行，{links} 個 wiki 連結")


def main() -> int:
    for fn in (check_workorder, check_syntax_gate, check_bootstrap,
               check_consumers_gate, check_nd_pipeline, check_docs):
        try:
            fn()
        except Exception as e:  # 檢查自己壞掉也要看得見，不准靜音
            record(f"{fn.__name__}.EXCEPTION", False, f"{type(e).__name__}: {e}")

    failed = [r for r in results if r["state"] == "fail"]
    skipped = [r for r in results if r["state"] == "skip"]
    passed = [r for r in results if r["state"] == "pass"]
    if AS_JSON:
        print(json.dumps({"deep": DEEP, "total": len(results),
                          "passed": len(passed), "failed": len(failed),
                          "skipped": len(skipped), "results": results},
                         ensure_ascii=False, indent=2))
        return 1 if failed else 0

    print(f"=== 糾偏機制自檢（{'deep' if DEEP else '快檢'}）"
          f" {len(results)} 項 ===\n")
    for r in results:
        mark = {"pass": "✅", "fail": "❌", "skip": "⏭️"}[r["state"]]
        print(f"{mark} {r['check']}")
        print(f"     {r['evidence']}")
        if r["note"]:
            print(f"     ↳ {r['note']}")
    print(f"\n通過 {len(passed)}／實跑 {len(passed) + len(failed)}"
          f"／全部 {len(results)}"
          + (f"（略過 {len(skipped)}，未實測不算通過）" if skipped else ""))
    if failed:
        print("FAILED: " + ", ".join(r["check"] for r in failed))
        return 1
    print("ALL MECHANISM CHECKS PASSED"
          + ("（但有略過項，完整驗證請加 --deep）" if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
