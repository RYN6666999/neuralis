"""E2 成本閘 acceptance — 小時窗預算，超支回 False（呼叫端降頻）。"""
from laap.cost_ledger import record, spent_last_hour, within_budget


def _ledger(tmp_path):
    return str(tmp_path / "cost.jsonl")


def test_records_sum_within_window(tmp_path):
    p = _ledger(tmp_path)
    record(30000, "x", when=1000.0, path=p)
    record(20000, "y", when=1500.0, path=p)
    assert spent_last_hour(now=2000.0, path=p) == 50000


def test_old_records_fall_out_of_window(tmp_path):
    p = _ledger(tmp_path)
    record(100000, "old", when=1000.0, path=p)      # >1hr 前
    record(10000, "new", when=5000.0, path=p)
    assert spent_last_hour(now=5001.0, path=p) == 10000, "超過 1 小時的不算"


def test_within_budget_true_under_cap(tmp_path):
    p = _ledger(tmp_path)
    record(100000, "x", when=1000.0, path=p)
    assert within_budget(50000, now=1001.0, path=p, budget=200000), \
        "150k <= 200k 應放行"


def test_over_budget_false(tmp_path):
    p = _ledger(tmp_path)
    record(180000, "x", when=1000.0, path=p)
    assert not within_budget(50000, now=1001.0, path=p, budget=200000), \
        "230k > 200k 應擋（呼叫端降頻）"


def test_empty_ledger_within_budget(tmp_path):
    p = _ledger(tmp_path)
    assert within_budget(1000, path=p, budget=200000), "空 ledger 當然沒超支"
    assert spent_last_hour(path=p) == 0
