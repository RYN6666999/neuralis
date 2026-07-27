#!/usr/bin/env python3
"""lint.py — 情報層守門人。違反鐵律就 exit 1。

╔══════════════════════════════════════════════════════════════════╗
║  鐵律一：事實只能推導，不能複製。                                  ║
║  一個事實被抄寫一次，就等於預約了未來某天的一個謊。                  ║
║  因為抄本不會跟著本體變，而沒有人會記得回頭對。                     ║
║                                                                  ║
║  鐵律二：0 信心路由 —— 預設第一次就有問題，換一條路驗過才算數。      ║
║  產出者不得自驗。用產出它的同一條路去驗，等於沒驗。                  ║
╚══════════════════════════════════════════════════════════════════╝

這裡是兩條鐵律的唯一權威正文。CLAUDE.md / AGENTS.md 只放指標不複述
（複述就是抄本，違反鐵律一）；反過來檢查 G 盯著那兩份文件，指標被拿掉
就擋 commit。兩邊互相咬住，任一邊爛掉都會紅。

── 鐵律二的判例（全部發生在 2026-07-27 同一天，同一個人身上）──

  · 「驗過」跨 repo 節點才推上去 —— 驗的方式是跑 probe.py，但 probe 只驗
    edges 的對稱差集，node 欄位一個字都不看。同角度驗 = 沒驗。
    結果一次放行三個假宣稱（at 指向不存在的目錄、紅線歸屬完全講反、
    能力描述與該 repo 實際做的事無關）。

  · 修好 topology.yaml 之後，習慣性想重跑 lint 確認 —— 但 lint 正是指導
    這次修改的那條路。改走獨立路徑（直接 stat 檔案）才發現：那次編輯
    把 yaml 語法弄壞了（未加引號的純量裡出現 `at: `，被當成 mapping key）。

  · 獨立路徑的第一版腳本自己也是錯的（`~` 在雙引號裡不展開，四個真實存在
    的路徑被誤報成開不起來）。**驗證器也是第一次寫的開發行為，也預設有問題。**

  · check F 第一版用「長得像不像路徑」猜，把 6 個正確的 repo 相對路徑和
    含空格的 macOS 路徑判成「描述」。兩條路互相打臉才抓到 ——
    **若只有一條路，我會去「修」6 個本來就對的東西。**

  推論：兩條獨立路徑得到不同答案時，那個「不一致」本身就是訊號。
  只有一條路的時候，你不會知道自己錯了。

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
import os
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
    # CI 上沒有 pre-commit 也不該有 —— CI 自己就是那道閘，要求它再裝一個
    # 本機 hook 是範疇錯誤。但版控裡的那份必須完好，否則本機裝了也是空的。
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        h = ROOT / ".githooks" / "pre-commit"
        if not h.exists():
            return ["版控裡的 .githooks/pre-commit 不見了 —— 本機再怎麼設定都掛不上"]
        if not h.stat().st_mode & 0o111:
            return [".githooks/pre-commit 沒有執行位元（git 會靜默跳過）→ "
                    "git update-index --chmod=+x .githooks/pre-commit"]
        return []

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


# ── F. 換個角度驗：拿檔案系統對 yaml 的宣稱 ────────────────────────
# 鐵律二：任何開發行為第一次一定有問題，換個角度驗過才算數。
#
# 2026-07-27 的實例：topology.yaml 加了三個跨 repo 節點，作者「驗過」的
# 方式是跑 probe.py —— 但 probe 只驗 edges 的對稱差集，**node 欄位它一個
# 字都不看**。同角度驗 = 沒驗。結果一次放行三個假宣稱：
#   · at: 指的目錄不存在（真實位置差一層）
#   · note: 說某條紅線「在此定義」，實際定義在完全另一個 repo
#   · owns: 描述的能力與該 repo 實際做的事無關
#
# 所以這道檢查刻意不讀 probe、不讀任何宣稱層，只做一件事：
# **把 yaml 說的位置，拿去檔案系統實際打開看。** 這就是「另一個角度」。
def check_claims_resolve(data: dict) -> list[str]:
    topo_path = ROOT / "topology.yaml"
    if not topo_path.exists():
        return ["topology.yaml 不存在"]
    topo = yaml.safe_load(topo_path.read_text(encoding="utf-8"))
    bad = []

    # CI 上沒有這些本機 checkout，路徑檢查在那裡沒有意義
    in_ci = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))

    for node in topo.get("nodes") or []:
        nid = node.get("id", "?")

        # F1. at: 宣告的位置要真的在
        # 三種病要分開報。訊息講錯病，讀的人就會誤判成假陽性然後忽略它 ——
        # 我 2026-07-27 就是這樣差點放掉一個真陽性。
        at = str(node.get("at") or "").strip()
        if at and not at.startswith(("http://", "https://")):
            # 不要用「長得像不像路徑」去猜 —— 我第一版就是這樣猜的，把 6 個
            # 正確的 repo 相對路徑和含空格的 macOS 路徑判成「描述」，差點去
            # 「修」本來就對的東西。直接開開看最省事也最準。
            p = Path(at).expanduser()
            if not p.is_absolute():
                p = ROOT / p
            if "..." in at:
                bad.append(f"node/{nid} at='{at}' 含縮寫 `...` —— 人看得懂，機器驗不了。"
                           "寫完整路徑，否則這行永遠沒人查得動")
            elif in_ci and at.startswith("~"):
                pass          # 家目錄下的東西 CI 上本來就沒有，不是問題
            elif not p.exists():
                bad.append(f"node/{nid} at='{at}' 開不起來 —— "
                           "若是路徑就修正它；若是描述請改放 note:")

        # F2. 文字裡引用 `檔案:行號` 的，該檔要在、該行要有東西
        blob = " ".join(str(node.get(k) or "") for k in ("note", "owns", "watch"))
        for ref, lineno in re.findall(r"([\w./-]+\.(?:py|yaml|yml|md|json|sh)):(\d+)", blob):
            f = ROOT / ref
            if not f.exists():
                bad.append(f"node/{nid} 引用 {ref}:{lineno} —— 檔案不存在")
                continue
            n = int(lineno)
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            if n > len(lines):
                bad.append(f"node/{nid} 引用 {ref}:{lineno} —— 該檔只有 {len(lines)} 行")

        # F3. watch: 指的工具要真的存在（不然「有人盯著」是假的）
        w = str(node.get("watch") or "").strip()
        if w and not (ROOT / w).exists():
            bad.append(f"node/{nid} watch='{w}' 不存在 —— 宣稱有監控但工具不在")

    return bad


# ── G. 鐵律不准從入口文件消失 ──────────────────────────────────────
# 把法條放進文件只解決一半問題：文件會被改、被重寫、被「精簡」掉。
# 這道檢查讓「拿掉鐵律」這個動作本身會擋 commit —— 文件與閘互相咬住。
#
# 只驗錨點與指標存不存在，不驗字句。驗字句就變成「文件必須逐字等於某個
# 樣板」，那是另一種抄本，會擋住正常的措辭調整 —— 假紅比沒有更糟。
IRON_LAW_ANCHOR = "IRON-LAW-ANCHOR"
ENTRY_DOCS = ("CLAUDE.md", "AGENTS.md")


def check_iron_law_anchored() -> list[str]:
    bad = []
    for name in ENTRY_DOCS:
        p = ROOT / name
        if not p.exists():
            bad.append(f"{name} 不見了 —— 那是各家 agent 的入口，沒有它鐵律傳不下去")
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if IRON_LAW_ANCHOR not in text:
            bad.append(f"{name} 的 {IRON_LAW_ANCHOR} 錨點被拿掉了 —— "
                       "鐵律從入口消失，下一個 agent 不會知道規矩")
        if "brain/lint.py" not in text:
            bad.append(f"{name} 沒有指向 brain/lint.py —— "
                       "指標斷了，法條正文就找不到（正文只在 lint.py 檔頭）")
    return bad


CHECKS = (
    ("A src-必填", lambda d: check_src_present(d)),
    ("B src-可解析", lambda d: check_src_resolves(d)),
    ("C schema", lambda d: check_schema(d)),
    ("D 常數未抄襲", lambda d: check_copied_constants()),
    ("E 閘存活", lambda d: check_gate_alive()),
    ("F 宣稱對得上檔案系統", check_claims_resolve),
    ("G 鐵律沒被摘掉", lambda d: check_iron_law_anchored()),
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
