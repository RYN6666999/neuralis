#!/usr/bin/env python3
"""aris_loops — Aris 自主迴圈的宿主。不起 HTTP，不寄生任何 API。

# 為什麼有這支

2026-08-19 退役 :11546 之後，AgencyLoop 與 ConsolidationLoop 一起停了 5 天沒人發現。
根因不是任一個迴圈壞掉，而是它們的**生死被綁在一支 HTTP API 上**：

    scripts/start.sh:57   startup_all()          ← 掛上 neuralis 的全部東西
    scripts/start.sh:85   runpy.run_path(api)    ← 作者的 API，順便撐住主執行緒

三個迴圈的 thread 全是 `daemon=True`
（agency.py:237 / consolidation.py:98 / status.py:134），
主執行緒一退出就被殺。所以那支 API 不是功能，**是那根柱子**。
換 API = 拔柱子 = 自主學習一起死，而且死得很安靜。

這支程式就是一根自己的柱子。它不提供 HTTP，只做四件事：
固定 import 路徑 → 起 startup_all → 吐心跳 → 卡住主執行緒。

# 六條設計原則（每條都對應一個踩過的坑）

1. 自己撐住主執行緒            ← daemon thread
2. sys.path 硬寫死             ← memory_store 同名檔靜默換版
3. 載錯檔就大聲死              ← 493 行 vs 187 行，錯了不會報錯
4. 不 pkill psi-daemon         ← start.sh:16-18 會誤殺活著的獨立 daemon
5. 自己吐心跳，死了就停        ← audit 檔會被自檢流量餵飽，不能當存活訊號
6. 迴圈起不來就死，不半殘活著  ← consolidation.py:115 的靜默失敗形態

原則 5 是整件事的教訓：08-19 之後 audit 檔還在長（人工跑自檢寫的），
所以「檔案有在更新」不代表「東西還活著」。心跳帶 pid + uptime_s，
人工跑出來的 uptime 永遠是個位數，常駐的會長到幾萬秒 —— 分得開才有用。

# 用法

    前景試跑（會真的動 gbrain，先讀下面的警告）：
        ~/Developer/laapenv/bin/python3 ~/Developer/neuralis/aris_loops.py

    只驗啟動不跑迴圈（安全，不碰資料）：
        NEURALIS_AGENCY=off NEURALIS_CONSOLIDATION=off \\
        ~/Developer/laapenv/bin/python3 ~/Developer/neuralis/aris_loops.py --check-only

    驗活著：
        scripts/check-loops.py

# ⚠️ 警告：ConsolidationLoop 會刪 gbrain 的頁

run_pass() 會對 laap/memory/episodic/* 做 delete / move（consolidation.py:143）。
門檻（PROMOTE_* / STALE_*）是 07 月調的。停機期間累積的 episodic 頁量若和當時
差很多，第一輪掃過去會刪掉什麼**沒有人算過**。第一次上線建議：

    NEURALIS_CONSOLIDATION=off   先只放 AgencyLoop，確認宿主穩了再開固化。
"""
from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
from pathlib import Path

# ── 原則 2：路徑硬寫死 ────────────────────────────────────────────
# 不讀 PYTHONPATH、不依賴 cwd。理由：Python 永遠把「執行腳本所在目錄」
# 放在 sys.path[0]，排在 PYTHONPATH 之前。neuralis 和 laap-AGI/aris_brain
# 都有 memory_store.py 與 memory_bridge.py，誰先誰後決定載到哪一份，
# 而兩份是不同世代的實作（493 行 gbrain 後端 vs 187 行 JSON 檔）。
NEURALIS = Path(__file__).resolve().parent
LAAP = NEURALIS.parent / "laap-AGI"
sys.path[:0] = [str(NEURALIS), str(LAAP), str(LAAP / "aris_brain")]

HEARTBEAT_PATH = Path(
    os.environ.get("NEURALIS_LOOPS_HEARTBEAT",
                   Path.home() / ".neuralis" / "loops-heartbeat.json"))
HEARTBEAT_INTERVAL = float(os.environ.get("NEURALIS_LOOPS_HEARTBEAT_INTERVAL", 30.0))

# 心跳的 schema 版本。check-loops.py 讀到不認得的版本要說「沒驗到」，
# 不要拿舊欄位硬解然後給出一個看起來很有信心的錯答案。
# v2（2026-08-24）：加 agency_state_loaded。版本要跟著跳，不要偷偷加欄位 ——
# 舊版 check-loops 遇到新欄位會安靜地不檢查它，那又是一個沒人看得見的缺口。
# 版本對不上時 check-loops 判 UNKNOWN（沒驗到），這才誠實。
HEARTBEAT_SCHEMA = "2"


def _die(msg: str) -> None:
    """設定層級的錯誤：印到 stderr 並用 exit 1 結束。

    plist 用 KeepAlive.SuccessfulExit=false，所以這條路徑會讓 launchd
    **停止重啟**而不是每 10 秒炸一次刷滿 log。載錯檔是設定錯誤，
    重試一萬次也不會好，讓它安靜地停在紅燈比較誠實。
    """
    print(f"FATAL: {msg}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def _assert_module_identity() -> None:
    """原則 3：確認撞名模組載到 neuralis 那份，否則大聲死。

    這裡不用 try/except 包起來 —— import 失敗本身就是要看到的事實。
    """
    import memory_store
    import memory_bridge

    for mod, want in ((memory_store, NEURALIS / "memory_store.py"),
                      (memory_bridge, NEURALIS / "memory_bridge.py")):
        got = Path(mod.__file__ or "")
        if got != want:
            _die(f"{mod.__name__} 載錯檔 → {got}\n"
                 f"       應為 {want}\n"
                 f"       （兩個 repo 有同名檔，sys.path 順序被誰改了？）")


def _warm_gbrain() -> None:
    """把 gbrain serve 叫醒，讓後面的讀寫都走熱路徑。

    失敗不擋啟動：迴圈本身不依賴 gbrain 也能跑，只是持久化會退化成
    「載不到 → _state_loaded=False → 之後每次存檔都靜默 return」。
    那條路徑不會印任何 warning，所以這裡的失敗訊息是唯一的線索，必須留痕。
    """
    try:
        from gbrain_client import get_client
        client = get_client()
        if client is None:
            print("[aris_loops] gbrain 不可用（binary 缺？）—— 狀態持久化會失效",
                  file=sys.stderr, flush=True)
            return
        t0 = time.time()
        client.call("get_stats", {}, timeout=30.0)
        print(f"[aris_loops] gbrain 暖機完成 {time.time() - t0:.1f}s", flush=True)
    except Exception as e:
        print(f"[aris_loops] gbrain 暖機失敗: {e} —— 狀態持久化可能失效",
              file=sys.stderr, flush=True)


def _write_heartbeat(agency, cons, started_at: float) -> None:
    """原則 5：心跳。程序死了 mtime 就凍住 —— 這是唯一可信的存活訊號。

    欄位名都對過原始碼，不是從交接文件抄的：
      agency.actions_total   agency.py:198 初始化 / :852 遞增
      agency.skipped_stale   agency.py:199 初始化 / :665,:670,:702 遞增
      cons.passes_total      consolidation.py:86 初始化 / :221 遞增
    """
    payload = {
        "schema": HEARTBEAT_SCHEMA,
        "pid": os.getpid(),
        "started_at": started_at,
        "uptime_s": round(time.time() - started_at),
        "ts": time.time(),
        "agency_enabled": agency is not None,
        "consolidation_enabled": cons is not None,
        "agency_actions_total": getattr(agency, "actions_total", None),
        "agency_skipped_stale": getattr(agency, "skipped_stale", None),
        # agency.py:367 —— _state_loaded=False 時 _save_state() 直接 return，
        # 而且**不印任何東西**（2026-08-24 實測：DEBUG 級別也沒有一行，
        # _save_state 的 stdout+stderr 是空字串）。整個 session 的學習狀態
        # 就這樣安靜地不落地。這是唯一會讓「Aris 學不起來」而毫無跡象的路徑，
        # 所以把旗標抬到心跳上，讓 check-loops 每次都看得到。
        "agency_state_loaded": getattr(agency, "_state_loaded", None),
        "agency_interval": getattr(agency, "interval", None),
        "consolidation_passes_total": getattr(cons, "passes_total", None),
        "consolidation_interval": getattr(cons, "interval", None),
    }
    tmp = HEARTBEAT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(HEARTBEAT_PATH)   # 原子替換：讀的人永遠不會撿到半個檔


def main() -> None:
    check_only = "--check-only" in sys.argv
    started_at = time.time()

    _assert_module_identity()

    # 原則 4：這裡**沒有** pkill psi-daemon。
    # start.sh:16-18 在設了 NEURALIS_PSI_BACKEND 時會 pkill，那是因為它
    # 自己要生一支。我們不生，所以也不該殺 —— 獨立跑著的 psi-daemon
    # 是別人的，動它就是這次調查在抓的那種副作用。
    #
    # 同理，這裡刻意**不設** NEURALIS_PSI_BACKEND=rust（start.sh:45 有設）。
    # 不設會走 PythonPsiBackend，和 :11546 時期的 rust backend 不同。
    # 這是一個明知的差異，不是疏忽：要切 rust 請在 plist 的
    # EnvironmentVariables 裡開，並且先想清楚 pkill 那條要怎麼處理。

    # gbrain client 暖機 —— 必須在 startup_all() **之前**。
    #
    # 2026-08-24 實測（探針直接讀 AgencyLoop 旗標）：`startup_all()` →
    # `ensure_agency()` → `.start()` 一啟動，daemon thread 首圈就跑
    # `_load_state()`（agency.py:252-254）。也就是說**讀取路徑在 startup_all
    # 回來之前就已經打過 gbrain 了**。暖機放在 startup_all 之後只救得到寫入，
    # 救不到讀取 —— 而讀取失敗會讓 `_state_loaded=False`，那之後每一次
    # `_save_state()` 都在 agency.py:367 靜默 return，整個 session 什麼都不存。
    # 那才是真正會讓「Aris 學不起來」的路徑，而且它連一行 warning 都不會印。
    #
    # 冷啟第一次 call 實測 5.04s；`_load_state()` 在暖的情況下只要 0.87s。
    # gbrain_client 自帶 30s 保活，開機叫一次就熱到關機。
    _warm_gbrain()

    from laap.startup import startup_all, get_agency, get_consolidation

    bus, psi, tools = startup_all()
    agency = get_agency()
    cons = get_consolidation()

    # 原則 6：半殘不算活著。
    # 兩個迴圈都被 env 明確關掉是合法的（例如只想跑 agency），
    # 但「該起卻沒起」要紅 —— 那正是 08-19 之後看不出來的狀態。
    def _wanted(name: str) -> bool:
        return os.environ.get(name, "on").lower() not in ("off", "0", "false")

    if _wanted("NEURALIS_AGENCY") and agency is None:
        _die("AgencyLoop 該起卻沒起（psi 或 tools 缺？看上面的 startup log）")
    if _wanted("NEURALIS_CONSOLIDATION") and cons is None:
        _die("ConsolidationLoop 該起卻沒起（看上面的 startup log）")
    if agency is None and cons is None:
        _die("兩個迴圈都關著 —— 這支程式沒有存在意義，不要空轉佔一個 service")

    print(f"[aris_loops] pid={os.getpid()} "
          f"agency={'on' if agency else 'off'} "
          f"consolidation={'on' if cons else 'off'} "
          f"tools={len(tools.list_tools()) if tools else 0} "
          f"psi={type(psi).__name__ if psi else None}", flush=True)

    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _write_heartbeat(agency, cons, started_at)   # 先寫一次，別讓第一個 30s 空窗

    if check_only:
        print("[aris_loops] --check-only：啟動驗證通過，不進駐。", flush=True)
        return

    stop = threading.Event()

    def _heartbeat_loop() -> None:
        while not stop.wait(HEARTBEAT_INTERVAL):
            try:
                _write_heartbeat(agency, cons, started_at)
            except Exception as e:
                # 心跳寫不出去是真問題（磁碟滿／權限），但不該讓迴圈陪葬。
                # 印到 stderr 讓 launchd log 收到；心跳自然會變舊，
                # check-loops.py 會據此判紅 —— 失敗本身就會被看見。
                print(f"[aris_loops] 心跳寫入失敗: {e}", file=sys.stderr, flush=True)

    threading.Thread(target=_heartbeat_loop, daemon=True,
                     name="aris-loops-heartbeat").start()

    def _on_signal(signum, _frame) -> None:
        print(f"[aris_loops] 收到 signal {signum}，收工", flush=True)
        stop.set()

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    # 原則 1：這一行就是柱子。
    stop.wait()

    for loop in (agency, cons):
        try:
            if loop is not None:
                loop.stop()
        except Exception as e:
            print(f"[aris_loops] stop() 失敗: {e}", file=sys.stderr, flush=True)

    # 退場時把心跳砍掉：留著會讓 check-loops.py 看到一個 pid 已死的遺骸。
    # 它本來就會判紅（pid 不在），但少一次誤判路徑總是好的。
    try:
        HEARTBEAT_PATH.unlink(missing_ok=True)
    except Exception:
        pass
    print("[aris_loops] 已停止", flush=True)


if __name__ == "__main__":
    main()
