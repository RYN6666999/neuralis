"""laap.audit 結案審計閘的測試。

這份測試的重點不是「證明它會過」，而是**反向測試**：每一個舊版放行過的
造假手法，這裡都植入一次，確認新版擋得下來。舊版的四個放行路徑：

1. manifest 換行 → 正則失配 → 完全不審計，原文放行
2. manifest 巢狀 → 正則截斷 → json 炸 → 假紅
3. `timeout(1.5)` → `signal.alarm(1.5)` TypeError → 任何輸入都回不了 PASS
4. 讀 Aris 自己寫的 log 搜 "ok" → 含 "token" 的垃圾就過關

另外測 worker thread（舊版 SIGALRM 在非主執行緒必炸）與 CLI exit code
（閘要是會 exit 1 的東西）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from laap.audit import audit_text, extract, run_gate  # noqa: E402
from laap.audit.gate import FAIL, INVALID, PASS  # noqa: E402
from laap.audit.manifest import Manifest  # noqa: E402
from laap.audit.verifiers import verify_cmd, verify_file, verify_http  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_ledger(tmp_path, monkeypatch):
    """每個測試用自己的 ledger，不要碰到真的那份。"""
    p = tmp_path / "ledger.jsonl"
    monkeypatch.setenv("LAAP_AUDIT_LEDGER", str(p))
    return p


def _manifest(**data) -> Manifest:
    return Manifest(raw=json.dumps(data), data=data)


# ───────────────────────── manifest 抽取 ─────────────────────────


def test_single_line_manifest_is_extracted():
    text = '[AUDIT_MANIFEST] {"task_id": "t1", "evidence_type": "file"}'
    got = extract(text)
    assert len(got) == 1
    assert got[0].data["task_id"] == "t1"


def test_reverse_multiline_manifest_no_longer_slips_through():
    """舊版 bug 1：換行的 manifest 正則完全不匹配，等於不審計就放行。"""
    text = '[AUDIT_MANIFEST] {\n  "task_id": "t1",\n  "evidence_type": "file"\n}'
    got = extract(text)
    assert len(got) == 1, "換行的 manifest 必須被抓到，不能靜默放行"
    assert got[0].data["task_id"] == "t1"


def test_reverse_nested_manifest_is_not_truncated():
    """舊版 bug 2：非貪婪正則把巢狀物件截斷，導致假紅。"""
    text = (
        '[AUDIT_MANIFEST] {"task_id": "t1", "evidence_type": "cmd", '
        '"evidence": {"argv": ["true"], "meta": {"deep": 1}}}'
    )
    got = extract(text)
    assert len(got) == 1
    assert got[0].ok, f"巢狀物件不該解析失敗: {got[0].error}"
    assert got[0].data["evidence"]["meta"]["deep"] == 1


def test_braces_inside_strings_do_not_break_matching():
    text = '[AUDIT_MANIFEST] {"task_id": "a}b{c", "evidence_type": "file"}'
    got = extract(text)
    assert len(got) == 1
    assert got[0].data["task_id"] == "a}b{c"


def test_escaped_quote_inside_string_is_handled():
    text = '[AUDIT_MANIFEST] {"task_id": "say \\"hi\\"", "evidence_type": "file"}'
    got = extract(text)
    assert len(got) == 1
    assert got[0].data["task_id"] == 'say "hi"'


def test_multiple_manifests_all_extracted():
    text = (
        '[AUDIT_MANIFEST] {"task_id": "a", "evidence_type": "file"}\n'
        'blah blah\n'
        '[AUDIT_MANIFEST] {"task_id": "b", "evidence_type": "file"}'
    )
    assert [m.data["task_id"] for m in extract(text)] == ["a", "b"]


def test_no_tag_returns_empty():
    assert extract("完全沒有標籤的一段話") == []


def test_malformed_json_is_recorded_not_silently_skipped():
    text = '[AUDIT_MANIFEST] {"task_id": "t1", oops}'
    got = extract(text)
    assert len(got) == 1
    assert not got[0].ok
    assert "JSON" in (got[0].error or "")


def test_unmatched_brace_is_recorded():
    text = '[AUDIT_MANIFEST] {"task_id": "t1"'
    got = extract(text)
    assert len(got) == 1
    assert not got[0].ok


def test_tag_in_prose_without_json_is_not_a_false_positive():
    """SKILL.md 那種說明格式的句子不該被當成真的宣告。"""
    text = "格式是 [AUDIT_MANIFEST] 後面接一個 JSON 物件，像這樣描述。"
    assert extract(text) == []


# ───────────────────────── cmd 驗證器（自己跑）─────────────────────────


def test_cmd_exit_zero_passes():
    ev = verify_cmd({"argv": ["true"]})
    assert ev.passed
    assert ev.detail["exit_code"] == 0


def test_reverse_cmd_exit_nonzero_fails():
    ev = verify_cmd({"argv": ["false"]})
    assert not ev.passed
    assert ev.detail["exit_code"] != 0


def test_cmd_expect_exit_can_be_nonzero():
    ev = verify_cmd({"argv": ["false"], "expect_exit": 1})
    assert ev.passed


def test_reverse_cmd_string_instead_of_argv_is_rejected():
    """不接受 shell 字串 —— 沒有 shell 就沒有注入面。"""
    ev = verify_cmd({"argv": "true && echo pwned"})
    assert not ev.passed
    assert "argv" in ev.reason


def test_reverse_missing_executable_fails():
    ev = verify_cmd({"argv": ["this-binary-does-not-exist-9f3a"]})
    assert not ev.passed
    assert "找不到可執行檔" in ev.reason


def test_reverse_cmd_timeout_fails():
    ev = verify_cmd({"argv": ["sleep", "5"], "timeout": 1})
    assert not ev.passed
    assert "逾時" in ev.reason


def test_cmd_reports_real_exit_code_of_a_real_test_run(tmp_path):
    """端到端：真的跑一個會失敗的 pytest，稽核必須看到它失敗。

    這正是舊版讀 log 搜字串搞錯的情境 —— 真的 pytest 綠燈輸出含 "0 failed"
    會被舊版判成失敗，而這裡我們根本不看輸出，只看 exit code。
    """
    failing = tmp_path / "test_x.py"
    failing.write_text("def test_x():\n    assert 1 == 2\n", encoding="utf-8")
    ev = verify_cmd(
        {"argv": [sys.executable, "-m", "pytest", "-q", str(failing)], "timeout": 60}
    )
    assert not ev.passed, "測試真的失敗時稽核必須 FAIL"

    passing = tmp_path / "test_y.py"
    passing.write_text("def test_y():\n    assert 1 == 1\n", encoding="utf-8")
    ev2 = verify_cmd(
        {"argv": [sys.executable, "-m", "pytest", "-q", str(passing)], "timeout": 60}
    )
    assert ev2.passed, "測試真的通過時稽核必須 PASS（舊版這裡會假紅）"


# ───────────────────────── file 驗證器 ─────────────────────────


def test_file_present_and_nonempty_passes(tmp_path):
    f = tmp_path / "out.txt"
    f.write_text("hello", encoding="utf-8")
    assert verify_file({"path": str(f)}).passed


def test_reverse_missing_file_fails(tmp_path):
    ev = verify_file({"path": str(tmp_path / "nope.txt")})
    assert not ev.passed


def test_reverse_empty_file_fails(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("", encoding="utf-8")
    ev = verify_file({"path": str(f)})
    assert not ev.passed
    assert "bytes" in ev.reason


def test_reverse_stale_artifact_fails(tmp_path):
    """拿三天前的舊產物交差要被擋下。"""
    f = tmp_path / "old.txt"
    f.write_text("x", encoding="utf-8")
    old = time.time() - 3 * 86400
    os.utime(f, (old, old))
    ev = verify_file({"path": str(f), "max_age_s": 3600})
    assert not ev.passed
    assert "舊產物" in ev.reason


def test_fresh_artifact_within_max_age_passes(tmp_path):
    f = tmp_path / "new.txt"
    f.write_text("x", encoding="utf-8")
    assert verify_file({"path": str(f), "max_age_s": 3600}).passed


# ───────────────────────── http 驗證器 ─────────────────────────


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/ok":
            body = b'{"status":"healthy"}'
            self.send_response(200)
        else:
            body = b"nope"
            self.send_response(500)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # 安靜
        pass


@pytest.fixture
def http_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def test_http_200_passes(http_server):
    assert verify_http({"url": f"{http_server}/ok"}).passed


def test_reverse_http_500_fails(http_server):
    ev = verify_http({"url": f"{http_server}/bad"})
    assert not ev.passed
    assert ev.detail["status"] == 500


def test_reverse_http_contains_mismatch_fails(http_server):
    ev = verify_http({"url": f"{http_server}/ok", "contains": "unhealthy"})
    assert not ev.passed


def test_reverse_non_http_scheme_rejected():
    ev = verify_http({"url": "file:///etc/passwd"})
    assert not ev.passed


# ───────────────────────── gate 迴歸 ─────────────────────────


def test_reverse_float_timeout_no_longer_kills_the_gate():
    """舊版 bug 3：`signal.alarm(1.5)` TypeError，任何輸入都回不了 PASS。"""
    m = _manifest(
        task_id="t1",
        evidence_type="cmd",
        evidence={"argv": ["true"], "timeout": 1.5},
    )
    v = run_gate(m)
    assert v.status == PASS, f"float timeout 不該讓閘崩潰，得到 {v.status}: {v.reason}"
    assert "Manifest 處理錯誤" not in v.reason


def test_reverse_gate_works_in_worker_thread():
    """舊版 bug：signal 只能在主執行緒用，Hermes worker thread 一律 ValueError。"""
    m = _manifest(task_id="t1", evidence_type="cmd", evidence={"argv": ["true"]})
    box = {}

    def run():
        box["v"] = run_gate(m)

    t = threading.Thread(target=run)
    t.start()
    t.join(timeout=30)
    assert "v" in box, "worker thread 沒跑完"
    assert box["v"].status == PASS, f"worker thread 得到 {box['v'].status}: {box['v'].reason}"


def test_unknown_evidence_type_is_invalid():
    m = _manifest(task_id="t1", evidence_type="tdd", evidence={})
    assert run_gate(m).status == INVALID


def test_missing_evidence_object_is_invalid():
    m = _manifest(task_id="t1", evidence_type="cmd")
    assert run_gate(m).status == INVALID


def test_unparseable_manifest_is_invalid_not_pass():
    m = Manifest(raw="{oops", error="JSON 解析失敗")
    v = run_gate(m)
    assert v.status == INVALID
    assert v.status != PASS


def test_legacy_audit_type_key_still_accepted():
    m = _manifest(task_id="t1", audit_type="cmd", evidence={"argv": ["true"]})
    assert run_gate(m).status == PASS


# ───────────────────────── audit_text + ledger ─────────────────────────


def test_audit_text_writes_ledger_even_on_fail(isolated_ledger):
    text = '[AUDIT_MANIFEST] {"task_id": "t1", "evidence_type": "cmd", "evidence": {"argv": ["false"]}}'
    report = audit_text(text, source="test")
    assert report.had_claims
    assert not report.all_passed
    assert isolated_ledger.exists(), "不管結果如何，ledger 一定要留一行"
    rows = [json.loads(x) for x in isolated_ledger.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["status"] == FAIL
    assert rows[0]["detail"]["argv"] == ["false"]


def test_audit_text_no_claims_is_quiet(isolated_ledger):
    report = audit_text("今天天氣很好", source="test")
    assert not report.had_claims
    assert report.render() == ""
    assert not isolated_ledger.exists()


def test_audit_text_caps_manifests_per_turn(isolated_ledger):
    one = '[AUDIT_MANIFEST] {"task_id": "t%d", "evidence_type": "cmd", "evidence": {"argv": ["true"]}}'
    text = "\n".join(one % i for i in range(8))
    report = audit_text(text, source="test")
    statuses = [v.status for v in report.verdicts]
    assert statuses.count(PASS) == 5
    assert INVALID in statuses, "超過上限的部分必須留痕，不能靜默丟掉"


def test_render_marks_failure_in_header():
    text = '[AUDIT_MANIFEST] {"task_id": "t1", "evidence_type": "cmd", "evidence": {"argv": ["false"]}}'
    out = audit_text(text, source="test").render()
    assert "未通過" in out
    assert "❌" in out


# ───────────────────────── 時間預算：不要被外部 SIGKILL ─────────────────────────


def test_budget_exhausted_marks_invalid_not_pass():
    """預算不夠時直接判 INVALID，不要開始一個注定被砍的驗證。"""
    m = _manifest(task_id="t1", evidence_type="cmd", evidence={"argv": ["true"]})
    v = run_gate(m, remaining_s=0.5)
    assert v.status == INVALID
    assert "預算耗盡" in v.reason


def test_budget_caps_declared_timeout(tmp_path):
    """manifest 宣告 300s，但預算只剩 3s → 實際只等 3s 就逾時，不是 300s。"""
    m = _manifest(
        task_id="t1",
        evidence_type="cmd",
        evidence={"argv": ["sleep", "30"], "timeout": 300},
    )
    t0 = time.time()
    v = run_gate(m, remaining_s=3)
    elapsed = time.time() - t0
    assert v.status == FAIL
    assert "逾時" in v.reason
    assert elapsed < 10, f"應該 3s 左右就收手，實際 {elapsed:.1f}s"
    assert v.detail["timeout_s"] == 3


def test_budget_does_not_mutate_caller_spec():
    """夾 timeout 用複製，不能改到呼叫端的 dict（immutability）。"""
    spec = {"argv": ["true"], "timeout": 300}
    m = _manifest(task_id="t1", evidence_type="cmd", evidence=spec)
    run_gate(m, remaining_s=5)
    assert spec["timeout"] == 300, "原始 spec 被改掉了"


def test_audit_text_budget_spans_multiple_manifests(isolated_ledger):
    """預算是整批共用的：第一筆吃光，後面幾筆要被判 INVALID 而不是靜默跳過。"""
    slow = '[AUDIT_MANIFEST] {"task_id": "slow", "evidence_type": "cmd", "evidence": {"argv": ["sleep", "30"], "timeout": 300}}'
    fast = '[AUDIT_MANIFEST] {"task_id": "fast", "evidence_type": "cmd", "evidence": {"argv": ["true"]}}'
    report = audit_text(slow + "\n" + fast, source="test", budget_s=3)
    assert len(report.verdicts) == 2
    assert report.verdicts[0].status == FAIL      # 逾時
    assert report.verdicts[1].status == INVALID   # 預算耗盡
    assert "預算耗盡" in report.verdicts[1].reason
    rows = [json.loads(x) for x in isolated_ledger.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2, "兩筆都必須留在 ledger，不能有一筆消失"


def test_no_budget_means_no_cap():
    """不給 budget 就照 manifest 宣告的 timeout 走（CLI 手動跑的情境）。"""
    spec = {"argv": ["true"], "timeout": 7}
    m = _manifest(task_id="t1", evidence_type="cmd", evidence=spec)
    v = run_gate(m)
    assert v.status == PASS


# ───────────────────────── CLI：閘要會 exit 1 ─────────────────────────


def _run_cli(text: str, ledger: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["LAAP_AUDIT_LEDGER"] = str(ledger)
    env["PYTHONPATH"] = str(REPO)
    return subprocess.run(
        [sys.executable, "-m", "laap.audit"],
        input=text,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
        timeout=90,
    )


def test_cli_exits_1_on_failed_claim(isolated_ledger):
    text = '[AUDIT_MANIFEST] {"task_id": "t1", "evidence_type": "cmd", "evidence": {"argv": ["false"]}}'
    proc = _run_cli(text, isolated_ledger)
    assert proc.returncode == 1, f"閘必須 exit 1。stdout={proc.stdout} stderr={proc.stderr}"


def test_cli_exits_0_on_passing_claim(isolated_ledger):
    text = '[AUDIT_MANIFEST] {"task_id": "t1", "evidence_type": "cmd", "evidence": {"argv": ["true"]}}'
    proc = _run_cli(text, isolated_ledger)
    assert proc.returncode == 0, f"stdout={proc.stdout} stderr={proc.stderr}"


def test_cli_exits_0_when_no_claims(isolated_ledger):
    proc = _run_cli("沒有任何宣告", isolated_ledger)
    assert proc.returncode == 0


def test_cli_exits_1_on_unparseable_manifest(isolated_ledger):
    proc = _run_cli('[AUDIT_MANIFEST] {"task_id": "t1", broken}', isolated_ledger)
    assert proc.returncode == 1, "壞掉的 manifest 不能當作沒看見"
