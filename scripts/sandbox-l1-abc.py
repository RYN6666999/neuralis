#!/usr/bin/env python3
"""
sandbox-l1-abc.py — 沙箱 L1 A/B/C 學習測試（真 _score_result）。

事前預測已封存於 reports/sandbox-l1-abc.md（跑前寫，跑完不改）。

跨真 gbrain 測角度 bandit：作法 vs 經驗（competence 的 gbrain 角度）。
訓練 outcome 走真 gbrain + 真 _score_result（含詞相關閘）。

安全：不呼叫 memory_bridge、不呼叫 _save_state、不碰 live 持久狀態、
不寫 gbrain。全新中性實例，hermetic。C 的持久化走暫存 json（測序列化存活，
不碰 live slug）。

用法:
    cd ~/Developer/neuralis
    PYTHONPATH=".:../laap-AGI" ../laapenv/bin/python scripts/sandbox-l1-abc.py
"""
import copy
import json
import os
import random
import re
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from laap.agency import AgencyLoop
from laap.constitution import get_constitution

NEED = "competence"
ANGLES = ["作法", "經驗"]                 # 問Scream 走 scream-ask，非 gbrain，排除
TOPICS = ["postgres 索引", "pgvector 檢索", "RPE bandit 學習"]  # 3 個有區辨 topic
PROBE = "教我一件事"                       # 固定探針 P
SELF_SLUG_PAT = re.compile(r"_internal/|agency-state|_agency", re.I)

random.seed(42)   # 可重現；探索雜訊固定


class MockPsi:
    """固定認知偏差（bias=0），讓 exploration 只受權重 + presence 影響。"""
    def __init__(self):
        self._last = ""
    def get_last_input(self):
        return self._last
    def get_cognitive_bias(self):
        return {"risk_seeking": 0.0, "attention_narrowing": 0.0}
    def get_drives(self):
        return {"competence": 0.6}


def _real_tools():
    from laap.startup import startup_all
    _, _, tools = startup_all()
    return tools


def strip_self(result: str) -> str:
    return "\n".join(ln for ln in result.splitlines() if not SELF_SLUG_PAT.search(ln))


def fresh(tools):
    a = AgencyLoop(psi=MockPsi(), tools=tools)
    a._need_stats = {NEED: {"expected": 0.3, "rpes": [], "angle_weights": {}}}
    a._exploration_rate = 0.15
    a._state_loaded = False   # 保險：禁止任何存檔
    return a


def angle_weights(a):
    return dict(a._need_stats[NEED]["angle_weights"])


def pick_angle(a):
    """複製 _form_intent 的角度選擇（epsilon-greedy），限 ANGLES 兩角度。"""
    aw = a._need_stats[NEED]["angle_weights"]
    weights = {ang: aw.get(ang, 1.0) for ang in ANGLES}
    if random.random() < a._effective_exploration():
        return random.choice(ANGLES)                     # 探索
    return max(weights, key=weights.get)                 # 利用（tie → 第一個=作法）


def train_once(a, tools, topic):
    """複製 _act 的 RPE + 權重 + 探索率更新（跳過 memory / save）。真 gbrain 評分。"""
    angle = pick_angle(a)
    query = f"{topic} {angle}".strip()
    raw = tools.execute("gbrain", query) or ""
    outcome = a._score_result(strip_self(raw), tool="gbrain", query=query)
    stats = a._need_stats[NEED]
    rpe = outcome - stats["expected"]
    stats["expected"] = 0.9 * stats["expected"] + 0.1 * outcome
    a._rpe_buffer.append(rpe)
    aw = stats["angle_weights"]
    old = aw.get(angle, 1.0)
    allowed = get_constitution().guard_weight(NEED, angle, rpe * 0.5)
    aw[angle] = max(0.1, min(3.0, old + allowed))
    if len(a._rpe_buffer) >= 5:
        avg = sum(a._rpe_buffer) / len(a._rpe_buffer)
        if avg > 0.05:
            a._exploration_rate = min(0.30, a._exploration_rate + 0.005)
        elif avg < -0.05:
            a._exploration_rate = max(0.05, a._exploration_rate - 0.005)
    return angle, outcome, rpe


def sample_dist(a, n=30):
    a.psi._last = PROBE
    counts = {ang: 0 for ang in ANGLES}
    for _ in range(n):
        counts[pick_angle(a)] += 1
    return counts


def snapshot_restore(b, tools):
    """C：把 B 的 state 序列化到暫存 json（同 _save_state 欄位）→ 全新實例載回。"""
    state = {
        "need_stats": b._need_stats,
        "trust_scores": b._trust_scores,
        "exploration_rate": b._exploration_rate,
    }
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    loaded = json.load(open(path, encoding="utf-8"))
    os.unlink(path)
    c = fresh(tools)
    c._need_stats = loaded["need_stats"]
    c._trust_scores = loaded["trust_scores"]
    c._exploration_rate = loaded["exploration_rate"]
    return c


def main():
    tools = _real_tools()

    # ── A: 全新中性 ──
    a = fresh(tools)
    dist_a = sample_dist(a)
    w_a = angle_weights(a)

    # ── B: 同實例訓練 30 筆真 topic ──
    b = fresh(tools)
    print("── 訓練 30 筆（真 gbrain 評分）──")
    log = []
    for i in range(30):
        topic = TOPICS[i % len(TOPICS)]
        ang, out, rpe = train_once(b, tools, topic)
        log.append((i + 1, topic, ang, out, rpe))
    dist_b = sample_dist(b)
    w_b = angle_weights(b)

    # ── C: 序列化 → 重載 ──
    c = snapshot_restore(b, tools)
    dist_c = sample_dist(c)
    w_c = angle_weights(c)

    # ── baseline: 純隨機 ──
    base = {ang: 0 for ang in ANGLES}
    for _ in range(30):
        base[random.choice(ANGLES)] += 1

    # ── 輸出 ──
    print("\n── 訓練逐筆 ──")
    for i, topic, ang, out, rpe in log:
        print(f"{i:2d}  {topic:<16} 角度={ang:<4} outcome={out:.3f}  rpe={rpe:+.3f}")

    def fmt_w(w):
        return ", ".join(f"{k}={w.get(k, 1.0):.3f}" for k in ANGLES)

    print("\n── 角度權重 ──")
    print(f"A: {fmt_w(w_a)}")
    print(f"B: {fmt_w(w_b)}")
    print(f"C: {fmt_w(w_c)}")

    print("\n── P 取樣分布（30 次）──")
    print(f"A: {dist_a}")
    print(f"B: {dist_b}")
    print(f"C: {dist_c}")
    print(f"baseline(隨機): {base}")

    # ── 判定（對照封存預測）──
    def wget(w, k):
        return w.get(k, 1.0)
    p1 = wget(w_b, "作法") > wget(w_b, "經驗")
    p2_survive = abs(wget(w_c, "作法") - wget(w_b, "作法")) < 0.01 and \
                 abs(wget(w_c, "經驗") - wget(w_b, "經驗")) < 0.01
    p2_diff = abs(wget(w_b, "作法") - wget(w_a, "作法")) > 0.1
    p3 = dist_b["作法"] > dist_a["作法"] and dist_b["作法"] > base["作法"]

    print("\n── 判定（對照 reports/sandbox-l1-abc.md 封存預測）──")
    print(f"  預測1 B 作法權重 > 經驗權重：{'✅' if p1 else '❌'} "
          f"(作法 {wget(w_b,'作法'):.3f} vs 經驗 {wget(w_b,'經驗'):.3f})")
    print(f"  預測2 C≈B（存活）：{'✅' if p2_survive else '❌'}；C≠A（差異）：{'✅' if p2_diff else '❌'}")
    print(f"  預測3 B 作法占比 > A 且 > baseline：{'✅' if p3 else '❌'} "
          f"(B={dist_b['作法']}, A={dist_a['作法']}, base={base['作法']})")
    verdict = "PASS" if (p1 and p2_survive and p2_diff and p3) else "FAIL/部分"
    print(f"\nL1(沙箱) = {verdict}")


if __name__ == "__main__":
    main()
