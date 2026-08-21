"""回歸測試：自檢腳本在「依賴不在」時不得印綠燈 —— 且修完仍抓得到真問題。

## 背景

`brain/drift.py` 已因這個病修過一次（`tests/test_drift_missing_upstream.py`）：
上游 404 卻印「✅ 全部同步」exit 0。同一個病在四支 `scripts/check-*.py` 上
原封不動地存在：

| 腳本 | 修前實測（Linux 沙盒，無 gbrain / 無 Rust daemon / :11546 不在） |
|---|---|
| `check-memory-gbrain.py` | 印 `B/C. gbrain backend: SKIP（binary 不存在）` 後仍印 `ALL CHECKS PASSED`，exit 0。docstring 自稱驗證「gbrain store → 新實例 recall」，實際上那段一行都沒跑 |
| `check-rust-psi-backend.py` | daemon 不在 → `FileNotFoundError` 被 `except Exception` 吞掉（後續檢查全部靜默消失），摘要印「⚠️ 有 WARN 項目」exit 0 |
| `check-stream.py` | `E. 線上 E2E: SKIP（:11546 不在）` 後仍印 `ALL STREAM CHECKS PASSED`，exit 0 |
| `check-watchdog.py` | 無 `lsof` → `print("SKIP: 需要 lsof"); return` → exit 0，五段全部沒跑 |

## 這裡守的兩個不變式（兩個都要，缺一個就是假解）

1. **沒驗到 ≠ 綠燈。** 依賴不在時：exit 2、且不得印 `ALL CHECKS PASSED`。
2. **修完仍抓得到真問題。** 「讓腳本少做事」或「永遠報紅」都能讓不變式 1
   變綠，而且測試看不出來。所以每支都額外植入一個**真的壞掉的依賴**，
   斷言腳本必須 exit 1 —— 偵測力沒被換掉。

## 刻意不做的事

- 不試圖在沙盒裡讓 gbrain / Rust daemon / `:11546` 真的跑通。
  那是環境問題（要 Ryan 本機），不在這裡的範圍。
- 不把「依賴不在」判成 fail。那是假紅，而 `guard.yml` 寫過
  「假紅比沒有更糟 —— 人會學會無視紅燈」。
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

EXIT_OK, EXIT_FAIL, EXIT_UNVERIFIED = 0, 1, 2

# 「這支綠了」的訊號 —— CI 與人都 grep 這句，所以沒驗到時不准出現
GREEN_PHRASES = ("ALL CHECKS PASSED", "ALL STREAM CHECKS PASSED",
                 "ALL WATCHDOG CHECKS PASSED", "全部通過")


def run_script(name: str, *args: str, env_extra: dict | None = None,
               timeout: int = 300, path_prepend: str | None = None):
    """跑 scripts/<name>，回 CompletedProcess。PATH 可加前綴（植入假依賴用）。"""
    env = {**os.environ}
    env.setdefault("NEURALIS_CONSTITUTION", "off")
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    if path_prepend:
        env["PATH"] = path_prepend + os.pathsep + env["PATH"]
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, str(SCRIPTS / name), *args],
                          cwd=ROOT, env=env, capture_output=True, text=True,
                          timeout=timeout)


def assert_not_green(out: str, script: str) -> None:
    for phrase in GREEN_PHRASES:
        assert phrase not in out, (
            f"{script} 沒驗到卻印了「{phrase}」—— 這就是綠燈說謊：\n{out[-2500:]}")


def assert_says_unverified(out: str, script: str) -> None:
    assert "沒驗到" in out, (
        f"{script} 應明說「沒驗到」而不是靜默 SKIP：\n{out[-2500:]}")


def write_exe(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


# ══════════════════════════════════════════════════════════════════
# 共用層：_check_verdict 的語義（三態的地基）
# ══════════════════════════════════════════════════════════════════

def test_verdict_unknown_is_neither_green_nor_fail():
    sys.path.insert(0, str(SCRIPTS))
    from _check_verdict import Verdict, EXIT_OK, EXIT_FAIL, EXIT_UNVERIFIED

    v = Verdict("t")
    v.ok("驗過的那段")
    assert v.exit_code() == EXIT_OK

    v.unknown("依賴不在的那段")
    assert v.exit_code() == EXIT_UNVERIFIED, "沒驗到被算成綠燈或失敗"
    assert "ALL CHECKS PASSED" not in v.summary(), "有段沒驗到還印 PASSED"

    v.fail("真的壞的那段")
    assert v.exit_code() == EXIT_FAIL, "有 FAIL 時 unknown 不該蓋掉它"


def test_verdict_warn_stays_green():
    """降級警告是「驗到了、可接受」，不是「沒驗到」—— 不該變成 exit 2。"""
    sys.path.insert(0, str(SCRIPTS))
    from _check_verdict import Verdict, EXIT_OK

    v = Verdict("t")
    v.ok("a")
    v.warn("非關鍵降級")
    assert v.exit_code() == EXIT_OK
    assert "ALL CHECKS PASSED" in v.summary()


def test_verdict_guard_turns_exception_into_fail():
    """腳本自己炸掉是真問題，不是「沒驗到」。
    舊 check-rust-psi-backend.py 把 FileNotFoundError 吞成 exit 0。"""
    sys.path.insert(0, str(SCRIPTS))
    from _check_verdict import Verdict, guard, EXIT_FAIL

    v = Verdict("t")
    with guard(v, "某段"):
        raise FileNotFoundError("/no/such/daemon")
    assert v.exit_code() == EXIT_FAIL, "例外被吞掉了"


# ══════════════════════════════════════════════════════════════════
# 1. check-memory-gbrain.py —— 四支裡最嚴重的那支
# ══════════════════════════════════════════════════════════════════

@pytest.mark.skipif(shutil.which("gbrain") is not None,
                    reason="本機有 gbrain binary，這條驗的是「binary 不在」的行為")
def test_memory_gbrain_no_binary_is_unverified_not_green():
    """docstring 承諾驗「gbrain store → 新實例 recall」。binary 不在時那段
    一行都沒跑 —— 那不是通過，是沒驗到。"""
    p = run_script("check-memory-gbrain.py")
    out = p.stdout + p.stderr
    assert_not_green(out, "check-memory-gbrain.py")
    assert_says_unverified(out, "check-memory-gbrain.py")
    assert p.returncode == EXIT_UNVERIFIED, (
        f"gbrain 不在應 exit 2（沒驗到），得到 {p.returncode}：\n{out[-2500:]}")


def test_memory_gbrain_local_only_mode_is_also_unverified():
    """`NEURALIS_MEMORY_BACKEND=local` 是「我明知不驗 gbrain」。
    local 那段是真的驗過（exit 0 沒錯），但不准聲稱驗了 gbrain 後端。"""
    p = run_script("check-memory-gbrain.py",
                   env_extra={"NEURALIS_MEMORY_BACKEND": "local"})
    out = p.stdout + p.stderr
    assert p.returncode in (EXIT_OK, EXIT_UNVERIFIED), (
        f"local 模式不該紅：{p.returncode}\n{out[-2000:]}")
    assert "gbrain" not in out.split("═" * 56)[-1] or "沒驗到" in out, (
        f"local 模式的摘要不得暗示 gbrain 後端驗過了：\n{out[-1500:]}")


def test_memory_gbrain_detects_a_really_broken_backend(tmp_path):
    """**偵測力測試**：植入一個存在但壞掉的 gbrain（呼叫全部回錯）。
    腳本必須報紅 —— 不能因為「怕假紅」就把真壞掉也放過。"""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    # 一個真的 gbrain serve 會講 JSON-RPC；這隻收到什麼都回 error。
    write_exe(fake_bin / "gbrain", f"""#!{sys.executable}
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except Exception:
        continue
    if msg.get("id") is None:
        continue
    if msg.get("method") == "initialize":
        print(json.dumps({{"jsonrpc": "2.0", "id": msg["id"], "result": {{
            "protocolVersion": "2024-11-05", "capabilities": {{}},
            "serverInfo": {{"name": "broken-gbrain", "version": "0"}}}}}}), flush=True)
    else:
        print(json.dumps({{"jsonrpc": "2.0", "id": msg["id"],
                          "error": {{"code": -1, "message": "backend is broken"}}}}),
              flush=True)
""")
    p = run_script("check-memory-gbrain.py", path_prepend=str(fake_bin),
                   env_extra={"NEURALIS_MEMORY_BACKEND": "auto"}, timeout=240)
    out = p.stdout + p.stderr
    assert p.returncode == EXIT_FAIL, (
        f"gbrain 存在但完全壞掉，腳本卻沒報紅（exit {p.returncode}）—— "
        f"偵測力被修掉了：\n{out[-2500:]}")
    assert_not_green(out, "check-memory-gbrain.py")


# ══════════════════════════════════════════════════════════════════
# 2. check-rust-psi-backend.py
# ══════════════════════════════════════════════════════════════════

DAEMON = ROOT / "rust" / "target" / "release" / "psi-daemon"


@pytest.mark.skipif(DAEMON.is_file(), reason="本機有 Rust daemon")
def test_rust_psi_no_daemon_is_unverified_not_green():
    p = run_script("check-rust-psi-backend.py", "--all")
    out = p.stdout + p.stderr
    assert_not_green(out, "check-rust-psi-backend.py")
    assert_says_unverified(out, "check-rust-psi-backend.py")
    assert p.returncode == EXIT_UNVERIFIED, (
        f"daemon 不在應 exit 2，得到 {p.returncode}：\n{out[-2500:]}")


@pytest.mark.skipif(DAEMON.is_file(), reason="本機有 Rust daemon")
def test_rust_psi_daemon_section_does_not_swallow_exception():
    """修前：FileNotFoundError 被 `except Exception` 吞掉，後面所有檢查
    靜默消失，仍 exit 0。腳本自己炸掉不該變成綠燈。"""
    p = run_script("check-rust-psi-backend.py", "--all")
    out = p.stdout + p.stderr
    assert "腳本例外" not in out, (
        f"daemon 不在應被判為「沒驗到」，不是讓腳本裸炸：\n{out[-2000:]}")
    # 不含 daemon 的那些段（remap / fallback / FIFO no-daemon）是真的驗過的，
    # 必須還在 —— 否則就是「讓腳本少做事」那種假解。
    assert "remap" in out or "B." in out, f"純 Python 段消失了：\n{out[-2000:]}"


def test_rust_psi_detects_a_really_broken_daemon(tmp_path, monkeypatch):
    """**偵測力測試**：植入一個「存在但什麼都不做」的 psi-daemon。
    它不寫 state 檔、tick 不推進 —— 腳本必須報紅。"""
    fake = tmp_path / "psi-daemon"
    write_exe(fake, "#!/usr/bin/env bash\nsleep 30\n")
    p = run_script("check-rust-psi-backend.py", "--all",
                   env_extra={"NEURALIS_PSI_DAEMON": str(fake)}, timeout=180)
    out = p.stdout + p.stderr
    assert p.returncode == EXIT_FAIL, (
        f"daemon 存在但什麼都不做，腳本卻沒報紅（exit {p.returncode}）：\n"
        f"{out[-2500:]}")


# ══════════════════════════════════════════════════════════════════
# 3. check-stream.py
# ══════════════════════════════════════════════════════════════════

def _port_11546_alive() -> bool:
    import socket
    try:
        with socket.create_connection(("localhost", 11546), timeout=1):
            return True
    except OSError:
        return False


@pytest.mark.skipif(_port_11546_alive(), reason=":11546 活著")
def test_stream_offline_e2e_is_unverified_not_green():
    p = run_script("check-stream.py", timeout=180)
    out = p.stdout + p.stderr
    assert_not_green(out, "check-stream.py")
    assert_says_unverified(out, "check-stream.py")
    assert p.returncode == EXIT_UNVERIFIED, (
        f":11546 不在應 exit 2，得到 {p.returncode}：\n{out[-2500:]}")


@pytest.mark.skipif(_port_11546_alive(), reason=":11546 活著")
def test_stream_offline_still_runs_the_local_sections():
    """A-D 段不需要 :11546，是真的可驗的。它們必須還在跑 ——
    「因為 E 沒驗到就整支不跑」是把偵測力一起關掉。"""
    p = run_script("check-stream.py", timeout=180)
    out = p.stdout + p.stderr
    for seg in ("工具串流時序", "execute drain", "SSE 解析", "交錯"):
        assert seg in out, f"本地可驗的段「{seg}」不見了：\n{out[-2500:]}"


def test_stream_detects_a_really_broken_pipeline(tmp_path):
    """**偵測力測試**：把 stream-test 工具的逐步輸出拆掉（改成整塊回傳），
    A 段的時序斷言必須紅。"""
    p = run_script("check-stream.py", timeout=180,
                   env_extra={"NEURALIS_CHECK_STREAM_SABOTAGE": "1"})
    out = p.stdout + p.stderr
    assert p.returncode == EXIT_FAIL, (
        f"串流被改成整塊回傳，腳本卻沒報紅（exit {p.returncode}）：\n{out[-2500:]}")


# ══════════════════════════════════════════════════════════════════
# 4. check-watchdog.py
# ══════════════════════════════════════════════════════════════════

def test_watchdog_missing_lsof_is_unverified_not_green(tmp_path):
    """修前：無 lsof → `print("SKIP: 需要 lsof"); return` → exit 0，
    五段一段都沒跑。用一個只有 python 的最小 PATH 模擬。"""
    stub = tmp_path / "bin"
    stub.mkdir()
    # 只留必要工具，刻意不放 lsof
    for tool in ("bash", "curl", "pkill", "sleep", "seq", "nohup", "true"):
        src = shutil.which(tool)
        if src:
            (stub / tool).symlink_to(src)
    p = subprocess.run(
        [sys.executable, str(SCRIPTS / "check-watchdog.py")],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
        env={"PATH": str(stub), "PYTHONPATH": str(ROOT),
             "NEURALIS_CONSTITUTION": "off",
             "HOME": os.environ.get("HOME", str(tmp_path))})
    out = p.stdout + p.stderr
    assert_not_green(out, "check-watchdog.py")
    assert_says_unverified(out, "check-watchdog.py")
    assert p.returncode == EXIT_UNVERIFIED, (
        f"缺 lsof 應 exit 2（沒驗到），得到 {p.returncode}：\n{out[-2500:]}")


@pytest.mark.skipif(shutil.which("lsof") is None, reason="需要 lsof 才能真跑")
def test_watchdog_detects_a_really_broken_watchdog(tmp_path):
    """**偵測力測試**：把 watchdog.sh 換成一個永遠什麼都不做的版本。
    「死了要重起」等段必須紅 —— 證明五段不是裝飾品。

    注意：`timeout 25` 造成的 exit=124 是量測方法的問題（實測需 ~26s），
    不是腳本缺口 —— 所以這裡給足時間，不去修不存在的問題。
    """
    stub_root = tmp_path / "repo"
    stub_root.mkdir()
    (stub_root / "scripts").mkdir()
    # 假 watchdog：只印一行就成功退出，什麼都不重啟
    write_exe(stub_root / "scripts" / "watchdog.sh",
              "#!/usr/bin/env bash\necho 'noop watchdog'\nexit 0\n")
    p = run_script("check-watchdog.py", timeout=300,
                   env_extra={"NEURALIS_WATCHDOG_SCRIPT":
                              str(stub_root / "scripts" / "watchdog.sh")})
    out = p.stdout + p.stderr
    assert p.returncode == EXIT_FAIL, (
        f"watchdog 換成 no-op，腳本卻沒報紅（exit {p.returncode}）：\n{out[-2500:]}")
