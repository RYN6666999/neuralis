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
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TOPO = ROOT / "topology.yaml"
CHANNEL = Path("/tmp/aris-scream-channel.jsonl")
BRIDGE_LOG = Path("/tmp/agentos-aris-bridge.log")
MEM_DB = Path.home() / ".aris-memory.db"
BOARD = Path.home() / ("Library/Mobile Documents/iCloud~md~obsidian"
                       "/Documents/Fun/Aris/留言板.md")
MEM_URL = "http://127.0.0.1:11551"
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
    """兩輪哨兵：第二輪答不出第一輪的代號 → relay 沒回放歷史。"""
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
    if token in reply:
        return True, f"第二輪回覆含哨兵「{token}」（注意：可能是從記憶繞回來的，不一定是從 messages 回放）"
    return False, f"真紅: 第二輪回覆不含哨兵「{token}」，回覆={reply[:120]}"


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


def wake_reaches_prompt():
    """塞哨兵 attention_line → 問 Aris 懸著什麼 → 看回覆含不含哨兵。
    存記憶時設 encoding_salience=5 確保不被 τ 排序擠出前 5。"""
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
    if not store_resp.get("id"):
        return False, f"probe 炸了: store 回應無 id, resp={store_resp}"
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
    # 可能是冷卻造成的假紅
    cooler_note = "（可能是 _BOOTSTRAP_MIN_GAP=1800 冷卻造成的假紅）"
    return False, f"真紅: 回覆不含哨兵「{token}」，回覆開頭={reply[:160]}{cooler_note}"


PROBES = {f.__name__: f for f in (
    board_to_channel, channel_to_aris, aris_to_memory,
    webchat_to_memory, memos_to_gbrain, wake_reads_three,
    bridge_scoring_router, relay_remembers_turn,
    recall_not_selfinflated, wake_reaches_prompt)}


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
        print(f"{mark} {eid:22} {msg}")
    print(f"\n{len(targets)} 條邊，{fails} 條非預期斷線")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
