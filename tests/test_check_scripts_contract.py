"""結構守衛：新的 `scripts/check-*.py` 不能再用兩態 exit 說謊。

## 為什麼要有這條

四個人（PI / Researcher / Option Compare / 我）漏掉同一支腳本，原因是
**「說謊腳本清單」是人工維護的**。第六支我們同樣不會知道它存在。
所以清單要從人腦搬到 CI。

## 為什麼不用 stdout grep

`verify-neuralis.sh:94` 的做法是跑腳本、`grep -qiE 'SKIP|不存在|not found'`，
exit 0 且命中就標「綠燈說謊」。**那個判準會偽陽，實測已經偽陽了：**

`check-trust-presence.py` 沒有任何 SKIP、沒有外部依賴、4 段 13 項全過
exit 0 —— 它被標成說謊，只因為 D 段（純靜態結構檢查）的**通過訊息**是
「舊 `1.0 + trust * 0.5` 增益碼**不存在**」。一個證明壞東西已被移除的
成功訊息，撞上了關鍵詞。`check-agency-intent.py` 用「跳過」描述通過的
查詢去重，同一個問題。

而且它會反過來咬修好的腳本：修完的 4 支摘要印「N 沒驗到」，其中
`check-watchdog.py` 是 `0 沒驗到` + exit 0 —— 關鍵詞清單一旦加上「沒驗到」，
最誠實的那支會被判成最會說謊的那支。

**根因：從散文猜語義，必然偽陽。** 散文是給人看的，它會為了解釋而提到
自己不是的那個狀態。所以這條測試改用**契約**：腳本自己宣告三態
（`_check_verdict.Verdict` + `CHECK-VERDICT:` 標記行），工具讀宣告，不猜散文。

## 這條守什麼（以及刻意不守什麼）

守：**新增**的 check 腳本如果會因外部依賴而跳過段落，就必須用共用層宣告
三態。用 allowlist 記錄目前尚未遷移的腳本 —— 清單只能變短，不能變長
（`test_allowlist_only_shrinks` 守這件事）。

不守：不強迫 27 支全部立刻遷移。那會是一次巨大的、無法審查的改動，而且
多數腳本沒有外部依賴、兩態就是正確的。**沒有依賴的腳本不需要三態** ——
硬要求它們遷移就是為了測試而改程式碼。
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

ALL_CHECKS = sorted(SCRIPTS.glob("check-*.py"))

# 已遷移到三態共用層的腳本。**這個清單只能變長。**
MIGRATED = {
    "check-memory-gbrain.py",
    "check-rust-psi-backend.py",
    "check-stream.py",
    "check-watchdog.py",
    "check-toolcall.py",
    "check-psi-response.py",
    "check-consolidation.py",
    "check-emotion-recall.py",
    "check-loops.py",
}

# 尚未遷移、且**已知**會因外部依賴而跳過段落的腳本。
# 這是技術債的明確記錄，不是豁免：清單只能變短（見 test_allowlist_only_shrinks）。
# 空 = 已知的依賴型腳本都遷移完了。
PENDING_MIGRATION: set[str] = set()

# 外部依賴的訊號：出現這些呼叫，代表腳本可能因環境而跳過真正的驗證。
#
# 2026-08-21：第一版把 `get_client` 一律當訊號，結果誤標了 5 支 ——
# 那個判準沒有區分**依賴決定結論**與**依賴只用於事後清理**。
# `check-agency.py` / `check-t5.py` 的 gbrain 只出現在 `finally` 的
# `delete_page`（包在 `try/except Exception: pass` 裡，缺了完全不影響結論），
# 它們用純假件驗完整迴路，兩態 exit 對它們是正確的。
# `check-memory-weave.py` 更極端：它**注入假 gbrain 模組**，正因為不想碰真後端。
#
# 教訓與偽陽性那條同源：**訊號要對準「依賴是否決定結論」，不是「檔案裡有沒有
# 提到依賴」。** 提到 ≠ 依賴。所以 gbrain 只在真的當閘時才算訊號（見下）。
DEPENDENCY_HINTS = (
    "urlopen",            # HTTP 服務（:11546 / :11550）
    "create_connection",  # 裸 socket 探測
    "shutil.which",       # 外部 binary
)

# gbrain 當「閘」用的形態：拿不到 client 就決定了結論（早退／assert／分支）。
# 只出現在 finally 清理裡的 `delete_page` 不算。
GATING_PATTERNS = (
    "assert client is not None",
    "client is None",
)


def _gbrain_gates_the_result(src: str) -> bool:
    return "get_client" in src and any(g in src for g in GATING_PATTERNS)

VERDICT_IMPORT = "_check_verdict"


def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _strip_docstrings(tree: ast.AST) -> ast.AST:
    """把所有 docstring 清成空字串。

    判準只能看**程式碼**：解釋「為什麼不用散文 grep」時必然要引用那些詞，
    把說明文字也算進判準，就是在複製我們正在修的那種偽陽性。
    """
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            body[0].value.value = ""
    return tree


def _looks_dependency_bound(src: str) -> bool:
    """依賴是否**決定結論**（而不只是被提到）。"""
    return any(h in src for h in DEPENDENCY_HINTS) or _gbrain_gates_the_result(src)


def _dependency_reasons(src: str) -> list:
    r = [h for h in DEPENDENCY_HINTS if h in src]
    if _gbrain_gates_the_result(src):
        r.append("gbrain 當閘")
    return r


# ══════════════════════════════════════════════════════════════════
# 1. 契約：依賴型腳本必須宣告三態
# ══════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("path", ALL_CHECKS, ids=lambda p: p.name)
def test_dependency_bound_scripts_declare_tri_state(path: Path):
    """會碰外部依賴的 check 腳本必須用 `_check_verdict`，不能自己 exit 0/1。

    這條是**新腳本的閘**：以後有人新寫一支會探 HTTP／探 binary 的自檢，
    忘了處理「依賴不在」就會被這裡擋下，不用等有人肉眼發現。
    """
    name = path.name
    src = _src(path)
    if not _looks_dependency_bound(src):
        pytest.skip("無外部依賴訊號 —— 兩態 exit 對它是正確的，不該硬遷移")
    if name in PENDING_MIGRATION:
        pytest.xfail(f"{name} 已記錄為待遷移技術債")
    assert VERDICT_IMPORT in src, (
        f"{name} 會碰外部依賴（{_dependency_reasons(src)}）"
        f"卻沒有用 scripts/_check_verdict.py 宣告三態。\n"
        f"依賴不在時它只能回 0 或 1：回 0 = 綠燈說謊，回 1 = 假紅。\n"
        f"兩個都錯 —— 需要第三態（exit 2 = 沒驗到）。"
    )


@pytest.mark.parametrize(
    "path", [p for p in ALL_CHECKS if p.name in MIGRATED], ids=lambda p: p.name)
def test_migrated_scripts_have_no_bare_exit(path: Path):
    """遷移過的腳本不該還留著繞過 Verdict 的 `sys.exit(0)` / `sys.exit(1)`。

    留一個就等於留一條後門：那條路徑上的結論不會經過三態判定。
    （`V.finish()` 內部的 `sys.exit(code)` 在 _check_verdict.py 裡，不在這些檔案。）
    """
    tree = ast.parse(_src(path))
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        is_exit = (isinstance(f, ast.Attribute) and f.attr == "exit"
                   and isinstance(f.value, ast.Name) and f.value.id == "sys")
        if is_exit and node.args:
            a = node.args[0]
            if isinstance(a, ast.Constant) and a.value in (0, 1):
                bad.append(getattr(node, "lineno", "?"))
    assert not bad, (
        f"{path.name} 仍有繞過 Verdict 的 sys.exit(0/1)，行號 {bad} —— "
        f"那條路徑的結論不經三態判定")


# ══════════════════════════════════════════════════════════════════
# 2. 標記行：外部工具讀宣告，不猜散文
# ══════════════════════════════════════════════════════════════════

MARKER_RE = re.compile(
    r"^CHECK-VERDICT: (?P<name>\S+) exit=(?P<exit>\d+) pass=(?P<p>\d+) "
    r"fail=(?P<f>\d+) warn=(?P<w>\d+) unknown=(?P<u>\d+)$", re.M)


def _run(path: Path, timeout: int = 200):
    import os
    env = {**os.environ, "PYTHONPATH": str(ROOT), "NEURALIS_CONSTITUTION": "off"}
    return subprocess.run([sys.executable, str(path)], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=timeout)


# 只實跑不需要外部服務、且已遷移的腳本。刻意不在測試裡跑全部 27 支：
# 其中有腳本會 `git commit`（check-mechanisms 的前科），跑全部等於讓
# 測試套件去執行任意副作用。守門靠上面的靜態契約，不靠實跑。
SAFE_TO_RUN = ["check-memory-gbrain.py", "check-stream.py",
               "check-toolcall.py", "check-psi-response.py"]


@pytest.mark.parametrize("name", SAFE_TO_RUN)
def test_marker_line_matches_real_exit_code(name: str):
    """標記行宣告的 exit 必須等於行程真正的 exit code。

    這是整個設計的信任基礎：如果標記行可以跟現實不一致，外部工具讀它
    就跟 grep 散文一樣不可靠。
    """
    p = _run(SCRIPTS / name)
    out = p.stdout + p.stderr
    m = MARKER_RE.search(out)
    assert m, (f"{name} 沒有輸出 CHECK-VERDICT 標記行 —— "
               f"外部工具只能回去 grep 散文（那會偽陽）：\n{out[-1500:]}")
    assert int(m.group("exit")) == p.returncode, (
        f"{name} 標記行說 exit={m.group('exit')}，實際 {p.returncode}")
    # 三態語義的一致性：有 fail → 1；無 fail 有 unknown → 2；否則 0
    f_, u_ = int(m.group("f")), int(m.group("u"))
    expect = 1 if f_ else (2 if u_ else 0)
    assert p.returncode == expect, (
        f"{name} counts=(fail={f_}, unknown={u_}) 應 exit {expect}，"
        f"實際 {p.returncode}")


@pytest.mark.parametrize("name", SAFE_TO_RUN)
def test_green_phrase_only_when_fully_verified(name: str):
    """`ALL CHECKS PASSED` 只准在真的全驗過時出現。

    CI 與人都 grep 那句話判斷「這支綠了」，所以它是一個承諾，不是裝飾。
    """
    p = _run(SCRIPTS / name)
    out = p.stdout + p.stderr
    if "ALL CHECKS PASSED" in out:
        assert p.returncode == 0, f"{name} 印了 PASSED 卻 exit {p.returncode}"
        m = MARKER_RE.search(out)
        assert m and int(m.group("u")) == 0, (
            f"{name} 有段落沒驗到卻印 ALL CHECKS PASSED")


# ══════════════════════════════════════════════════════════════════
# 3. 防偽陽：這條測試本身不得用 stdout 關鍵詞猜語義
# ══════════════════════════════════════════════════════════════════

def test_this_guard_does_not_use_prose_grep():
    """守衛自己不能退化成「跑腳本 + grep stdout 關鍵詞」。

    這條看起來像在測試自己，但它守的是一個真實的退化路徑：以後有人覺得
    契約式判準太麻煩，改回搜尋輸出裡的字，就會重新引入
    `check-trust-presence.py` 那個偽陽性。把理由釘在測試裡。

    **判準是「關鍵詞有沒有被用來對 stdout 做判定」，不是「檔案裡有沒有出現
    那些字」** —— 後者會把解釋用的散文和斷言訊息一起誤殺，那正是我們在修的
    那種偽陽。所以這裡用 AST 找「拿腳本輸出去比對字串」的形態。
    """
    tree = ast.parse(_src(Path(__file__)))

    # 這支測試檔裡，唯一允許對 stdout 做的字串判定是 ALL CHECKS PASSED
    # （那是腳本自己的承諾語句，不是拿來猜語義的散文關鍵詞）。
    allowed = {"ALL CHECKS PASSED"}
    offenders = []
    for node in ast.walk(tree):
        # `<字面量> in out` / `<字面量> not in out` 這種對輸出的散文比對
        if isinstance(node, ast.Compare) and node.ops and isinstance(
                node.ops[0], (ast.In, ast.NotIn)):
            left, right = node.left, node.comparators[0]
            if isinstance(left, ast.Constant) and isinstance(left.value, str) \
                    and isinstance(right, ast.Name) and right.id in ("out", "stdout"):
                if left.value not in allowed:
                    offenders.append((node.lineno, left.value))
    assert not offenders, (
        f"守衛把散文關鍵詞拿去比對腳本輸出：{offenders} —— "
        f"那正是造成偽陽的做法。要判斷語義請讀 CHECK-VERDICT 標記行或原始碼結構")

    # 也不准用 regex 把那組關鍵詞打包起來掃輸出。字面量在執行期組出來，
    # 否則這條檢查會命中自己（第一版就是這樣自我否定的）。
    banned_regex = "SKIP" + "|"
    code_only = ast.unparse(_strip_docstrings(ast.parse(_src(Path(__file__)))))
    hits = [ln for ln in code_only.splitlines()
            if banned_regex in ln and "banned_regex" not in ln]
    assert not hits, (
        f"守衛用了 verify-neuralis.sh 那組關鍵詞 regex（已證實會偽陽）：{hits}")


def test_trust_presence_is_not_a_liar():
    """回歸：`check-trust-presence.py` 曾被 verify-neuralis.sh 判成綠燈說謊。

    它其實沒有任何外部依賴、也沒有 SKIP —— 那是偽陽性。這條釘住事實，
    避免下一輪又有人把它列進待修清單（我們為它繞了一輪）。
    """
    src = _src(SCRIPTS / "check-trust-presence.py")
    assert not _looks_dependency_bound(src), (
        "check-trust-presence.py 現在有外部依賴了 —— 那它就真的需要三態，"
        "這條回歸測試的前提要重新評估")
    p = _run(SCRIPTS / "check-trust-presence.py", timeout=120)
    assert p.returncode == 0, (
        f"它在無依賴的環境下應該全過：\n{(p.stdout + p.stderr)[-1500:]}")


def test_allowlist_only_shrinks():
    """`PENDING_MIGRATION` 是技術債記錄，只能變短。

    每一個名字都代表「這支腳本在依賴缺失時會說謊或假紅，我們知道但還沒修」。
    允許它變長，就等於允許用 allowlist 讓新的說謊腳本通過 CI。
    """
    assert len(PENDING_MIGRATION) <= 0, (
        f"待遷移清單變長了：{sorted(PENDING_MIGRATION)}。"
        f"新腳本請直接用 _check_verdict 三態，不要加進 allowlist")
    unknown = PENDING_MIGRATION - {p.name for p in ALL_CHECKS}
    assert not unknown, f"allowlist 裡有不存在的腳本（已改名或刪除？）：{unknown}"
    overlap = PENDING_MIGRATION & MIGRATED
    assert not overlap, f"同時列在待遷移與已遷移：{overlap}"


def test_migrated_list_matches_reality():
    """`MIGRATED` 清單要跟實際 import 一致 —— 清單本身也會漂移。"""
    actual = {p.name for p in ALL_CHECKS if VERDICT_IMPORT in _src(p)}
    assert actual == MIGRATED, (
        f"清單與實際不符。\n只在清單裡：{MIGRATED - actual}\n"
        f"只在實際裡：{actual - MIGRATED}（記得加進 MIGRATED）")


# ══════════════════════════════════════════════════════════════════
# 4. 偵測力：守衛必須抓到「新寫的說謊腳本」
# ══════════════════════════════════════════════════════════════════
# 這條是 PI 的硬要求在守衛上的對應。守衛本身也可能是裝飾品：
# 如果 `_looks_dependency_bound` 的訊號太窄，它會對新的說謊腳本沉默，
# 而測試全綠沒人看得出來。所以植入一支真的會說謊的腳本，斷言守衛抓到。

LIAR_TEMPLATE = '''#!/usr/bin/env python3
"""植入用的假腳本：探 HTTP 服務，不在就印 SKIP 然後照樣報成功。"""
import sys
import urllib.request

try:
    urllib.request.urlopen("http://localhost:1/health", timeout=1)
except Exception:
    print("SKIP: 服務不在")
    print("ALL CHECKS PASSED")
    sys.exit(0)
print("ALL CHECKS PASSED")
sys.exit(0)
'''


def test_guard_catches_a_newly_planted_liar(tmp_path, monkeypatch):
    """植入一支「探 HTTP + 缺依賴回綠」的新腳本，契約檢查必須判它違規。

    這模擬的正是我們四個人漏掉第五支的情境：有人新寫一支自檢，忘了處理
    「依賴不在」。守衛的價值全在這一條 —— 它要能對**還沒有人看過**的腳本說不。
    """
    liar = tmp_path / "check-planted-liar.py"
    liar.write_text(LIAR_TEMPLATE, encoding="utf-8")
    src = liar.read_text(encoding="utf-8")

    # 1. 依賴訊號要認得出來
    assert _looks_dependency_bound(src), (
        "守衛沒認出這支會碰外部依賴 —— 訊號清單太窄，新的說謊腳本會漏網")
    # 2. 沒有三態宣告 → 契約不合
    assert VERDICT_IMPORT not in src
    # 3. 而且它確實在說謊：依賴不在卻 exit 0 + 印 PASSED
    p = _run(liar, timeout=60)
    assert p.returncode == 0 and "ALL CHECKS PASSED" in p.stdout, (
        "植入的假腳本沒有表現出說謊行為，這條測試就失去意義")


def test_guard_does_not_flag_a_dependency_free_script(tmp_path):
    """反向：純函式自檢（無外部依賴）不該被要求遷移。

    守死一邊很容易 —— 把所有腳本都判違規也能讓上面那條過。這條守另一邊：
    沒有依賴的腳本用兩態 exit 是**正確的**，硬逼它們三態就是為測試改程式碼。
    """
    clean = tmp_path / "check-pure.py"
    clean.write_text(
        "#!/usr/bin/env python3\n"
        '"""純函式自檢，不碰任何外部依賴。"""\n'
        "assert 1 + 1 == 2\n"
        "print('ALL CHECKS PASSED')\n", encoding="utf-8")
    assert not _looks_dependency_bound(clean.read_text(encoding="utf-8")), (
        "守衛把無依賴的腳本也判成依賴型 —— 那會製造假紅，"
        "而且會逼出一堆為了過測試而寫的三態樣板")
