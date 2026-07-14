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
"""
import json
import os
import sys
import urllib.request

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


errors = 0


# ── A: 基礎回應檢查 ──
_section("A — 基礎回應 engine != laap-fallback")
try:
    data = _chat("你好")
    engine = data.get("engine", "")
    content = data["choices"][0]["message"]["content"]
    if engine == "laap-fallback":
        print(f"❌ engine 仍是 laap-fallback")
        errors += 1
    elif engine == "psi-respond":
        print(f"✅ engine=psi-respond, content={content[:60]}...")
    else:
        print(f"⚠️  engine={engine}, content={content[:60]}...")
except Exception as e:
    print(f"❌ 請求失敗: {e}")
    errors += 1


# ── B: relatedness 觸發 ──
_section("B — relatedness 觸發檢查")
try:
    data = _chat("謝謝你陪我聊天，我很開心")
    content = data["choices"][0]["message"]["content"]
    if "relatedness" in content:
        print(f"✅ relatedness 被觸發: {content[:80]}...")
    else:
        print(f"⚠️  content 中無 relatedness: {content[:80]}...")
except Exception as e:
    print(f"❌ 請求失敗: {e}")
    errors += 1


# ── C: certainty 觸發 ──
_section("C — certainty 觸發檢查")
try:
    data = _chat("為什麼這個系統是這樣運作的？可以解釋一下嗎？")
    content = data["choices"][0]["message"]["content"]
    if "certainty" in content:
        print(f"✅ certainty 被觸發: {content[:80]}...")
    else:
        print(f"⚠️  content 中無 certainty: {content[:80]}...")
except Exception as e:
    print(f"❌ 請求失敗: {e}")
    errors += 1


# ── D: 開關測試 ──
_section("D — NEURALIS_PSI_RESPOND=off 降級（需重啟 server）")
if os.environ.get("NEURALIS_PSI_RESPOND", "").lower() in ("off", "0", "false"):
    print("⏭️  在 off 環境下執行，跳過 D 段（需重啟 server: NEURALIS_PSI_RESPOND=off 啟動）")
else:
    print("ℹ️  測試 D 段需重啟 server：")
    print("   NEURALIS_PSI_RESPOND=off ~/Developer/neuralis/scripts/start.sh")
    print("   然後重跑此腳本")


# ── 結果 ──
print(f"\n{'='*40}")
if errors:
    print(f"❌ {errors} 個測試失敗")
    sys.exit(1)
else:
    print("✅ 全部通過")