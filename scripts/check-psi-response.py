#!/usr/bin/env python3
"""
check-psi-response.py — 自檢 PsiCore 狀態回流聊天管線。

驗證 4 段：
A. 基礎回應 engine 不是 laap-fallback
B. 觸發 relatedness 後 delta 有記錄
C. 觸發 certainty 後 delta 有記錄
D. NEURALIS_PSI_RESPOND=off 環境退回到原 fallback

用法:
    python3 scripts/check-psi-response.py
    NEURALIS_PSI_RESPOND=off python3 scripts/check-psi-response.py  # 只測 D 段

exit code（三態，見 scripts/_check_verdict.py）:
    0 = 驗過且都好      1 = 驗過，有壞的      2 = 沒驗到（:11546 不在）

2026-08-21 修：舊版把 `urlopen` 的**任何**例外都算 `errors += 1` → exit 1，
所以「server 沒開」跟「回流管線壞了」是同一個紅燈。那是 guard.yml 明文警告的
假紅（「假紅比沒有更糟 —— 人會學會無視紅燈」）。連不上是沒驗到（exit 2）；
連上了但 engine 是 laap-fallback 才是真的壞（exit 1）。
D 段本來就需要重啟 server 才驗得到，那也是沒驗到，不是通過。
"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _check_verdict import Verdict   # noqa: E402

V = Verdict("psi-response")

API = "http://localhost:11546/v1/chat/completions"
HEADERS = {"Content-Type": "application/json"}


def _chat(user_msg: str) -> dict:
    req = urllib.request.Request(
        API,
        data=json.dumps({"messages": [{"role": "user", "content": user_msg}], "model": "laap-core"}).encode(),
        headers=HEADERS,
    )
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read())


def _section(name: str) -> None:
    print(f"\n─── {name} ───")



def _unreachable(e: Exception) -> bool:
    """連不上 = 沒驗到；已連上後的協議/內容問題才是真壞。"""
    return isinstance(e, (urllib.error.URLError, OSError)) and \
        not isinstance(e, urllib.error.HTTPError)


def _probe() -> bool:
    """先探一次 health。連不上就整支標「沒驗到」，不要讓三段各自假紅。"""
    try:
        urllib.request.urlopen("http://localhost:11546/health", timeout=5)
        return True
    except Exception as e:
        V.unknown("A-C. PsiCore 狀態回流管線",
                  f":11546 不在線（{e}）—— 基礎回應 / relatedness / certainty "
                  f"三段都沒驗到。起 server 後重跑")
        return False


def main() -> None:
    if _probe():
        # ── A: 基礎回應檢查 ──
        _section("A — 基礎回應 engine != laap-fallback")
        try:
            data = _chat("你好")
            engine = data.get("engine", "")
            content = data["choices"][0]["message"]["content"]
            if engine == "laap-fallback":
                V.fail("A. engine 仍是 laap-fallback", "狀態回流沒接上")
            elif engine == "psi-respond":
                V.ok("A. engine=psi-respond", f"content={content[:60]}...")
            else:
                V.warn(f"A. engine={engine}", f"content={content[:60]}...")
        except Exception as e:
            if _unreachable(e):
                V.unknown("A. 基礎回應", f"連線中斷: {e}")
            else:
                V.fail("A. 請求失敗", str(e))

        # ── B: relatedness 觸發 ──
        _section("B — relatedness 觸發檢查")
        try:
            content = _chat("謝謝你陪我聊天，我很開心")["choices"][0]["message"]["content"]
            if "relatedness" in content:
                V.ok("B. relatedness 被觸發", f"{content[:80]}...")
            else:
                # 「這次沒觸發」是行為偏弱，不是管線壞掉 —— 維持舊版的 ⚠️ 語義。
                V.warn("B. content 中無 relatedness", f"{content[:80]}...")
        except Exception as e:
            if _unreachable(e):
                V.unknown("B. relatedness 觸發", f"連線中斷: {e}")
            else:
                V.fail("B. 請求失敗", str(e))

        # ── C: certainty 觸發 ──
        _section("C — certainty 觸發檢查")
        try:
            content = _chat("為什麼這個系統是這樣運作的？可以解釋一下嗎？")[
                "choices"][0]["message"]["content"]
            if "certainty" in content:
                V.ok("C. certainty 被觸發", f"{content[:80]}...")
            else:
                V.warn("C. content 中無 certainty", f"{content[:80]}...")
        except Exception as e:
            if _unreachable(e):
                V.unknown("C. certainty 觸發", f"連線中斷: {e}")
            else:
                V.fail("C. 請求失敗", str(e))

    # ── D: 開關測試 ──
    _section("D — NEURALIS_PSI_RESPOND=off 降級（需重啟 server）")
    if os.environ.get("NEURALIS_PSI_RESPOND", "").lower() in ("off", "0", "false"):
        # 舊版這裡印「跳過 D 段」然後**不記任何東西**，於是 D 段從未被驗過卻
        # 不影響結論。沒驗到就是沒驗到。
        V.unknown("D. NEURALIS_PSI_RESPOND=off 降級",
                  "本 process 在 off 環境下執行，但 D 段要驗的是 server 端行為 —— "
                  "需以 off 重啟 server 後重跑")
    else:
        V.unknown("D. NEURALIS_PSI_RESPOND=off 降級",
                  "需重啟 server 才驗得到："
                  "NEURALIS_PSI_RESPOND=off scripts/start.sh，然後重跑此腳本")

    V.finish()


if __name__ == "__main__":
    main()
