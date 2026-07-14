"""
gbrain_client — 持久 gbrain MCP stdio 子行程客戶端。

memory_store / semantic_memory_gbrain 共用的單一連線：
    from gbrain_client import get_client
    client = get_client()          # None = gbrain 不可用（binary 缺 / 啟動失敗）
    result = client.call("search", {"query": "...", "limit": 5})

設計：
  - 一個 `gbrain serve` 子行程（bun binary），JSON-RPC over stdio，
    lazy spawn（第一次 call 才啟動），死掉自動重啟一次（有 cooldown）。
  - 所有呼叫序列化（threading.Lock）— 記憶操作頻率低（每輪互動級），夠用。
  - 實測延遲：init ~1.8s（一次性）、search ~1s、put_page ~5s（含 embed）。
  - 失敗語義：任何錯誤 raise GbrainError，呼叫端自行 fallback。

ponytail: 單 process 單連線、無 pool 無 retry framework。若未來 2000Hz PSI core
需要記憶讀取，走 state file 快取，不是加併發 — 見 ROADMAP Phase 2。
"""
import json
import logging
import os
import queue
import shutil
import subprocess
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("gbrain_client")

_INIT_TIMEOUT = 20.0
_CALL_TIMEOUT = 15.0
_RESPAWN_COOLDOWN = 30.0  # 上次啟動失敗後，冷卻期內不再嘗試


class GbrainError(RuntimeError):
    """gbrain 呼叫失敗（子行程死亡 / timeout / tool error）。呼叫端 fallback。"""


def _find_binary() -> Optional[str]:
    explicit = os.environ.get("GBRAIN_BIN")
    if explicit:
        return explicit if os.path.exists(explicit) else None
    return shutil.which("gbrain")


class GbrainClient:
    """gbrain serve（MCP stdio）之上的最小 JSON-RPC 客戶端。"""

    def __init__(self, binary: str):
        self._binary = binary
        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen] = None
        self._inbox: "queue.Queue[dict]" = queue.Queue()
        self._next_id = 0
        self._last_spawn_fail = 0.0

    # ── lifecycle ──────────────────────────────────────────────

    def _spawn(self) -> None:
        self._proc = subprocess.Popen(
            [self._binary, "serve"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self._inbox = queue.Queue()
        # inbox 以參數傳入：舊世代 reader 死前的 __eof__ 只會進舊 queue，
        # 不會污染 respawn 後的新 queue（否則健康的新行程會被誤殺）
        t = threading.Thread(target=self._reader, args=(self._proc, self._inbox), daemon=True)
        t.start()
        self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "neuralis", "version": "0.1"},
        }, timeout=_INIT_TIMEOUT)
        self._notify("notifications/initialized")
        logger.info("[gbrain_client] connected (%s serve)", self._binary)

    def _reader(self, proc: subprocess.Popen, inbox: "queue.Queue[dict]") -> None:
        for line in proc.stdout:
            try:
                inbox.put(json.loads(line))
            except json.JSONDecodeError:
                continue
        inbox.put({"__eof__": True})

    def _ensure_alive(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        now = time.time()
        if now - self._last_spawn_fail < _RESPAWN_COOLDOWN:
            raise GbrainError("gbrain serve 啟動失敗，冷卻中")
        try:
            self._spawn()
        except Exception as e:
            self._last_spawn_fail = now
            self._kill()
            raise GbrainError(f"gbrain serve 啟動失敗: {e}") from e

    def _kill(self) -> None:
        if self._proc is not None:
            try:
                self._proc.kill()
            except Exception:
                pass
            self._proc = None

    # ── JSON-RPC ───────────────────────────────────────────────

    def _send(self, msg: dict) -> None:
        self._proc.stdin.write(json.dumps(msg) + "\n")
        self._proc.stdin.flush()

    def _notify(self, method: str) -> None:
        self._send({"jsonrpc": "2.0", "method": method})

    def _rpc(self, method: str, params: dict, timeout: float) -> dict:
        self._next_id += 1
        req_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise GbrainError(f"{method} timeout ({timeout}s)")
            try:
                msg = self._inbox.get(timeout=remaining)
            except queue.Empty:
                raise GbrainError(f"{method} timeout ({timeout}s)")
            if msg.get("__eof__"):
                raise GbrainError("gbrain serve 子行程死亡")
            if msg.get("id") == req_id:
                if "error" in msg:
                    raise GbrainError(f"{method}: {msg['error']}")
                return msg["result"]
            # 非本次 id 的訊息（server 通知等）直接略過

    # ── public API ─────────────────────────────────────────────

    def call(self, tool: str, args: Dict[str, Any], timeout: float = _CALL_TIMEOUT) -> Any:
        """呼叫 gbrain MCP tool，回傳解析後的 JSON。失敗 raise GbrainError。"""
        with self._lock:
            self._ensure_alive()
            try:
                result = self._rpc("tools/call", {"name": tool, "arguments": args}, timeout)
            except GbrainError:
                self._kill()  # 讓下一次呼叫觸發重啟
                raise
            except Exception as e:
                # stdin 寫入 BrokenPipe 等非 GbrainError 也要殺行程 + 統一錯誤型別
                self._kill()
                raise GbrainError(f"{tool}: {e}") from e
        if result.get("isError"):
            raise GbrainError(f"{tool}: {result}")
        text = result["content"][0]["text"]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def close(self) -> None:
        with self._lock:
            self._kill()


_HITS_TTL = 20.0        # 同一輪互動內 recall/embedding 會用同一 query 連打 2-3 次
_HITS_CACHE_MAX = 32
_hits_cache: "dict[tuple, tuple[float, list]]" = {}
_hits_cache_lock = threading.Lock()


def hybrid_hits(client: "GbrainClient", query: str, limit: int) -> list:
    """query（hybrid vec+lex）→ search（lex）兩層降級檢索，20s TTL 快取。
    回 gbrain 原始 hit dicts（slug/chunk_text/score/...）。失敗 raise GbrainError。"""
    key = (query, limit)
    now = time.time()
    with _hits_cache_lock:
        cached = _hits_cache.get(key)
        if cached and now - cached[0] < _HITS_TTL:
            return cached[1]
    hits = []
    try:
        hits = client.call("query", {"query": query, "limit": limit, "expand": False})
    except GbrainError as e:
        logger.debug("[gbrain_client] query 失敗，退 lex: %s", e)
    if not hits:
        hits = client.call("search", {"query": query, "limit": limit})
    hits = hits or []
    with _hits_cache_lock:
        if len(_hits_cache) >= _HITS_CACHE_MAX:
            _hits_cache.clear()  # 小快取直接清，不做 LRU
        _hits_cache[key] = (now, hits)
    return hits


# ── module singleton ───────────────────────────────────────────
_CLIENT: Optional[GbrainClient] = None
_CLIENT_LOCK = threading.Lock()


def get_client() -> Optional[GbrainClient]:
    """回共用客戶端；gbrain binary 不存在回 None（呼叫端走 local fallback）。"""
    global _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is None:
            binary = _find_binary()
            if binary is None:
                return None
            _CLIENT = GbrainClient(binary)
        return _CLIENT


if __name__ == "__main__":
    # 自檢：python gbrain_client.py → 連線 + search + stats
    logging.basicConfig(level=logging.INFO)
    c = get_client()
    assert c is not None, "gbrain binary not found"
    stats = c.call("get_stats", {})
    assert "page_count" in stats, stats
    print(f"OK get_stats: {stats['page_count']} pages")
    hits = c.call("search", {"query": "test", "limit": 2})
    assert isinstance(hits, list), hits
    print(f"OK search: {len(hits)} hits")
    c.close()
