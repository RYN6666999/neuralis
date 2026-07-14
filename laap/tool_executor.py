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

from laap.agi.cognitive_bus import CognitiveBus, CognitiveEventType

logger = logging.getLogger("laap.tool_executor")


class ToolExecutor:
    """工具執行層 — 把 CognitiveBus 事件轉成真實動作。"""

    def __init__(self, bus: CognitiveBus, agentos_registry=None):
        self.bus = bus
        self._registry = agentos_registry  # AgentOS executor_registry 模組
        self._tools: Dict[str, dict] = {}  # 本機註冊的 tools

        bus.register_module("tool_executor", "1.0",
                            ["web_search", "file_search", "gbrain", "qmd", "shell", "http"])

        # 註冊內建工具
        self._register_builtins()

        # 訂閱工具請求事件
        bus.subscribe("tool_executor", CognitiveEventType.ACTION_REQUEST, self._on_action_request)
        logger.info("[ToolExecutor] 初始化完成 — 就緒")

    # ── 公開 API ──

    def register_tool(self, name: str, exec_fn, description: str = "") -> None:
        """註冊自訂工具。exec_fn 簽名: (prompt: str) → str"""
        self._tools[name] = {"fn": exec_fn, "description": description}
        logger.info(f"[ToolExecutor] 工具註冊: {name}")

    def execute(self, tool: str, prompt: str, timeout: int = 30) -> str:
        """執行工具，回傳結果文字。"""
        logger.info(f"[ToolExecutor] 執行: {tool}({prompt[:60]})")

        # 1. 本機工具
        if tool in self._tools:
            try:
                return self._tools[tool]["fn"](prompt)
            except Exception as e:
                return f"[錯誤] {tool}: {e}"

        # 2. AgentOS executor
        if self._registry:
            try:
                return self._registry.run(tool, prompt, timeout=timeout)
            except KeyError:
                pass
            except Exception as e:
                return f"[AgentOS 錯誤] {tool}: {e}"

        return f"[未知工具] {tool} — 未註冊"

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

        # qmd 本地知識搜尋
        def qmd_search(query: str) -> str:
            result = subprocess.run(
                ["qmd", "query", query],
                capture_output=True, text=True, timeout=15,
            )
            return (result.stdout or result.stderr or "").strip()[:2000]

        # ripgrep 檔案全文搜尋
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

        self.register_tool("gbrain", gbrain_search, "gbrain 長期記憶搜尋 (hybrid search)")
        self.register_tool("qmd", qmd_search, "qmd 本地知識庫搜尋 (hybrid + rerank)")
        self.register_tool("file-search", file_search, "ripgrep 檔案全文搜尋")
        self.register_tool("http-get", http_get, "HTTP GET 請求")

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