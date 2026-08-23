"""回歸測試：audit 每一行必須記錄「誰寫的、用什麼配置、跑哪版程式碼」。

## 背景（2026-08-21 ~ 08-23）

這台機器上有**兩個 launchd service 各自跑決策、共寫同一份 `agency-audit.jsonl`**：

| | `task-executor` | `agentos-aris-bridge` |
|---|---|---|
| python | `laapenv/bin/python` 3.12 | `/opt/homebrew/bin/python3` 3.14 |
| PYTHONPATH | `.:../laap-AGI` | 未設 |
| env | `SCORING_ROUTER_ENABLED=1` `SCORING_YOLO_MODE=0` | 無 |

`cwd` 相同 → 載入同一份 `agency.py`（原始碼沒混雜），但**兩個跑不同 scoring
配置、各自 `open("a")` append、無鎖，而每一行都沒有記錄來源進程**。

後果：`advantage` 的差異有一部分來自「哪個進程寫的」而不是「學到了什麼」，
事後無法拆開。舊的 1099 筆已經無法救 —— 這裡守的是**新資料不重複這個病**。

盤點那 1099 筆的實際成分：234 筆 (21.3%) 的 prompt 含 "test"（其中 158 筆是
一模一樣的 `test query 作法`），68 筆的 prompt 是某個 agent 的
`<system-reminder>` 系統提示（07-17~07-26，已停）。真正乾淨的只有 797 筆。

## 為什麼也守程式碼版本

2026-08-21 我們花一整天分析一份資料，最後發現寫它的進程跑的是 22 小時前的
舊碼。一行 `ps` 就能發現，但沒人想到要查。**資料的產生者也有版本，而版本
不會出現在資料裡** —— 除非把它寫進去。

## 這裡刻意**不**守的

- **無鎖 append 的併發安全**：POSIX 對 `O_APPEND` 的小寫入是原子的，所以
  行不會互相截斷；真正的問題是「分不出來源」，那才是這裡修的。
- **`MAX_MUTATIONS_PER_PASS` / `_too_similar` / `_recent_queries`**：指定不動。
  預算排擠（合併把升層額度吃光）是設計決策，等 Ryan 定；`_too_similar`
  沒擋住重複 prompt 是**舊碼行為**，重啟後才知道還在不在 —— 現在改會讓人
  分不清是修好了還是本來就不會再犯。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# 下游讀取端實際會讀的既有欄位。這些的名稱與語義**不得改變**。
# 來源：.patches/run-sspan.py、laap/s_span_bench.py（choice/outcome）、
#       scripts/morning-brief.py（ts/need/ok）、scripts/backtest-c-a.py
LEGACY_FIELDS = {
    "ts": 1755780000.0, "need": "competence", "tool": "gbrain",
    "prompt": "測試 prompt", "ok": True, "result_len": 42, "mem_id": None,
    "outcome": 0.7, "expected": 0.5, "rpe": 0.2, "exploration": 0.15,
}

PROVENANCE_KEYS = {
    "src_service",          # 哪個 service（區分那兩個 launchd job）
    "src_pid",              # 進程
    "src_py",               # 3.12 vs 3.14
    "src_exe",              # laapenv vs homebrew
    "src_code",             # 程式碼版本（22 小時舊碼那件事）
    "src_scoring_router",   # SCORING_ROUTER_ENABLED
    "src_scoring_yolo",     # SCORING_YOLO_MODE
}


@pytest.fixture
def audited(tmp_path, monkeypatch):
    """把 AUDIT_PATH 指到 tmp，回 (寫入函式, 讀取函式)。"""
    from laap import agency
    path = tmp_path / "agency-audit.jsonl"
    monkeypatch.setattr(agency, "AUDIT_PATH", path)

    def write(entry: dict) -> None:
        agency.AgencyLoop._audit(dict(entry))

    def rows() -> list:
        if not path.exists():
            return []
        return [json.loads(ln) for ln in path.read_text(
            encoding="utf-8").splitlines() if ln.strip()]

    return write, rows


# ── 不變式 1：新資料必須帶得出來源 ────────────────────────────────────

def test_audit_row_carries_provenance(audited):
    write, rows = audited
    write(LEGACY_FIELDS)
    row = rows()[0]
    missing = PROVENANCE_KEYS - set(row)
    assert not missing, (
        f"audit 行缺少來源欄位 {sorted(missing)} —— "
        f"兩個 service 寫同一份檔案時分不出誰寫的")


def test_provenance_identifies_the_writing_service(audited, monkeypatch):
    """`NEURALIS_SERVICE` 是 launchd plist 該設的顯式標籤，設了就要照用。"""
    import importlib
    from laap import agency
    monkeypatch.setenv("NEURALIS_SERVICE", "task-executor")
    importlib.reload(agency)
    try:
        assert agency._PROVENANCE["src_service"] == "task-executor"
        assert not agency._PROVENANCE["src_service"].startswith("?"), (
            "顯式設定的服務名不該被標成推測值")
    finally:
        monkeypatch.delenv("NEURALIS_SERVICE", raising=False)
        importlib.reload(agency)


def test_guessed_service_is_marked_as_a_guess(monkeypatch):
    """沒有顯式標籤時只能靠 sys.executable 推 —— 推測值必須可分辨。

    這條防的是「猜測被當成事實」：如果推測值和顯式值長得一樣，分析的人
    無法知道 `src_service` 是它自己說的還是我們猜的。這跟這條線一路在修的
    「把一種狀態偽裝成另一種」同型。

    conftest.py 會替整個 pytest session 設 NEURALIS_SERVICE=pytest，
    所以這裡必須先清掉才驗得到推測路徑 —— 不清的話這條測試永遠不會真的跑到。
    """
    from laap import agency
    monkeypatch.delenv("NEURALIS_SERVICE", raising=False)
    guessed = agency._service_name()
    assert guessed.startswith("?"), (
        f"推測出的服務名 {guessed!r} 沒有標成推測 —— "
        f"讀的人會把猜測當成事實")


def test_scoring_config_recorded_and_unset_is_none(audited, monkeypatch):
    """兩個 service 的行為差異來源就是這兩個 env，必須逐行記下。

    未設 = None，不是 ""：在 shell 裡「沒設」與「設成空字串」是兩件事，
    而它們對 scoring 的影響不同。壓成同一個值就是丟掉資訊。
    """
    import importlib
    from laap import agency
    monkeypatch.setenv("SCORING_ROUTER_ENABLED", "1")
    monkeypatch.delenv("SCORING_YOLO_MODE", raising=False)
    importlib.reload(agency)
    try:
        assert agency._PROVENANCE["src_scoring_router"] == "1"
        assert agency._PROVENANCE["src_scoring_yolo"] is None, (
            "未設的 env 應為 None（不是空字串）—— 否則分不出「沒設」與「設成空」")
    finally:
        monkeypatch.delenv("SCORING_ROUTER_ENABLED", raising=False)
        importlib.reload(agency)


def test_code_version_is_recorded_and_never_empty():
    """程式碼版本必須有值。

    「查不到版本」與「沒有版本」不同，下游要能分辨 —— 所以 git 取不到時
    退回 mtime，而不是留空。mtime 至少能答「是不是同一份檔案」，那正是
    「舊碼跑了 22 小時」那次需要的資訊。
    """
    from laap import agency
    v = agency._code_version()
    assert v and isinstance(v, str), "程式碼版本不得為空"
    assert v.startswith(("git:", "mtime:")) or v == "unknown", (
        f"版本字串要能看出來源（git / mtime），得到 {v!r}")


def test_two_configs_are_distinguishable_in_one_file(audited, monkeypatch):
    """核心情境：同一份檔案裡兩個不同配置的行，必須能被拆開。

    這就是 2026-08-21 抓到的那個問題 —— 修好之後它必須不再成立。
    """
    import importlib
    from laap import agency

    write, rows = audited
    write(LEGACY_FIELDS)          # 先取得 path
    audited_path = agency.AUDIT_PATH

    def write_as(service, router, yolo):
        monkeypatch.setenv("NEURALIS_SERVICE", service)
        if router is None:
            monkeypatch.delenv("SCORING_ROUTER_ENABLED", raising=False)
        else:
            monkeypatch.setenv("SCORING_ROUTER_ENABLED", router)
        if yolo is None:
            monkeypatch.delenv("SCORING_YOLO_MODE", raising=False)
        else:
            monkeypatch.setenv("SCORING_YOLO_MODE", yolo)
        importlib.reload(agency)
        monkeypatch.setattr(agency, "AUDIT_PATH", audited_path)
        agency.AgencyLoop._audit(dict(LEGACY_FIELDS))

    try:
        write_as("task-executor", "1", "0")
        write_as("agentos-aris-bridge", None, None)
        data = rows()
        by_service = {r["src_service"]: r for r in data if "src_service" in r}
        assert "task-executor" in by_service and \
            "agentos-aris-bridge" in by_service, \
            f"兩個 service 的行分不出來：{sorted(by_service)}"
        assert by_service["task-executor"]["src_scoring_router"] == "1"
        assert by_service["agentos-aris-bridge"]["src_scoring_router"] is None, (
            "兩個 service 的 scoring 配置在資料裡必須不同 —— "
            "否則 advantage 的差異仍然分不出是配置還是學習")
    finally:
        for k in ("NEURALIS_SERVICE", "SCORING_ROUTER_ENABLED", "SCORING_YOLO_MODE"):
            monkeypatch.delenv(k, raising=False)
        importlib.reload(agency)


# ── 不變式 2：既有欄位一字不動 ────────────────────────────────────────

def test_legacy_fields_are_untouched(audited):
    """下游讀 need / tool / outcome / ts / ok —— 名稱與值都必須原樣。"""
    write, rows = audited
    write(LEGACY_FIELDS)
    row = rows()[0]
    for k, v in LEGACY_FIELDS.items():
        assert k in row, f"既有欄位 {k} 消失了 —— 下游讀取端會壞"
        assert row[k] == v, f"既有欄位 {k} 的值被改了：{v!r} → {row[k]!r}"


def test_caller_entry_wins_over_provenance(audited):
    """呼叫端傳的欄位優先。

    provenance 是**補充**，不是覆寫。如果 provenance 能蓋掉 entry，
    某天新增一個同名欄位就會靜默改掉既有語義。
    """
    write, rows = audited
    write({**LEGACY_FIELDS, "src_pid": "CALLER_VALUE"})
    assert rows()[0]["src_pid"] == "CALLER_VALUE"


def test_caller_dict_is_not_mutated(audited):
    """`_audit` 不准改呼叫端的 dict —— 呼叫端可能還要拿它做別的事。"""
    from laap import agency
    entry = dict(LEGACY_FIELDS)
    before = dict(entry)
    agency.AgencyLoop._audit(entry)
    assert entry == before, f"呼叫端的 entry 被就地改掉了：{entry}"


def test_provenance_keys_do_not_collide_with_legacy():
    """新鍵與既有鍵不得有交集 —— 有交集就是在改既有語義。"""
    from laap import agency
    overlap = set(agency._PROVENANCE) & set(LEGACY_FIELDS)
    assert not overlap, f"新增欄位與既有欄位撞名：{sorted(overlap)}"


def test_row_is_valid_single_line_json(audited):
    """每筆一行、可 json.loads。無鎖 append 下多行 entry 會互相截斷。"""
    from laap import agency
    write, rows = audited
    write(LEGACY_FIELDS)
    write(LEGACY_FIELDS)
    raw = agency.AUDIT_PATH.read_text(encoding="utf-8")
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    assert len(lines) == 2
    for ln in lines:
        json.loads(ln)          # 不炸即可


# ── 不變式 3：舊資料（無 src_*）不能讓讀取端炸掉 ──────────────────────

def test_readers_tolerate_rows_without_provenance():
    """舊的 1099 筆沒有 src_* 欄位，讀取端必須容忍混合資料。"""
    from laap import s_span_bench as sb
    old = {"ts": 1, "need": "competence", "tool": "gbrain", "outcome": 0.7}
    new = {"src_service": "task-executor", "src_pid": 1729, "src_code": "git:abc",
           "ts": 2, "need": "competence", "tool": "qmd", "outcome": 0.3}
    recs = [{"choice": f'{r["need"]}|{r["tool"]}',
             "outcome": r.get("outcome", 0)} for r in (old, new)]
    v = sb.learning_verdict(recs, iters=50)
    assert v["n_records"] == 2, "混合資料被吃掉了"
    assert sb.realized_advantage(recs) is not None
    assert sb.behavior_entropy([r["choice"] for r in recs]) > 0
    # morning-brief 的讀法：純 .get()，舊筆缺欄位要回預設而不是 KeyError
    for r in (old, new):
        assert r.get("need", "?") != "?"
        r.get("src_service", "(舊筆無此欄)")


def test_s_span_reader_ignores_new_fields():
    """新增欄位對下游不可見 —— 它們讀既有鍵，不做 schema 驗證。"""
    from laap import s_span_bench as sb
    with_prov = [{"choice": "competence|gbrain", "outcome": 0.7,
                  "src_service": "task-executor", "src_code": "git:abc"},
                 {"choice": "competence|qmd", "outcome": 0.2,
                  "src_service": "agentos-aris-bridge", "src_code": "git:abc"}]
    plain = [{k: v for k, v in r.items() if not k.startswith("src_")}
             for r in with_prov]
    assert sb.realized_advantage(with_prov) == sb.realized_advantage(plain), (
        "新增欄位改變了下游計算結果 —— 那就不是「純新增」了")


# ── 不變式 4：不碰指定不動的東西 ──────────────────────────────────────

def test_patch_did_not_touch_out_of_scope_knobs():
    """結構守衛：`MAX_MUTATIONS_PER_PASS` / `_too_similar` 維持原狀。

    預算排擠是設計決策（等 Ryan 決定）；`_too_similar` 沒擋住重複 prompt 是
    **舊碼行為**，重啟後才知道還在不在 —— 現在改會讓人分不清「修好了」
    還是「本來就不會再犯」。
    """
    src = (ROOT / "laap" / "agency.py").read_text(encoding="utf-8")
    assert "_too_similar" in src, "_too_similar 被移除了（本輪不該碰它）"
    assert "def _audit" in src
    cons = (ROOT / "laap" / "consolidation.py").read_text(encoding="utf-8")
    assert "MAX_MUTATIONS_PER_PASS = 5" in cons, (
        "MAX_MUTATIONS_PER_PASS 被改了 —— 那是設計決策，不在本輪範圍")


def test_provenance_computed_once_not_per_write(audited):
    """provenance 在 import 時算一次。

    每行 audit 都跑 `git rev-parse` 子進程會拖慢決策迴圈，而這些值在一個
    process 的生命週期內不會變。這條也順便防「有人把它改成每次重算」。
    """
    write, rows = audited
    calls = []
    real = subprocess.run

    def counting_run(*a, **kw):
        if a and isinstance(a[0], (list, tuple)) and "rev-parse" in " ".join(
                str(x) for x in a[0]):
            calls.append(a[0])
        return real(*a, **kw)

    import unittest.mock as mock
    with mock.patch.object(subprocess, "run", counting_run):
        for _ in range(5):
            write(LEGACY_FIELDS)
    assert not calls, (
        f"寫 audit 時跑了 {len(calls)} 次 git 子進程 —— "
        f"provenance 應該在 import 時算一次")
    assert len(rows()) == 5


# ══════════════════════════════════════════════════════════════════
# 不變式 5：靜默失敗必須留下痕跡
# ══════════════════════════════════════════════════════════════════
# `_audit()` 與 consolidation `_loop()` 原本失敗時只 `logger.warning`。
# 而下一步是「重啟後累積新資料」—— 寫入靜默失敗的話，我們會**再等一次
# 永遠不會來的資料**（2026-08-21 已經發生過一次：以為在累積，其實是舊碼在寫）。
#
# 要的性質：**失敗留下事後查得到、而且看得出是失敗的痕跡**，
# 不是只在某個 log 裡印一行沒人會看的 warning。
#
# 硬要求：**不得改變成功路徑的行為。**

@pytest.fixture
def trail(tmp_path, monkeypatch):
    """把 failure sentinel 指到 tmp，並清掉 in-process 計數。"""
    from laap import failure_trail
    path = tmp_path / "audit-failures.jsonl"
    monkeypatch.setattr(failure_trail, "FAILURE_PATH", path)
    monkeypatch.setattr(failure_trail, "_counts", {})
    return failure_trail, path


def test_success_path_leaves_no_failure_trail(audited, trail):
    """成功時 sentinel 不得出現 —— 它的存在本身就是訊號。"""
    ft, path = trail
    write, rows = audited
    write(LEGACY_FIELDS)
    assert len(rows()) == 1, "成功路徑寫入行為改變了"
    assert not path.exists(), (
        "成功時產生了失敗記錄 —— 那會讓 sentinel 失去「存在即異常」的意義")
    assert ft.failure_count() == 0


def test_audit_write_failure_is_recorded_not_swallowed(audited, trail, tmp_path,
                                                      monkeypatch):
    """audit 寫入失敗必須留下痕跡，而不是只印一行 warning。"""
    from laap import agency
    ft, path = trail
    # 指到一個不存在的目錄 → open("a") 必然失敗
    monkeypatch.setattr(agency, "AUDIT_PATH",
                        tmp_path / "no_such_dir" / "agency-audit.jsonl")
    agency.AgencyLoop._audit(dict(LEGACY_FIELDS))
    assert path.exists(), (
        "audit 寫入失敗卻沒有留下任何事後查得到的痕跡 —— "
        "我們會以為資料在累積")
    row = json.loads(path.read_text(encoding="utf-8").strip())
    assert row["kind"] == "agency_audit_write"
    assert "error" in row and row["error"], "沒記下失敗原因"
    assert ft.failure_count("agency_audit_write") == 1


def test_failure_record_identifies_what_was_lost(audited, trail, tmp_path,
                                                 monkeypatch):
    """痕跡要能答「丟掉的是哪些決策」，不只是「有東西丟了」。"""
    from laap import agency
    ft, path = trail
    monkeypatch.setattr(agency, "AUDIT_PATH", tmp_path / "nope" / "a.jsonl")
    agency.AgencyLoop._audit(dict(LEGACY_FIELDS))
    row = json.loads(path.read_text(encoding="utf-8").strip())
    assert row.get("lost_need") == LEGACY_FIELDS["need"]
    assert row.get("lost_tool") == LEGACY_FIELDS["tool"]
    assert row.get("lost_ts") == LEGACY_FIELDS["ts"]


def test_audit_failure_does_not_kill_the_decision_loop(audited, trail, tmp_path,
                                                       monkeypatch):
    """審計壞掉不得升級成「Aris 停止決策」—— 要吵，但不要致命。"""
    from laap import agency
    ft, path = trail
    monkeypatch.setattr(agency, "AUDIT_PATH", tmp_path / "nope" / "a.jsonl")
    for _ in range(3):
        agency.AgencyLoop._audit(dict(LEGACY_FIELDS))   # 不得 raise
    assert ft.failure_count("agency_audit_write") == 3, "連續失敗要累計"


def test_failure_trail_survives_its_own_write_failure(trail, monkeypatch, capsys):
    """連 sentinel 都寫不進去時，必須至少吼到 stderr（不留無聲路徑）。"""
    ft, path = trail
    monkeypatch.setattr(ft, "FAILURE_PATH",
                        Path("/nonexistent-root-dir/cannot-write.jsonl"))
    ft.record("agency_audit_write", RuntimeError("原始失敗"))   # 不得 raise
    err = capsys.readouterr().err
    assert "failure_trail" in err and "原始失敗" in err, (
        f"連 sentinel 都寫不進去時完全無聲：{err!r}")


def test_consolidation_pass_failure_is_recorded(trail, monkeypatch):
    """固化 pass 失敗必須留下痕跡 —— 否則它會一輪輪安靜地失敗。

    舊行為：`_loop` 每 interval 秒重試，失敗只印 warning，
    外面看起來就像「固化在跑」。
    """
    from laap.consolidation import ConsolidationLoop
    ft, path = trail
    cons = ConsolidationLoop(psi=None, interval=0.01, idle_s=0)

    def boom():
        raise RuntimeError("gbrain 掛了")

    monkeypatch.setattr(cons, "run_pass", boom)
    cons._running = True

    import threading
    t = threading.Thread(target=cons._loop, daemon=True)
    t.start()
    for _ in range(100):
        if ft.failure_count("consolidation_pass") >= 1:
            break
        time.sleep(0.02)
    cons._running = False
    t.join(timeout=2)

    assert ft.failure_count("consolidation_pass") >= 1, (
        "固化 pass 失敗沒有留下痕跡 —— 它會一輪輪安靜地失敗")
    assert path.exists()
    kinds = {json.loads(ln)["kind"]
             for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()}
    assert "consolidation_pass" in kinds


def test_consolidation_failure_does_not_stop_the_daemon(trail, monkeypatch):
    """daemon 執行緒不得因 pass 失敗而死 —— 死掉會讓固化完全停止且更難發現。"""
    from laap.consolidation import ConsolidationLoop
    ft, path = trail
    cons = ConsolidationLoop(psi=None, interval=0.01, idle_s=0)
    monkeypatch.setattr(cons, "run_pass",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    cons._running = True
    import threading
    t = threading.Thread(target=cons._loop, daemon=True)
    t.start()
    for _ in range(150):
        if ft.failure_count("consolidation_pass") >= 2:
            break
        time.sleep(0.02)
    still_alive = t.is_alive()
    cons._running = False
    t.join(timeout=2)
    assert ft.failure_count("consolidation_pass") >= 2, (
        "第一次失敗後迴圈就停了 —— 應該繼續嘗試並累計")
    assert still_alive, "daemon 執行緒因 pass 失敗而死掉"


def test_sentinel_file_is_separate_from_the_audit_it_guards():
    """失敗記錄不得寫回被守護的那份檔案。

    主 audit 寫不進去時（磁碟滿／權限／路徑消失），它自己就是不可信的地方 ——
    把失敗記錄寫回同一個檔案等於沒記。
    """
    from laap import agency, consolidation, failure_trail
    assert failure_trail.FAILURE_PATH != agency.AUDIT_PATH
    assert failure_trail.FAILURE_PATH != consolidation.AUDIT_PATH


def test_failure_trail_never_raises():
    """`record()` 在任何情況下都不得 raise —— 呼叫端是決策迴圈與 daemon。"""
    from laap import failure_trail as ft

    class Nasty(Exception):
        def __str__(self):
            raise RuntimeError("連 str() 都會炸")

    ft.record("weird_kind", Nasty())          # 不得 raise
    ft.record("weird_kind", "字串也可以")
    ft.record("weird_kind", ValueError("x"), unserialisable=object())
