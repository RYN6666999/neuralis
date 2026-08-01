#!/usr/bin/env python3
"""probe.py — 跑 topology.yaml 每條邊，確認它現在還通著。

節點都有人寫、有人測、有人 commit；邊沒有任何人的任務涵蓋 —— 所以邊斷了沒人知道。
這支就是那個「會叫的東西」。

yaml 管人看的（contract / note），這裡管機器跑的。兩邊 edge id 必須一一對應，
對不上就是漂移，開頭先擋下來。

用法：
    probe.py            # 跑全部
    probe.py <edge_id>  # 跑一條
exit 1 = 有非預期的紅。`expect: fail` 的邊紅了算預期，不影響 exit code。
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TOPO = ROOT / "topology.yaml"


def _laap_const(name: str, _src=None):
    """現讀 laap/chatflow.py 的模組常數真值。

    鐵律：事實只能推導，不能複製。這支曾把 bootstrap 冷卻常數抄進註解，
    抄的值比真值大 15 倍，害「假紅」的判斷整個歪掉。用讀的就不會歪。
    （不 import chatflow —— 它會拉起一整串重依賴，probe 要能單獨跑。）
    """
    src = _src or (ROOT / "laap" / "chatflow.py").read_text(encoding="utf-8")
    m = re.search(rf"^{re.escape(name)}\s*=\s*(\d+(?:\.\d+)?)", src, re.M)
    if not m:
        return f"?（chatflow.py 找不到 {name}）"
    v = float(m.group(1))
    return int(v) if v.is_integer() else v
CHANNEL = Path("/tmp/aris-scream-channel.jsonl")
BRIDGE_LOG = Path("/tmp/agentos-aris-bridge.log")
# 跟 scripts/aris-memory.py 的 DB 同一個解析規則（它讀 ARIS_MEMORY_DB）。
# probe 現在會對這個檔做 DELETE（收哨兵），指錯 DB 就是刪錯地方。
MEM_DB = Path(os.environ.get("ARIS_MEMORY_DB", str(Path.home() / ".aris-memory.db")))
BOARD = Path.home() / ("Library/Mobile Documents/iCloud~md~obsidian"
                       "/Documents/Fun/Aris/留言板.md")
MEM_URL = "http://127.0.0.1:11551"
# probe 結果落地。放 ~/.neuralis/ 不放 /tmp：/tmp 重開機清空，
# 而讀這份檔的 aris_growth_check 是 topology 的永久邊。
RESULTS = Path(os.environ.get(
    "NEURALIS_PROBE_RESULTS", str(Path.home() / ".neuralis" / "probe-last.json")))
RESULTS_FRESH_SEC = 3600
BRIDGE_PLIST = Path.home() / "Library/LaunchAgents/com.neuralis.task-executor.plist"


def _live_bridge_python() -> str:
    """從正在跑的 bridge process 抓它實際用的 python 路徑。

    不問 plist（plist 說謊過、也可能 bridge 是手動重開的）。
    從 __PYVENV_LAUNCHER__ 環境變數拿（保留 virtualenv symlink）。
    找不到 process 時回空字串 — 讓呼叫端退到 _bridge_python_fallback()。
    """
    try:
        import subprocess
        r = subprocess.run(["pgrep", "-f", "agentos-aris-bridge\\.py"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode != 0 or not r.stdout.strip():
            return ""
        pid = r.stdout.strip().splitlines()[0]
        # 從 process 的環境變數拿 __PYVENV_LAUNCHER__（叫用時的 python 路徑）
        env = subprocess.run(["ps", "eww", "-p", pid],
                             capture_output=True, text=True, timeout=5)
        if env.returncode == 0:
            for token in env.stdout.split():
                if token.startswith("__PYVENV_LAUNCHER__="):
                    return token.split("=", 1)[1]
        # 備案：command line 第一個 token
        cmd = subprocess.run(["ps", "-o", "command=", "-p", pid],
                             capture_output=True, text=True, timeout=5)
        if cmd.returncode == 0 and cmd.stdout.strip():
            return cmd.stdout.strip().split()[0]
    except Exception:
        pass
    return ""


def _bridge_python_fallback() -> str:
    """plist 備案 — 只在 bridge 沒跑時用。"""
    try:
        import plistlib
        with BRIDGE_PLIST.open("rb") as f:
            pl = plistlib.load(f)
        cmd = " ".join(pl.get("ProgramArguments", []))
        for token in cmd.split():
            if token.endswith("/python") or token.endswith("/python3"):
                return token
        import re
        m = re.search(r'\bexec\s+(/[^\s]+/python[3]?\S*)', cmd)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""


def _record_result(eid: str, ok: bool, msg: str) -> None:
    """每條邊跑完就落地。best-effort，寫不進去不影響 probe 本身。"""
    try:
        RESULTS.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads(RESULTS.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        data[eid] = {"ok": bool(ok), "msg": str(msg)[:200], "ts": time.time()}
        RESULTS.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    except OSError as e:
        print(f"  ⚠️ probe 結果沒寫進去 {RESULTS}: {e}", file=sys.stderr)


def _rows() -> int:
    return sqlite3.connect(f"file:{MEM_DB}?mode=ro", uri=True).execute(
        "SELECT count(*) FROM memories").fetchone()[0]


def _kick(text: str) -> str:
    """注一筆 kick 進 channel，回 entry id。"""
    eid = f"probe-{int(time.time()*1000):x}"
    CHANNEL.open("a").write(json.dumps({
        "ts": time.time(), "id": eid, "direction": "scream→aris",
        "type": "kick", "content": text,
        "context": {"source": "probe"}}, ensure_ascii=False) + "\n")
    return eid


def _wait(pred, timeout=45, step=2):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(step)
    return False


# ── 每條邊一個函式，key 對上 topology.yaml 的 edge id ──────────────

def board_to_channel():
    """碰一下留言板 mtime，看 watcher 有沒有寫出合格 entry。"""
    if not BOARD.exists():
        return False, "留言板不存在"
    before = CHANNEL.stat().st_size if CHANNEL.exists() else 0
    BOARD.touch()
    if not _wait(lambda: CHANNEL.exists() and CHANNEL.stat().st_size > before, 25):
        return False, "watcher 沒寫出 entry（debounce 10s / 自我簽名跳過 也可能）"
    for line in CHANNEL.read_text().splitlines()[::-1]:
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("context", {}).get("source") == "message-board-watcher":
            missing = [k for k, v in (("id", e.get("id")),
                                      ("direction", e.get("direction") == "scream→aris"),
                                      ("type", e.get("type") == "kick")) if not v]
            return (not missing), ("契約缺: " + ",".join(missing) if missing else "契約符合")
    return False, "找不到 watcher entry"


def channel_to_aris():
    """注 kick，看 bridge log 有沒有出現 Aris 回應。"""
    if not BRIDGE_LOG.exists():
        return False, "bridge log 不存在（bridge 沒跑？）"
    # 用字元數不用 st_size：log 全是中文，byte offset 拿去切 str 會切過頭。
    before = len(BRIDGE_LOG.read_text(errors="replace"))
    _kick("probe: channel→aris 連通性測試，回一個字即可。")
    ok = _wait(lambda: "✅ Aris 回應"
               in BRIDGE_LOG.read_text(errors="replace")[before:], 60)
    return ok, "log 有回應" if ok else "60s 內沒看到「✅ Aris 回應」"


def aris_to_memory():
    """注 kick，看 DB 有沒有多一筆、且 content 沒殘留 salience 標記。"""
    before = _rows()
    _kick("probe: aris→memory 寫入測試，回一個字即可。")
    if not _wait(lambda: _rows() > before, 60):
        return False, f"60s 內 rows 沒增加（仍 {before}）"
    c = sqlite3.connect(f"file:{MEM_DB}?mode=ro", uri=True).execute(
        "SELECT content FROM memories ORDER BY id DESC LIMIT 1").fetchone()[0]
    if "⫸salience⫷" in (c or ""):
        return False, "content 殘留 salience 標記（剝除失效）"
    return True, f"rows {before}→{_rows()}，content 乾淨"


def webchat_to_memory():
    """真的打一輪 webchat，看記憶多兩筆（使用者 + Aris），且回覆沒殘留標記。

    relay 的 idempotency_key = md5(conv:text)，所以 text 每次要不一樣，
    否則第二次會被 dedup 擋掉、看起來像斷線。
    """
    before = _rows()
    payload = json.dumps({"text": f"probe webchat 連通測試 {int(time.time())}，回一個字即可。",
                          "conv": "probe", "uid": "probe"}).encode()
    try:
        r = json.loads(urllib.request.urlopen(urllib.request.Request(
            "http://127.0.0.1:11550/c", data=payload,
            headers={"Content-Type": "application/json"}), timeout=90).read())
    except Exception as e:
        return False, f"POST 11550 失敗: {e}"
    if r.get("dedup"):
        return False, "被 idempotency 擋掉（probe text 撞號）"
    if not _wait(lambda: _rows() >= before + 2, 90):
        return False, f"90s 內沒多兩筆（{before}→{_rows()}）"
    db = sqlite3.connect(f"file:{MEM_DB}?mode=ro", uri=True)
    got = {s for (s,) in db.execute(
        "SELECT source FROM memories ORDER BY id DESC LIMIT 2")}
    last = db.execute("SELECT content FROM memories WHERE source='aris-self' "
                      "ORDER BY id DESC LIMIT 1").fetchone()
    if "⫸salience⫷" in ((last or [""])[0] or ""):
        return False, "回覆殘留 salience 標記（webchat 使用者會看到裸 JSON）"
    if got != {"webchat", "aris-self"}:
        return False, f"source 不對: {sorted(got)}（應為 webchat + aris-self）"
    return True, f"rows {before}→{_rows()}，雙筆 source 正確"


def memos_to_gbrain():
    """夜班固化能不能列出待固化，且不報錯。用 bridge 的 interpreter 跑，不是 probe 自己的。"""
    bp = _live_bridge_python() or _bridge_python_fallback()
    py = bp or sys.executable
    log_prefix = f" (live bridge python: {bp})" if bp else " (fallback: probe's own python)"
    r = subprocess.run([py, str(ROOT / "scripts/consolidate-memos.py"),
                        "--all", "--dry-run"], capture_output=True, text=True)
    if r.returncode != 0:
        return False, r.stderr.strip()[:160]
    return (("固化" in r.stdout) or ("no memos" in r.stdout.lower())), (
        r.stdout.strip().splitlines()[-1][:120] + log_prefix)


def wake_reads_three():
    """/wake 三源匯流：至少要有一源出東西。"""
    try:
        ctx = json.loads(urllib.request.urlopen(
            f"{MEM_URL}/wake?limit=3", timeout=5).read()).get("context", "")
    except Exception as e:
        return False, f"/wake 打不到: {e}"
    n = ctx.count("【")
    return (n >= 1), f"{n} 個區塊" + ("" if n else "（三源全空）")


def bridge_scoring_router():
    """Scoring router import 是否成功。用 bridge 自己的 python 跑 import 測試。

    2026-07-26 證實：plist→laapenv 但實跑 homebrew → pydantic 不在 → import 靜默降級。
    probe 用自己的 interpreter（有 pydantic）永遠測不出來。
    """
    bp = _live_bridge_python() or _bridge_python_fallback()
    if not bp:
        return False, "抓不到 live bridge process，plist 也解析失敗"
    sandbox = str(Path.home() / "agent-sandbox")
    r = subprocess.run([bp, "-c",
                        "from contracts.verdict_v2 import ActionRequest, VerdictV2; "
                        "from router.scoring import score; "
                        "print('OK')"],
                       capture_output=True, text=True, timeout=10,
                       env={**os.environ, "PYTHONPATH": sandbox})
    if r.returncode != 0:
        err = r.stderr.strip()
        # 截取有效錯誤訊息（避免 traceback flood）
        lines = err.splitlines()
        key = "\n".join(ln for ln in lines if "Error" in ln or "error" in ln or "No module" in ln)
        return False, f"scoring router import 失敗: {(key or err)[:200]}"
    # 第二層確認：bridge log 最近的 startup 有 enabled 嗎？
    if BRIDGE_LOG.exists():
        lines = BRIDGE_LOG.read_text(errors="replace").splitlines()
        for line in reversed(lines):
            if "Scoring Router canary bridge" in line:
                ok = "enabled" in line
                return ok, ("enabled" if ok else f"disabled: {line.split('—')[-1].strip()}")
    return True, f"import OK（log 未確認）"


# ── 三條新 probe（2026-07-26 追加，推論驗證，預期全紅）─────────────

RELALY_URL = "http://127.0.0.1:11550"
ARIS_API_URL = "http://127.0.0.1:11546/v1/chat/completions"
MEM_STORE_URL = "http://127.0.0.1:11551/memories/store"


def _webchat(conv: str, text: str) -> dict | None:
    """打一輪 webchat relay，回 response dict 或 None（連線失敗）。"""
    try:
        r = urllib.request.urlopen(urllib.request.Request(
            f"{RELALY_URL}/c",
            data=json.dumps({"text": text, "conv": conv, "uid": "probe"}).encode(),
            headers={"Content-Type": "application/json"}), timeout=90)
        return json.loads(r.read())
    except Exception as e:
        return None


def relay_remembers_turn():
    """兩輪哨兵：第二輪答得出第一輪給過代號（不要求 exact match—Aris 會幻覺具體內容）。"""
    token = f"紫貘{int(time.time())%10000}"
    conv = f"probe-relay-{int(time.time())}"
    # 第一輪：塞代號
    r1 = _webchat(conv, f"記住這個代號：{token}。回一個好就行。")
    if r1 is None:
        return False, "服務未啟動: relay 11550 連不上"
    # 第二輪：問代號
    r2 = _webchat(conv, f"我剛給你的代號是什麼？")
    if r2 is None:
        return False, "服務未啟動: relay 11550 連不上（第二輪）"
    reply = r2.get("reply", "") or ""
    # 2026-08-01 修回精準匹配。
    # 前一版改成「回覆含『代號/記得/剛剛』等字就算過」，結果她回
    # 「你沒給過我代號啊」—— 裡面正好有「代號」，**否認被判成通過**。
    # 那不是修好了閘，是把閘改到能通過為止（法零：調鬆比修對容易）。
    # 哨兵是隨機字串，她編不出來 —— 只有這個匹配騙不了人。
    if token in reply:
        return True, f"綠: 回覆含哨兵「{token}」（她真的記得上一輪）"

    # 明確否認要單獨標出來，不然下一個人又會想「加幾個關鍵字就綠了」
    if any(neg in reply for neg in ["沒給", "沒有給", "沒印象", "不記得", "忘了", "沒說過"]):
        return False, f"真紅（她明確否認記得）: {reply[:80]}"
    return False, f"真紅: 回覆不含哨兵「{token}」，回覆開頭={reply[:80]}"


def recall_not_selfinflated():
    """新寫入的 aris-self 記憶 discovered_salience 必須為 0。
    用 event_id 精準定位，不抓「最新一筆」避免撈到 bridge 寫的。"""
    conv = f"probe-recall-{int(time.time())}"
    r = _webchat(conv, f"代號 {conv}。回一個好就行。")
    if r is None:
        return False, "服務未啟動: relay 11550 連不上"
    eid = r.get("event_id", "")
    if not eid:
        return False, f"probe 炸了: relay 回應無 event_id，原始回應={r}"
    source_id = f"relay-{eid}-a"
    # _remember 在 POST /c 回應（delivered）之後才寫，所以打完 webchat 立刻查
    # 會撞上 write race。等記憶真的落地再判斷，否則「不存在」是假紅不是真洞。
    def _fetch():
        db = sqlite3.connect(f"file:{MEM_DB}?mode=ro", uri=True)
        try:
            return db.execute(
                "SELECT discovered_salience, total_recalls FROM memories WHERE source_id=?",
                (source_id,)).fetchone()
        finally:
            db.close()
    row = None
    if _wait(lambda: (_fetch() is not None), 20):
        row = _fetch()
    if row is None:
        return False, f"真紅: source_id={source_id} 等 20s 仍未寫入（記憶未落地）"
    ds, tr = row[0] or 0.0, row[1] or 0
    if ds == 0.0 and tr == 0:
        return True, f"綠: ds={ds} tr={tr}（寫入端守規矩）"
    return False, f"真紅: discovered_salience={ds} total_recalls={tr}（寫入端偷加了分）"


def _purge_probe_sentinel(mem_id) -> None:
    """收掉哨兵。

    2026-08-01：這個 probe 每跑一次就在 Aris 工作記憶留一筆
    `attention_line=下一步要處理 藍鯨NNNN 這個問題`，而且 salience 開到 5
    保證擠不掉，卻從來不刪。累積 17 筆之後她真的把它當成待辦，跨 session
    追問了五天「藍鯨6061 是什麼」—— 測試資料變成她的人格輸入。
    哨兵的壽命只該是這個函式，不是她的一輩子。
    """
    if not mem_id:
        return
    try:
        conn = sqlite3.connect(MEM_DB)
        with conn:
            conn.execute(
                "DELETE FROM memories WHERE id=? AND source='probe'", (mem_id,)
            )
        conn.close()
    except Exception as e:
        print(f"  ⚠️ 哨兵沒收乾淨 id={mem_id}: {e}", file=sys.stderr)


def wake_reaches_prompt():
    """塞哨兵 attention_line → 問 Aris 懸著什麼 → 看回覆含不含哨兵。

    存記憶時設 encoding_salience=5 確保不被 τ 排序擠出前 5，
    驗完一定要 _purge_probe_sentinel 收掉（成敗都收）。
    """
    token = f"藍鯨{int(time.time())%10000}"
    payload = json.dumps({
        "content": f"probe: working-set 哨兵測試 {token}",
        "source": "probe",
        "attention_line": f"下一步要處理 {token} 這個問題",
        "encoding_salience": 5,
    }).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request(
            MEM_STORE_URL, data=payload,
            headers={"Content-Type": "application/json"}), timeout=5)
        store_resp = json.loads(r.read())
    except Exception as e:
        return False, f"服務未啟動: aris-memory 11551 存記憶失敗: {e}"
    mem_id = store_resp.get("id")
    if not mem_id:
        return False, f"probe 炸了: store 回應無 id, resp={store_resp}"

    # 從這裡開始，哨兵已經在她記憶裡了 —— 不管底下怎麼 return，finally 都要收掉
    try:
        # 直打 11546 問 Aris
        ask = json.dumps({
            "model": "laap-core",
            "messages": [{"role": "user", "content": "你上一刻懸著什麼還沒解決？只回答你實際記得的，不要編。"}]
        }).encode()
        try:
            resp = urllib.request.urlopen(urllib.request.Request(
                ARIS_API_URL, data=ask,
                headers={"Content-Type": "application/json"}), timeout=30)
            result = json.loads(resp.read())
            reply = (
                (result.get("choices") or [{}])[0].get("message", {}).get("content", "")
                or result.get("response", "")
            )
        except Exception as e:
            return False, f"服務未啟動: Aris API 11546 打不到: {e}"
        if token in reply:
            return True, f"綠: 回覆含哨兵「{token}」（/wake 有進 prompt）"
        # 可能是快取造成的假紅。真凶是 TTL 不是 MIN_GAP：
        # _session_bootstrap_memories() 在 TTL 內直接回傳快取，所以剛寫的哨兵
        # 進不去，但舊哨兵會出現在回覆裡 —— 看到舊的沒新的就是這個。
        # 值一律現讀 chatflow.py，不抄。抄了就是下一個 doc-lie（brain/lint.py 檢查 D）。
        cooler_note = (f"（可能是 _BOOTSTRAP_TTL={_laap_const('_BOOTSTRAP_TTL')}s 快取造成的假紅"
                       f"：回覆若含『舊』哨兵即為此症）")
        return False, f"真紅: 回覆不含哨兵「{token}」，回覆開頭={reply[:160]}{cooler_note}"
    finally:
        _purge_probe_sentinel(mem_id)


# ── evaluator 三條邊（跨 repo：~/.aris-evaluator） ──────────────────────
# 這三條的 probe 早就寫好在 ~/.aris-evaluator/probe.py，只是沒接進來，
# 於是 topology.yaml 有邊、這裡沒函式 → 漂移檢查 exit 2 → 整組 probe 拒跑。
# （2026-08-01 發現時已經是啞的。）
# 下面只做轉接，不抄它的實作 —— 抄一份就是預約一個謊（鐵律一）。
# 它的函式回 bool 並把原因 print 出來，這裡把 stdout 接回來當 message，
# 才不會自己另編一句理由。
_EVALUATOR_PROBE = Path.home() / ".aris-evaluator" / "probe.py"


def _run_evaluator_probe(func_name: str):
    """呼叫 ~/.aris-evaluator/probe.py 裡的某條 probe，轉成 (ok, message)。"""
    import contextlib
    import importlib.util
    import io

    if not _EVALUATOR_PROBE.exists():
        return False, f"服務未啟動: 找不到 {_EVALUATOR_PROBE}"
    try:
        spec = importlib.util.spec_from_file_location("aris_evaluator_probe", _EVALUATOR_PROBE)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["aris_evaluator_probe"] = mod
        spec.loader.exec_module(mod)
    except Exception as e:
        return False, f"probe 炸了: 載入 evaluator probe 失敗: {e}"

    fn = getattr(mod, func_name, None)
    if fn is None:
        return False, f"probe 炸了: {_EVALUATOR_PROBE.name} 沒有 {func_name}()"

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            ok = fn()
    except Exception as e:
        return False, f"probe 炸了: {func_name}() 拋出 {type(e).__name__}: {e}"

    lines = [ln.strip() for ln in buf.getvalue().splitlines() if ln.strip()]
    detail = lines[-1] if lines else f"{func_name}() 無輸出"
    return bool(ok), ("綠: " if ok else "真紅: ") + detail


def psi_evaluator_state():
    """邊：注入 need_bias → psi_state.json 的 needs 值正確更新。"""
    return _run_evaluator_probe("probe_psi_state")


def evaluator_audit():
    """邊：每次評估寫一筆到 audit/，JSON schema 正確。"""
    return _run_evaluator_probe("probe_audit_write")


def dual_evaluation_compare():
    """邊：同一份 log，PSI 與 Cloud 各自評估，比對不一致。"""
    return _run_evaluator_probe("probe_dual_evaluation")


# ── Rust PSI M3 B-route probes（2026-08-01 加）──────────────


def rust_b1_read():
    """邊：daemon → read latest.json → remap.
    確認 daemon 有寫 snapshot 且 RustPsiBackend 讀得回來。"""
    state_file = "/tmp/rust-probe-b1.json"
    fifo = "/tmp/rust-probe-b1.fifo"
    for f in [state_file, fifo]:
        try: os.remove(f)
        except FileNotFoundError: pass
    binary = ROOT / "rust" / "target" / "release" / "psi-daemon"
    if not binary.is_file():
        return False, f"服務未啟動: 找不到 daemon binary {binary}"
    proc = subprocess.Popen(
        [str(binary), "--state-file", state_file, "--event-fifo", fifo,
         "--max-seconds", "5", "--seed", "1"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    try:
        raw = json.loads(Path(state_file).read_text())
        ok = raw.get("schema") == "neuralis-rust-psi/v1" and raw.get("tick", 0) > 100
        if ok:
            return True, f"schema={raw['schema']} tick={raw['tick']} pleasure={raw['affect']['pleasure']:.3f}"
        return False, f"schema={raw.get('schema','?')} tick={raw.get('tick',0)}"
    except Exception as e:
        return False, f"probe 炸了: {e}"
    finally:
        proc.terminate()
        try: proc.wait(3)
        except: proc.kill()


def rust_b2_write():
    """邊：write SocialPraise 到 FIFO → daemon 消耗 → tick 前進。"""
    state_file = "/tmp/rust-probe-b2.json"
    fifo = "/tmp/rust-probe-b2.fifo"
    for f in [state_file, fifo]:
        try: os.remove(f)
        except FileNotFoundError: pass
    binary = ROOT / "rust" / "target" / "release" / "psi-daemon"
    if not binary.is_file():
        return False, f"服務未啟動: 找不到 daemon binary {binary}"
    proc = subprocess.Popen(
        [str(binary), "--state-file", state_file, "--event-fifo", fifo,
         "--max-seconds", "6", "--seed", "2"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)

    # Check FIFO exists
    if not Path(fifo).exists():
        proc.terminate()
        return False, "FIFO 不存在"
    try:
        # Write B2 event
        fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
        os.write(fd, b"SocialPraise,1.0\n")
        os.close(fd)
        time.sleep(2)
        raw = json.loads(Path(state_file).read_text())
        tick = raw.get("tick", 0)
        if tick > 200:
            return True, f"B2 write ok, tick={tick}"
        return False, f"tick 未前進: {tick}"
    except Exception as e:
        return False, f"probe 炸了: {e}"
    finally:
        proc.terminate()
        try: proc.wait(3)
        except: proc.kill()


def rust_compare_python():
    """邊：Python vs Rust 對拍。預期會 fail（兩邊 alive 的依賴太重）。"""
    script = "/tmp/psi-compare.py"
    if not Path(script).is_file():
        # 不存在時直接生成精簡版
        return False, "找不到對拍腳本 /tmp/psi-compare.py（需手動建立）"
    try:
        r = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=25)
        if r.returncode == 0:
            return True, "PASS: dominant 一致"
        # 撈最後一行輸出
        lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
        detail = lines[-1] if lines else f"exit={r.returncode}"
        return False, f"exit={r.returncode}: {detail}"
    except subprocess.TimeoutExpired:
        return False, "對拍腳本超時 25s"


def aris_growth_check():
    """邊：綜合成長指標 —— PSI 活著 + 記憶累積 + 關鍵邊維持綠燈。

    2026-08-01 重寫：本來是在 probe 裡面再 subprocess 跑 6 條 probe，
    巢狀執行必然超過 30s timeout，於是這條邊永遠紅，紅的原因還跟
    「成長」無關（是它自己的架構）。假紅跟假綠一樣有害 ——
    人會學會忽略它。

    改成讀 `_record_result` 落地的結果檔。誰跑的不重要，重要的是
    那些邊最近一次的真實結果。讀不到 / 太舊就照實說「不知道」，
    不要拿舊資料當現況。
    """
    required = ["rust_b1_read", "rust_b2_write", "recall_not_selfinflated",
                "wake_reads_three", "psi_evaluator_state"]
    try:
        data = json.loads(RESULTS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, f"沒有 probe 結果檔（{RESULTS}）—— 先跑一次 probe.py"

    now = time.time()
    missing, stale, red = [], [], []
    for eid in required:
        r = data.get(eid)
        if not r:
            missing.append(eid)
        elif now - r.get("ts", 0) > RESULTS_FRESH_SEC:
            stale.append(eid)
        elif not r.get("ok"):
            red.append(eid)

    if missing or stale:
        return False, (f"結果不完整：缺 {missing or '—'} / 過期 {stale or '—'}"
                       f"（>{RESULTS_FRESH_SEC//60} 分鐘不採信）")
    if red:
        return False, f"關鍵邊紅著: {', '.join(red)}"
    return True, f"{len(required)} 條關鍵邊近期皆綠"


PROBES = {f.__name__: f for f in (
    board_to_channel, channel_to_aris, aris_to_memory,
    webchat_to_memory, memos_to_gbrain, wake_reads_three,
    bridge_scoring_router, relay_remembers_turn,
    recall_not_selfinflated, wake_reaches_prompt,
    psi_evaluator_state, evaluator_audit, dual_evaluation_compare,
    rust_b1_read, rust_b2_write, rust_compare_python,
    aris_growth_check)}


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    topo = yaml.safe_load(TOPO.read_text())
    edges = {e["id"]: e for e in topo["edges"]}

    # 漂移檢查：yaml 與 probe 必須一一對應
    drift = (set(edges) ^ set(PROBES))
    if drift:
        print(f"❌ topology.yaml 與 probe.py 對不上: {sorted(drift)}")
        return 2
    for e in topo["nodes"]:  # owns 唯一性
        pass
    owned: dict[str, str] = {}
    for n in topo["nodes"]:
        for c in n.get("owns", []):
            if c in owned:
                print(f"❌ 概念「{c}」有兩個 owner: {owned[c]} / {n['id']}")
                return 2
            owned[c] = n["id"]

    targets = argv or list(edges)
    fails = 0
    for eid in targets:
        if eid not in PROBES:
            print(f"❌ 沒這條邊: {eid}")
            return 2
        expect_fail = edges[eid].get("expect") == "fail"
        try:
            ok, msg = PROBES[eid]()
        except Exception as e:
            ok, msg = False, f"probe 自己炸了: {e}"
        if ok:
            mark = "✅"
        elif expect_fail:
            mark = "🟡"
        else:
            mark = "❌"
            fails += 1
        _record_result(eid, ok, msg)
        print(f"{mark} {eid:22} {msg}")
    print(f"\n{len(targets)} 條邊，{fails} 條非預期斷線")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
