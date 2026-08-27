#!/usr/bin/env python3
"""check-loops — 驗 aris_loops 宿主是不是真的活著，而且真的在做事。

    PYTHONPATH=. ../laapenv/bin/python scripts/check-loops.py

# 為什麼「活著」和「有在做事」要分開判

2026-08-19 之後 AgencyLoop 與 ConsolidationLoop 一起死了 5 天沒人發現，
因為 `consolidation-audit.jsonl` 還在長 —— 那些是人工跑自檢寫進去的。
**檔案有在更新 ≠ 東西還活著。**

而就算宿主活著，agency.py:669 在 seed 為空時會 `skipped_stale += 1` 直接返回，
什麼都不做。2026-08-23 前台實測：running=True、actions_total=0、
skipped_stale=1、audit 沒增一行。**行程活著 ≠ 有產出。**

所以這支腳本有兩層判準：
  A-C 段：宿主活著嗎（心跳新鮮、pid 還在）
  D-F 段：有在做事嗎（passes / actions 有沒有動）

D-F 用 warn 不用 fail：沒產出是已知的設計缺口（自舉種子還沒做），
不是宿主壞了。混在一起判會讓「宿主死了」被「還沒產出」的雜訊淹掉。

# 三態怎麼分

  FAIL     心跳不存在 / 太舊 / pid 已死  ← 這些都是量到的事實，不是沒驗到
  WARN     活著但還沒產出                ← 可接受的降級
  UNKNOWN  心跳 schema 不認得            ← 真的沒驗到，不准裝綠燈

心跳檔不存在**不是** UNKNOWN。UNKNOWN 是「依賴不在所以我沒辦法量」，
而這裡「檔案不在」本身就是答案：迴圈沒在跑。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _check_verdict import Verdict, guard   # noqa: E402

HEARTBEAT_PATH = Path(
    os.environ.get("NEURALIS_LOOPS_HEARTBEAT",
                   Path.home() / ".neuralis" / "loops-heartbeat.json"))

# 心跳每 30s 寫一次（aris_loops.HEARTBEAT_INTERVAL）。90s = 連漏三拍才判死，
# 留給系統睡眠／磁碟卡頓一點餘裕，又不至於讓一個死掉的宿主綠好幾分鐘。
STALE_AFTER_S = float(os.environ.get("NEURALIS_LOOPS_STALE_AFTER", 90.0))

# 剛起來的行程還沒累積產出是正常的，別在這段誤報。
# 300s 也剛好能抓到「launchd 反覆重啟」：那種情況 uptime 永遠回到個位數。
YOUNG_S = 300.0

# 活著超過這麼久還零產出，就值得看一眼了。
# agency 預設 interval=60s（agency.py:187），一小時 = 約 60 輪都沒動作。
BARREN_AFTER_S = 3600.0

KNOWN_SCHEMA = {"2"}


def _read_heartbeat(v: Verdict):
    """A 段：心跳檔在不在、讀不讀得動、schema 認不認得。"""
    if not HEARTBEAT_PATH.exists():
        v.fail("A. 心跳存在", f"{HEARTBEAT_PATH} 不存在 —— 宿主從沒起來過，"
                              f"或 plist 沒裝。裝法見 "
                              f"scripts/install-aris-loops-launchagent.sh")
        return None
    try:
        hb = json.loads(HEARTBEAT_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        v.fail("A. 心跳存在", f"{HEARTBEAT_PATH} 讀不動: {e}")
        return None

    schema = str(hb.get("schema", ""))
    if schema not in KNOWN_SCHEMA:
        # 拿舊欄位硬解一個不認得的 schema，會給出一個看起來很有信心的錯答案。
        v.unknown("A. 心跳存在", f"schema={schema!r} 不認得（認得 {sorted(KNOWN_SCHEMA)}）"
                                 f" —— 心跳格式變了，這支腳本要跟著更新")
        return None

    v.ok("A. 心跳存在", f"schema={schema} pid={hb.get('pid')}")
    return hb


def _check_fresh(v: Verdict, hb: dict) -> bool:
    """B 段：心跳新不新鮮。這是唯一可信的存活訊號。"""
    age = time.time() - float(hb.get("ts", 0))
    if age > STALE_AFTER_S:
        v.fail("B. 心跳新鮮", f"最後一拍在 {age:.0f}s 前（門檻 {STALE_AFTER_S:.0f}s）"
                              f" —— 宿主死了或卡住了")
        return False
    v.ok("B. 心跳新鮮", f"{age:.0f}s 前")
    return True


def _pid_alive(pid: int) -> bool:
    """signal 0 探測：不送訊號，只問「這個 pid 存不存在且我有權碰」。"""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True   # 存在，只是不是我的
    return True


def _check_pid(v: Verdict, hb: dict) -> None:
    """C 段：心跳檔可能是遺骸 —— 行程死了但檔案還在。"""
    pid = hb.get("pid")
    if not isinstance(pid, int):
        v.fail("C. 行程存活", f"心跳沒帶合法 pid: {pid!r}")
        return
    if not _pid_alive(pid):
        v.fail("C. 行程存活", f"pid={pid} 已不存在 —— 心跳檔是遺骸")
        return
    v.ok("C. 行程存活", f"pid={pid}")


def _check_uptime(v: Verdict, hb: dict) -> float:
    """D 段：太年輕 = 剛起來，或者 launchd 正在反覆重啟。"""
    uptime = float(hb.get("uptime_s", 0))
    if uptime < YOUNG_S:
        v.warn("D. 已穩定運行", f"uptime={uptime:.0f}s（< {YOUNG_S:.0f}s）"
                                f" —— 剛起來，或 launchd 在反覆重啟。"
                                f"隔幾分鐘再跑一次；uptime 沒長就是後者")
    else:
        v.ok("D. 已穩定運行", f"uptime={uptime / 3600:.1f}h")
    return uptime


def _check_productive(v: Verdict, hb: dict, uptime: float) -> None:
    """E/F 段：活著，但有在做事嗎。

    刻意用 warn 不用 fail：零產出是已知的設計缺口（自舉種子還沒做，
    見 agency.py:658-669），不是宿主壞掉。把它判紅會讓真正的宿主死亡
    被雜訊淹掉 —— 那就是這支腳本要避免的事。
    """
    if hb.get("consolidation_enabled"):
        passes = hb.get("consolidation_passes_total")
        interval = float(hb.get("consolidation_interval") or 1800.0)
        if passes is None:
            v.warn("E. 固化有產出", "心跳沒帶 passes_total（欄位改名了？）")
        elif passes == 0 and uptime > interval * 2:
            v.warn("E. 固化有產出", f"passes=0 而 uptime={uptime:.0f}s "
                                    f"已過 2 個 interval({interval:.0f}s)"
                                    f" —— 排程沒觸發，或睡眠窗判斷一直不成立")
        else:
            v.ok("E. 固化有產出", f"passes={passes}")
    else:
        v.ok("E. 固化有產出", "ConsolidationLoop 明確關閉（NEURALIS_CONSOLIDATION=off）")

    if hb.get("agency_enabled"):
        # G 段先判，因為它比「有沒有行動」嚴重得多。
        #
        # 2026-08-24 實測（PATH 抽掉 gbrain）：_load_state 失敗 →
        # _state_loaded=False → 之後每次 _save_state() 在 agency.py:367
        # 直接 return，stdout+stderr 是空字串，DEBUG 級別也沒有一行 log。
        # 迴圈照跑、心跳照長、actions 照增，但**學到的東西一個字都不落地**。
        # 重啟後從零開始，外表看起來完全正常。
        #
        # 判 FAIL 不判 WARN：這不是可接受的降級，這是「在學但學不進去」。
        loaded = hb.get("agency_state_loaded")
        if loaded is False:
            v.fail("G. 學習狀態可持久化",
                   "_state_loaded=False —— 開機時 gbrain 讀不到，"
                   "本 session 的學習狀態不會落地（agency.py:367 靜默 return）。"
                   "查 gbrain binary 在不在、/tmp/com.neuralis.aris-loops.log 的暖機行")
        elif loaded is None:
            v.warn("G. 學習狀態可持久化", "心跳沒帶 agency_state_loaded（宿主版本較舊？）")
        else:
            v.ok("G. 學習狀態可持久化", "_state_loaded=True")

        actions = hb.get("agency_actions_total")
        stale = hb.get("agency_skipped_stale")
        if actions is None:
            v.warn("F. 自主有產出", "心跳沒帶 actions_total（欄位改名了？）")
        elif actions == 0 and uptime > BARREN_AFTER_S:
            v.warn("F. 自主有產出", f"actions=0 skipped_stale={stale} "
                                    f"而 uptime={uptime / 3600:.1f}h"
                                    f" —— 活著但沒行動。若 skipped_stale 同步在長，"
                                    f"就是 agency.py:669 的冷啟動種子缺席，"
                                    f"那是已知缺口不是宿主問題")
        else:
            v.ok("F. 自主有產出", f"actions={actions} skipped_stale={stale}")
    else:
        v.ok("F. 自主有產出", "AgencyLoop 明確關閉（NEURALIS_AGENCY=off）")


def main() -> None:
    v = Verdict("check-loops")
    print(f"心跳檔: {HEARTBEAT_PATH}")

    # 先給定值：guard 吞掉段內例外之後，後面的段落仍會執行，
    # 這時 hb / uptime 若還沒被賦值就會 NameError —— 那會變成
    # 「腳本自己炸掉」而不是「檢查失敗」，兩者的意義完全不同。
    hb = None
    uptime = 0.0

    with guard(v, "A. 心跳存在"):
        hb = _read_heartbeat(v)

    if hb:
        with guard(v, "B. 心跳新鮮"):
            _check_fresh(v, hb)
        with guard(v, "C. 行程存活"):
            _check_pid(v, hb)
        with guard(v, "D. 已穩定運行"):
            uptime = _check_uptime(v, hb)
        with guard(v, "E/F. 產出"):
            _check_productive(v, hb, uptime)

    v.finish()


if __name__ == "__main__":
    main()
