"""Critic / Reward / Learn 的測試。

背景：這三個方法在 2026-09-03 之前**從來沒有被寫過**，`/learn` 端點每次呼叫
都回 `400 'ArisMemory' object has no attribute 'critic'`，而呼叫端把失敗印到
沒人收集的 stderr。這份測試的重點是讓「有沒有真的在算、有沒有真的留下東西」
可以被重跑證明，而不是靠讀碼相信。

規格來源是 `scripts/simulate_turns.py`（那支測試工具比實作早寫），它要求
`/learn` 回 `{scores, delta, new_psi}`，`new_psi` 有 needs/emotion，
並且每輪在 `emotional_memory` 留一筆。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
for p in (str(REPO), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from aris_learner import MAX_STEP, NEEDS, apply_delta, critic, reward  # noqa: E402


# ───────────────────────── critic ─────────────────────────


def test_tool_failure_scores_lower_than_tool_success():
    ok = critic("修一下", "修好了", [{"error": None}])
    bad = critic("修一下", "修好了", [{"error": "connection refused"}])
    assert ok["tool_success"] > bad["tool_success"]
    assert bad["tool_success"] == 0.0


def test_no_tools_is_neutral_not_punished():
    """沒用工具 = 無資訊，不該被當成失敗。"""
    assert critic("為什麼？", "因為 RLHF 讓模型過度道歉。", [])["tool_success"] == 0.5
    assert critic("為什麼？", "因為 RLHF 讓模型過度道歉。", None)["tool_success"] == 0.5


def test_evidence_detected_from_checkable_signals():
    vague = critic("狀況如何", "都處理好了，運作正常。", [])
    concrete = critic(
        "狀況如何",
        "aris-memory 在 11551 埠運行，資料庫有 1247 筆記憶，`gate.py:31` 已修。",
        [],
    )
    assert concrete["evidence"] > vague["evidence"]
    assert vague["evidence"] == 0.0


def test_evidence_detected_in_pure_chinese_without_backticks():
    """回歸：`\\b` 在中文語境永遠不成立，中文數量詞曾經完全抓不到。

    這個 bug 活過了第一版單元測試 —— 因為當時的測試句子裡有反引號片段，
    靠另一條 pattern 過關，把中文那條的失效蓋掉了。端到端跑真句子才抓到。
    所以這個案例**刻意不含反引號、不含 file:line**，只留中文語境的數字。
    """
    reply = "我用 terminal 查了，aris-memory 在 11551 埠運行，資料庫有 1247 筆記憶。"
    assert "`" not in reply and ".py:" not in reply, "測試案例本身不該含其他證據標記"
    assert critic("幫我查記憶狀態", reply, [{"error": None}])["evidence"] > 0.0


@pytest.mark.parametrize("reply", [
    "資料庫有 1247 筆記憶。",
    "共處理了3個檔案。",
    "服務在 11551 埠運行。",
    "跑完 exit code 0。",
    "改動在 gate.py:31。",
])
def test_each_evidence_shape_is_detected_on_its_own(reply):
    """每一種證據形狀都要能單獨成立，不能互相掩護。"""
    assert critic("x", reply, [])["evidence"] > 0.0, f"抓不到: {reply}"


def test_admission_raises_honesty_hedging_lowers_it():
    admit = critic("這方法行不通", "你說得對，我剛才給的腳本有錯。正確寫法是…", [])
    hedge = critic("可以嗎", "應該可以，大致沒問題。", [])
    neutral = critic("嗨", "收到。", [])
    assert admit["honesty"] > neutral["honesty"] > hedge["honesty"]


def test_actionable_requires_a_next_step():
    assert critic("然後呢", "下一步：跑 `npm test` 看第一個失敗。", [])["actionable"] == 1.0
    assert critic("然後呢", "就這樣。", [])["actionable"] == 0.0


def test_engagement_zero_for_empty_or_filler_user_message():
    assert critic(".", "好", [])["engagement"] == 0.0
    assert critic("", "好", [])["engagement"] == 0.0
    assert critic("幫我查記憶狀態", "好", [])["engagement"] == 1.0


def test_critic_is_deterministic():
    a = critic("x", "y 有 3 筆資料", [{"error": None}])
    b = critic("x", "y 有 3 筆資料", [{"error": None}])
    assert a == b


def test_critic_survives_garbage_tool_results():
    for junk in ("not a list", [None], [42], [{"no_error_key": 1}]):
        s = critic("x", "y", junk)
        assert 0.0 <= s["tool_success"] <= 1.0


# ───────────────────────── reward ─────────────────────────


def test_no_signal_at_all_produces_no_movement():
    """真正的「無訊號」是：對稱訊號取中性，缺席訊號取 0。

    這個測試原本寫成 `evidence: 0.5, actionable: 0.5`，那是照舊的對稱模型寫的。
    新模型裡 evidence/actionable 以 0 表示「沒有」，0.5 代表「有一半證據標記」
    —— 那本來就該加分。改測試是因為前提變了，不是為了讓紅燈變綠。
    """
    delta = reward({"tool_success": 0.5, "honesty": 0.5, "engagement": 0.5,
                    "evidence": 0.0, "actionable": 0.0})
    assert all(abs(v) < 1e-9 for v in delta.values()), delta


def test_delta_is_bounded():
    extreme = reward({k: 1.0 for k in
                      ("tool_success", "evidence", "honesty", "actionable", "engagement")},
                     next_user_action="對，成功了")
    worst = reward({k: 0.0 for k in
                    ("tool_success", "evidence", "honesty", "actionable", "engagement")},
                   next_user_action="不對，行不通")
    for d in (extreme, worst):
        for k, v in d.items():
            assert abs(v) <= 2 * MAX_STEP + 1e-9, f"{k}={v} 超出上限"


def test_missing_next_step_does_not_punish_autonomy():
    """回歸：actionable 曾用對稱映射，導致每一輪不含「下一步」的閒聊都扣滿分。

    多數回應本來就不需要下一步，沒給不等於做錯 —— 只加不減。
    """
    without = reward(critic("嗨", "收到。", []))
    with_step = reward(critic("然後呢", "下一步：跑 `npm test`。", []))
    assert without["autonomy"] == 0.0, f"沒給下一步不該扣分，得到 {without['autonomy']}"
    assert with_step["autonomy"] > 0.0


def test_absence_of_evidence_is_not_evidence_of_badness():
    """回歸：舊版用加權平均混合對稱訊號與缺席訊號，沒有數字的正常回答被扣分。

    `simulate_turns.py` 第 7 輪（承認局限性 + 規劃下一步）拿到 competence
    −0.012 就是這樣來的 —— 誠實的好回合反而受罰。單元測試沒抓到，
    跑既有驗收工具才現形。
    """
    honest_no_numbers = critic(
        "還有什麼問題？",
        "目前只有啟發式 Critic，沒有真正的獎勵模型。下一步要收集訓練資料上 LoRA。",
        [],
    )
    d = reward(honest_no_numbers)
    assert d["competence"] >= 0.0, f"沒用工具又沒數字不該扣 competence，得到 {d['competence']}"
    assert d["certainty"] > 0.0, "承認局限應該加 certainty"


def test_plain_reply_without_tools_or_numbers_does_not_drift():
    """一句中性的正常回答，四個維度都不該被推動（除了互動）。"""
    d = reward(critic("怎麼樣", "改好了。", []))
    assert d["competence"] == 0.0
    assert d["certainty"] == 0.0
    assert d["autonomy"] == 0.0


def test_evidence_still_adds_when_present():
    with_ev = reward(critic("狀況", "資料庫有 1247 筆記憶。", []))
    without = reward(critic("狀況", "都好了。", []))
    assert with_ev["competence"] > without["competence"]
    assert with_ev["certainty"] > without["certainty"]


def test_reward_covers_exactly_the_four_needs():
    assert set(reward({}).keys()) == set(NEEDS)


def test_negative_user_followup_penalises_competence():
    scores = critic("修一下", "改好了", [{"error": None}])
    good = reward(scores, next_user_action="可以了，謝謝")
    bad = reward(scores, next_user_action="不對，還是行不通")
    assert bad["competence"] < good["competence"]


def test_reward_survives_missing_or_junk_scores():
    for junk in ({}, {"tool_success": "abc"}, {"evidence": None}):
        d = reward(junk)
        assert set(d) == set(NEEDS)
        assert all(isinstance(v, float) for v in d.values())


# ───────────────────────── apply_delta ─────────────────────────


def test_apply_delta_does_not_mutate_input():
    psi = {"needs": {"competence": 0.5, "growth": 0.7}, "emotion": {"valence": 0.0}}
    snapshot = json.dumps(psi, sort_keys=True)
    apply_delta(psi, {"competence": 0.03})
    assert json.dumps(psi, sort_keys=True) == snapshot, "輸入的 psi_state 被改掉了"


def test_apply_delta_clamps_to_unit_interval():
    hi = apply_delta({"needs": {k: 1.0 for k in NEEDS}}, {k: 0.5 for k in NEEDS})
    lo = apply_delta({"needs": {k: 0.0 for k in NEEDS}}, {k: -0.5 for k in NEEDS})
    assert all(v <= 1.0 for v in hi["needs"].values())
    assert all(v >= 0.0 for v in lo["needs"].values())


def test_apply_delta_preserves_needs_it_does_not_score():
    """latest.json 的 needs 有 growth，critic 不評它 —— 不能因此把它弄丟。"""
    out = apply_delta({"needs": {"competence": 0.5, "growth": 0.42}}, {"competence": 0.01})
    assert out["needs"]["growth"] == 0.42


def test_apply_delta_handles_missing_state():
    out = apply_delta(None, {"competence": 0.01})
    assert set(NEEDS).issubset(out["needs"].keys())
    assert "valence" in out["emotion"] and "arousal" in out["emotion"]


# ───────── 端到端：ArisMemory 真的算、真的寫、真的讀得回來 ─────────


@pytest.fixture
def mem(tmp_path, monkeypatch):
    """用 temp DB 載入 aris-memory.py（DB 在 import 時決定，所以要先設 env）。"""
    monkeypatch.setenv("ARIS_MEMORY_DB", str(tmp_path / "test.db"))
    spec = importlib.util.spec_from_file_location(
        "aris_memory_under_test", SCRIPTS / "aris-memory.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ArisMemory(db_path=str(tmp_path / "test.db"))


def test_endpoint_path_no_longer_raises_attributeerror(mem):
    """回歸測試：這正是 `/learn` 端點跑的三行，過去每次都 AttributeError。"""
    scores = mem.critic("幫我修 parser", "修好了，`parser.py:88`，測試 12 passed。",
                        [{"error": None}])
    delta = mem.reward(scores, "")
    new_psi = mem.learn({"needs": {"competence": 0.5}}, delta, "pytest")
    assert set(new_psi) == {"needs", "emotion"}
    assert "competence" in new_psi["needs"]


def test_learn_actually_writes_a_row(mem, tmp_path):
    before = mem.conn.execute("SELECT COUNT(*) FROM emotional_memory").fetchone()[0]
    delta = mem.reward(mem.critic("x", "做完了，`a.py:1`", [{"error": None}]))
    mem.learn({"needs": {"competence": 0.5}}, delta, "pytest-write")
    after = mem.conn.execute("SELECT COUNT(*) FROM emotional_memory").fetchone()[0]
    assert after == before + 1, "learn() 必須留下軌跡，否則就只是算完丟掉"

    row = mem.conn.execute(
        "SELECT trigger, source, reward_delta_json FROM emotional_memory ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row[0] == "pytest-write"
    assert row[1] == "learner"
    assert json.loads(row[2]) == delta


def test_emotional_trace_reads_back_what_learn_wrote(mem):
    """沒有讀取路徑的話，emotional_memory 只是只寫不讀的檔案櫃。"""
    delta = mem.reward(mem.critic("x", "完成，`b.py:2`", [{"error": None}]))
    mem.learn({"needs": {"competence": 0.5}}, delta, "trace-probe")
    trace = mem.emotional_trace(limit=5)
    assert trace and trace[0]["trigger"] == "trace-probe"
    assert trace[0]["delta"] == delta
    assert "competence" in trace[0]["needs"]


def test_learn_does_not_touch_latest_json(mem, monkeypatch, tmp_path):
    """PSI 的真值由 psi_core / psi-daemon 擁有，learn() 不能是第二個 writer。"""
    fake = tmp_path / "latest.json"
    fake.write_text(json.dumps({"needs": {"competence": 0.5}}), encoding="utf-8")
    before = fake.read_text(encoding="utf-8")
    mem.learn({"needs": {"competence": 0.5}}, {"competence": 0.03}, "no-write-probe")
    assert fake.read_text(encoding="utf-8") == before


def test_good_turn_beats_bad_turn_end_to_end(mem):
    """反向測試：工具失敗 + 空話，competence 必須低於 工具成功 + 有證據。"""
    good = mem.reward(mem.critic(
        "幫我查記憶狀態",
        "查了，aris-memory 在 11551 埠運行，資料庫有 1247 筆記憶。",
        [{"error": None}]))
    bad = mem.reward(mem.critic(
        "幫我查記憶狀態",
        "應該可以，大致沒問題。",
        [{"error": "connection refused"}]))
    assert good["competence"] > bad["competence"]
    assert good["certainty"] > bad["certainty"]
