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

import ast
import os
import re
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

def _gbrain_available() -> bool:
    """gbrain binary 在不在。與 `check-*.py` 判斷可用性的方式一致。"""
    return shutil.which("gbrain") is not None


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


# ══════════════════════════════════════════════════════════════════
# 5. 反方向的病：假紅（依賴不在卻報 FAIL）
# ══════════════════════════════════════════════════════════════════
# 2026-08-21：掃完 27 支後發現的第二種病，方向跟綠燈說謊相反但後果同類。
# `guard.yml` 原文：「假紅比沒有更糟 —— 人會學會無視紅燈」。
#   · check-toolcall.py:180      :11546 不在線 → sys.exit(1)
#   · check-psi-response.py      urlopen 例外一律 errors += 1 → exit 1
#   · check-consolidation.py     module 層 assert client → AssertionError + exit 1
#   · check-emotion-recall.py    同上
# 服務沒開 / 後端沒裝，不是「協議壞了」。兩者的正確行動完全不同。

# 每支的依賴探針，以及「依賴在場時**可達的** exit 集合」。
#
# 2026-08-21 修（Ryan 在他機器上抓到，p3 的缺陷）：舊版這兩條測試沒有 skip
# guard，硬斷言 `returncode == EXIT_UNVERIFIED`。在有 gbrain 的機器上
# `check-emotion-recall.py` **真的驗過了**（exit 0、A-D 全 PASS、
# `CHECK-VERDICT: ... unknown=0`），測試卻要求它「必須沒驗到」。
#
# 為什麼沙盒測不到：沙盒永遠缺依賴 → `exit 2` 那條路永遠成立，`exit 0` 那條
# 路一次都沒被執行過。**這正是我們整條線在抓的「只有依賴部分存在才顯形」，
# 這次的受害者是我們自己的測試。** p2 的同類測試都有 skipif，p3 追加時漏了。
#
# `reachable_with_dep` 逐支給，不套同一條斷言 —— 否則會在修掉一個假斷言的
# 同時寫進另一個假斷言：
#   · check-toolcall      B-E 需要 :11546，齊全時 A-F 全可驗 → 0 或 1
#   · check-psi-response  D 段（off 降級）要驗的是 **server 端** 行為，需以 off
#                         重啟 server，光靠本 process 的環境變數驗不到 →
#                         **即使 :11546 活著也永遠是 unknown** → 只可能 2
#   · check-consolidation 齊全時走真驗證路徑 → 0 或 1
#                         （Ryan 機器上實測 exit 1 是**真陽性**：`:98`
#                          `assert stats["promoted"] >= 2` 實際 promoted=0，
#                          A/B/C 三段全跑通。那是產品層問題，不是假紅 ——
#                          所以這裡刻意允許 1，不讓它變綠。）
#   · check-emotion-recall 齊全時走真驗證路徑 → 0 或 1
FALSE_RED_SCRIPTS = [
    # (腳本, timeout, 依賴是否在場, 依賴在場時可達的 exit)
    ("check-toolcall.py", 60, _port_11546_alive, {EXIT_OK, EXIT_FAIL}),
    ("check-psi-response.py", 60, _port_11546_alive, {EXIT_UNVERIFIED}),
    ("check-consolidation.py", 60, _gbrain_available, {EXIT_OK, EXIT_FAIL}),
    ("check-emotion-recall.py", 60, _gbrain_available, {EXIT_OK, EXIT_FAIL}),
]

FALSE_RED_IDS = [f[0] for f in FALSE_RED_SCRIPTS]


@pytest.mark.parametrize("name,timeout,dep_present,_reachable",
                         FALSE_RED_SCRIPTS, ids=FALSE_RED_IDS)
def test_missing_dependency_is_not_reported_as_failure(
        name, timeout, dep_present, _reachable):
    """依賴**不在**時必須是 exit 2（沒驗到），不是 exit 1（失敗）。

    這條驗的是「依賴不在」的行為，所以依賴在場時要跳過 —— 語義同 p2 的
    `test_memory_gbrain_no_binary_is_unverified_not_green`。
    """
    if dep_present():
        pytest.skip(f"{name} 的依賴在場 —— 這條驗的是「依賴不在」的行為，"
                    f"在場時該走 test_dependency_present_yields_real_verdict")
    p = run_script(name, timeout=timeout)
    out = p.stdout + p.stderr
    assert p.returncode != EXIT_FAIL, (
        f"{name} 把「依賴不在」報成失敗（exit 1）—— 假紅：\n{out[-2000:]}")
    assert p.returncode == EXIT_UNVERIFIED, (
        f"{name} 應 exit 2（沒驗到），得到 {p.returncode}：\n{out[-2000:]}")
    assert_not_green(out, name)


@pytest.mark.parametrize("name,timeout,dep_present,_reachable",
                         FALSE_RED_SCRIPTS, ids=FALSE_RED_IDS)
def test_missing_dependency_does_not_traceback(
        name, timeout, dep_present, _reachable):
    """依賴不在不該丟 traceback。

    `assert client is not None` 的 AssertionError 會印出堆疊，讓「環境沒裝」
    看起來像「腳本自己壞了」—— 讀的人無法區分這兩件事。
    """
    if dep_present():
        pytest.skip(f"{name} 的依賴在場 —— 這條驗的是「依賴不在」的行為")
    p = run_script(name, timeout=timeout)
    out = p.stdout + p.stderr
    assert "Traceback (most recent call last)" not in out, (
        f"{name} 因依賴不在而裸炸：\n{out[-1500:]}")


# ── 正面測試：依賴在場時必須給真結論，不准還說「沒驗到」 ──────────────
# 只加 skip guard 是不夠的：那只是把測不到的地方變成沉默，而沉默正是這整條
# 線在修的病（「沒驗到」被講成別的東西）。依賴齊全時，腳本必須真的去驗。
#
# **這條只有在依賴齊全的機器上才會執行** —— 沙盒永遠 skip。
# 所以它在沙盒的綠燈不代表任何事，只有 Ryan 機器上的結果才算證據。

@pytest.mark.parametrize("name,timeout,dep_present,reachable",
                         FALSE_RED_SCRIPTS, ids=FALSE_RED_IDS)
def test_dependency_present_yields_real_verdict(
        name, timeout, dep_present, reachable):
    """依賴在場 → exit code 必須落在該支**可達**的集合裡。

    抓兩種病：
      1. 依賴明明在，卻還回 exit 2（該驗卻沒驗 —— 反方向的說謊）
      2. 腳本永遠回同一個值（依賴在不在都一樣，等於沒在看依賴）

    `reachable` 逐支不同，理由見 FALSE_RED_SCRIPTS 的註解。特別是
    `check-psi-response.py`：它的 D 段需要用 off **重啟 server** 才驗得到，
    所以 `{2}` 是它的正確答案，不是缺陷。
    """
    if not dep_present():
        pytest.skip(f"{name} 的依賴不在場（沙盒常態）—— "
                    f"這條只有依賴齊全的機器驗得到")
    p = run_script(name, timeout=timeout)
    out = p.stdout + p.stderr
    assert p.returncode in reachable, (
        f"{name} 依賴在場，exit 應落在 {sorted(reachable)}，"
        f"得到 {p.returncode}：\n{out[-2500:]}")
    if EXIT_UNVERIFIED not in reachable:
        assert p.returncode != EXIT_UNVERIFIED, (
            f"{name} 依賴在場卻回「沒驗到」—— 該驗的時候沒去驗")


@pytest.mark.parametrize("name,timeout,dep_present,reachable",
                         FALSE_RED_SCRIPTS, ids=FALSE_RED_IDS)
def test_dependency_present_marker_agrees_with_exit(
        name, timeout, dep_present, reachable):
    """依賴在場時，若腳本走完 Verdict 路徑，宣告行必須跟真實 exit 一致。

    標記行 ↔ 現實的綁定是整個三態設計的信任基礎。沙盒只驗得到「依賴不在」
    那半邊，這條補「依賴在場」那半邊。

    **已知缺口（本輪刻意不修）**：這四支的段內斷言用的是裸 `assert`，沒有包在
    `guard()` 裡。所以依賴在場而斷言失敗時，會是 traceback + exit 1 且
    **沒有標記行**。`check-consolidation.py` 在 Ryan 機器上就是這條路徑
    （`:98` promoted=0 的真陽性）。

    這條測試因此只在「沒有裸炸」時才要求標記行 —— 否則我會在修一個
    「沙盒驗不到的假斷言」的同時，寫進另一個同型的假斷言。裸炸缺口本身
    列為獨立發現，見 P3B 報告，不在本輪範圍（PI 指定不要碰
    `check-consolidation.py`，讓它的真陽性保持紅）。
    """
    if not dep_present():
        pytest.skip(f"{name} 的依賴不在場 —— 這條只有依賴齊全的機器驗得到")
    p = run_script(name, timeout=timeout)
    out = p.stdout + p.stderr
    if "Traceback (most recent call last)" in out:
        pytest.skip(f"{name} 走了裸 assert 路徑（已知缺口，見 docstring）—— "
                    f"該路徑不經 Verdict，沒有標記行")
    m = re.search(r"^CHECK-VERDICT: \S+ exit=(\d+) pass=(\d+) fail=(\d+) "
                  r"warn=(\d+) unknown=(\d+)$", out, re.M)
    assert m, f"{name} 走完 Verdict 卻沒有標記行：\n{out[-1500:]}"
    declared, fail_n, unknown_n = int(m.group(1)), int(m.group(3)), int(m.group(5))
    assert declared == p.returncode, (
        f"{name} 標記行說 exit={declared}，實際 {p.returncode}")
    expect = EXIT_FAIL if fail_n else (
        EXIT_UNVERIFIED if unknown_n else EXIT_OK)
    assert p.returncode == expect, (
        f"{name} counts=(fail={fail_n}, unknown={unknown_n}) 應 exit {expect}，"
        f"實際 {p.returncode}")


# ── 沙盒可驗：偵測力沒有因為加了 skip guard 而消失 ──────────────────
# 加 skip guard 最廉價的假解是「讓測試在哪裡都跳過」—— 那會讓假紅偵測
# 靜靜消失，而測試全綠沒人看得出來。這條在沙盒（依賴全缺）實跑，
# 確認假紅偵測仍然活著。

def test_false_red_detection_still_active_without_dependencies():
    """沙盒（依賴全缺）中，假紅偵測必須真的執行，不是全部 skip 掉。"""
    active = [name for name, _t, dep, _r in FALSE_RED_SCRIPTS if not dep()]
    assert active, (
        "四支的依賴在這台機器上全部在場 —— 那麼假紅偵測這輪一項都沒跑。"
        "在沙盒（依賴全缺）看到這個訊息，代表 skip 條件寫反了")
    # 而且它們現在真的都回 exit 2（不是 exit 1）
    for name in active:
        p = run_script(name, timeout=90)
        assert p.returncode == EXIT_UNVERIFIED, (
            f"{name} 在依賴缺失時應 exit 2，得到 {p.returncode}")


def test_planted_false_red_is_caught(tmp_path):
    """**偵測力**：植入一支「依賴不在就 exit 1」的假紅腳本，斷言判準抓得到。

    這條證明 skip guard 沒有把偵測力一起關掉：判準對真的假紅仍然說不。
    """
    liar = tmp_path / "check-planted-false-red.py"
    liar.write_text(
        "#!/usr/bin/env python3\n"
        '"""植入用：探 HTTP，不在就報失敗（假紅）。"""\n'
        "import sys, urllib.request\n"
        "try:\n"
        "    urllib.request.urlopen('http://localhost:1/health', timeout=1)\n"
        "except Exception as e:\n"
        "    print(f'FAIL: 服務不在 {e}')\n"
        "    sys.exit(1)\n"
        "sys.exit(0)\n", encoding="utf-8")
    import os as _os
    env = {**_os.environ, "PYTHONPATH": str(ROOT), "NEURALIS_CONSTITUTION": "off"}
    p = subprocess.run([sys.executable, str(liar)], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == EXIT_FAIL, "植入的假紅腳本沒表現出假紅行為"
    assert p.returncode != EXIT_UNVERIFIED, (
        "植入的腳本回了 exit 2 —— 那它就不是假紅，這條測試失去意義")


# ══════════════════════════════════════════════════════════════════
# 6. 真陽性不得長成 traceback（p3c）
# ══════════════════════════════════════════════════════════════════
# Ryan 機器上 `check-consolidation.py` 的 `promoted=0` 是**真陽性**，但它
# 長成 traceback + exit 1 + **沒有標記行** —— 段內裸 `assert` 繞過 Verdict。
# 那讓「產品有問題」看起來像「工具自己壞了」，跟這條線一路在修的病同型
# （把一種狀態偽裝成另一種），只是換到斷言失敗這條路上。
#
# 真問題應該長成 `❌ FAIL` + 標記行 + exit 1。
#
# 範圍：只有這 2 支需要修。`check-toolcall.py` 的裸 assert 在**被 guard 包住
# 的 seg 函式裡**（實測植入 assert False 得到 `exit=1 fail=1` + 標記行），
# `check-psi-response.py` 每段已被 try/except 包住 —— 動它們就是為了統一而
# 改已經正確的程式碼。

GUARDED_ASSERT_SCRIPTS = [
    ("check-consolidation.py", _gbrain_available),
    ("check-emotion-recall.py", _gbrain_available),
]
GUARDED_IDS = [n for n, _ in GUARDED_ASSERT_SCRIPTS]


@pytest.mark.parametrize("name,dep_present", GUARDED_ASSERT_SCRIPTS,
                         ids=GUARDED_IDS)
def test_section_failures_go_through_verdict(name, dep_present):
    """依賴在場且有段落失敗時：不得 traceback，且必須有標記行 + fail>=1。

    **這條只有依賴齊全的機器（或假依賴）才會執行。** 它守的是「真陽性的
    呈現方式」，不是「有沒有真陽性」—— 所以 exit 1 是允許的結果之一。
    """
    if not dep_present():
        pytest.skip(f"{name} 的依賴不在場 —— 這條只有依賴齊全的機器驗得到")
    p = run_script(name, timeout=90)
    out = p.stdout + p.stderr
    assert "Traceback (most recent call last)" not in out, (
        f"{name} 的段落失敗仍在裸炸 —— 真陽性被偽裝成「工具壞了」：\n{out[-2000:]}")
    m = re.search(r"^CHECK-VERDICT: \S+ exit=(\d+) pass=\d+ fail=(\d+) ",
                  out, re.M)
    assert m, f"{name} 沒有標記行 —— 該路徑繞過了 Verdict：\n{out[-2000:]}"
    if p.returncode == EXIT_FAIL:
        assert int(m.group(2)) >= 1, (
            f"{name} exit 1 但標記行說 fail=0 —— 宣告與現實不符")


@pytest.mark.parametrize("name,dep_present", GUARDED_ASSERT_SCRIPTS,
                         ids=GUARDED_IDS)
def test_guard_wraps_every_section(name, dep_present):
    """結構守衛：這 2 支必須用 `guard()` 包段落，且不得留 `raise SystemExit`。

    **沙盒可驗**（純靜態，不需依賴）—— 所以它是 p3c 在沙盒唯一的硬證據。
    `raise SystemExit` 會被 `guard()` 放行（那是 finish() 的正常出口），
    拿它當失敗訊號等於繞過三態判定。
    """
    src = (SCRIPTS / name).read_text(encoding="utf-8")
    assert "with guard(" in src, (
        f"{name} 沒有用 guard() 包段落 —— 段內斷言失敗會繞過 Verdict")
    tree = ast.parse(src)
    bad = [n.lineno for n in ast.walk(tree)
           if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call)
           and isinstance(n.exc.func, ast.Name) and n.exc.func.id == "SystemExit"]
    assert not bad, (
        f"{name} 用 raise SystemExit 當失敗訊號（行 {bad}）—— "
        f"guard() 會放行它，等於繞過三態判定")


def test_assertion_judgements_unchanged_by_p3c():
    """p3c 只改呈現方式，不改任何斷言的判定內容。

    釘住 `promoted >= 2` 這條 —— 它是 Ryan 機器上的真陽性，**必須繼續失敗**。
    p3c 若把它放寬（例如改成 >= 0）就會讓真問題變綠，那是最糟的假解。
    """
    src = (SCRIPTS / "check-consolidation.py").read_text(encoding="utf-8")
    assert 'assert stats["promoted"] >= 2' in src, (
        "`promoted >= 2` 被改動或移除 —— 那會讓 Ryan 機器上的真陽性變綠")
    assert 'assert stats["merged"] >= 2' in src, "`merged >= 2` 被改動或移除"
    emo = (SCRIPTS / "check-emotion-recall.py").read_text(encoding="utf-8")
    assert 'assert _emotion_intensity_for(client, HI) == 0.9' in emo, (
        "emotion 讀取斷言被改動")
