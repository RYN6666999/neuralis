#!/usr/bin/env python3
"""rust-psi-bridge.py — 每秒把 Rust 引擎輸出轉成 latest.json（Python 格式）。

Rust daemon (PID 1749) 每 100ms 寫 rust-latest.json。
:11547 的 cognitive_bus 讀 latest.json。
這支腳本在兩者之間做欄位轉換，讓 :11547 吃到即時情緒。

2026-08-27 接線：Ryan 選擇 Rust 真實情緒。
"""
import json, os, time
from pathlib import Path

STATE_DIR = Path.home() / "Developer/laap-AGI/aris_brain/state"
RUST_FILE = STATE_DIR / "rust-latest.json"
PYTHON_FILE = STATE_DIR / "latest.json"

def rust_to_python(rust: dict) -> dict:
    """Rust neuralis-rust-psi/v1 → Python latest.json 格式。"""
    needs = rust.get("needs", {})
    affect = rust.get("affect", {})
    return {
        "cycle": rust.get("tick", 0),
        "needs": {
            "certainty": needs.get("certainty", 0.5),
            "competence": needs.get("competence", 0.5),
            "autonomy": needs.get("autonomy", 0.5),
            "relatedness": needs.get("relatedness", 0.5),
            "growth": needs.get("growth", 0.5),
        },
        "attention": rust.get("attention", "idle").upper(),
        "emotion": {
            "valence": affect.get("pleasure", 0.0),
            "arousal": affect.get("arousal", 0.5),
            "dominance": affect.get("dominance", 0.5),
            "raw_valence": affect.get("pleasure", 0.0),
        },
        # cognitive_bus 讀 latest.json 時會 .get() 帶預設值
        # 以下欄位是 bridge 額外需要的，Rust 沒有，補預設值
        "quantum_engine": "none",
        "quantum_response": "",
        "self_presence": 0.5,
        "daemon_uptime": rust.get("daemon_uptime", 0),
        "ts": rust.get("ts", time.time()),
        "source": "neuralis-rust-psi",
    }

def main():
    last_mtime = 0
    fail_count = 0
    while True:
        try:
            mtime = os.path.getmtime(RUST_FILE)
            if mtime > last_mtime:
                raw = json.loads(RUST_FILE.read_text(encoding="utf-8"))
                converted = rust_to_python(raw)
                tmp = PYTHON_FILE.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(converted, ensure_ascii=False), encoding="utf-8")
                tmp.rename(PYTHON_FILE)
                last_mtime = mtime
                fail_count = 0
            # 如果超過 5 秒沒有新檔案 → daemon 可能掛了
            if time.time() - mtime > 5:
                fail_count += 1
                if fail_count >= 3:
                    print("[rust-psi-bridge] ⚠️ Rust daemon 無回應 >5s — latest.json 可能已過時",
                          file=__import__('sys').stderr, flush=True)
        except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
            fail_count += 1
            if fail_count >= 3:
                print(f"[rust-psi-bridge] ⚠️ 轉換失敗 {fail_count} 次: {e}",
                      file=__import__('sys').stderr, flush=True)
        time.sleep(1.0)

if __name__ == "__main__":
    print("✅ rust-psi-bridge 啟動 — 每秒轉換 Rust 引擎到 latest.json")
    main()
