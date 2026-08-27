# -*- coding: utf-8 -*-
"""房多多偏好 harness v2 — 情境分類 → 選對應 Ryan 口吻。
輸入一句情境/問題 → 分類出是哪種人 → 找 Ryan 存好的接法講。
沒有對應錨 → 用『薩提爾式先探渴望』當底線回。
"""
import json, os, re, difflib, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
PREF = os.path.join(BASE, "pref_fangduoduo.jsonl")

def load_prefs():
    out = []
    if os.path.exists(PREF):
        for line in open(PREF, encoding="utf-8"):
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out

def save_pref(p):
    with open(PREF, "a", encoding="utf-8") as f:
        f.write(json.dumps(p, ensure_ascii=False) + "\n")

# 情境分類：關鍵詞 → 類別名
CATEGORIES = [
    ("怕花錢白學", ["學費", "繳", "付費", "花錢", "白學", "沒結果", "被騙", "又要收"]),
    ("怕賠怕錯",   ["賠", "買錯", "賭", "賠掉", "損失"]),
    ("高薪自研",   ["自己研究", "頭腦", "專業", "聰明", "我懂", "不用教"]),
    ("防衛被坑",   ["直銷", "被坑", "投資虧", "防衛", "騙過", "資金盤"]),
    ("拖延觀望",   ["等", "再想", "考慮", "時機", "再看看", "以後"]),
]

SATIR_FALLBACK = ("先別急著講。我想先問你：現在最卡你的，不是這件事本身，"
                  "是你怕它又變成『你不想看到的那種結果』，對嗎？"
                  "我們先從把你卡住的那個點講清楚開始，會不會比較簡單一點？")

def classify(q):
    for name, kws in CATEGORIES:
        if any(kw in q for kw in kws):
            return name
    return "通用"

def pick_anchor(prefs, cat):
    # 找 type 精準對應情境的錨
    for r in prefs:
        if r.get("type") == f"情境_{cat}" or r.get("type") == f"情境_{cat}接住":
            return r
    # 找不到就回通用定義(第一個)
    return next((r for r in prefs if "通用" in r.get("type","")), None)

def norm(s):
    return re.sub(r"[^\w\u4e00-\u9fff]", "", s.lower())

def main():
    prefs = load_prefs()
    q = input("房多多情境/問題: ").strip() or "客戶怕繳學費"
    cat = classify(q)
    print("→ 判斷這情境:", cat)
    ref = pick_anchor(prefs, cat)
    if ref:
        out = ref["user_voice"]
        print("→ 啟用 Ryan 錨：「%s」" % out)
    else:
        out = SATIR_FALLBACK
        print("→ 無對應錨，用薩提爾底線接法")

    print("\nharness:「%s」" % out)
    edit = input("\n校正(直接 Enter 保留): ").strip()
    if edit:
        p = {
            "type": f"情境_{cat}",
            "user_voice": edit,
            "tags": ["校正", "v2"],
            "why": "由「%s」經 Ryan 當場校正" % out,
            "avoid": (ref or {}).get("avoid", []),
            "captured_at": datetime.datetime.now().isoformat(),
        }
        save_pref(p)
        print("已記住校正，下一版會用你的版本。")
    else:
        print("保留原句。")

if __name__ == "__main__":
    main()
