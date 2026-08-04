#!/usr/bin/env python3
"""aris-memory HTTP API 整合測試。
注意：需要 aris-memory 服務在背景運行（port 11551）。
不包含在 pre-commit hook 中，需手動執行：
  python3 -m pytest tests_integration/ -v
"""
import sys, json, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
with open(Path(__file__).parent.parent / "scripts" / "aris-memory.py") as f:
    _src = f.read()
_src = _src.replace('if __name__ == "__main__":', 'if False:')
exec(compile(_src, str(Path(__file__).parent.parent / "scripts" / "aris-memory.py"), 'exec'))

AM_PORT = 11551
AM_BASE = f"http://localhost:{AM_PORT}"

class TestHttpApi:
    """證據鏈：aris-memory 服務在 port 11551，實際 HTTP 請求驗證。
    注意：此測試需要 aris-memory 服務在背景運行。CI 不執行此測試。"""

    def test_health(self):
        """GET /health → 200 ok"""
        resp = urllib.request.urlopen(f"{AM_BASE}/health", timeout=5)
        assert resp.status == 200
        data = json.loads(resp.read())
        assert data["status"] == "ok"

    def test_query(self):
        """GET /memories/query → 200 results"""
        resp = urllib.request.urlopen(f"{AM_BASE}/memories/query?limit=2", timeout=5)
        data = json.loads(resp.read())
        assert "results" in data

    def test_query_green_filter(self):
        """GET /memories/query?confidence=green → 只回 green"""
        resp = urllib.request.urlopen(f"{AM_BASE}/memories/query?confidence=green&limit=5", timeout=5)
        data = json.loads(resp.read())
        for r in data.get("results", []):
            assert r["confidence"] == "green"

    def test_contradictions(self):
        """GET /contradictions → 200 results"""
        resp = urllib.request.urlopen(f"{AM_BASE}/contradictions?limit=3", timeout=5)
        data = json.loads(resp.read())
        assert "results" in data
        if data["results"]:
            r = data["results"][0]
            assert "external_verified" in r


# ═══════════════════════════════════════════════════════════════
# 測試 8: 邊界情況
# ═══════════════════════════════════════════════════════════════
