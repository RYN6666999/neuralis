import hashlib, json, sys
from pathlib import Path

NEURALIS_HOME = Path.home() / "Developer/neuralis"
CORE_CONFIGS = [NEURALIS_HOME / "laap/agency.py", NEURALIS_HOME / "laap/safety_gate.py"]
HASH_REGISTRY = NEURALIS_HOME / ".doctor_hashes.json"

def get_hashes():
    hashes = {}
    for p in CORE_CONFIGS:
        if p.exists():
            hashes[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return hashes

def doctor():
    current = get_hashes()
    if HASH_REGISTRY.exists():
        expected = json.loads(HASH_REGISTRY.read_text())
        for p, h in expected.items():
            if current.get(p) != h:
                print(f"[🚨 SYSTEM-HALT] 偵測到代碼竄改: {Path(p).name}")
                sys.exit(1)
    else:
        HASH_REGISTRY.write_text(json.dumps(current))
        print("[✅] 初始化安全指紋")
    print("[✅] 系統健康檢查通過 (SHA-256 Verified)")

if __name__ == "__main__":
    doctor()
