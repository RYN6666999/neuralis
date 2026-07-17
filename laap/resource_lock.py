"""resource_lock — 跨行程資源鎖，防止 Aris 與 Scream cron 同時搶 gbrain/ToolExecutor。

使用 agentOS blackboard（`.sdd/` 目錄）作為後端，所有 agent 共享同一份鎖狀態。

用法:
    from laap.resource_lock import acquire, release, is_locked

    if acquire("gbrain", timeout=30):
        try:
            # 使用 gbrain ...
        finally:
            release("gbrain")
    else:
        # 跳過（鎖被 cron 佔用）
"""
import json
import os
import time
from pathlib import Path

# agentOS blackboard 目錄
SDD = Path.home() / "agent-sandbox" / ".sdd"
SDD_LOCK = Path.home() / "agent-sandbox" / ".sdd" / ".locks"
SDD_LOCK.mkdir(parents=True, exist_ok=True)

# 鎖的 owner 標識（每次呼叫時重新讀取，支援測試切換）
def _owner() -> str:
    return os.environ.get("RESOURCE_LOCK_OWNER", "aris")


def _lock_path(resource: str) -> Path:
    return SDD_LOCK / f"{resource}.json"


def acquire(resource: str, timeout: float = 0, ttl: float = 60) -> bool:
    """嘗試取得資源鎖。timeout=0 不等待，timeout>0 最多等 timeout 秒。
    ttl：鎖自動過期秒數（防止當機後鎖永不釋放）。
    回傳 True 表示取得鎖，False 表示鎖被佔用。"""
    deadline = time.time() + timeout if timeout > 0 else 0
    path = _lock_path(resource)

    while True:
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                # 檢查是否過期
                if time.time() - data.get("acquired_at", 0) > ttl:
                    path.unlink(missing_ok=True)
                else:
                    if data.get("owner") == _owner():
                        # 自己持有，續約
                        _write_lock(path, resource)
                        return True
                    if time.time() >= deadline:
                        return False
                    time.sleep(0.1)
                    continue
            # 寫入鎖
            _write_lock(path, resource)
            return True
        except (OSError, json.JSONDecodeError):
            if time.time() >= deadline:
                return False
            time.sleep(0.1)


def _write_lock(path: Path, resource: str) -> None:
    path.write_text(json.dumps({
        "resource": resource,
        "owner": _owner(),
        "acquired_at": time.time(),
        "pid": os.getpid(),
        "host": os.uname().nodename,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def release(resource: str) -> None:
    """釋放資源鎖。"""
    path = _lock_path(resource)
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("owner") == _owner():
                path.unlink(missing_ok=True)
    except (OSError, json.JSONDecodeError):
        pass


def is_locked(resource: str, ttl: float = 60) -> bool:
    """檢查資源是否被鎖住（含過期檢查）。"""
    path = _lock_path(resource)
    try:
        if not path.exists():
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - data.get("acquired_at", 0) > ttl:
            path.unlink(missing_ok=True)
            return False
        return True
    except (OSError, json.JSONDecodeError):
        return False


def list_locks() -> list[dict]:
    """列出所有活躍鎖。"""
    locks = []
    for p in SDD_LOCK.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            age = time.time() - data.get("acquired_at", 0)
            lock = {"file": p.name, "age_s": round(age, 1)}
            lock.update(data)
            locks.append(lock)
        except Exception:
            locks.append({"file": p.name, "error": "parse error"})
    return locks


def release_all() -> int:
    """釋放當前 owner 的所有鎖。回傳釋放數量。"""
    count = 0
    for p in SDD_LOCK.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("owner") == _owner():
                p.unlink(missing_ok=True)
                count += 1
        except Exception:
            pass
    return count