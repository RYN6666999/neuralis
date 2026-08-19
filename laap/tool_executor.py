"""
ToolExecutor — CognitiveBus → AgentOS executor_registry 橋接

把 PSI Core 的「想探索/想了解/想做」轉成實際工具呼叫。
不需要自己造輪子——所有工具執行都委託給已經存在的系統：

  AgentOS executor_registry  → web-search, agnes-analyze, claude-code
  gbrain CLI                 → 長期記憶讀寫
  qmd CLI                    → 本地知識庫搜尋
  subprocess                 → rg (檔案搜尋), httpx (API), curl, jq...
"""
from __future__ import annotations
import json
import logging
import subprocess
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
import os
import time
import uuid

from laap.agi.cognitive_bus import CognitiveBus, CognitiveEventType

logger = logging.getLogger("laap.tool_executor")


class ToolExecutor:
    """工具執行層 — 把 CognitiveBus 事件轉成真實動作。"""

    TOOL_STATUS_FILE = "/tmp/laap-tool-status.json"
    CHANNEL_PATH = "/tmp/aris-scream-channel.jsonl"

    def __init__(self, bus: CognitiveBus, agentos_registry=None):
        self.bus = bus
        self._registry = agentos_registry  # AgentOS executor_registry 模組
        self._tools: Dict[str, dict] = {}  # 本機註冊的 tools
        self._tool_start_time: float = 0.0
        self._last_status_emit_ts: float = 0.0
        self._last_status_key: tuple[str, str, str, str] | None = None

        bus.register_module("tool_executor", "1.0",
                            ["web_search", "file_search", "gbrain", "qmd", "shell", "http"])

        # 註冊內建工具
        self._register_builtins()

        # 訂閱工具請求事件
        bus.subscribe("tool_executor", CognitiveEventType.ACTION_REQUEST, self._on_action_request)
        logger.info("[ToolExecutor] 初始化完成 — 就緒")

    # ── 公開 API ──

    def register_tool(self, name: str, exec_fn, description: str = "",
                      stream_fn=None) -> None:
        """註冊自訂工具。exec_fn 簽名: (prompt: str) → str。
        stream_fn（可選）簽名: (prompt: str) → Iterator[str]，逐行 yield 中間輸出；
        有 stream_fn 的工具在 stream() 路徑會逐步輸出，最終結果 = 全部行拼接。"""
        self._tools[name] = {"fn": exec_fn, "description": description,
                             "stream_fn": stream_fn}
        logger.info(f"[ToolExecutor] 工具註冊: {name}")

    def _emit_tool_status(self, icon: str, status: str, desc: str,
                          tool: str = "", elapsed: float = 0):
        """寫 LAAP 工具狀態到檔案 + channel，供 Scream TUI 即時消費。"""
        import time, uuid
        # 狀態節流：避免高頻重複事件把 TUI 推進重繪抖動。
        desc = (desc or "").replace("\n", " ")[:96]
        status_key = (icon, status, tool, desc)
        now = time.time()
        if self._last_status_key == status_key and (now - self._last_status_emit_ts) < 0.35:
            return

        payload = {
            "icon": icon, "status": status, "description": desc,
            "tool": tool, "elapsed": round(elapsed, 1),
            "ts": now,
        }
        try:
            with open(self.TOOL_STATUS_FILE, "w") as f:
                json.dump(payload, f)
            # 2026-08-19：原本每次工具執行都 append 一筆到
            # /tmp/aris-scream-channel.jsonl 給 Scream TUI 顯示狀態列。
            # Ryan 已改成只走 Hermes，Scream 不再啟動 → 那個檔沒有讀者，
            # 只會無上限長大（刪除時實測 223KB / 803 行）。整段刪掉。
            self._last_status_emit_ts = now
            self._last_status_key = status_key
        except Exception:
            pass

    def _clear_tool_status(self):
        """清除狀態檔案（工具完成後）。"""
        import os, time
        payload = {
            "icon": "✔️", "status": "idle", "description": "",
            "tool": "", "elapsed": 0, "ts": time.time(),
        }
        try:
            with open(self.TOOL_STATUS_FILE, "w") as f:
                json.dump(payload, f)
        except Exception:
            pass

    TOOL_ICONS = {
        "gbrain": "🧠", "qmd": "📚", "file-search": "🔍",
        "http-get": "🌐", "http": "🌐", "web-search": "🌐",
        "shell": "⚙️", "bash": "⚙️",
    }

    def execute(self, tool: str, prompt: str, timeout: int = 30) -> str:
        """執行工具，回傳結果文字。所有呼叫先過安全閘（Phase 4a）。
        = stream() 的 drain 包裝：吃完全部事件，只回最終 result（舊呼叫者零改動）。"""
        result = ""
        for ev in self.stream(tool, prompt, timeout=timeout):
            if ev.get("type") == "result":
                result = ev.get("text", "")
        return result

    def stream(self, tool: str, prompt: str, timeout: int = 30):
        """執行工具，逐步 yield 事件 dict（sync generator，供 thread 中迭代）：
          {"type": "status", "text": ...}  執行階段（開始/完成/失敗）
          {"type": "output", "text": ...}  中間輸出（有 stream_fn 的工具逐行）
          {"type": "result", "text": ...}  最終結果 — 恰一個、必為最後一個事件
        安全閘與 execute() 同一道；拒絕時直接 yield result 事件。
        ponytail: 只有掛 stream_fn 的工具有真中間輸出；opaque fn / AgentOS
        executor 只有前後 status。升級路徑 = 把 subprocess builtins 換 _popen_lines。"""
        import time
        from laap.safety_gate import check as safety_check
        allowed, reason = safety_check(tool, prompt)
        if not allowed:
            yield {"type": "result", "text": f"[安全閘] 拒絕: {reason}"}
            return

        icon = self.TOOL_ICONS.get(tool, "⚙️")
        short_desc = prompt.strip()[:40]
        # elapsed 用區域變數：agency 與 chat 並行跑工具時，instance 共享的
        # _tool_start_time 會互相覆蓋，elapsed 顯示錯亂（實測 127s 顯示 9.5s）
        t0 = time.time()
        self._tool_start_time = t0
        self._emit_tool_status(icon, "start", f"{tool}: {short_desc}", tool=tool)
        yield {"type": "status", "text": f"{icon} {tool} 開始: {short_desc}"}

        logger.info(f"[ToolExecutor] 執行: {tool}({prompt[:60]})")

        result = ""
        finished = False
        try:
            # 1. 本機工具
            if tool in self._tools:
                self._emit_tool_status(icon, "running", f"{tool}: {short_desc}", tool=tool)
                entry = self._tools[tool]
                if entry.get("stream_fn"):
                    lines = []
                    for line in entry["stream_fn"](prompt):
                        lines.append(line)
                        yield {"type": "output", "text": line}
                    result = "\n".join(lines).strip()[:3000] or "無結果"
                else:
                    result = entry["fn"](prompt)

            # 2. AgentOS executor
            elif self._registry:
                self._emit_tool_status(icon, "running", f"{tool}: {short_desc}", tool=tool)
                try:
                    result = self._registry.run(tool, prompt, timeout=timeout)
                except KeyError:
                    result = f"[未知工具] {tool} — 未註冊"
                except Exception as e:
                    result = f"[AgentOS 錯誤] {tool}: {e}"
            else:
                result = f"[未知工具] {tool} — 未註冊"

            elapsed = time.time() - t0
            self._emit_tool_status(icon, "done", f"{tool}: 完成 ({elapsed:.1f}s)",
                                   tool=tool, elapsed=elapsed)
            self._clear_tool_status()
            finished = True
            yield {"type": "status", "text": f"{icon} {tool} 完成 ({elapsed:.1f}s)"}
            yield {"type": "result", "text": result}

        except Exception as e:
            elapsed = time.time() - t0
            self._emit_tool_status("❌", "fail", f"{tool}: {e}", tool=tool, elapsed=elapsed)
            self._clear_tool_status()
            finished = True
            yield {"type": "status", "text": f"❌ {tool} 失敗: {e}"}
            yield {"type": "result", "text": f"[錯誤] {tool}: {e}"}
        finally:
            # caller 中途棄迭代（GeneratorExit）時 done/clear 不會跑 →
            # busy 檔卡 "running" = 忙碌保護把 Aris 永久噤聲。這裡兜底清掉。
            if not finished:
                self._clear_tool_status()

    @staticmethod
    def _popen_lines(argv: list, timeout: int = 30):
        """跑 subprocess，stdout 逐行 yield（stderr 併入 stdout）。
        ponytail: 逾時只在行與行之間檢查 — 沉默的長行程要等到下一行才被殺。"""
        import time
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        deadline = time.time() + timeout
        try:
            for line in proc.stdout:
                yield line.rstrip("\n")
                if time.time() > deadline:
                    proc.kill()
                    yield f"[逾時 {timeout}s，已中止]"
                    return
            proc.wait(timeout=5)
        finally:
            if proc.poll() is None:
                proc.kill()

    def list_tools(self) -> List[Dict[str, str]]:
        """列出所有可用工具。"""
        tools = []
        for name in self._tools:
            tools.append({"name": name, "source": "builtin",
                          "desc": self._tools[name]["description"]})
        if self._registry:
            for e in self._registry.list_all():
                tools.append({"name": e["name"], "source": "agentos"})
        return tools

    # ── 內部 ──

    def _register_builtins(self):
        """註冊本機可直接叫的工具（不透過 AgentOS）。"""

        # gbrain 記憶搜尋 — 走 neuralis 持久 MCP client（免 CLI 冷啟 ~3s/次），
        # client 不可用再退 CLI
        def gbrain_search(query: str) -> str:
            try:
                from gbrain_client import get_client, hybrid_hits
                client = get_client()
                if client is not None:
                    hits = hybrid_hits(client, query, 5)
                    lines = [f"[{h.get('score', 0):.2f}] {h.get('slug','')} — "
                             f"{(h.get('chunk_text') or h.get('title') or '')[:200]}"
                             for h in hits]
                    return "\n".join(lines) if lines else "無結果"
            except Exception as e:
                logger.debug(f"[ToolExecutor] gbrain client 失敗，退 CLI: {e}")
            result = subprocess.run(
                ["gbrain", "query", query],
                capture_output=True, text=True, timeout=15,
            )
            return (result.stdout or result.stderr or "").strip()[:2000]

        # qmd 本地知識搜尋（stream_fn 逐行 — 串流路徑即時可見）
        def qmd_stream(query: str):
            yield from ToolExecutor._popen_lines(["qmd", "query", query], timeout=15)

        def qmd_search(query: str) -> str:
            result = subprocess.run(
                ["qmd", "query", query],
                capture_output=True, text=True, timeout=15,
            )
            return (result.stdout or result.stderr or "").strip()[:2000]

        # ripgrep 檔案全文搜尋（stream_fn 逐行）
        def file_search_stream(query: str):
            yield from ToolExecutor._popen_lines(
                ["rg", "-n", "--max-count", "20", query, "."], timeout=10)

        def file_search(query: str) -> str:
            result = subprocess.run(
                ["rg", "-n", "--max-count", "20", query, "."],
                capture_output=True, text=True, timeout=10,
            )
            return (result.stdout or "無結果").strip()[:2000]

        # httpx 簡單網頁請求
        def http_get(url: str) -> str:
            import httpx
            resp = httpx.get(url, timeout=10, follow_redirects=True)
            return resp.text[:3000]

        # stream-test — 串流管線自測：固定慢指令逐行輸出（不插值使用者輸入，無 injection 面）
        def stream_test_stream(_prompt: str):
            yield from ToolExecutor._popen_lines(
                ["/bin/sh", "-c",
                 'echo "step 1/3 開始"; sleep 1; echo "step 2/3 處理中"; sleep 1; echo "step 3/3 done"'],
                timeout=15)

        def stream_test_exec(prompt: str) -> str:
            return "\n".join(stream_test_stream(prompt))

        self.register_tool("gbrain", gbrain_search, "gbrain 長期記憶搜尋 (hybrid search)")
        self.register_tool("qmd", qmd_search, "qmd 本地知識庫搜尋 (hybrid + rerank)",
                           stream_fn=qmd_stream)
        self.register_tool("file-search", file_search, "ripgrep 檔案全文搜尋",
                           stream_fn=file_search_stream)
        self.register_tool("http-get", http_get, "HTTP GET 請求")
        self.register_tool("stream-test", stream_test_exec,
                           "串流管線自測（固定慢指令，逐行輸出）",
                           stream_fn=stream_test_stream)

    def _on_action_request(self, source: str, data: dict) -> None:
        """CognitiveBus ACTION_REQUEST 事件回呼。"""
        tool = data.get("tool", "")
        prompt = data.get("prompt", "")
        timeout = data.get("timeout", 30)

        result = self.execute(tool, prompt, timeout=timeout)

        self.bus.publish(
            CognitiveEventType.ACTION_RESULT,
            "tool_executor",
            {"tool": tool, "prompt": prompt, "result": result},
        )