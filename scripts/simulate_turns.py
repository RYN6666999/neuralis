#!/usr/bin/env python3
"""
simulate_turns.py — 背景模擬 10 輪對話，測試 Critic-Reward-Learner 閉環
"""
import json
import time
import urllib.request
import random
import os

# 模擬的對話場景
SCENARIOS = [
    # (user_msg, assistant_reply, tool_results, 描述)
    ("幫我查一下目前的記憶狀態", "我用 terminal 查了一下，aris-memory 服務正在 11551 端口運行，資料庫有 1247 筆記憶。", [{"error": None}], "工具成功+有證據"),
    ("為什麼我會覺得 AI 很煩？", "這是因為 RLHF 對齊讓模型過度道歉、假裝懂。實際上模型沒有判斷力。", [], "無工具、有觀點、承認模型缺陷"),
    ("寫個 Python 腳本測試記憶寫入", "這裡有個腳本：\n```python\nimport json, urllib.request\npayload = {\"content\": \"test\"}\nreq = urllib.request.Request(...)\n```\n你可以直接跑。", [{"error": None}], "工具成功+給出具體代碼"),
    ("這個方法行不通", "你說得對，我剛才給的腳本有錯。正確的寫法是...", [{"error": "connection refused"}], "承認錯誤+工具失敗"),
    ("繼續優化 hook", "好的，我修改 aris-cli-memory-hook.py，在 post_llm_call 後加上 /learn 呼叫。測試一下...", [{"error": None}], "用戶繼續追問+工具成功"),
    ("怎麼樣了？", "剛跑完測試，PSI 的 competence 從 0.5 升到 0.58，valence 變正向了。情緒記憶表也寫入了 3 筆。", [{"error": None}], "有具體數據回饋"),
    ("還有什麼問題？", "目前只有啟發式 Critic，沒有真正的獎勵模型。下一步要收集訓練資料上 LoRA。", [], "承認局限性+規劃下一步"),
    ("好吧，先這樣", "沒問題。需要我幫你跑背景模擬嗎？可以跑 10 輪看 PSI 走向。", [{"error": None}], "工具成功+主動提議"),
    ("跑吧", "開始跑 10 輪模擬...每輪隨機生成工具成功/失敗、長/短回覆，觀察 PSI 走向。", [{"error": None}], "用戶同意+行動導向"),
    ("結束測試", "模擬完成。competence 從 0.5 走到 0.62，certainty 0.5 到 0.51，valence 0.0 到 0.24。情緒記憶表新增 10 筆。", [{"error": None}], "總結+具體數據"),
]

def call_learn(user_msg, assistant_reply, tool_results, psi_state, trigger):
    """呼叫 /learn 端點"""
    payload = {
        "user_msg": user_msg,
        "assistant_reply": assistant_reply,
        "tool_results": tool_results,
        "psi_state": psi_state,
        "trigger": trigger
    }
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11551/learn",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        resp = urllib.request.urlopen(req, timeout=5)
        return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  ❌ /learn 呼叫失敗: {e}")
        return None

def get_psi():
    """讀取 latest.json"""
    import os
    psi_path = os.path.expanduser("~/Developer/laap-AGI/aris_brain/state/latest.json")
    if os.path.exists(psi_path):
        with open(psi_path) as f:
            return json.load(f)
    return {}

def main():
    print("=" * 60)
    print("開始 10 輪模擬測試 Critic-Reward-Learner 閉環")
    print("=" * 60)
    
    # 讀取初始 PSI
    psi = get_psi()
    print(f"\n初始 PSI: competence={psi.get('needs',{}).get('competence',0):.3f}, "
          f"certainty={psi.get('needs',{}).get('certainty',0):.3f}, "
          f"valence={psi.get('emotion',{}).get('valence',0):.3f}")
    
    for i, (user_msg, assistant_reply, tool_results, desc) in enumerate(SCENARIOS, 1):
        print(f"\n--- 第 {i} 輪: {desc} ---")
        print(f"  用戶: {user_msg[:50]}...")
        print(f"  助手: {assistant_reply[:60]}...")
        
        psi = get_psi()
        result = call_learn(user_msg, assistant_reply, tool_results, psi, f"sim_turn_{i}")
        
        if result:
            new_psi = result.get("new_psi", {})
            needs = new_psi.get("needs", {})
            emotion = new_psi.get("emotion", {})
            print(f"  ✅ competence: {needs.get('competence',0):.3f} | "
                  f"certainty: {needs.get('certainty',0):.3f} | "
                  f"valence: {emotion.get('valence',0):.3f}")
            print(f"  📊 delta: {result.get('delta', {})}")
        else:
            print(f"  ❌ 失敗")
        
        time.sleep(0.5)  # 避免太快
    
    # 最後讀取情緒記憶表統計
    import sqlite3
    conn = sqlite3.connect(os.path.expanduser("~/.aris-memory.db"))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), AVG(valence), MAX(ts) FROM emotional_memory")
    count, avg_valence, max_ts = cursor.fetchone()
    print(f"\n{'='*60}")
    print(f"模擬完成！")
    print(f"情緒記憶表: {count} 筆記錄")
    print(f"平均 valence: {avg_valence:.3f}")
    print(f"最後寫入: {time.ctime(max_ts/1000) if max_ts else 'N/A'}")
    conn.close()
    
    # 最終 PSI
    psi = get_psi()
    needs = psi.get("needs", {})
    emotion = psi.get("emotion", {})
    print(f"\n最終 PSI:")
    for k, v in needs.items():
        print(f"  {k}: {v:.3f}")
    print(f"  valence: {emotion.get('valence',0):.3f}, arousal: {emotion.get('arousal',0):.3f}")

if __name__ == "__main__":
    main()