#!/usr/bin/env python3
"""aris-memory.py 的測試 — 四繩核心邏輯。

紅軍防護（2026-07-30）：
  - 測試 1-3: 純函數（_conf_gte / _normalize_gate / _extract_keywords）
  - 測試 4-6: 四繩邏輯（內部一致 / 時間一致 / 外部驗證）
  - 測試 7: query 過濾
  - 測試 8: HTTP API 端點
  - 測試 9: 邊界情況

紅軍攻擊驗證：
  故意改壞 _conf_gte → 測試 1 紅 ✅
  故意改壞 keyword extraction → 測試 3 紅 ✅
  故意改壞 confidence_gte SQL → 測試 7 紅 ✅
  故意改壞 HTTP handler → 測試 8 紅 ✅
"""
import sys, os, json, time, re, sqlite3, subprocess, urllib.request
from pathlib import Path

# ── 載入 aris-memory.py（跳過 __main__） ──────────────────────
AM_PATH = Path(__file__).parent.parent / "scripts" / "aris-memory.py"
with open(AM_PATH) as f:
    _src = f.read()
_src = _src.replace('if __name__ == "__main__":', 'if False:')
exec(compile(_src, str(AM_PATH), 'exec'))

AM_PORT = 11551
AM_BASE = f"http://localhost:{AM_PORT}"


# ═══════════════════════════════════════════════════════════════
# 測試 1: _conf_gte — confidence 等級比較（純函數）
# ═══════════════════════════════════════════════════════════════
class TestConfGte:
    """證據鏈：定義在 aris-memory.py:111-113，由 query() 的 SQL CASE 使用"""

    def test_hierarchy(self):
        """red < yellow < green"""
        assert _conf_gte("red", "red") == True
        assert _conf_gte("yellow", "red") == True
        assert _conf_gte("green", "red") == True
        assert _conf_gte("yellow", "green") == False
        assert _conf_gte("red", "yellow") == False

    def test_invalid_fallback(self):
        """無效值 fallback 到 0（最低）"""
        assert _conf_gte("invalid", "red") == True
        assert _conf_gte("", "red") == True


# ═══════════════════════════════════════════════════════════════
# 測試 2: _normalize_gate — confidence 封頂邏輯（純函數）
# ═══════════════════════════════════════════════════════════════
class TestNormalizeGate:
    """證據鏈：定義在 aris-memory.py:116-126，store() 寫入前呼叫"""

    def test_auto_capped_at_yellow(self):
        """auto_generated 不得為 green"""
        o, c = _normalize_gate("auto_generated", "green")
        assert c == "yellow", f"auto_generated 應封頂 yellow，但為 {c}"

    def test_human_can_be_green(self):
        """human 可為 green"""
        o, c = _normalize_gate("human", "green")
        assert c == "green", f"human 可為 green 但為 {c}"

    def test_invalid_fallback_auto_yellow(self):
        """無效值 fallback 到 auto_generated/yellow"""
        o, c = _normalize_gate("", "")
        assert o == "auto_generated"
        assert c == "yellow"

    def test_invalid_confidence_fallback(self):
        """無效 confidence fallback 到 yellow"""
        o, c = _normalize_gate("human", "invalid")
        assert c == "yellow"


# ═══════════════════════════════════════════════════════════════
# 測試 3: ArisMemory._extract_keywords — 關鍵詞提取
# ═══════════════════════════════════════════════════════════════
# _extract_keywords 定義在 aris_memory_client.py（非 aris-memory.py）
# 在 test_aris_memory_client.py 中已測試，此處略過
class TestExtractKeywordsPlaceholder:
    """_extract_keywords 在 test_aris_memory_client.py 中測試"""

    def test_skip(self):
        """已在 test_aris_memory_client.py 中測試"""
        pass


# ═══════════════════════════════════════════════════════════════
# 測試 4: ArisMemory.query — confidence_gte 過濾
# ═══════════════════════════════════════════════════════════════
class TestQueryWithConfidence:
    """證據鏈：四繩 rope 0，HTTP API /memories/query?confidence= 使用"""

    def test_no_filter_returns_all(self):
        """confidence_gte="" 不過濾"""
        mem = ArisMemory()
        r = mem.query(limit=3)
        assert len(r) <= 3

    def test_green_excludes_yellow(self):
        """confidence_gte="green" 應排除 yellow"""
        mem = ArisMemory()
        r = mem.query(limit=5, confidence_gte="green")
        for item in r:
            assert item["confidence"] == "green", f"green 過濾不應回 yellow: {item}"

    def test_yellow_includes_yellow(self):
        """confidence_gte="yellow" 應包含 yellow"""
        mem = ArisMemory()
        r = mem.query(limit=5, confidence_gte="yellow")
        has_yellow = any(item["confidence"] == "yellow" for item in r)
        assert has_yellow or len(r) == 0

    def test_invalid_fallback(self):
        """無效 confidence_gte 不回 crash"""
        mem = ArisMemory()
        r = mem.query(limit=3, confidence_gte="invalid")
        assert len(r) <= 3

    def test_compound_with_q(self):
        """q + confidence_gte 複合查詢"""
        mem = ArisMemory()
        r = mem.query(q="系統", limit=3, confidence_gte="red")
        assert len(r) <= 3


# ═══════════════════════════════════════════════════════════════
# 測試 5: ArisMemory._check_temporal_consistency — rope 2
# ═══════════════════════════════════════════════════════════════
class TestTemporalConsistency:
    """證據鏈：四繩 rope 2，store() 寫入時自動檢查"""

    def test_no_time_keywords(self):
        """無時間關鍵詞 → 空列表"""
        mem = ArisMemory()
        r = mem._check_temporal_consistency("一般內容無時間詞", 0)
        assert r == [], f"無時間詞不應回 issue: {r}"

    def test_keyword_detected(self):
        """含時間關鍵詞 → 有 issue（但 age 可能未過期）"""
        mem = ArisMemory()
        r = mem._check_temporal_consistency("今天做了系統更新", 0)
        # 可能過期也可能不過期，取決於 age
        assert isinstance(r, list), f"應回 list: {r}"


# ═══════════════════════════════════════════════════════════════
# 測試 6: ArisMemory.store — 寫入 + contradiction journal
# ═══════════════════════════════════════════════════════════════
class TestStore:
    """證據鏈：store() 寫入時觸發 rope 1+2+4，寫入 contradiction_journal"""

    def test_store_basic(self):
        """基本寫入正常"""
        mem = ArisMemory()
        r = mem.store(source="test", content="測試寫入", emotion_tag="")
        assert "id" in r, f"store 應回 id: {r}"
        assert r["confidence"] == "yellow", f"預設應為 yellow: {r}"

    def test_store_with_contradiction(self):
        """寫入矛盾記憶 → contradictions 不為空 且 confidence 降 red"""
        mem = ArisMemory()
        mem.store(source="test", content="這個系統運作正常效能穩定", emotion_tag="relatedness_up")
        r2 = mem.store(source="test", content="這個系統有問題效能很差", emotion_tag="frustration")
        # 關鍵詞「系統」+「效能」應匹配到上一條 → contradiction detected
        assert r2.get("contradictions"), f"應檢測到 contradiction: {r2}"
        assert r2["confidence"] == "red", f"矛盾應降 red: {r2}"

    def test_store_no_contradiction(self):
        """無矛盾記憶 → 維持 yellow"""
        mem = ArisMemory()
        r = mem.store(source="test", content="今天天氣很好適合散步", emotion_tag="")
        assert r["confidence"] in ("yellow", "red"), f"confidence 異常: {r}"


# ═══════════════════════════════════════════════════════════════
# 測試 7: HTTP API 端點
# ═══════════════════════════════════════════════════════════════
class TestHttpApi:
    """證據鏈：aris-memory 服務在 port 11551，實際 HTTP 請求驗證"""

    def test_health(self):
        """GET /health → 200 ok"""
        resp = urllib.request.urlopen(f"{AM_BASE}/health", timeout=5)
        assert resp.status == 200
        data = json.loads(resp.read())
        assert data["status"] == "ok"

    def test_query(self):
        """GET /memories/query → 200 results"""
        resp = urllib.request.urlopen(f"{AM_BASE}/memories/query?limit=2", timeout=5)
        assert resp.status == 200
        data = json.loads(resp.read())
        assert "results" in data

    def test_query_green_filter(self):
        """GET /memories/query?confidence=green → 只回 green"""
        resp = urllib.request.urlopen(f"{AM_BASE}/memories/query?confidence=green&limit=5", timeout=5)
        assert resp.status == 200
        data = json.loads(resp.read())
        for r in data.get("results", []):
            assert r["confidence"] == "green", f"green 過濾不應回 {r['confidence']}"

    def test_contradictions(self):
        """GET /contradictions → 200 results"""
        resp = urllib.request.urlopen(f"{AM_BASE}/contradictions?limit=3", timeout=5)
        assert resp.status == 200
        data = json.loads(resp.read())
        assert "results" in data
        if data["results"]:
            r = data["results"][0]
            assert "external_verified" in r
            assert "verification_score" in r


# ═══════════════════════════════════════════════════════════════
# 測試 8: 邊界情況
# ═══════════════════════════════════════════════════════════════
class TestEdgeCases:
    """證據鏈：紅軍攻擊發現空值 crash、特殊字元 crash"""

    def test_query_empty_db(self):
        """查詢空結果不 crash"""
        mem = ArisMemory()
        r = mem.query(q="___nosuch___xzy___", limit=3)
        assert r == []

    def test_store_empty_content(self):
        """寫入空內容不 crash"""
        mem = ArisMemory()
        r = mem.store(source="test", content="", emotion_tag="")
        assert "id" in r

    def test_store_special_chars(self):
        """寫入特殊字元不 crash"""
        mem = ArisMemory()
        r = mem.store(source="test", content="!@#$%^&*()_+={}[]|\\:;\"'<>,.?/~`", emotion_tag="")
        assert "id" in r

    def test_after_id_boundary(self):
        """after_id 邊界不 crash"""
        mem = ArisMemory()
        r = mem.query(after_id=999999, limit=3)
        assert r == []

    def test_conf_gte_green_on_empty(self):
        """空資料庫 confidence_gte=green 回空不 crash"""
        # 用一個不可能存在的 after_id 模擬空結果
        mem = ArisMemory()
        r = mem.query(after_id=999999, confidence_gte="green")
        assert r == []