"""結構守衛：patch／合併流程的殘留不得偽造 `src_code` 的 `-dirty`。

## 背景（2026-08-21 稽核）

`laap/agency.py:_code_version()` 用 `git status --porcelain` 判斷工作區是否乾淨，
結果寫進每一筆 audit 的 `src_code`。那個 porcelain **刻意不加
`--untracked-files=no`** —— `git apply` 建立新檔但不 `git add`，patch 帶進來的
新模組是 untracked 的，必須算 dirty。

副作用：**任何**未追蹤檔案都會讓 `src_code` 變 `-dirty`，即使一行碼都沒改。
而**假的 `-dirty` 事後無法跟真的區分** —— 那批資料永久標錯。

三個來源，三問（逐一實測過）：
  1. 這個 patch 產生什麼           → `audit-failures.jsonl`（p5 處理）
  2. 我們教對方跑的指令產生什麼      → `*.rej` / `*.orig`
  3. 我們交給對方的東西會留在哪裡    → `*.patch` / `*.diff`（每輪都在丟）

第 3 項最後才被想到：前兩項是某個動作的副作用，第 3 項沒有動作 ——
東西就在那裡，因為我們給了，所以它不在「工具會產生什麼」的搜尋空間裡。

## 這裡守兩個方向（缺一個就是半個解）

正向：上列殘留必須被 ignore。
**反向：不得過度矯正** —— `brain/consumers.yaml.bak` 是**已追蹤**檔案，
裸 `*.bak` 會遮蔽它（`git check-ignore --no-index` 驗得到）。
只擋 patch／編輯器產生的形態。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# 會偽造 dirty 的殘留（相對 repo 根）
LEFTOVERS = [
    "laap/agency.py.rej",       # patch --reject
    "laap/agency.py.orig",      # patch --backup
    "laap/agency.py.bak",       # 編輯器／手動備份
    "laap/#agency.py#",         # Emacs 自動存檔（`#` 在 gitignore 是註解，需轉義）
    ".merge_file_abc123",       # git 合併暫存
    "laap/agency.BASE.py",      # 合併衝突殘留
    "laap/agency.LOCAL.py",
    "laap/agency.REMOTE.py",
    "p5-audit-provenance.patch",  # **我們自己交給對方的檔案**
    "somefix.diff",
]


def _ignored(rel: str) -> bool:
    """這個路徑會被 .gitignore 排除嗎（不看是否已追蹤）。"""
    r = subprocess.run(["git", "check-ignore", "--no-index", "-q", rel],
                       cwd=ROOT, capture_output=True)
    return r.returncode == 0


@pytest.mark.skipif(not shutil.which("git"), reason="需要 git")
@pytest.mark.parametrize("rel", LEFTOVERS)
def test_patch_leftover_is_ignored(rel: str):
    """每一種殘留都必須被 ignore，否則它一出現就讓 src_code 說謊。"""
    assert _ignored(rel), (
        f"{rel} 沒有被 .gitignore 排除 —— 它一出現就會讓 src_code 變假 -dirty，"
        f"而假 dirty 事後無法跟真 dirty 區分")


@pytest.mark.skipif(not shutil.which("git"), reason="需要 git")
def test_no_over_correction_on_tracked_files():
    """反向：ignore pattern 不得遮蔽**已追蹤**的檔案。

    只守正向很容易 —— 加一行 `*` 也能讓上面全部通過。這條守另一邊。
    """
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT,
                             capture_output=True, text=True).stdout.split()
    shadowed = [f for f in tracked if _ignored(f)]
    assert not shadowed, (
        f"這些**已追蹤**的檔案會被 .gitignore 遮蔽：{shadowed}。"
        f"已追蹤檔案的修改仍看得到，但刪掉再重建就會靜默消失，而且語義上誤導")


@pytest.mark.skipif(not shutil.which("git"), reason="需要 git")
def test_emacs_pattern_is_escaped():
    """`#` 在 gitignore 是註解字元 —— Emacs 的 `#*#` 未轉義時完全不生效。

    這條釘住那個轉義，因為它「看起來已經加了」但實際無效 ——
    正是本輪一路在修的「看起來在運作，實際失去效力」。
    """
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "\\#*#" in text, (
        "Emacs 自動存檔 pattern 沒有轉義成 `\\#*#` —— 未轉義的 `#*#` 是註解，不生效")


def test_rationale_is_documented():
    """理由必須寫在 .gitignore 裡。

    只有規則沒有理由的話，下一個人會把它當成整潔設定而順手刪掉 ——
    而它其實是資料正確性設定。
    """
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "src_code" in text, "沒有寫明這些行與 src_code 的關係"
    assert "-dirty" in text, "沒有寫明它們會造成假 -dirty"


@pytest.mark.skipif(not shutil.which("git"), reason="需要 git")
def test_code_version_actually_reports_dirty():
    """`_code_version()` 真的會標 `-dirty` —— 否則上面全部是純整潔設定。

    2026-08-23 加這條：p6 交付時本 repo 的 `_code_version()` 只回 `git:<sha>`，
    沒有任何 dirty 判斷。那樣的話 .gitignore 擋不擋殘留，對 audit 的 src_code
    一點影響都沒有 —— **整個 patch 的理由基礎不存在，但四條測試照樣全綠。**
    這條把理由與實作綁在一起：驗的不是「有沒有寫 porcelain」（那是文本表面），
    而是「同一份 repo 在 dirty 與否兩種狀態下，回傳值必須不同」。
    """
    from laap import agency
    v = agency._code_version()
    assert v.startswith("git:"), f"這個 repo 有 git，版本卻不是 git:*：{v!r}"
    st = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                        capture_output=True, text=True)
    is_dirty = bool(st.stdout.strip())
    assert v.endswith("-dirty") == is_dirty, (
        f"src_code 說 {'dirty' if v.endswith('-dirty') else 'clean'}，"
        f"但 git status 說 {'dirty' if is_dirty else 'clean'}：{v!r}")
