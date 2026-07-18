"""C-a 快取規劃器 acceptance — 詞相關命中（非分數門檻）+ 真實命中率量測。"""
from laap import experience_cache as ec


def test_relevant_hit_by_terms_not_score():
    q = "React 效能優化 作法"
    # 高分但不相關（backtest 的假 100% 就是這種）
    irrelevant = {"score": 0.9, "chunk_text": "臉書密碼是 abc123", "slug": "notes/密碼"}
    # 分數沒寫但詞相關
    relevant = {"score": 0.0, "chunk_text": "React 效能優化用 memo 和 useMemo", "slug": "wiki/react"}
    assert ec.is_relevant(q, relevant), "詞相關應命中"
    assert not ec.is_relevant(q, irrelevant), "高分但不相關不該算命中"


def test_lookup_returns_first_relevant():
    q = "gbrain 混合檢索"
    hits = [
        {"score": 0.95, "chunk_text": "無關內容天氣很好", "slug": "notes/天氣"},
        {"score": 0.3, "chunk_text": "gbrain 混合檢索用 RRF 融合", "slug": "wiki/gbrain"},
    ]
    r = ec.lookup(q, hits)
    assert r["hit"] and "RRF" in r["experience"]


def test_lookup_miss_when_nothing_relevant():
    r = ec.lookup("量子重力", [{"score": 0.9, "chunk_text": "貓很可愛", "slug": "notes/貓"}])
    assert not r["hit"] and r["experience"] is None


def test_hit_rate_tracks(tmp_path):
    b = str(tmp_path)
    ec.record(True, "competence", base=b)
    ec.record(False, "growth", base=b)
    ec.record(True, "competence", base=b)
    r = ec.hit_rate(base=b)
    assert r["total"] == 3 and r["hits"] == 2
    assert abs(r["rate"] - 2 / 3) < 0.01


def test_hit_rate_window(tmp_path):
    b = str(tmp_path)
    ec.record(True, when=1000.0, base=b)         # 舊
    ec.record(False, when=9000.0, base=b)        # 新
    r = ec.hit_rate(base=b, window_s=3600, now=9001.0)
    assert r["total"] == 1 and r["hits"] == 0, "只算窗內"


def test_empty_ledger_zero_rate(tmp_path):
    r = ec.hit_rate(base=str(tmp_path))
    assert r == {"rate": 0.0, "hits": 0, "total": 0}
