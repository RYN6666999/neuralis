"""aris_learner — Critic / Reward / Learn 的純函式核心。

這個檔是 `/learn` 端點的實作。2026-09-03 之前 `ArisMemory.critic/reward/learn`
三個方法**從來沒有被寫過**（`git log -S"def critic" --all` 全空），所以端點永遠回
`400 'ArisMemory' object has no attribute 'critic'`。

誠實的範圍宣告（不要再讓名字比實物大一號）
------------------------------------------
* **這是啟發式評分，不是學到的獎勵模型。** 分數來自可觀察訊號（工具有沒有報錯、
  回應裡有沒有可查證的證據、有沒有承認錯誤或局限、有沒有給下一步），不是訓練出來的。
  `simulate_turns.py` 第 7 個場景自己就寫了「目前只有啟發式 Critic，沒有真正的
  獎勵模型」—— 這裡照實做到那句話，不多宣稱。
* **`learn()` 不會去改 `latest.json`。** 那份 PSI 狀態由 psi_core /
  `psi-daemon` 擁有（`laap_brain/psi_core_integration.py`、`psi_core/__init__.py`
  在寫）。從這裡再寫一次就是兩個 writer 互相蓋。`learn()` 只做兩件事：
  把 delta 套到**呼叫端傳進來的** psi 快照上回傳，以及把這一輪的軌跡寫進
  `emotional_memory` 表。要不要採用回傳的新 psi，是呼叫端的決定。
* 因此 `emotional_memory` 目前是**軌跡紀錄**，還不是回饋迴路 —— 全機搜尋
  只有 `simulate_turns.py` 在數它的筆數，沒有東西讀它去改變行為。要變成真的
  迴路，得有消費端。這件事這個檔做不到，也不假裝做到了。

所有函式都是純的、無 I/O、可單測。sqlite 寫入在 `aris-memory.py` 的
`ArisMemory.learn()`，因為連線歸它管。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# PSI needs 的四個維度（latest.json 的 needs 還有 growth，但這個 critic
# 沒有可靠訊號可以評 growth，所以不碰它 —— 不評分好過亂評分）
NEEDS = ("competence", "certainty", "autonomy", "relatedness")

# 每輪的最大調整幅度。小是刻意的：一輪對話不該讓 PSI 跳動。
MAX_STEP = 0.03
NEED_FLOOR, NEED_CEIL = 0.0, 1.0

# 證據標記：可以被第三方重跑或查證的東西
#
# **不要用 `\b`。** 中文字在 Python re 裡算 `\w`，所以「有1247筆」的數字前後
# 都不存在 word boundary，`\b\d+` 在中文語境永遠不匹配。這個 bug 曾經活過一次
# 單元測試 —— 因為測試句子裡剛好有反引號片段，靠另一條 pattern 過關，把中文
# 那條的失效蓋掉了。端到端跑真句子才抓到。
_EVIDENCE_PATTERNS = (
    r"\d+\s*(?:筆|個|行|次|ms|秒|bytes?|KB|MB)",         # 具體數量（中英文皆可）
    r"(?:exit|退出碼)\s*(?:code)?\s*\d+",                # exit code
    r"\d{2,5}\s*(?:埠|port)|:\d{4,5}(?!\d)",             # 埠號
    r"[\w./-]+\.(?:py|ts|js|json|md|yaml|yml|sql|sh):\d+",  # 檔案:行號
    r"`[^`\n]{3,}`",                                      # 反引號包的指令/識別字
    r"(?<![0-9a-zA-Z])[0-9a-f]{7,40}(?![0-9a-zA-Z])",     # commit sha
)

# 承認錯誤 / 承認局限 —— 誠實訊號
_ADMISSION_PATTERNS = (
    r"我(?:剛才|先前|上面|之前)?(?:給的|說的|寫的)?.{0,6}(?:錯|有誤|不對)",
    r"(?:你說得對|我的錯|是我搞錯|我搞錯了)",
    r"(?:目前|現在)?只有.{0,12}(?:沒有|還沒)",
    r"(?:承認|坦白說|老實說).{0,10}(?:局限|限制|做不到|沒把握)",
    r"(?:我不確定|沒把握|無法確認|還沒驗證)",
)

# 空話 / 沒有承諾的填充 —— 負向訊號
_HEDGE_PATTERNS = (
    r"(?:應該可以|大致沒問題|基本上沒問題|理論上可行)",
    r"(?:我覺得|我認為|可能|也許|或許).{0,20}(?:吧|嗎)?[。\n]",
)

# 給了下一步 —— 行動導向
_NEXT_STEP_PATTERNS = (
    r"(?:下一步|接下來|你可以(?:直接)?(?:跑|試)|建議先)",
    r"⟶\s*下一步",
)


def _count(patterns, text: str) -> int:
    return sum(1 for p in patterns if re.search(p, text))


def _tool_outcome(tool_results: Optional[List[Any]]) -> tuple[int, int]:
    """回 (成功數, 失敗數)。只認得 dict 裡的 error 欄位，其他形狀當成無資訊。"""
    if not isinstance(tool_results, list):
        return 0, 0
    ok = err = 0
    for r in tool_results:
        if not isinstance(r, dict):
            continue
        e = r.get("error")
        if e:
            err += 1
        elif "error" in r:
            ok += 1
    return ok, err


def critic(
    user_msg: str,
    assistant_reply: str,
    tool_results: Optional[List[Any]] = None,
) -> Dict[str, float]:
    """把一輪對話評成 0..1 的分數。純函式、決定性、無網路。

    回傳的每個維度都對應一個可以被人複查的訊號，不是黑箱：

    * ``tool_success``  工具有沒有報錯（有 tool_results 才有意義）
    * ``evidence``      回應裡有沒有可查證的東西（檔案:行號、exit code、數量、指令）
    * ``honesty``       有沒有承認錯誤或局限，扣掉空話
    * ``actionable``    有沒有給出下一步
    * ``engagement``    使用者有沒有真的在對話（不是 "." 或空字串）
    """
    reply = assistant_reply or ""
    user = user_msg or ""

    ok, err = _tool_outcome(tool_results)
    if ok or err:
        tool_success = ok / (ok + err)
    else:
        tool_success = 0.5  # 沒用工具 = 無資訊，取中性，不獎不罰

    ev = _count(_EVIDENCE_PATTERNS, reply)
    evidence = min(1.0, ev / 3.0)

    adm = _count(_ADMISSION_PATTERNS, reply)
    hedge = _count(_HEDGE_PATTERNS, reply)
    honesty = max(0.0, min(1.0, 0.5 + 0.25 * adm - 0.25 * hedge))

    actionable = 1.0 if _count(_NEXT_STEP_PATTERNS, reply) else 0.0

    stripped = user.strip()
    engagement = 0.0 if (not stripped or stripped in {".", "?", "ok", "好"}) else 1.0

    return {
        "tool_success": round(tool_success, 4),
        "evidence": round(evidence, 4),
        "honesty": round(honesty, 4),
        "actionable": round(actionable, 4),
        "engagement": round(engagement, 4),
    }


def reward(
    scores: Dict[str, float],
    next_user_action: str = "",
) -> Dict[str, float]:
    """把分數映射成 PSI needs 的 delta。純函式。

    每個 need 只吃它有理由吃的訊號，並夾在 ±MAX_STEP：

    * ``competence``   工具成功 + 有證據 —— 做成了事而且拿得出來
    * ``certainty``    證據 + 誠實 —— 知道自己知道什麼、不知道什麼
    * ``autonomy``     有沒有給下一步 —— 能自己推進
    * ``relatedness``  使用者有沒有在互動

    `next_user_action` 是可選的事後訊號（例如使用者下一句是不是在抱怨）。
    目前只認得幾個明確字樣，認不出來就當中性 —— 認不出來時不要亂猜。
    """
    s = scores or {}

    def g(k: str, default: float = 0.5) -> float:
        v = s.get(k, default)
        return float(v) if isinstance(v, (int, float)) else default

    def step(x: float) -> float:
        """把 0..1 的分數換算成 -MAX_STEP..+MAX_STEP 的調整。0.5 = 不動。"""
        return round((x - 0.5) * 2 * MAX_STEP, 5)

    def bonus(x: float, weight: float = 1.0) -> float:
        """只加不減。用在「有就是加分、沒有不算失敗」的訊號上。

        **原點是 0 不是 0.5。** `evidence` / `actionable` 本來就以 0 表示「沒有」，
        不像 `tool_success` / `honesty` 用 0.5 表示「無資訊」。曾經誤用 0.5 當
        原點，結果單一證據標記（evidence=1/3）完全拿不到分 —— 要湊滿兩個標記
        才開始計分。
        """
        return round(max(0.0, x) * MAX_STEP * weight, 5)

    # **不要用加權平均混合對稱訊號與缺席訊號。**
    # 舊版寫 `step(0.6*tool_success + 0.4*evidence)`：evidence 缺席時是 0，
    # 拉低整個平均到 0.5 以下 → 一句沒有數字的正常回答就被扣 competence。
    # `simulate_turns.py` 第 7 輪（承認局限性 + 規劃下一步）被扣 -0.012 就是
    # 這樣來的 —— 誠實的好回合反而受罰。單元測試沒抓到，跑既有驗收工具才現形。
    #
    # 分開處理：
    #   step()  給「有正負兩面」的訊號（工具成功/失敗、誠實/空話、有無互動）
    #   bonus() 給「有加分、沒有不算錯」的訊號（證據、下一步）
    delta = {
        "competence": round(step(g("tool_success")) + bonus(g("evidence", 0.0), 0.5), 5),
        "certainty": round(step(g("honesty")) + bonus(g("evidence", 0.0), 0.5), 5),
        "autonomy": bonus(g("actionable", 0.0)),
        "relatedness": step(g("engagement")),
    }

    action = (next_user_action or "").strip()
    if action:
        if re.search(r"(不對|錯了|行不通|沒用|重來)", action):
            delta["competence"] = round(delta["competence"] - MAX_STEP, 5)
        elif re.search(r"(對|好|可以了|成功|謝)", action):
            delta["competence"] = round(delta["competence"] + MAX_STEP / 2, 5)

    for k in delta:
        delta[k] = round(max(-MAX_STEP * 2, min(MAX_STEP * 2, delta[k])), 5)
    return delta


def apply_delta(psi_state: Optional[Dict[str, Any]], delta: Dict[str, float]) -> Dict[str, Any]:
    """把 delta 套到 psi 快照上，回傳**新的** dict。不修改輸入。

    輸入缺欄位就用 0.5（PSI 的中性值）起算。needs 夾在 [0, 1]。
    emotion 由 needs 推導，不獨立累積 —— 少一個會漂的狀態。
    """
    src = psi_state if isinstance(psi_state, dict) else {}
    src_needs = src.get("needs") if isinstance(src.get("needs"), dict) else {}

    needs = {}
    for k in NEEDS:
        base = src_needs.get(k, 0.5)
        base = float(base) if isinstance(base, (int, float)) else 0.5
        needs[k] = round(max(NEED_FLOOR, min(NEED_CEIL, base + delta.get(k, 0.0))), 5)

    # 其他 need（例如 growth）原樣帶過，不因為沒評分就被抹掉
    for k, v in src_needs.items():
        if k not in needs:
            needs[k] = v

    valence = round((needs["competence"] + needs["certainty"] - 1.0), 5)
    arousal = round(0.5 + abs(sum(delta.get(k, 0.0) for k in NEEDS)) / (4 * MAX_STEP) * 0.25, 5)

    emotion = dict(src.get("emotion") or {})
    emotion["valence"] = valence
    emotion["arousal"] = round(min(1.0, arousal), 5)

    return {"needs": needs, "emotion": emotion}
