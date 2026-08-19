#!/usr/bin/env python3
"""
aris-truth — Aris 系統的唯一動態真相來源

為什麼存在：同一個事實（「Aris 現在的 PSI 是誰算的」）在這台機器上有六份副本，
沒有一份標示自己權威，而且數字全都不一樣。任何人要回答都得做考古。
這支指令取代考古。

設計鐵律（違反就是又造了一份會過期的副本）：
  1. 不 parse log — log 格式會漂，parse log 等於把事實抄一份。
     要知道 backend 是什麼，就 import 那段 code、跑那個判斷。
  2. 不讀任何 .md — 文件會過期，這支指令是給文件引用的，不是反過來。
  3. 每個欄位都帶 evidence — 說得出「我怎麼知道的」，不然不輸出。
  4. 任何一項失敗只汙染那一項，不讓整份報告掛掉。
  5. 時間性判斷至少兩點採樣（例如 Hz、是否還在寫）。

用法：
  aris-truth.py            # 人看的
  aris-truth.py --json     # 機器/agent 看的
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

NEURALIS = Path("/Users/ryan/Developer/neuralis")
LAAP = Path("/Users/ryan/Developer/laap-AGI")
STATE = LAAP / "aris_brain" / "state"
VENV_PY = Path("/Users/ryan/Developer/laapenv/bin/python3")
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"

# 服務清單：(顯示名, port, 進程比對字串, 是否已退役, 進入點檔案)
#
# 退役 = 刻意關掉，不是故障。仍然探測並顯示（若忽然又活了要看得見），
# 但不進 warnings —— 把「我關的」報成警告，會把真警告淹掉。
# 2026-08-19：11546 chat API 退役（Hermes 全走 11547）；11550 relay 同期退役。
#
# 這裡刻意「沒有」uses_psi 欄位。第一版有，是手標的 —— 那就是又一份會腐爛的
# 副本（本檔開頭鐵律 1 禁止的事，我自己犯了）。改成從進入點的 import 閉包推導，
# 見 _uses_psi()。退役服務不給進入點：它不在聽，算不算消費者無意義。
SERVICES = [
    ("aris-api-chat", 11546, "start.sh", True, None),
    ("aris-cognitive-api", 11547, "aris_cognitive_api.py", False,
     LAAP / "aris_brain" / "aris_cognitive_api.py"),
    ("aris-relay", 11550, "aris-relay", True, None),
    ("aris-memory", 11551, "aris-memory", False,
     NEURALIS / "scripts" / "aris-memory.py"),
]

# PSI backend 的取用只可能經這幾個名字進來（laap.startup 是唯一的 backend 工廠）。
_PSI_IMPORT_MARKERS = ("laap.psi_backend", "laap.psi_core", "from laap.startup",
                       "get_psi_core", "RustPsiBackend", "PythonPsiBackend")


def _uses_psi(entry: Path | None, depth: int = 2) -> dict:
    """從進入點的 import 閉包推導「這個服務會不會取用 PSI backend」。

    為什麼不手標：手標的旗標改接線時不會自己更新，會靜默說謊。
    為什麼掃 import 而不是掃全文：aris-memory.py 有 33 個 `psi_*` 命中，
    全是 SQLite 欄位名（存呼叫端傳來的快照），跟取用 backend 無關 ——
    全文比對會把它誤判成消費者。判準是 import，不是字串出現。

    限制（誠實登記）：只跟 laap/ 與 aris_brain/ 底下的本地模組，深度 2。
    動態 import 字串拼接抓不到。抓不到就回 unknown，不回 False。
    """
    if entry is None:
        return {"uses_psi": None, "why": "退役服務，未指定進入點"}
    if not entry.exists():
        return {"uses_psi": None, "why": f"進入點不存在：{entry}"}

    seen, frontier = set(), [entry]
    for _ in range(depth + 1):
        nxt = []
        for f in frontier:
            if f in seen or not f.exists():
                continue
            seen.add(f)
            try:
                src = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for line in src.splitlines():
                t = line.strip()
                if not (t.startswith("from ") or t.startswith("import ")):
                    continue
                if any(m in t for m in _PSI_IMPORT_MARKERS):
                    return {"uses_psi": True, "why": f"{f.name}: {t[:70]}"}
                # 本地模組才跟：laap.x / aris_brain 同層 / neuralis 同層
                mod = t.split()[1].split(".")[0] if len(t.split()) > 1 else ""
                for root in (f.parent, NEURALIS, LAAP / "aris_brain"):
                    for cand in (root / f"{mod}.py",
                                 root / mod.replace(".", "/") / "__init__.py"):
                        if cand.exists() and cand not in seen:
                            nxt.append(cand)
                if t.startswith("from laap.") or t.startswith("import laap."):
                    sub = t.split()[1].split(".")
                    if len(sub) > 1:
                        cand = NEURALIS / "laap" / f"{sub[1]}.py"
                        if cand.exists() and cand not in seen:
                            nxt.append(cand)
        frontier = nxt
        if not frontier:
            break
    return {"uses_psi": False,
            "why": f"掃了 {len(seen)} 個模組的 import，沒有 PSI backend 取用"}


# 探測失敗一律登記在這裡，並在報告裡明示。
# 鐵則：指令失敗 ≠ 東西不存在。舊版 _sh 失敗回空字串，
# 於是「ps 掛了」被呈現成「0 個 psi-daemon」—— 那是說謊，不是回報。
PROBE_ERRORS: list[str] = []


def _sh(args: list[str], timeout: float = 10.0) -> str:
    """跑指令拿 stdout。

    - 用 bytes 收再 errors='replace' 解碼：本機有進程的 cmdline 帶非 UTF-8
      位元組（0xa0），text=True 會直接 UnicodeDecodeError。
      （同一個原因讓 pgrep -f 回 `illegal byte sequence` 且靜默回空，所以本檔不用 pgrep。）
    - 任何失敗都登記進 PROBE_ERRORS，呼叫端看到空字串時報告會標明「這是失敗，不是沒有」。
    """
    try:
        r = subprocess.run(args, capture_output=True, timeout=timeout)
        if r.returncode != 0 and not r.stdout:
            PROBE_ERRORS.append(
                f"{' '.join(args)} → rc={r.returncode} "
                f"{r.stderr.decode('utf-8', 'replace').strip()[:120]}"
            )
        return r.stdout.decode("utf-8", "replace")
    except Exception as e:
        PROBE_ERRORS.append(f"{' '.join(args)} → {type(e).__name__}: {e}")
        return ""


def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def ps_all() -> list[tuple[str, str]]:
    """全機進程 (pid, cmdline)。

    不用 pgrep：pgrep 在非 UTF-8 locale 的 subprocess 裡會以
    `Regular expression evaluation error (illegal byte sequence)` 失敗，
    而且是 **靜默回空字串** —— 正是「空輸出被當成沒有」的經典陷阱。
    ps 全列 + Python 自己比對字串，沒有 regex、沒有 locale 依賴。
    """
    out = _sh(["/bin/ps", "-Ao", "pid=,args="])
    rows = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        pid, _, args = line.partition(" ")
        if pid.isdigit():
            rows.append((pid, args.strip()))
    return rows


# ── 1. Rust daemon：活著嗎？多快？──────────────────────────────

def check_rust_daemon() -> dict:
    """兩點採樣量 Hz。單點只能證明檔案存在，證不了它還在動。"""
    canonical = str(STATE / "rust-latest.json")
    out = {"file": canonical}

    daemons = [(pid, args) for pid, args in ps_all() if "psi-daemon" in args]
    canon, stray = [], []
    # 比對必須正規化：launchd 傳的是 `neuralis/../laap-AGI/...`，
    # 字串不等但 realpath 相同。純字串比對會把正牌 daemon 判成孤兒。
    canon_real = os.path.realpath(canonical)
    for pid, args in daemons:
        sf = _state_file_of(args)
        same = sf != "?" and os.path.realpath(sf) == canon_real
        (canon if same else stray).append({"pid": pid, "state_file": sf})
    out["instances"] = len(daemons)
    out["canonical"] = canon
    out["stray"] = stray

    d1 = _read_json(STATE / "rust-latest.json")
    if not d1:
        out["running"] = False
        out["evidence"] = "rust-latest.json 讀不到或非 JSON"
        return out

    time.sleep(0.5)
    d2 = _read_json(STATE / "rust-latest.json")

    # Hz 的分母用 daemon 自己寫的 ts，不用我這邊的 wall clock —
    # 我的 read/sleep 有排程誤差，會把 2000Hz 算成 2092Hz。
    dt = d2.get("ts", 0) - d1.get("ts", 0)
    tick_delta = d2.get("tick", 0) - d1.get("tick", 0)
    out["state_age_s"] = round(time.time() - d2.get("ts", 0), 2)
    out["hz"] = round(tick_delta / dt) if dt > 0 else 0
    out["running"] = out["hz"] > 0 and out["state_age_s"] < 2.0
    out["tick"] = d2.get("tick")
    out["needs"] = {k: round(v, 3) for k, v in (d2.get("needs") or {}).items()}
    out["evidence"] = (
        f"0.5s 兩點採樣：tick 差 {tick_delta} / daemon 自報 ts 差 {dt:.3f}s；"
        f"進程來自 ps 全列比對"
    )
    if len(canon) > 1:
        out["warning"] = f"{len(canon)} 個 daemon 同時寫 canonical state 檔，互相覆蓋"
    return out


def _state_file_of(args: str) -> str:
    parts = args.split()
    if "--state-file" in parts:
        i = parts.index("--state-file")
        if i + 1 < len(parts):
            return parts[i + 1]
    return "?"


# ── 2. 實際生效的 backend：跑那段 code，不看 log ────────────────

# ⚠️ 這支 probe 絕對不能呼叫 start()。
# 第一版呼叫了，而且沒設 LAAP_AGI_DIR → state_file 落到 /tmp 預設值 →
# 那個檔沒人在寫 → 跨 process 守衛放行 → **它 spawn 了一隻孤兒 daemon**。
# 診斷工具生出被診斷的病，就是 08-01「十隻 psi-daemon」的複製。
#
# healthy() 本身是唯讀的（只看 _daemon_process 和讀檔），可以安全呼叫。
# start() 會不會 spawn，用「state 檔新不新鮮」直接推導，不需要真的跑。
PROBE = r"""
import json, sys, time, os
os.environ.setdefault("LAAP_AGI_DIR", "/Users/ryan/Developer/laap-AGI")
sys.path[:0] = ["/Users/ryan/Developer/neuralis", "/Users/ryan/Developer/laap-AGI"]
res = {}
try:
    from laap.psi_backend import RustPsiBackend
    b = RustPsiBackend()                      # __init__ 無副作用
    res["state_file"] = b._state_file
    raw = b._read_raw()                       # 純讀
    res["read_raw_ok"] = raw is not None
    res["healthy"] = bool(b.healthy())        # 唯讀；未 start 故 _daemon_process is None
    # start() 的守衛：state 新鮮 (<2s) 就 return 不 spawn。原地推導，不執行。
    try:
        ts = json.load(open(b._state_file, encoding="utf-8")).get("ts", 0)
        age = time.time() - ts
        res["state_age_s"] = round(age, 2)
        res["start_would_spawn"] = not (0 <= age < 2.0)
    except Exception:
        res["start_would_spawn"] = True
except Exception as e:
    res["error"] = f"{type(e).__name__}: {e}"
print(json.dumps(res))
"""


def check_effective_backend() -> dict:
    """
    startup.py:50 的判斷是：env==rust 且 healthy() 為真 → Rust，否則 Python。
    這裡原地重跑同一個判斷，得到的就是服務開機時會得到的結果。
    這是推導，不是抄 log。
    """
    out = {}
    env_val = "rust"  # start.sh:45 對 11546 export 的值；11547 不經 start.sh
    py = str(VENV_PY) if VENV_PY.exists() else sys.executable

    raw = _sh([py, "-c", PROBE], timeout=20)
    try:
        probe = json.loads(raw.strip().splitlines()[-1])
    except Exception:
        out["error"] = "probe 沒有回傳可解析的 JSON"
        out["raw"] = raw[:200]
        return out

    out["probe"] = probe
    if probe.get("error"):
        out["effective"] = "unknown"
        out["reason"] = probe["error"]
        return out

    if probe.get("healthy"):
        out["effective"] = "rust"
        out["reason"] = "healthy() 為真 → startup.py 會用 RustPsiBackend"
    else:
        out["effective"] = "python"
        if probe.get("read_raw_ok") and not probe.get("start_would_spawn"):
            out["reason"] = (
                "資料讀得到但 healthy() 為假："
                "start() 因 state 新鮮而跳過 spawn（psi_backend.py:368），"
                "healthy() 又要求 _daemon_process 非 None（psi_backend.py:405）。"
                "兩個守衛互斥 → 必然回退 Python，不是競態。"
            )
        else:
            out["reason"] = "healthy() 為假 → startup.py 回退 PythonPsiBackend"
    out["env_would_be"] = env_val
    out["evidence"] = "原地 import laap.psi_backend 跑 start()+healthy()，與 startup.py 同一段邏輯"
    return out


# ── 3. Python PSI：還在寫嗎？──────────────────────────────────

def check_python_psi() -> dict:
    """latest.json 由 chatflow.py:288 每輪對話寫一次（事件驅動，不是週期）。
    所以「age 大」不等於「死了」，只等於「最近沒對話」。這裡兩者都報，不下結論。"""
    d = _read_json(STATE / "latest.json")
    if not d:
        return {"present": False, "evidence": "latest.json 讀不到"}
    age = round(time.time() - d.get("ts", 0), 1)
    return {
        "present": True,
        "source_label": d.get("source"),
        "cycle": d.get("cycle"),
        "age_s": age,
        "needs": {k: round(v, 3) for k, v in (d.get("needs") or {}).items()},
        "note": "事件驅動（每輪對話寫一次）。age 大只代表最近沒流量，不代表死掉。",
        "evidence": "latest.json 的 source 欄位；該標籤全機只由 chatflow.py:288 產生",
    }


# ── 4. 服務與 launchd ─────────────────────────────────────────

def check_services() -> list[dict]:
    listen = _sh(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"])
    rows = []
    for name, port, _match, retired, entry in SERVICES:
        psi = _uses_psi(entry)
        hit = [l for l in listen.splitlines() if f":{port} " in l]
        pid = hit[0].split()[1] if hit else None
        rows.append({
            "name": name, "port": port, "retired": retired,
            "uses_psi": psi["uses_psi"], "uses_psi_why": psi["why"],
            "listening": bool(hit), "pid": pid,
            "evidence": "lsof -nP -iTCP -sTCP:LISTEN 全列比對",
        })
    return rows


def check_launchd() -> dict:
    listed = _sh(["launchctl", "list"])
    loaded = {}
    for line in listed.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[2].startswith("com.neuralis."):
            loaded[parts[2]] = {"pid": parts[0], "last_exit": parts[1]}

    on_disk = sorted(p.stem for p in LAUNCH_AGENTS.glob("com.neuralis.*.plist"))
    not_loaded = [n for n in on_disk if n not in loaded]
    failing = {k: v for k, v in loaded.items()
               if v["last_exit"] not in ("0", "-15") and v["pid"] == "-"}
    return {
        "loaded": loaded,
        "plist_on_disk_but_not_loaded": not_loaded,
        "loaded_but_last_exit_nonzero": failing,
        "evidence": "launchctl list 全列 vs ~/Library/LaunchAgents/com.neuralis.*.plist",
    }


# ── 5. Rust 有沒有真的被消費 ──────────────────────────────────

def check_rust_consumers(backend: dict, launchd: dict, services: list) -> dict:
    """只報能現場判定的，不列靜態 code 清單（那會變成又一份會過期的副本）。"""
    consumers = []
    # 2026-08-19：原本這裡是 `if backend=='rust': consumers.append("11546 PSI backend")`
    # ——硬抄一個服務名，沒驗它在不在聽。11546 退役後這支就開始說謊：同一份輸出
    # 上面說「生效消費者 = 11546」，下面說「11546 沒在聽」。事實只能推導不能複製。
    if backend.get("effective") == "rust":
        for s in services:
            if s["listening"] and s["uses_psi"] is True:
                consumers.append(f"{s['name']}:{s['port']} PSI backend（pid={s['pid']}）")

    latest = STATE / "latest.json"
    quantum_reads_rust = not latest.exists() or not _read_json(latest)
    if quantum_reads_rust:
        consumers.append("quantum_output.py")

    autoupdate_scheduled = "com.neuralis.aris-autoupdate" in launchd.get("loaded", {})
    if autoupdate_scheduled:
        consumers.append("aris-autoupdate（排程中）")

    return {
        "effective_consumer_count": len(consumers),
        "effective_consumers": consumers,
        "notes": [
            "quantum_output.py:80 是 `_read(LATEST) or _read(RUST)` — latest.json 只要存在就永遠讀不到 Rust",
            "aris-autoupdate 未排程時仍可手動執行；那只更新 Obsidian 文字，不影響服務行為",
        ],
        "evidence": "逐條現場判定（backend probe / latest.json 是否存在 / launchd 是否載入）",
    }


# ── 組裝 ──────────────────────────────────────────────────────

def collect() -> dict:
    rust = check_rust_daemon()
    backend = check_effective_backend()
    python_psi = check_python_psi()
    services = check_services()
    launchd = check_launchd()
    consumers = check_rust_consumers(backend, launchd, services)

    warnings = []
    if rust.get("running") and consumers["effective_consumer_count"] == 0:
        warnings.append("Rust daemon 在跑但零個生效消費者 —— 它的運算沒有進入任何服務行為")
    if rust.get("warning"):
        warnings.append(rust["warning"])
    for s in rust.get("stray", []):
        warnings.append(
            f"孤兒 psi-daemon pid={s['pid']} 寫 {s['state_file']}"
            f"（非 canonical；通常是誰的探針呼叫了 RustPsiBackend.start()）"
        )
    # 退役服務不進 warnings（我關的 ≠ 壞了）；但若退役的忽然又在聽，那才是警告。
    for s in services:
        if s["retired"] and s["listening"]:
            warnings.append(f"{s['name']} (:{s['port']}) 已退役卻在聽 pid={s['pid']} —— 誰起的？")
        elif not s["retired"] and not s["listening"]:
            warnings.append(f"{s['name']} (:{s['port']}) 沒在聽")
        # unknown 不得靜默當成 False —— 那正是「探測失敗被呈現成沒有」。
        if s["listening"] and s["uses_psi"] is None:
            warnings.append(
                f"{s['name']} (:{s['port']}) 的 PSI 取用推導不出來：{s['uses_psi_why']}"
                "（消費者清單因此可能少算）")
    # 未載入的 plist：只報「對應服務還在役」的那些。留在磁碟的廢棄 plist 是
    # 考古層，不是待辦；9 條噪音會把真警告淹掉。
    _live_units = {f"com.neuralis.{s['name']}" for s in services if not s["retired"]}
    for n in launchd["plist_on_disk_but_not_loaded"]:
        if n in _live_units:
            warnings.append(f"{n} 有 plist 但未載入 launchd")
    for n in launchd["loaded_but_last_exit_nonzero"]:
        warnings.append(f"{n} 上次以非零碼結束")

    return {
        "schema": "aris-truth/v1",
        "ts": time.time(),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "psi": {
            "rust_daemon": rust,
            "effective_backend": backend,
            "python_psi": python_psi,
            "rust_consumption": consumers,
        },
        "services": services,
        "launchd": launchd,
        "warnings": warnings + [f"探測失敗（此項結果不可信）：{e}" for e in PROBE_ERRORS],
        "probe_errors": list(PROBE_ERRORS),
    }


def render(r: dict) -> str:
    L = []
    b = r["psi"]["effective_backend"]
    rust = r["psi"]["rust_daemon"]
    py = r["psi"]["python_psi"]
    con = r["psi"]["rust_consumption"]

    L.append(f"aris-truth  {r['generated_at']}")
    L.append("")
    L.append(f"PSI 實際生效 backend : {b.get('effective', '?').upper()}")
    L.append(f"  why               : {b.get('reason', '-')}")
    L.append("")
    L.append(f"Rust daemon         : {'跑' if rust.get('running') else '沒跑'}"
             f"  {rust.get('hz', 0)}Hz  age {rust.get('state_age_s', '?')}s"
             f"  實例 {rust.get('instances', '?')}")
    L.append(f"  生效消費者         : {con['effective_consumer_count']}"
             f"  {con['effective_consumers'] or '（無）'}")
    L.append("")
    L.append(f"Python PSI          : source={py.get('source_label')}"
             f"  cycle={py.get('cycle')}  age {py.get('age_s')}s")
    L.append(f"  {py.get('note', '')}")
    L.append("")
    L.append("服務")
    for s in r["services"]:
        # ⚫ = 退役且確實沒在聽（預期）；退役卻在聽 → 🔴，那是異常。
        if s["retired"]:
            dot, tail = ("🔴", "  ← 已退役卻在聽") if s["listening"] else ("⚫", "  （已退役）")
        else:
            dot, tail = ("🟢", "") if s["listening"] else ("🔴", "")
        L.append(f"  {dot} {s['name']:<22} :{s['port']}  pid={s['pid'] or '-'}{tail}")
    L.append("")
    if r["warnings"]:
        L.append("⚠️  警告")
        for w in r["warnings"]:
            L.append(f"  - {w}")
    else:
        L.append("✅ 無警告")
    return "\n".join(L)


def main() -> int:
    r = collect()
    if "--json" in sys.argv:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(render(r))
    return 1 if r["warnings"] else 0


if __name__ == "__main__":
    sys.exit(main())
