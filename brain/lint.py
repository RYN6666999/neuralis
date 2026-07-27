#!/usr/bin/env python3
"""lint.py — 情報層守門人。違反鐵律就 exit 1。

╔══════════════════════════════════════════════════════════════════╗
║  鐵律：事實只能推導，不能複製。                                    ║
║                                                                  ║
║  一個事實被抄寫一次，就等於預約了未來某天的一個謊。                  ║
║  因為抄本不會跟著本體變，而沒有人會記得回頭對。                     ║
╚══════════════════════════════════════════════════════════════════╝

這支不是文件，是閘。文件會腐敗（它自己就是抄本），閘不會 —— 閘要嘛跑
過要嘛擋下來，沒有第三種狀態。所以鐵律寫在這裡，不寫在 README。

三個真實案例催生了下面四道檢查（2026-07-27 一天內抓到）：

  1. `_現況.md` 宣稱 relay 雙寫上線於 commit 3b966ae —— 該 hash 不存在。
     → 檢查 B：src 指到 commit 就去驗它在不在。

  2. probe.py 的註解抄了 chatflow.py 的 bootstrap 冷卻常數，抄的值比真值
     大 15 倍。同一個變數名、術語完全一致，照樣說謊。
     → 檢查 D：抄來的常數值對不上真值就擋。**這是鐵律的核心。**
     （這段刻意不寫出那兩個數字 —— 寫了就是又一份會腐敗的抄本，
       而且檢查 D 會當場抓到我。要真值就跑 lint，它會去讀。）

  3. `.git/hooks/pre-commit` symlink 還在，目標檔早已不在此分支。
     git 當作沒 hook 直接放行，exit 0，靜默。
     → 檢查 E：閘要實跑證明自己活著，不能只看檔案在不在。

為什麼統一 spec 解決不了：案例 2 的兩邊術語本來就統一。病不在講法
不同，在那個數字是「打字打進去的」而不是「讀出來的」。統一 spec 只是
多一份要維護的抄本，多一個腐敗點。

用法：
    python3 brain/lint.py           # 全跑
    python3 brain/lint.py --json    # 給機器讀
exit 0 = 乾淨 · exit 1 = 有違規
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("需要 pyyaml：pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
CAUSAL = ROOT / "brain" / "causal.yaml"

# causal.yaml 開頭自己宣告的合法狀態。抄在這裡是刻意的例外：
# yaml 註解不可執行，沒別的地方可讀。若哪天狀態集要改，檢查 C 會擋下
# 未宣告的新狀態，逼人回來同步 —— 抄本有守門人看著就不會爛。
VALID_STATUS = {"done", "partial", "not_started", "sealed"}

# 掃這些目錄找常數定義與引用
SCAN_DIRS = ("laap", "scripts", "brain")
SCAN_EXT = (".py", ".md", ".yaml", ".yml")

CONST_DEF = re.compile(r"^(_?[A-Z][A-Z0-9_]{3,})\s*=\s*(\d+(?:\.\d+)?)\s*(?:#.*)?$")
SHA_LIKE = re.compile(r"\b([0-9a-f]{7,40})\b")


def load() -> dict:
    with CAUSAL.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _git(*args: str) -> tuple[int, str]:
    p = subprocess.run(["git", "-C", str(ROOT), *args],
                       capture_output=True, text=True)
    return p.returncode, (p.stdout or p.stderr).strip()


def _files() -> list[Path]:
    out = []
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.is_file() and p.suffix in SCAN_EXT and "__pycache__" not in p.parts:
                out.append(p)
    return sorted(out)


# ── A. 每個項目要有出處。無出處的宣稱 = 幻覺 ──────────────────────
# 兩種出處都算數，而且 detected_by 更強：
#   src:         人手指回文件章節 —— 抄本，會腐敗，但總比沒有好
#   detected_by: 指向可重跑的工具 —— 推導，重跑就知道還算不算數
# 不要求兩個都填。逼人補一份 src 去複述 detected_by 說過的話，
# 就是在製造抄本 —— 那正是鐵律要禁的事。
PROVENANCE = ("src", "detected_by")


def check_src_present(data: dict) -> list[str]:
    bad = []
    for section in ("blockers", "sealed", "risks"):
        for item in data.get(section) or []:
            if not any(str(item.get(k) or "").strip() for k in PROVENANCE):
                bad.append(f"{section}/{item.get('id', '?')} 無出處"
                           f"（要有 {' 或 '.join(PROVENANCE)} 其一，否則是幻覺，刪掉）")
    return bad


# ── B. src 指到 commit 就驗它存在。3b966ae 那個病 ──────────────────
def check_src_resolves(data: dict) -> list[str]:
    bad = []
    for section in ("blockers", "sealed", "risks"):
        for item in data.get(section) or []:
            src = " ".join(str(item.get(k) or "") for k in PROVENANCE)
            for sha in SHA_LIKE.findall(src):
                # 純數字不是 hash（§11 #26 這種章節號會誤命中）
                if sha.isdigit():
                    continue
                if _git("cat-file", "-e", f"{sha}^{{commit}}")[0] != 0:
                    bad.append(
                        f"{section}/{item.get('id','?')} src 引用 commit {sha} —— 此 repo 找不到"
                        "（這正是 _現況.md 那個謊的形狀）")
    return bad


# ── C. 狀態只准四種 · 引用不准懸空 ────────────────────────────────
def check_schema(data: dict) -> list[str]:
    bad = []
    ids = {i.get("id") for sec in ("blockers", "sealed", "risks")
           for i in (data.get(sec) or []) if i.get("id")}
    for section in ("blockers", "sealed"):
        for item in data.get(section) or []:
            iid = item.get("id", "?")
            st = item.get("status")
            if st is not None and st not in VALID_STATUS:
                bad.append(f"{section}/{iid} status='{st}' 不在合法集 {sorted(VALID_STATUS)}")
            for field in ("blocks", "blocked_by"):
                for ref in item.get(field) or []:
                    if ref not in ids:
                        bad.append(f"{section}/{iid} {field} 指向不存在的 id '{ref}'（懸空引用）")
    return bad


# ── D. 抄來的常數。鐵律的核心，1800 那個病 ────────────────────────
def check_copied_constants() -> list[str]:
    """先蒐集程式碼裡的常數真值，再掃全 repo 找講了不同值的地方。"""
    defs: dict[str, list[tuple[float, Path, int]]] = {}
    files = _files()

    for p in files:
        if p.suffix != ".py":
            continue
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(lines, 1):
            m = CONST_DEF.match(line.strip())
            if m:
                defs.setdefault(m.group(1), []).append((float(m.group(2)), p, n))

    # 同名多處定義且值不同 = 無法判斷真值，跳過（不製造假陽性）
    truth = {k: v[0][0] for k, v in defs.items() if len({d[0] for d in v}) == 1}

    bad = []
    for p in files:
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(lines, 1):
            for name, real in truth.items():
                src_p, src_n = defs[name][0][1], defs[name][0][2]
                if name not in line:
                    continue
                # 定義行本身不算抄
                if CONST_DEF.match(line.strip()):
                    continue
                for quoted in re.findall(rf"{re.escape(name)}\s*=\s*(\d+(?:\.\d+)?)", line):
                    if float(quoted) != real:
                        bad.append(
                            f"{p.relative_to(ROOT)}:{n} 寫 {name}={quoted}，真值是 {real:g}"
                            f"（定義於 {src_p.relative_to(ROOT)}:{src_n}）"
                            " —— 別抄常數，讀真值")
    return bad


# ── E. 閘要證明自己活著。懸空 symlink 那個病 ──────────────────────
def check_gate_alive() -> list[str]:
    """閘要能證明自己活著。`ls` 會被懸空 symlink 騙，所以逐層驗到可執行為止。

    不在這裡跑 `git hook run pre-commit` —— 這支自己被 pre-commit 呼叫，
    那樣會無限遞迴。改成解析出「git 實際會用的那個檔」再驗它。
    """
    rc, configured = _git("config", "core.hooksPath")
    versioned = rc == 0 and configured
    hooks_dir = (ROOT / configured) if versioned else (ROOT / ".git" / "hooks")
    hook = hooks_dir / "pre-commit"

    if hook.is_symlink() and not hook.exists():
        return [f"pre-commit 是懸空 symlink → {hook.readlink()}"
                "（git 對懸空 hook 靜默放行 exit 0，看起來有閘實際沒有）"]
    if not hook.exists():
        return [f"{hook.relative_to(ROOT)} 不存在 —— 無閘，commit 一路放行"]
    if not hook.stat().st_mode & 0o111:
        return [f"{hook.relative_to(ROOT)} 沒有執行權限（git 會跳過）→ chmod +x"]
    if not versioned:
        return ["閘裝在 .git/hooks（不進版控）—— 換分支或重 clone 就會靜默消失。"
                "改用版控目錄：git config core.hooksPath .githooks"]
    return []


CHECKS = (
    ("A src-必填", lambda d: check_src_present(d)),
    ("B src-可解析", lambda d: check_src_resolves(d)),
    ("C schema", lambda d: check_schema(d)),
    ("D 常數未抄襲", lambda d: check_copied_constants()),
    ("E 閘存活", lambda d: check_gate_alive()),
)


def main() -> int:
    as_json = "--json" in sys.argv
    data = load()
    report, failed = {}, 0

    for name, fn in CHECKS:
        try:
            issues = fn(data)
        except Exception as e:            # 檢查自己爆掉要講出來，不能當成通過
            issues = [f"檢查器自身異常：{e!r}"]
        report[name] = issues
        failed += len(issues)

    if as_json:
        print(json.dumps({"ok": failed == 0, "total": failed, "checks": report},
                         ensure_ascii=False, indent=2))
        return 1 if failed else 0

    print("\n=== 情報層守門人 · 鐵律：事實只能推導，不能複製 ===\n")
    for name, issues in report.items():
        if issues:
            print(f"  ✗ {name}")
            for i in issues:
                print(f"      {i}")
        else:
            print(f"  ✓ {name}")
    print()
    if failed:
        print(f"✗ {failed} 項違規。修掉，或把宣稱刪掉。\n")
        return 1
    print("✓ 情報層乾淨。\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
