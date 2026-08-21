"""回歸測試：上游 repo 消失（404）必須讓 drift 偵測器出聲。

2026-08-20：`lorryjovens-hub/laap-AGI` 404 了，而 `brain/drift.py` 印
「✅ 全部同步」、exit 0。兩層失效疊在一起：
  · `check_git` 在本地目錄不存在時就早退，**遠端根本沒查** —— 所以在 CI／新機器
    上永遠不會發現上游整個沒了
  · `main()` 只把 `drift`/`stale` 算失敗，404 落在 `unknown`，不觸發非零 exit

根因不是少寫一個狀態，是把「我沒去查」「網路壞了」「它不存在」三種語義壓進同一個
`unknown`，而三者的正確行動完全不同。

這裡守的不變式：**偵測器在它存在的全部理由所對應的最壞情況下必須出聲**，
同時離線／限流不得變成假紅（`guard.yml`：假紅比沒有更糟，人會學會無視紅燈）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from brain import drift


@pytest.fixture
def no_local(tmp_path):
    """一個一定不存在的本地路徑，逼 check_git 走「本地沒 checkout」那條。"""
    return {"id": "x", "label": "測試上游", "kind": "git",
            "local": tmp_path / "nope", "repo": "someone/gone-repo",
            "branch": "main", "owner": "someone（不是你）"}


def _fake_get(mapping):
    """把 drift._get 換成查表，不打網路。"""
    def _get(url):
        for frag, resp in mapping.items():
            if frag in url:
                return resp
        return {"_error": "HTTP Error 404: Not Found"}
    return _get


# ── 不變式 1：404 必須是 gone，且 gone 必須算失敗 ──

def test_remote_404_is_gone_not_unknown(monkeypatch, no_local):
    monkeypatch.setattr(drift, "_get", _fake_get(
        {"repos/someone/gone-repo": {"_error": "HTTP Error 404: Not Found"}}))
    r = drift.check_git(no_local)
    assert r["status"] == "gone", (
        f"上游 404 被判成 {r['status']!r} —— 舊版就是這樣印出「全部同步」的"
    )


def test_gone_counts_as_failure():
    assert "gone" in drift.FAIL_STATUS, "gone 不算失敗 → exit 0 → 沒人會知道"


def test_gone_has_a_marker():
    assert drift.MARK.get("gone"), "gone 沒有顯示符號會 KeyError"


# ── 不變式 2：離線／限流不得變成假紅 ──

def test_network_error_stays_unknown_and_does_not_fail(monkeypatch, tmp_path):
    """限流（403）、DNS 失敗這類錯誤是「沒驗到」，不是「不存在」。
    算失敗會製造假紅，兩週後就會有人把這支加上 --quiet。"""
    cfg = {"id": "x", "label": "測試", "kind": "git", "local": tmp_path / "nope",
           "repo": "someone/rate-limited", "branch": "main", "owner": "x"}
    monkeypatch.setattr(drift, "_get", _fake_get(
        {"repos/someone/rate-limited": {"_error": "HTTP Error 403: rate limit exceeded"}}))
    r = drift.check_git(cfg)
    assert r["status"] == "unknown"
    assert "unknown" not in drift.FAIL_STATUS


# ── 不變式 3：本地沒 checkout 時仍然要查遠端 ──

def test_missing_local_still_probes_remote(monkeypatch, no_local):
    """舊版在本地目錄不存在時直接 return，遠端一次都沒問過。"""
    called = []

    def _get(url):
        called.append(url)
        return {"_error": "HTTP Error 404: Not Found"}

    monkeypatch.setattr(drift, "_get", _get)
    drift.check_git(no_local)
    assert any("someone/gone-repo" in u for u in called), (
        "本地沒 checkout 就不查遠端 → CI／新機器上永遠發現不了上游消失"
    )


# ── 不變式 4：main() 的 exit code 與摘要行 ──

def test_main_exits_nonzero_when_upstream_gone(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(drift, "CHECKS", [
        {"id": "x", "label": "測試上游", "kind": "git", "local": tmp_path / "nope",
         "repo": "someone/gone-repo", "branch": "main", "owner": "x"}])
    monkeypatch.setattr(drift, "_get", _fake_get(
        {"someone/gone-repo": {"_error": "HTTP Error 404: Not Found"}}))
    monkeypatch.setattr(drift.sys, "argv", ["drift.py"])

    rc = drift.main()
    out = capsys.readouterr().out

    assert rc != 0, "上游消失卻 exit 0"
    assert "全部同步" not in out, f"上游消失還印「全部同步」：\n{out}"


def test_unknown_does_not_print_all_synced(monkeypatch, capsys, tmp_path):
    """查不到就是查不到，不能印成綠燈 —— 那是把「沒驗到」講成「沒問題」。"""
    monkeypatch.setattr(drift, "CHECKS", [
        {"id": "x", "label": "測試上游", "kind": "git", "local": tmp_path / "nope",
         "repo": "someone/offline", "branch": "main", "owner": "x"}])
    monkeypatch.setattr(drift, "_get", _fake_get(
        {"someone/offline": {"_error": "urlopen error [Errno -3] Temporary failure"}}))
    monkeypatch.setattr(drift.sys, "argv", ["drift.py"])

    rc = drift.main()
    out = capsys.readouterr().out

    assert rc != 1, "離線不該假紅（1 是「要行動」）"
    assert "全部同步" not in out, f"查不到卻印「全部同步」：\n{out}"


# ── 不變式 5：三態 exit code（docstring 第 18 行的承諾）──────────────
# drift.py 的 docstring 一直寫著「exit 1 = 有漂移。exit 2 = 查不到」，
# 但實作只有 0/1 —— 「查不到」被併進 0，自動化讀不出「沒驗到」與「沒問題」的差別。
# 這是 Researcher 那條線交叉比對抓到的：行為修好了，但 docstring 承諾的三態沒到。

def test_exit_2_when_only_unknown(monkeypatch, capsys, tmp_path):
    """離線／限流：不是失敗（不能假紅），也不是綠燈（沒驗到）→ 需要第三個 code。"""
    monkeypatch.setattr(drift, "CHECKS", [
        {"id": "x", "label": "t", "kind": "git", "local": tmp_path / "nope",
         "repo": "someone/offline", "branch": "main", "owner": "o"}])
    monkeypatch.setattr(drift, "_get", _fake_get(
        {"someone/offline": {"_error": "urlopen error [Errno -3] Temporary failure"}}))
    monkeypatch.setattr(drift.sys, "argv", ["drift.py"])
    assert drift.main() == 2


def test_gone_still_beats_unknown_for_exit_code(monkeypatch, capsys, tmp_path):
    """同時有 gone 與 unknown 時，exit 必須是 1（要行動的優先）。"""
    monkeypatch.setattr(drift, "CHECKS", [
        {"id": "a", "label": "gone one", "kind": "git", "local": tmp_path / "n1",
         "repo": "someone/gone-repo", "branch": "main", "owner": "o"},
        {"id": "b", "label": "offline one", "kind": "git", "local": tmp_path / "n2",
         "repo": "someone/offline", "branch": "main", "owner": "o"}])
    monkeypatch.setattr(drift, "_get", _fake_get({
        "someone/gone-repo": {"_error": "HTTP Error 404: Not Found"},
        "someone/offline": {"_error": "urlopen error [Errno -3] Temporary failure"}}))
    monkeypatch.setattr(drift.sys, "argv", ["drift.py"])
    assert drift.main() == 1


def test_docstring_exit_codes_match_implementation():
    """docstring 承諾的 exit code 必須真的存在於實作 —— 這條測試本身就是
    為了防「文件寫下正確設計但實作未跟上」這個模式再次發生。"""
    import inspect
    import re
    doc = inspect.getdoc(drift) or ""
    promised = {int(m) for m in re.findall(r"exit (\d)", doc)}
    src = inspect.getsource(drift.main)
    implemented = {int(m) for m in re.findall(r"return (\d)", src)}
    missing = promised - implemented
    assert not missing, f"docstring 承諾 exit {sorted(missing)} 但 main() 不會回這個值"
