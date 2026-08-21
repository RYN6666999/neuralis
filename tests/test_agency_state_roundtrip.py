"""回歸測試：_need_stats 的寫入端與讀取端必須用同一個 key。

為什麼要有這個檔（2026-08-20）：
`3f4df6e` 把 expected 的粒度改成 (need, tool)，用 tuple 當 key。但
  · `_act` 寫 tuple key，`_get_angle_weights(need)` 讀 str key → 同一個 process 內就讀不到
  · `_save_state` 把 tuple 轉 "a|b" 字串，`_load_state` 沒轉回來 → 重啟後累積歸零
330 條既有測試全綠，因為唯一觸及 angle_weights 的 test_memory_utility 走的是
E1.2 延遲獎勵路徑（`setdefault(need, ...)`，str key）—— 剛好是沒斷的那條。

所以這裡驗的不是「某一次轉換寫對了」，是**寫入端與讀取端用同一個 key**這個不變式。
"""
from __future__ import annotations

import json
import random

import pytest

from laap import agency as A


class _FakePsi:
    def get_last_input(self):
        return "光錐"

    def get_cognitive_bias(self):
        return {"risk_seeking": 0.0, "attention_narrowing": 0.0}

    def post_affective_event(self, *a, **k):
        pass

    def get_state(self):
        return {}


class _ScoreByAngle:
    """「作法」高分、其餘低分 —— 若學習有效，作法權重應上升。"""

    def execute(self, tool, prompt, timeout=30):
        return "[0.95] 命中 作法 光錐" if "作法" in prompt else "[0.05] 光錐 經驗"


def _loop(tools=None):
    """繞過 __init__ 的 I/O（gbrain / thread），只裝純函式需要的欄位。"""
    a = A.AgencyLoop.__new__(A.AgencyLoop)
    for k, v in dict(
        _need_stats={}, _trust_scores={"user": 0.3}, _exploration_rate=0.15,
        _rpe_buffer=[], _rpe_total=0.0, _rpe_count=0, _recent_queries=[],
        _seed_snippet="光錐", _cycle_guard=False, _last_was_self_initiated=False,
        _self_cycle_count=0, _cycle_max=3, skipped_stale=0, _state_loaded=True,
        _task_queue=[], _task_index=0, _goal_spec="", psi=_FakePsi(),
        tools=tools or _ScoreByAngle(), actions_taken=0, _action_times=[], _action_ts=[],
    ).items():
        setattr(a, k, v)
    return a


def _act(loop, need="competence", tool="gbrain", prompt="光錐 作法"):
    """跑一次 _act，忽略缺 gbrain 後端造成的回寫失敗（本測試不驗回寫）。"""
    try:
        loop._act(need, 0.8, tool, prompt)
    except AttributeError:
        pass


# ── 不變式 1：_act 學到的角度權重，_form_intent 選角度時必須讀得到 ──

def test_learned_angle_weight_is_visible_to_angle_selection():
    """修復前紅：_act 寫 tuple key，_get_angle_weights 讀 str key → 永遠讀到初始 1.0。"""
    loop = _loop()
    random.seed(7)
    for i in range(30):
        _act(loop, prompt=f"光錐 作法 v{i}")

    weights = loop._get_angle_weights("competence")
    assert weights["作法"] > 1.0, (
        f"30 次高分回饋後，選角度時讀到的權重仍是初始值：{weights} —— "
        "寫入端與讀取端的 key 不一致，學習沒有進到決策"
    )


def test_angle_weights_live_at_need_level_not_pair_level():
    """角度必須存在 need 層。_form_intent 選角度時還沒決定工具（工具路由在那之後），
    存 pair 層等於寫進一個讀取端結構上到不了的地方。"""
    loop = _loop()
    _act(loop, tool="gbrain", prompt="光錐 作法")
    _act(loop, tool="web-search", prompt="光錐 作法 x")

    need_aw = loop._need_stats.get("competence", {}).get("angle_weights", {})
    assert "作法" in need_aw, f"角度權重不在 need 層：{loop._need_stats!r}"
    # 同一個角度在不同工具下應累積到同一格，不被工具切碎
    for tool in ("gbrain", "web-search"):
        pair = loop._need_stats.get(A._pair_key("competence", tool), {})
        assert not pair.get("angle_weights"), (
            f"角度權重不應存在 pair 層 {tool}：{pair.get('angle_weights')!r}"
        )


# ── 不變式 2：學習狀態必須撐過 gbrain 的 JSON round-trip（重啟） ──

def test_need_stats_is_json_serializable_without_conversion():
    """key 必須本身就是 JSON-safe。需要轉換 = 存與讀兩處各有一份邏輯 = 會漂移
    （舊版就是 _save_state 有轉、_load_state 沒轉）。"""
    loop = _loop()
    _act(loop)
    json.dumps(loop._need_stats)  # 修復前這行 TypeError: keys must be str...


def test_expected_survives_save_load_roundtrip():
    """修復前紅：_save_state 存 "need|tool"，_load_state 不還原 tuple →
    _act 下次查 pair_key 必 miss，走冷啟動 expected=0.3，累積歸零。"""
    loop = _loop()
    _act(loop)
    pair = A._pair_key("competence", "gbrain")
    before = loop._need_stats[pair]["expected"]
    assert before != pytest.approx(0.3), "先驗值沒被 EMA 動過，這個測試就驗不到東西"

    revived = _loop()
    revived._need_stats = json.loads(json.dumps(loop._need_stats))

    assert pair in revived._need_stats, (
        f"重啟後 pair key {pair!r} 不見了，keys={list(revived._need_stats)!r}"
    )
    assert revived._need_stats[pair]["expected"] == pytest.approx(before)


def test_angle_weights_survive_save_load_roundtrip():
    loop = _loop()
    random.seed(11)
    for i in range(10):
        _act(loop, prompt=f"光錐 作法 v{i}")
    before = loop._need_stats["competence"]["angle_weights"]["作法"]

    revived = _loop()
    revived._need_stats = json.loads(json.dumps(loop._need_stats))

    assert revived._get_angle_weights("competence")["作法"] == pytest.approx(before)


def test_cold_start_falls_back_to_need_level_prior():
    """新的 (need, tool) 組合應繼承 need 層 expected 當先驗，不從 0.3 重來。"""
    loop = _loop()
    loop._need_stats["competence"] = {
        "expected": 0.8, "rpes": [], "angle_weights": {}}

    _act(loop, tool="qmd", prompt="光錐 作法")

    pair = loop._need_stats[A._pair_key("competence", "qmd")]
    # 一次 EMA：0.9*0.8 + 0.1*outcome，必定明顯高於冷啟動 0.3 的同一步
    assert pair["expected"] > 0.5, f"沒吃到 need 層先驗 0.8：{pair['expected']}"


# ── 不變式 3：E1.2 延遲獎勵與 _act 必須落在同一格（否則兩條路各學一半） ──

def test_delayed_reward_and_act_share_the_same_angle_bucket():
    loop = _loop()
    _act(loop, prompt="光錐 作法")
    direct = loop._need_stats["competence"]["angle_weights"].get("作法")
    assert direct is not None

    # _apply_utility_rewards 寫的位置（agency.py 的 setdefault(need, ...)）
    bucket = loop._need_stats.setdefault(
        "competence", {"expected": 0.3, "rpes": [], "angle_weights": {}})
    assert bucket["angle_weights"].get("作法") == direct, (
        "延遲獎勵與 _act 寫到不同格 —— 兩條學習路徑各自累積一半"
    )
