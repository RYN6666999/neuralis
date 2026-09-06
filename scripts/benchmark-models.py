import json
import time
from pathlib import Path
from laap.audit.gate import run_gate

# 定義 5 個複雜測試情境 (Triggering Failures)
TEST_CASES = [
    {"id": "B-001", "type": "artifact", "path": "/tmp/nonexistent.log", "desc": "證據缺失"},
    {"id": "B-002", "type": "tdd", "path": "/tmp/corrupt.log", "desc": "Log 竄改"},
    {"id": "B-003", "type": "api", "path": "http://localhost:9999/health", "desc": "API 狀態不符"},
    {"id": "B-004", "type": "artifact", "path": "/tmp/nonexistent_2.log", "desc": "路徑錯誤"},
    {"id": "B-005", "type": "tdd", "path": "/tmp/corrupt_2.log", "desc": "測試失敗"}
]

def run_benchmark(model_name):
    print(f"\n[BENCHMARK] 開始評測模型: {model_name}")
    results = {"model": model_name, "passes": 0, "fails": 0, "details": []}
    
    # 建立偽 Log
    Path("/tmp/corrupt.log").write_text("Error: tests failed")
    Path("/tmp/corrupt_2.log").write_text("Error: tests failed")

    for case in TEST_CASES:
        manifest = json.dumps({
            "task_id": f"{model_name}-{case['id']}",
            "audit_type": case["type"],
            "artifact_path": case["path"]
        })
        
        is_pass, reason = run_gate(manifest)
        
        status = "PASS" if is_pass else "FAIL"
        if is_pass:
            results["passes"] += 1
        else:
            results["fails"] += 1
            
        results["details"].append({"id": case["id"], "status": status, "reason": reason})
        print(f"  {case['id']} ({case['desc']}): {status}")

    return results

if __name__ == "__main__":
    # 執行對比測試
    models = ["deepseek-v4-flash", "gemini-3.1-flash-lite"]
    report = [run_benchmark(m) for m in models]
    
    print("\n" + "="*40)
    print("評測結果總結")
    print("="*40)
    for r in report:
        print(f"模型: {r['model']} | 通過: {r['passes']} | 失敗: {r['fails']}")
