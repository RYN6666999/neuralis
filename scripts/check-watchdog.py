#!/usr/bin/env python3
"""韌性層自檢：watchdog 四段（健康不動 / 死了重起 / 假死重起 / crash-loop 停手）。

不碰線上那隻 API — 起一個假 health server（可選「假死」模式）在備用 port，
用 NEURALIS_WATCHDOG_START_CMD 把重啟指令換掉，跑的是真 watchdog.sh 流程。

用法: python3 scripts/check-watchdog.py
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / "scripts" / "watchdog.sh"
AUDIT = ROOT / "watchdog-audit.jsonl"

# 假 server：healthy 模式正常回 200；hang 模式收了連線就睡死（單執行緒 = event loop 凍結）
FAKE_SERVER = '''
import sys, time, http.server
mode, port = sys.argv[1], int(sys.argv[2])
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if mode == "hang":
            time.sleep(300)
        self.send_response(200); self.end_headers(); self.wfile.write(b'{"status":"ok"}')
    def log_message(self, *a): pass
http.server.HTTPServer(("127.0.0.1", port), H).serve_forever()
'''


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def audit_since(offset: int) -> list:
    if not AUDIT.exists():
        return []
    with AUDIT.open(encoding="utf-8") as f:
        f.seek(offset)
        return [json.loads(ln) for ln in f if ln.strip()]


def audit_offset() -> int:
    return AUDIT.stat().st_size if AUDIT.exists() else 0


def healthy(port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
            s.sendall(b"GET /health HTTP/1.0\r\n\r\n")
            s.settimeout(timeout)
            return b"200" in s.recv(64)
    except OSError:
        return False


def run_watchdog(port: int, tmp: Path, start_cmd: str, cycles: int, fails: int = 1) -> tuple:
    env = {
        **os.environ,
        "NEURALIS_WATCHDOG_INTERVAL": "1",
        "NEURALIS_WATCHDOG_TIMEOUT": "2",
        "NEURALIS_WATCHDOG_FAILS": str(fails),
        "NEURALIS_WATCHDOG_READY_WAIT": "5",
        "NEURALIS_WATCHDOG_MAX_RESTARTS": "2",
        "NEURALIS_WATCHDOG_WINDOW": "3600",
        "NEURALIS_WATCHDOG_MAX_CYCLES": str(cycles),
        "NEURALIS_WATCHDOG_START_CMD": start_cmd,
    }
    p = subprocess.run(["bash", str(WATCHDOG), str(port)], env=env,
                       capture_output=True, text=True, timeout=180)
    return p.returncode, p.stdout


def main():
    if not shutil.which("lsof"):
        print("SKIP: 需要 lsof"); return
    tmp = Path(tempfile.mkdtemp(prefix="watchdog-check-"))
    (tmp / "fake_server.py").write_text(FAKE_SERVER, encoding="utf-8")
    py = sys.executable

    def start_cmd(mode: str, port: int) -> str:
        """把假 server 起在背景並等就緒 — 對應 start-laap-api.sh 的角色。"""
        sh = tmp / f"start-{mode}-{port}.sh"
        sh.write_text(
            "#!/usr/bin/env bash\n"
            f'nohup "{py}" "{tmp}/fake_server.py" {mode} {port} '
            f'> "{tmp}/fake-{port}.log" 2>&1 &\n'
            "for _ in $(seq 1 20); do sleep 0.3; "
            f'curl -sf -m1 http://localhost:{port}/health >/dev/null && exit 0; done\n'
            "exit 1\n", encoding="utf-8")
        sh.chmod(0o755)
        return str(sh)

    spawned = []

    def spawn(mode: str, port: int):
        p = subprocess.Popen([py, str(tmp / "fake_server.py"), mode, str(port)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        spawned.append(p)
        return p

    try:
        # A. 健康 → 不重啟
        port = free_port()
        spawn("healthy", port)
        for _ in range(20):
            if healthy(port):
                break
            time.sleep(0.2)
        assert healthy(port), "假 server 沒起來"
        off = audit_offset()
        rc, out = run_watchdog(port, tmp, start_cmd("healthy", port), cycles=3)
        events = [e["event"] for e in audit_since(off)]
        assert rc == 0, f"健康時 watchdog 不該非零退出: {out}"
        assert "restart" not in events, f"健康時不該重啟: {events}"
        print("A. 健康不動: OK — events =", events)

        # B. 行程死了 → 殺不到東西，直接重起（OOM/crash 情境）
        port = free_port()
        spawn("healthy", port)
        for _ in range(20):
            if healthy(port):
                break
            time.sleep(0.2)
        subprocess.run(["pkill", "-f", f"fake_server.py healthy {port}"], check=False)
        time.sleep(0.5)
        assert not healthy(port), "server 應該已經死了"
        off = audit_offset()
        rc, out = run_watchdog(port, tmp, start_cmd("healthy", port), cycles=2)
        events = [e["event"] for e in audit_since(off)]
        assert "restart" in events and "restart_ok" in events, f"應重啟成功: {events}\n{out}"
        assert healthy(port), "重啟後 server 應該健康"
        print("B. 死了自動重起: OK — events =", events)

        # C. 假死（行程活著但不回應）→ launchd KeepAlive 抓不到的那種，watchdog 要抓到
        port = free_port()
        spawn("hang", port)
        time.sleep(1)
        assert not healthy(port), "hang server 不該回應"
        assert subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                              capture_output=True).stdout.strip(), "hang server 應仍佔著 port"
        off = audit_offset()
        rc, out = run_watchdog(port, tmp, start_cmd("healthy", port), cycles=2)
        events = [e["event"] for e in audit_since(off)]
        assert "restart_ok" in events, f"假死應被殺掉重起: {events}\n{out}"
        assert healthy(port), "重啟後應恢復健康"
        print("C. 假死殺掉重起: OK — events =", events)

        # D. crash-loop：重啟指令根本起不來 → 撞上限就停手，不無限刷
        port = free_port()
        off = audit_offset()
        rc, out = run_watchdog(port, tmp, "/usr/bin/true", cycles=20)
        events = [e["event"] for e in audit_since(off)]
        assert rc == 1, f"crash-loop 應以 exit 1 停手，得到 {rc}\n{out}"
        assert "crashloop" in events, f"應有 crashloop 審計: {events}"
        assert events.count("restart") == 2, f"應停在 MAX_RESTARTS=2: {events}"
        print("D. crash-loop 停手: OK — events =", events)

        print("ALL WATCHDOG CHECKS PASSED")
    finally:
        for p in spawned:
            p.kill()
        subprocess.run(["pkill", "-f", str(tmp / "fake_server.py")], check=False)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
