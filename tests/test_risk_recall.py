#!/usr/bin/env python3
"""
risk-scorer 召回率測試套件。

已知有 bug 的 patch 樣本 → 餵給 risk-scorer → 看它抓到幾個。
每漏一個 → 補一個靜態分析規則。

目標：對已知 bug 類型的召回率 > 80%
"""
import json, os, sys, subprocess, tempfile

# 加入 risk-scorer 路徑
sys.path.insert(0, os.path.expanduser("~/Developer/neuralis/scripts"))
import importlib.util as _iu
_spec = _iu.spec_from_file_location("risk_scorer", os.path.expanduser("~/Developer/neuralis/scripts/risk-scorer.py"))
_risk_mod = _iu.module_from_spec(_spec)
_spec.loader.exec_module(_risk_mod)
_classify_risk = _risk_mod._classify_risk
_changed_symbols = _risk_mod._changed_symbols

def _strip_diff(diff_text: str) -> str:
    """從 diff 文字中提取真正新增的程式碼（去掉 + 前綴和 - 行）。"""
    lines = []
    for line in diff_text.split("\n"):
        if line.startswith("+"):
            lines.append(line[1:])  # 去掉 +
        elif not line.startswith("-") and not line.startswith("@") and not line.startswith("diff") and not line.startswith("index"):
            lines.append(line)
    return "\n".join(lines)

RECALL_TEST_CASES = [
    {
        "id": "bug001",
        "name": "跨進程 module-level 變數遺失",
        "file": "aris_memory_client.py",
        "code": """
_fail_count = 0
_repo_names = set()

def handle_post_llm_call(data):
    global _fail_count
    try:
        result = store(data)
        if result is None:
            _fail_count += 1
    except Exception:
        pass
    return result
""",
        "expected_risks": ["cross_process", "silent_degradation"],
        "story": "post_llm_call hook 每次新進程 module-level 變數歸零，連續失敗 3 次才警報"
    },
    {
        "id": "bug002",
        "name": "try/except:pass 靜默吞錯誤",
        "file": "aris_relay.py",
        "code": """
def process_message(msg):
    try:
        result = api_call(msg)
        return result
    except Exception:
        pass
    return None
""",
        "expected_risks": ["silent_degradation"],
        "story": "try/except:pass 吞掉 api_call 錯誤，回傳 None 讓呼叫端以為成功"
    },
    {
        "id": "bug003",
        "name": "不釋放 threading.Lock",
        "file": "tulpa_engine.py",
        "code": """
import threading
_lock = threading.Lock()

def update_state(data):
    _lock.acquire()
    state = data
    return state
""",
        "expected_risks": ["concurrent_state", "lifetime_asymmetry"],
        "story": "lock.acquire() 沒有配對 release()，第二次呼叫 deadlock"
    },
    {
        "id": "bug004",
        "name": "2048 條 HTTP 連線不關閉",
        "file": "http_server.py",
        "code": """
from http.server import HTTPServer, BaseHTTPRequestHandler

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        resp = fetch_data()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(resp)

srv = HTTPServer(("127.0.0.1", 11551), H)
srv.serve_forever()
""",
        "expected_risks": ["cross_process", "lifetime_asymmetry"],
        "story": "HTTP server 沒設 timeout，連線 leak FD 撐爆 256 limit"
    },
    {
        "id": "bug005",
        "name": "快取永不過期",
        "file": "memory_bridge.py",
        "code": """
_emotion_cache = {}

def get_emotion(slug):
    if slug in _emotion_cache:
        return _emotion_cache[slug]
    val = fetch(slug)
    _emotion_cache[slug] = val
    return val
""",
        "expected_risks": ["cache_staleness"],
        "story": "emotion_cache 無 TTL，來源更新後永遠讀到舊值"
    },
    {
        "id": "bug006",
        "name": "hybrid_search 回傳形狀不一致",
        "file": "aris_memory.py",
        "code": """
def hybrid_search(self, q, limit=20):
    like_results = self.query(q, limit)
    if len(like_results) >= limit:
        return like_results
    like_ids = {r["id"] for r in like_results}
    ter = self.ternary_search(q, limit * 2)
    for r in ter:
        if r["id"] not in like_ids:
            like_results.append({"id": r["id"], "content": r["content"]})
    return like_results
""",
        "expected_risks": ["format_coupling"],
        "story": "三元補充路徑只回 3 欄，但 LIKE 路徑回 18 欄，消費端炸 KeyError"
    },
    {
        "id": "bug007",
        "name": "新 schema 沒補舊資料遷移腳本",
        "file": "aris_memory.py",
        "code": """
def _ensure_columns(conn):
    conn.execute("ALTER TABLE memories ADD COLUMN confidence TEXT DEFAULT 'yellow'")
    conn.commit()
""",
        "expected_risks": ["schema_rigidity"],
        "story": "加 confidence 欄位但沒補舊資料預設值，查詢吃到 NULL 炸 TypeError"
    },
    {
        "id": "bug008",
        "name": "全域變數被多執行緒同時寫",
        "file": "tulpa_engine.py",
        "code": """
import threading
_lock = threading.Lock()
_turn_counter = 0

def compete(inputs):
    global _turn_counter
    _turn_counter += 1
    if _turn_counter % 10 == 0:
        prune()
    return True
""",
        "expected_risks": ["concurrent_state"],
        "story": "_turn_counter 無鎖保護，多執行緒併發寫入 race condition"
    },
    {
        "id": "bug009",
        "name": "return None 當成功回傳",
        "file": "memory_controller.py",
        "code": """
def get_context(self, user_msg):
    result = self._search(user_msg)
    if not result:
        return None
    return result
""",
        "expected_risks": ["silent_degradation"],
        "story": "get_context 回 None 時呼叫端沒檢查，當成成功處理"
    },
    {
        "id": "bug010",
        "name": "寫了但沒人消費的孤立端點",
        "file": "aris_memory.py",
        "code": """
if u.path == "/memories/legacy_export":
    data = mem.export_all()
    self._send(200, {"data": data})
""",
        "expected_risks": ["consumer_island"],
        "story": "新增 /legacy_export 端點但沒有任何 hook 或 consumer 使用它"
    },
]


def test_risk_scorer_recall():
    """跑全部 10 個已知 bug，統計召回率。"""
    total = len(RECALL_TEST_CASES)
    detected = 0
    results = []

    for case in RECALL_TEST_CASES:
        symbols = _changed_symbols("", case["file"])
        # 寫入真實程式碼到暫存檔
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
        tmp.write(case["code"])
        tmp_path = tmp.name
        tmp.close()

        # 用 risk-scorer 分析這個檔
        try:
            risk = _classify_risk(symbols, tmp_path, os.path.expanduser("~/Developer/neuralis"))
        except Exception as e:
            risk = {"score": 0, "dimensions": {}, "evidence": [f"crash: {e}"]}
        os.unlink(tmp_path)

        hits = []
        misses = []
        for expected in case["expected_risks"]:
            val = risk.get("dimensions", {}).get(expected, 0)
            if val >= 2:
                hits.append(expected)
            elif val >= 1:
                hits.append(f"{expected}(弱)")
            else:
                misses.append(expected)

        case_detected = len(hits) > 0
        if case_detected:
            detected += 1

        results.append({
            "id": case["id"],
            "name": case["name"],
            "story": case["story"],
            "expected": case["expected_risks"],
            "hits": hits,
            "misses": misses,
            "detected": case_detected,
            "score": risk.get("score", 0),
            "level": risk.get("level", "?"),
        })

    # 輸出報告
    recall = detected / total * 100
    print("=" * 55)
    print("risk-scorer 召回率測試報告")
    print("=" * 55)
    print(f"\n共 {total} 個已知 bug patch")
    print(f"偵測到 {detected} 個（召回率 {recall:.0f}%）")
    print(f"漏掉 {total - detected} 個")

    if recall >= 80:
        print(f"\n🎯 目標達成（>80%）")
    else:
        print(f"\n⚠️  未達標（目標 80%），需補規則")

    print(f"\n{'─' * 55}")
    print(f"{'ID':<8} {'偵測':<6} {'分數':<6} {'名稱':<20} {'漏掉':<20}")
    print(f"{'─' * 55}")
    for r in results:
        label = "✅" if r["detected"] else "❌"
        miss_str = ", ".join(r["misses"]) if r["misses"] else "—"
        print(f"{r['id']:<8} {label:<6} {r['score']:<6} {r['name'][:18]:<20} {miss_str:<20}")

    print(f"\n{'─' * 55}")
    print("詳細結果")
    print(f"{'─' * 55}")
    for r in results:
        label = "✅" if r["detected"] else "❌"
        hit_str = ", ".join(r["hits"]) if r["hits"] else "（無）"
        miss_str = ", ".join(r["misses"]) if r["misses"] else "（無）"
        print(f"\n{r['id']} {label} {r['name']}")
        print(f"  故事: {r['story']}")
        print(f"  期望抓到: {', '.join(r['expected'])}")
        print(f"  實際命中: {hit_str}")
        print(f"  漏掉: {miss_str}")
        print(f"  風險分數: {r['score']}/{r['level']}")

    return recall >= 80


if __name__ == "__main__":
    passed = test_risk_scorer_recall()
    sys.exit(0 if passed else 1)