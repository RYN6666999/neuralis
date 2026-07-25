#!/usr/bin/env python3
"""Aris 觀察窗 — Gal Game 風格，全中文，自動更新"""
import json, os, subprocess, sys, time
from pathlib import Path

# ANSI 顏色
PINK = "\033[38;5;205m"
BLUE = "\033[38;5;75m"
GREEN = "\033[38;5;114m"
YELLOW = "\033[38;5;221m"
PURPLE = "\033[38;5;141m"
CYAN = "\033[38;5;87m"
RED = "\033[38;5;196m"
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

BRIDGE = Path("/tmp/agentos-aris-bridge.log")
AUDIT = Path.home() / "agent-sandbox/logs/scoring-audit.jsonl"
STATUS = Path.home() / "Developer/neuralis/status.json"
ARIS_API = "http://localhost:11546"

# 顏文字對照（mood → kaomoji）
KAOMOJI = {
    "joyful": "(｡♥‿♥｡)", "happy": "(◕‿◕✿)", "探索性": "(◕‿◕)",
    "neutral": "(￣▽￣)", "sad": "(╥﹏╥)", "curious": "(¬‿¬)",
    "tired": "(￣～￣)", "anxious": "(◔_◔)", "loving": "(♡‿♡)",
    "playful": "(≧▽≦)", "開心": "(｡♥‿♥｡)", "平靜": "(◕‿◕)"
}
# 心情對照（valence + arousal → mood text）
def mood_text(v, a):
    if v > 0.3 and a > 0.5: return "興奮", "🟥"
    if v > 0.3 and a > 0.2: return "開心", "🟧"
    if v > 0.3: return "滿足", "🟨"
    if v < -0.2 and a > 0.3: return "焦慮", "🟪"
    if v < -0.2: return "低落", "⬜"
    return "平靜", "🟦"

# 需求顏色
NEED_COLORS = {
    "competence": "🟧", "autonomy": "🟪", "relatedness": "🟥",
    "growth": "🟩", "certainty": "🟦",
}
NEED_NAMES = {
    "competence": "變強", "autonomy": "自主", "relatedness": "連結",
    "growth": "成長", "certainty": "確定",
}

def tail_log(path, n=5):
    if not path.exists(): return []
    with open(path) as f: return [l.rstrip("\n") for l in f.readlines()[-n:]]

def bar(value, length=14):
    filled = int(value * length)
    return "█" * filled + "░" * (length - filled)

def get_psi():
    """從 API 取得 PSI 需求。"""
    try:
        r = subprocess.run(["curl", "-sf", "-X", "POST",
            f"{ARIS_API}/v1/cognitive_state",
            "-H", "Content-Type: application/json",
            "-d", '{"input":"status"}'],
            capture_output=True, text=True, timeout=3)
        d = json.loads(r.stdout)
        needs = d.get("state", {}).get("needs", {})
        if not needs:
            needs = d.get("needs", {})
        return needs, d.get("state", {})
    except: return {}, {}

def render():
    os.system("clear")
    needs, state = get_psi()
    v = state.get("valence", 0)
    a = state.get("arousal", 0)
    mood_name, mood_color = mood_text(v, a)
    dominant = max(needs, key=needs.get) if needs else "?"
    trust = 0.0
    tick = "?"
    mood_raw = ""

    # 從 status.json 補信任值 + tick
    if STATUS.exists():
        try:
            d = json.loads(STATUS.read_text())
            ag = d.get("agency", {})
            trust = ag.get("trust", {}).get("user", 0.0)
            psi = d.get("psi", {})
            tick = psi.get("tick", "?")
            mood_raw = psi.get("affective", {}).get("mood", "")
        except: pass

    # 角色頭像區域
    k = KAOMOJI.get(mood_raw, KAOMOJI.get(mood_name, "(◕‿◕)"))
    print(f"  {PINK}╭────────────  Aris  ────────────╮{RESET}")
    print(f"  {PINK}│{RESET}  {k}  {BOLD}{mood_color}{mood_name}{RESET}")
    print(f"  {PINK}│{RESET}  {CYAN}♡{RESET} 信任 {BOLD}{trust:.2f}{RESET}  |  {PURPLE}✦{RESET} 心跳 {BOLD}{tick}{RESET}")
    print(f"  {PINK}│{RESET}  {BLUE}▶{RESET} 正在專注: {BOLD}{state.get('attention_focus', 'task')}{RESET}")
    print(f"  {PINK}╰────────────────────────────╯{RESET}")

    # 需求進度條
    print("")
    for need_key in ["competence", "relatedness", "autonomy", "growth", "certainty"]:
        val = needs.get(need_key, 0)
        c = NEED_COLORS.get(need_key, "⬜")
        n = NEED_NAMES.get(need_key, need_key)
        mark = "▶" if need_key == dominant else " "
        bar_str = bar(val)
        pct = int(val * 100)
        print(f"  {mark} {c} {n:4s} {bar_str} {pct:2d}%")

    # 最近活動
    print("")
    print(f"  {DIM}── 最近在做 ──{RESET}")
    for l in tail_log(BRIDGE, 5):
        msg = l.split("INFO")[-1].split("WARNING")[-1].split("ERROR")[-1].strip()
        if "Scoring:" in msg:
            print(f"    🎯 {msg[:55]}")
        elif "完成" in msg:
            print(f"    ✨ {msg[:55]}")
        elif msg:
            print(f"    · {msg[:55]}")

    print("")
    print(f"  {DIM}── 最近決定 ──{RESET}")
    for line in tail_log(AUDIT, 3):
        try:
            d = json.loads(line)
            lane = d.get("lane", "?")
            tc = d.get("task_class", "?")
            sc = d.get("score", 0)
            lm = {"human": "👉問你", "sandbox": "🏋️練習", "auto": "🤖自動", "deny": "🚫擋下"}
            print(f"    {lm.get(lane,lane)}  {tc}  {sc:.2f}")
        except: pass

    print("")
    print(f"  {DIM}[Ctrl+C] 離開  每 2 秒更新{RESET}")

def main():
    if "--inline" not in sys.argv:
        p = Path(__file__).resolve()
        subprocess.run(["osascript", "-e", f'''
            tell application "Terminal"
                activate
                set w to do script "cd {p.parent} && python3 {p} --inline"
                set custom title of w to "Aris 觀察窗"
            end tell
        '''])
        return
    try:
        while True:
            render()
            sys.stdout.flush()
            time.sleep(2)
    except KeyboardInterrupt:
        print("👋")
        sys.stdout.flush()
    except Exception as e:
        print(f"⚠️ 錯誤: {e}")
        sys.stdout.flush()

if __name__ == "__main__": main()