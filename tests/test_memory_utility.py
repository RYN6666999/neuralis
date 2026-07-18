"""E1.2 下游效用信號 acceptance — tag → recall → 延遲獎勵，長度騙不了。"""
from laap import memory_utility as mu


def test_recalled_memory_becomes_pending_reward(tmp_path):
    b = str(tmp_path)
    mu.tag_memory("mem-1", "competence", "gbrain", angle="作法", when=1000.0, base=b)
    mu.record_recall("mem-1", when=1500.0, base=b)
    pend = mu.pending_rewards(now=1600.0, base=b)
    assert len(pend) == 1
    assert pend[0]["need"] == "competence" and pend[0]["angle"] == "作法"
    assert pend[0]["reward"] == mu.DOWNSTREAM_REWARD


def test_credited_not_rewarded_twice(tmp_path):
    b = str(tmp_path)
    mu.tag_memory("mem-1", "competence", "gbrain", angle="作法", when=1000.0, base=b)
    mu.record_recall("mem-1", when=1500.0, base=b)
    assert mu.pending_rewards(now=1600.0, base=b)
    mu.mark_credited("mem-1", base=b)
    assert mu.pending_rewards(now=1600.0, base=b) == [], "已 credited 不重複發"


def test_recall_outside_window_not_rewarded(tmp_path):
    b = str(tmp_path)
    mu.tag_memory("mem-1", "competence", "gbrain", when=1000.0, base=b)
    mu.record_recall("mem-1", when=1000.0, base=b)          # 8 天前
    pend = mu.pending_rewards(now=1000.0 + 8 * 86400, base=b)
    assert pend == [], "7 天窗外不算"


def test_untagged_recall_no_reward(tmp_path):
    b = str(tmp_path)
    mu.record_recall("mem-orphan", when=1500.0, base=b)     # 沒 provenance
    assert mu.pending_rewards(now=1600.0, base=b) == [], "沒 provenance 不發獎"


def test_written_but_never_recalled_no_reward(tmp_path):
    b = str(tmp_path)
    mu.tag_memory("mem-1", "growth", "web-search", when=1000.0, base=b)
    assert mu.pending_rewards(now=1600.0, base=b) == [], "寫了沒被用到 = 無下游獎勵"


def test_length_cannot_game_downstream(tmp_path):
    """核心不變式：獎勵綁『被 recall』，跟長度無關 —— 長垃圾騙不了未來被想起。"""
    b = str(tmp_path)
    mu.tag_memory("short-useful", "competence", "gbrain", when=1000.0, base=b)
    mu.tag_memory("long-garbage", "competence", "gbrain", when=1000.0, base=b)
    mu.record_recall("short-useful", when=1500.0, base=b)   # 短的被用到
    rewarded = {p["mem_id"] for p in mu.pending_rewards(now=1600.0, base=b)}
    assert rewarded == {"short-useful"}, "被 recall 的才有獎，長度不影響"


def test_agency_sweep_applies_reward(monkeypatch):
    """wire 2 整合：agency._apply_utility_rewards 把延遲獎勵灌進 angle 權重。"""
    from laap.agency import AgencyLoop
    ag = AgencyLoop.__new__(AgencyLoop)
    ag._need_stats = {}
    monkeypatch.setattr(mu, "pending_rewards", lambda *a, **k: [
        {"mem_id": "mem-1", "need": "competence", "angle": "作法",
         "tool": "gbrain", "reward": 0.7}])
    credited = []
    monkeypatch.setattr(mu, "mark_credited", lambda mid, **k: credited.append(mid))
    ag._apply_utility_rewards()
    aw = ag._need_stats["competence"]["angle_weights"]
    assert aw.get("作法", 1.0) > 1.0, "被 recall 的記憶應提升其 angle 權重"
    assert credited == ["mem-1"], "發完獎應 mark_credited（防重複）"
