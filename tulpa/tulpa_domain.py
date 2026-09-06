#!/usr/bin/env python3
"""tulpa_domain — 領域樹定義與路由（窄而深）。

切割自 tulpa_engine.py（947 行）。
獨立模組：領域樹可以單獨測試、抽換、擴充。
"""

from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import List, Optional

from tulpa.tulpa_db import load_object_facets


@dataclass
class DomainNode:
    """領域樹節點：L1 分類 → L2 細分 → L3 策略/記憶。"""
    name: str
    keywords: List[str]                     # 觸發此節點的關鍵字
    context_text: str = ""                  # 此節點的 context
    children: List['DomainNode'] = field(default_factory=list)
    memory_key: Optional[str] = None        # 對應 ontology 物件 ID


COACH_TREE = DomainNode(
    name="房產財商教練",
    keywords=["課程", "教學", "訓練", "教練", "方法論", "體系", "知識", "輸出", "設計課程", "學員", "教材", "框架", "理論", "輸出方法論"],
    children=[
        DomainNode(
            name="課程設計",
            keywords=["課程", "教材", "設計", "框架", "體系", "輸出"],
            context_text="設計課程不是寫SOP——是在設計一場認知重組。讓學員從「不知道不知道」到「知道不知道」再到「知道知道」。先問：這堂課要讓人改變什麼行為？",
            children=[
                DomainNode(
                    name="教學設計",
                    keywords=["教學", "講解", "示範", "演練", "回饋"],
                    context_text="教與講不同。教是設計體驗，講是輸出資訊。每堂課至少一個「做中學」環節，學員不做就沒學。",
                ),
                DomainNode(
                    name="方法論輸出",
                    keywords=["方法論", "框架", "理論", "模型", "SOP", "流程"],
                    context_text="方法論不是知識堆疊，是可操作的思維路徑。好的方法論：①有步驟可執行 ②有原則可判斷 ③有例子可模仿 ④有反例可避開。",
                ),
            ],
        ),
        DomainNode(
            name="學員輔導",
            keywords=["學員", "輔導", "追蹤", "進度", "考核", "評量"],
            context_text="輔導不是上課，是看個人卡在哪一關。先問：他的問題是知識缺口、技能缺口、還是心態缺口？三類用三種解法。",
            children=[
                DomainNode(
                    name="個人 Coaching",
                    keywords=["1對1", "個別", "私密", "深談", "深度"],
                    context_text="1對1 Coaching 的節奏：先聽→再問→最後才給建議。Ryan 的風格：問清楚比說漂亮重要。",
                ),
                DomainNode(
                    name="團體訓練",
                    keywords=["團體", "集體", "工作坊", "seminar", "營隊"],
                    context_text="團體訓練的重點是「同伴壓力」和「即時練習」。學員互相看彼此怎麼做，比聽講師講有效十倍。",
                ),
            ],
        ),
        DomainNode(
            name="教練體系",
            keywords=["體系", "組織", "管理", "成長", "擴展", "複製"],
            context_text="教一人會教，教十人需要體系，教百人需要機器。體系的三要素：SOP（流程）、選拔（人是誰）、激勵（為什麼留下）。",
            children=[
                DomainNode(
                    name="制度設計",
                    keywords=["制度", "規範", "準則", "考核", "標準"],
                    context_text="好制度讓人不用靠自律也能做對的事。壞制度逼人違背本性。設計前先問：這個制度在獎勵什麼行為？",
                ),
                DomainNode(
                    name="人才培育",
                    keywords=["培育", "訓練教練", "升遷", "晉升", "接班人"],
                    context_text="培育不是上更多課，是找對的人給對的環境。選拔重潛質，訓練重實戰，晉升重結果。",
                ),
            ],
        ),
    ],
)

# ═══════════════════════════════════════════════════════════════
# 除錯方法論領域樹 — 從真實debug經驗中長出來的判斷力
# ═══════════════════════════════════════════════════════════════

DEBUG_TREE = DomainNode(
    name="除錯方法論",
    keywords=["debug", "審計", "trace", "ponytail", "紅軍", "bug", "修復", "檢查", "驗證", "收斂", "完成", "對賭", "查清楚", "判斷力", "收工", "有效", "指標", "問清楚"],
    children=[
        DomainNode(
            name="Ponytail 審計",
            keywords=["ponytail", "清查", "清單", "列清單", "全面", "盤點", "先列"],
            context_text="先列清單再給結論——不跳步驟。Step 1全面清查→Step 2依賴圖→Step 3風險分級🔴🟡🟢→Step 4分批執行→Step 5單一權威管線→Step 6加警報→Step 7驗證。",
            children=[
                DomainNode(
                    name="風險分級",
                    keywords=["🔴", "🟡", "🟢", "紅燈", "黃燈", "綠燈", "風險", "分級"],
                    context_text="🔴紅燈：砍了會炸（主服務、核心import）→🟡黃燈：砍了需留stub→🟢綠燈：直接刪除零影響。",
                ),
                DomainNode(
                    name="分批執行",
                    keywords=["分批", "先綠", "再黃", "最後紅", "順序"],
                    context_text="先綠燈、再黃燈、最後才碰紅燈。每步操作後驗證所有health端點。",
                ),
            ],
        ),
        DomainNode(
            name="紅軍攻擊方案",
            keywords=["紅軍", "攻擊", "方案", "漏洞", "破綻", "自審", "打自己", "抽象層", "靜默失敗", "平行結構", "收斂"],
            context_text=(
                "提案後先攻自己：①這跟誰綁在一起？（DB壽命=子系統壽命）②誰會讀它？（寫了沒人讀=空島）③誰觸發它？（被動=等人踹，自動=循環）④我是不是在蓋第四座島？（先打通已存在的路再建新路）"
                "⑤抽象層靜默失敗：AI寫程式的特有bug——看到新數據就建新表/新端點/新節點，不問現有結構能不能吸收。可以長新節點，但長之前必須回答：❶現有結構為什麼不能吸收？❷新東西的獨特價值是什麼？❸如果不建會怎樣？三題答完才准長。違反=🔴收斂違規。"
                "實例：compressed_lessons 跟 domain_optimization 同一張地圖、hybrid_search 跟 ternary_search 同一件事。\n\n"
                "🔴 NOT-TODO（絕對不要做的事）：\n"
                "① 不要建跟現有結構平行的新表/新端點/新節點。domain_optimization 在存就不要建 compressed_lessons。\n"
                "② 不要寫需要我判斷才能正確的映射表。DIM_TO_DEBUG_NODE 我寫錯就是證明。\n"
                "③ 不要硬編碼可從現有結構自動派生的東西。risk-scorer 維度該從除錯樹 keywords 讀。\n"
                "④ 不要在 hook 管線加新步驟。既有步驟能吸收就不要加 Step 3.2b。\n"
                "⑤ 不要宣稱完成卻沒驗證對面收到。鐵律零：改了沒重啟=沒發生。\n"
                "⑥ 不要用「我應該會記得」代替機械化規則。規則寫在程式碼裡強制我查，不要靠我記。\n"
                "⑦ 不要用自我驗證代替獨立驗證（0 信心路由）。自己寫完自己測 = 沒測。\n"
                "⑧ 不要建沒有消費者的功能。建之前先回答：誰讀它的輸出？\n"
                "⑨ 不要只修一個檔案就停。找到一個 bug → 搜整個 repo 有無同樣 pattern。\n"
                "⑩ 不要用 syntax check 取代 runtime 驗證。py_compile 不證明系統會動。\n"
                "⑪ 不要當丞相（附和）。對的說對、錯的說錯、有證據說有證據。"
            ),
        ),
        DomainNode(
            name="消費者鏈檢查",
            keywords=["消費者", "誰會讀", "誰消費", "輸出給誰", "feed"],
            context_text="每次實作完一個功能，先問：誰消費這個輸出？它在哪個pipe裡？消費者斷了會怎樣？如果答案是「不知道」或「沒人」，先不要宣布完成。",
            memory_key="消費者",
        ),
        DomainNode(
            name="驗證清單",
            keywords=["驗證", "檢查", "完整測試", "單點", "路徑", "邊界", "斷線", "空數據"],
            context_text="驗證6項：□單點測試（import+回傳正確）□所有return路徑都覆蓋□誰讀這個結果？（消費者檢查）□服務掛了不擋主流程（斷線檢查）□DB沒資料不亂報（空數據檢查）□session_id空？domain_path空？（邊界檢查）",
            memory_key="驗證",
        ),
        DomainNode(
            name="self-audit 循環",
            keywords=["self-audit", "自審", "自我審計", "observer", "insight", "提醒"],
            context_text="compete結束後自動檢查domain_optimization：校正率>40%→寫入observer_insights→下一輪hook注入【自我審計提醒】。不需要等人說「你錯了」，系統自己會先報。",
        ),
        DomainNode(
            name="鋼人審計",
            keywords=["鋼人", "審計", "普查", "真相", "truth census", "實測", "dead path", "死路", "gilnexus", "codegraph", "宣稱 vs 事實", "證據 vs 假設", "FAB", "無視表面話", "report card"],
            context_text=(
                "鋼人審計是去脈絡化的真相普查：把你的宣稱當成行銷文案，逐條到 runtime 拿證據檢驗。"
                "步驟：① 列出你的 claim（我說的每項優勢/FAB）→ ② curl/sqlite/grep 拿真實數據 → ③ 每條標 ✅ Evidence（有 terminal stdout）或 🔴 虛構（不存在）"
                "→ ④ 找出死路（code path exists but never called / DB table empty / endpoint 404）→ ⑤ 給 report card：真實存在 / 誇大 / 虛構。"
                "實例（2026-08-29）：我 FAB 說機械化判斷層存在 → 實測 decision_log 有 11 筆但只有鋼人路徑、verification_log 表空、blindspot 404、observer_insights 從未寫入。"
                "GitNexus 的限制：Python 符號追蹤有效但 SQL string 和 YAML config 不在索引，需 terminal/grep 交叉驗證。"
                "鐵律：孤島函數（有定義無 caller）vs 空表（有 schema 無 INSERT）vs 死端點（spec 有 code 無）— 三種死路各有不同的修法。"
            ),
        ),
        DomainNode(
            name="對賭驗證機制",
            keywords=["對賭", "驗證", "打臉", "再測", "逼問", "不信", "騙"],
            context_text="Ryan不相信我說「完成」。他的工作流：我說完→他再測→找到新bug→我被打臉→他邏輯正確→記到verification_log。歷史數據證明我總是宣稱太早，他總是對的。機械化流程：宣稱完成→驗證清單全過→交給Ryan測試→找到剩餘bug→記錄→再宣稱→再驗證→直到連續N輪找不到新bug。",
        ),
        DomainNode(
            name="判斷完成時機",
            keywords=["停", "時機", "判斷", "敷衍", "騙自己", "到底", "真正完成"],
            context_text="什麼時候可以說完成了？不是「我覺得好了」。是verification_log顯示連續N輪found=0。不是因為懶得找了，是真的找不到了。懷疑自己敷衍自己→再跑一次紅軍攻擊+驗證清單。如果還是0，才是真的停。不是我的判斷力決定停，是機械化數據決定停。",
        ),
        DomainNode(
            name="PSI 行為有效性指標",
            keywords=["先問清楚", "先驗證", "有效", "指標", "psi_action_log", "ask_clear", "verify_first", "outcome"],
            context_text="PSI觸發的行動要有機械化指標驗證是否有效，不是只換一句話。ask_clear→action_taken=1表示我確實問了問題沒直接回答，outcome=1表示用戶回覆後certainty提升。verify_first→action_taken=1表示我確實跑了工具驗證，outcome=1表示驗證結果改變了結論。self_audit→action_taken=1表示我確實查了DB，outcome=1表示找到新問題或確認無問題。數據存在psi_action_log表，用_psi_action_effectiveness()查執行率與有效率。",
        ),
    ],
)

ALL_DOMAINS = [COACH_TREE, DEBUG_TREE]


def _match_tree(node: DomainNode, text: str) -> dict:
    """遞迴匹配領域樹。回傳最深匹配節點的 context + path。"""
    if not any(kw in text for kw in node.keywords):
        return {"matched": False, "depth": 0, "path": []}
    # 防雜訊：單字元關鍵字（約、追、傭、談等）在無領域專詞時不觸發
    has_domain_word = any(dw in text for dw in _domain_words())
    valid_kws = [kw for kw in node.keywords if kw in text and (len(kw) >= 2 or has_domain_word)]
    if not valid_kws and not has_domain_word:
        # 只有單字元關鍵字命中但無領域專詞→不觸發
        return {"matched": False, "depth": 0, "path": []}
    path = [node.name]
    best = node
    best_depth = 1
    for child in node.children:
        result = _match_tree(child, text)
        if result["matched"] and result["depth"] + 1 > best_depth:
            best = result["leaf"]
            best_depth = result["depth"] + 1
            path = [node.name] + result["path"]
    ctx = best.context_text
    if best.memory_key:
        facets = load_object_facets(best.memory_key)
        if facets:
            past = " | ".join(f"[{f['tulpa_name']}] {f['view']} (×{f['count']})" for f in facets[:3])
            ctx = f"{ctx}\n過去記錄: {past}"
    return {"matched": True, "depth": best_depth, "path": path, "context": ctx, "leaf": best, "leaf_name": best.name}


def route_domain(text: str) -> dict:
    """全域 route：輸入先走所有已註冊領域樹，最深匹配優先。"""
    best = {"matched": False, "depth": 0, "context": "", "path": []}
    for domain in ALL_DOMAINS:
        result = _match_tree(domain, text)
        if result["matched"] and result["depth"] > best["depth"]:
            best = result
    if best["matched"]:
        return {"routed": True, "context": best["context"], "domain_path": best["path"]}
    return {"routed": False, "context": "", "domain_path": []}


def _find_node(path: list, tree=ALL_DOMAINS) -> Optional[object]:
    """依領域路徑(names)定位 DomainNode。"""
    for d in tree:
        if d.name != path[0]:
            continue
        node = d
        for seg in path[1:]:
            nxt = None
            for ch in node.children:
                if ch.name == seg:
                    nxt = ch; break
            if nxt is None:
                return d
            node = nxt
        return node
    return None


def _path_keywords(domain_path: list) -> set:
    """收集 domain_path 從根到葉所有節點的 keywords。"""
    known = set()
    def walk(node, prefix):
        p = prefix + [node.name]
        known.update(node.keywords)
        for ch in node.children:
            walk(ch, p)
    for d in ALL_DOMAINS:
        walk(d, [])
    return known


def _domain_words() -> list:
    """領域專詞白名單。"""
    return ["課程", "教學", "教材", "設計", "框架", "體系", "輸出", "方法論",
            "學員", "輔導", "教練", "制度", "培育", "升遷", "團隊", "工作",
            "debug", "審計", "trace", "ponytail", "紅軍", "bug", "修復",
            "驗證", "收斂", "對賭", "判斷力", "recall", "tulpa", "psi",
            "memory", "記憶", "認知", "架構"]