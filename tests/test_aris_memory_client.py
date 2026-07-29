#!/usr/bin/env python3
"""aris_memory_client.py 的測試。

紅軍防護（2026-07-30）：
  - 測試 1: format→parse 雙向一致（防止格式漂移）
  - 測試 2: flatline 維度不在輸出（防止自主/連結復活）
  - 測試 3: v1 向後相容（防止破壞舊格式）
  - 測試 4: 確定性（防止非確定性輸出）
  - 測試 5: 無效輸入回空 dict（防止 crash）
  
紅軍攻擊驗證：
  故意改壞 format_salience() → 測試 1 紅 ✅
  故意加入自主/連結 → 測試 2 紅 ✅
  故意改壞 parse_salience() → 測試 3 紅 ✅
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import importlib.util
spec = importlib.util.spec_from_file_location("amc", 
    os.path.join(os.path.dirname(__file__), '..', 'scripts', 'aris_memory_client.py'))
amc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(amc)


class TestFormatSalience:
    """format_salience() 的 4 項測試"""

    def test_roundtrip(self):
        """format → parse 雙向一致：es=4 → parse 回 es=4"""
        f = amc.format_salience(4, "好奇", energy=2.0, cycle=41831, feeling="測試")
        p = amc.parse_salience("x\n\n" + f)
        assert p.get("encoding_salience") == 4, f"roundtrip 失敗: es={p.get('encoding_salience')}"

    def test_no_flatline(self):
        """自主/連結不應出現在輸出中（紅軍攻擊實測：永遠 0.5 flatline）"""
        f = amc.format_salience(3, "", energy=2.0, cycle=0)
        assert "自主" not in f, f"輸出包含 flatline 維度：{f}"
        assert "連結" not in f, f"輸出包含 flatline 維度：{f}"
        assert "內心" not in f, f"輸出包含舊欄位 內心：{f}"

    def test_deterministic(self):
        """同一輸入 → 同一輸出（3 次比對）"""
        results = []
        for _ in range(3):
            f = amc.format_salience(4, "好奇", energy=2.0, cycle=41831, feeling="測試")
            p = amc.parse_salience("x\n\n" + f)
            results.append(p.get("encoding_salience"))
        assert len(set(results)) == 1, f"非確定性輸出: {results}"


class TestParseSalience:
    """parse_salience() 的 3 項測試"""

    def test_v1_json(self):
        """v1 JSON 格式仍可解析（向後相容）"""
        reply = "x\n\n⫸salience⫷ {\"es\":4,\"sn\":[0.5,0.5,0.5,0.5,0.5],\"emotion\":\"ok\"}"
        p = amc.parse_salience(reply)
        assert p.get("encoding_salience") == 4, f"v1 JSON 解析失敗: {p}"

    def test_v2_chinese(self):
        """v2 中文格式正確解析"""
        reply = "x\n\n⫸salience⫷ 重要:5 | 情緒:興奮 | sn:勝任0.8 自主0.6 連結0.7 確定0.5 成長0.9 | 內心:重要發現"
        p = amc.parse_salience(reply)
        assert p.get("encoding_salience") == 5, f"v2 解析失敗: {p}"
        assert p.get("emotion_label") == "興奮", f"v2 emotion 解析失敗: {p}"

    def test_invalid_returns_empty(self):
        """無效輸入回空 dict，不 crash"""
        cases = [
            "",                          # 空字串
            "沒有 salience 標記",         # 無標記
            "x\n\n⫸salience⫷ 重要:abc",  # 非數字
            None,                        # None
        ]
        for c in cases:
            p = amc.parse_salience(c)
            assert isinstance(p, dict), f"應回 dict 但為 {type(p)}: {c}"