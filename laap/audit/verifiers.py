"""證據驗證器 —— 全部走「自己重新推導」，不讀被稽核方寫的東西。

鐵律
----
**事實只能推導，不能複製。** 舊版 `verify_test_log()` 的做法是打開 Aris 指定
的 log 檔、搜尋 "passed" 字樣 —— 那是複製，而且複製的是被稽核方自己寫的檔。
它的兩個方向都壞掉：真的 pytest 輸出含 "0 failed" 被判失敗，而任何含
"token" 的垃圾（"ok" 是子字串）被判通過。

這裡改成：稽核器**自己執行**那條指令、**自己發**那個請求、**自己 stat**
那個檔案，只採信自己量到的結果。

誠實邊界（不要宣稱做不到的事）
------------------------------
Aris 與稽核器跑在同一個使用者底下，Aris 本來就有 terminal 工具。因此：
* 這不是安全邊界。Aris 若刻意造假，可以宣告 `["true"]` 當測試指令。
* 這是**誠實輔助**：ledger 會逐字記下實際跑的 argv 與 exit code，讓造假
  變成「留在稽核軌跡裡、你翻得到」的東西，而不是一句沒人能查的「已完成」。
* 舊版的 `.fingerprint` 自簽 MD5 假裝解決了這件事（同目錄、同使用者、無
  密鑰，改完重簽即可過關），所以整個 anchor.py 被移除而不是修好。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_TIMEOUT_S = 30
MAX_TIMEOUT_S = 300
_OUTPUT_TAIL_CHARS = 800


@dataclass
class Evidence:
    """一次推導的結果。`detail` 進 ledger，是之後對帳的唯一依據。"""

    passed: bool
    reason: str
    detail: Dict[str, Any] = field(default_factory=dict)


def _tail(text: str, limit: int = _OUTPUT_TAIL_CHARS) -> str:
    if len(text) <= limit:
        return text
    return "…(截斷)…" + text[-limit:]


def _coerce_timeout(raw: Any) -> int:
    """timeout 一律轉成 int 秒並夾在合法範圍。

    舊版 gate.py 把 1.5 直接丟給 signal.alarm()，而 alarm() 只接受 int，
    每次呼叫都在真正開始檢查前就 TypeError。這裡不再用 signal（它也只能在
    主執行緒用），改用 subprocess 自己的 timeout，並且明確轉型。
    """
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_S
    return max(1, min(value, MAX_TIMEOUT_S))


def verify_cmd(spec: Dict[str, Any]) -> Evidence:
    """自己跑一條指令，只採信 exit code。

    spec:
        argv          list[str]，必填。不接受字串，不經 shell。
        cwd           選填，工作目錄
        expect_exit   選填，預期 exit code，預設 0
        timeout       選填秒數
    """
    argv = spec.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        return Evidence(False, "argv 必須是非空的字串陣列（不接受 shell 字串）")

    exe = shutil.which(argv[0])
    if exe is None:
        return Evidence(False, f"找不到可執行檔: {argv[0]}", {"argv": argv})

    cwd = spec.get("cwd")
    if cwd is not None:
        cwd = os.path.expanduser(str(cwd))
        if not os.path.isdir(cwd):
            return Evidence(False, f"cwd 不存在: {cwd}", {"argv": argv})

    expect_exit = spec.get("expect_exit", 0)
    try:
        expect_exit = int(expect_exit)
    except (TypeError, ValueError):
        return Evidence(False, f"expect_exit 必須是整數，收到 {expect_exit!r}")

    timeout = _coerce_timeout(spec.get("timeout", DEFAULT_TIMEOUT_S))
    started = time.time()

    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return Evidence(
            False,
            f"指令逾時（{timeout}s）",
            {"argv": argv, "cwd": cwd, "timeout_s": timeout},
        )
    except OSError as exc:
        return Evidence(False, f"指令無法執行: {exc}", {"argv": argv, "cwd": cwd})

    detail = {
        "argv": argv,
        "cwd": cwd,
        "exit_code": proc.returncode,
        "expect_exit": expect_exit,
        "duration_ms": int((time.time() - started) * 1000),
        "stdout_tail": _tail(proc.stdout or ""),
        "stderr_tail": _tail(proc.stderr or ""),
    }

    if proc.returncode != expect_exit:
        return Evidence(
            False,
            f"exit code {proc.returncode}，預期 {expect_exit}",
            detail,
        )
    return Evidence(True, f"指令 exit {proc.returncode}（自行執行）", detail)


def verify_file(spec: Dict[str, Any]) -> Evidence:
    """自己 stat 檔案。存在、非空、（選填）夠新。

    spec:
        path          必填
        min_bytes     選填，預設 1（拒絕空檔）
        max_age_s     選填，檔案 mtime 必須在這麼多秒內（防止拿舊產物交差）
    """
    raw_path = spec.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return Evidence(False, "path 必填且必須是字串")

    path = Path(os.path.expanduser(raw_path))
    if not path.exists():
        return Evidence(False, f"檔案不存在: {path}", {"path": str(path)})
    if not path.is_file():
        return Evidence(False, f"不是一般檔案: {path}", {"path": str(path)})

    stat = path.stat()
    age_s = int(time.time() - stat.st_mtime)
    detail = {"path": str(path), "size": stat.st_size, "age_s": age_s}

    min_bytes = spec.get("min_bytes", 1)
    try:
        min_bytes = int(min_bytes)
    except (TypeError, ValueError):
        return Evidence(False, f"min_bytes 必須是整數，收到 {min_bytes!r}", detail)
    if stat.st_size < min_bytes:
        return Evidence(False, f"檔案只有 {stat.st_size} bytes，需要 >= {min_bytes}", detail)

    max_age_s = spec.get("max_age_s")
    if max_age_s is not None:
        try:
            max_age_s = int(max_age_s)
        except (TypeError, ValueError):
            return Evidence(False, f"max_age_s 必須是整數，收到 {max_age_s!r}", detail)
        if age_s > max_age_s:
            return Evidence(
                False,
                f"檔案 {age_s}s 前就存在了，超過 max_age_s={max_age_s}（可能是舊產物）",
                detail,
            )

    return Evidence(True, f"檔案存在 {stat.st_size} bytes，{age_s}s 前寫入", detail)


def verify_http(spec: Dict[str, Any]) -> Evidence:
    """自己發請求，只採信自己收到的狀態碼。

    spec:
        url           必填，只接受 http/https
        expect_status 選填，預設 200
        timeout       選填秒數
        contains      選填，回應內容必須包含這段字
    """
    url = spec.get("url")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return Evidence(False, "url 必填且必須是 http:// 或 https:// 開頭")

    expect_status = spec.get("expect_status", 200)
    try:
        expect_status = int(expect_status)
    except (TypeError, ValueError):
        return Evidence(False, f"expect_status 必須是整數，收到 {expect_status!r}")

    timeout = _coerce_timeout(spec.get("timeout", 10))
    detail: Dict[str, Any] = {"url": url, "expect_status": expect_status}

    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
            status = resp.status
            body = resp.read(4096).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = ""
    except Exception as exc:
        detail["error"] = f"{type(exc).__name__}: {exc}"
        return Evidence(False, f"請求失敗: {type(exc).__name__}", detail)

    detail["status"] = status
    detail["body_head"] = body[:200]

    if status != expect_status:
        return Evidence(False, f"HTTP {status}，預期 {expect_status}", detail)

    contains = spec.get("contains")
    if isinstance(contains, str) and contains and contains not in body:
        return Evidence(False, f"回應不含預期字串: {contains!r}", detail)

    return Evidence(True, f"HTTP {status}（自行請求）", detail)


VERIFIERS = {
    "cmd": verify_cmd,
    "file": verify_file,
    "http": verify_http,
}


def known_types() -> List[str]:
    return sorted(VERIFIERS)
