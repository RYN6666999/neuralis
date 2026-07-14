"""
SafetyGate — Phase 4a：工具執行安全閘（外部審查紅線：煞車先於能力）。

兩層，全部 0 LLM：
  1. 工具分級：唯讀安全組（gbrain/qmd/file-search）直接過；其他工具
     預設拒絕，除非列進 NEURALIS_TOOL_ALLOW（逗號分隔）— v0 的人工批准閘
     = 人明確在環境變數簽名。
  2. 內容掃描：prompt 過 AgentOS orchestrator/safety.py 的 check_command
     （rm -rf / DROP TABLE / 格式化 / restricted paths…）；AgentOS 不在就用
     內建縮小版規則。命中即拒。

每次 DENY 寫審計（safety-audit.jsonl）。放行不記（低噪音）。
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger("laap.safety_gate")

READONLY_SAFE = frozenset({"gbrain", "qmd", "file-search"})
AUDIT_PATH = Path(__file__).resolve().parents[1] / "safety-audit.jsonl"

# AgentOS 不可用時的內建縮小版（與 orchestrator/safety.py 同源精神）
_FALLBACK_PATTERNS = [
    re.compile(r"\brm\s+-[rf]{1,2}\b", re.I),
    re.compile(r"drop\s+table", re.I),
    re.compile(r"truncate\s+\w", re.I),
    re.compile(r"push\s+(--force|-f)\b", re.I),
    re.compile(r"清空資料庫|格式化硬碟|格式化磁碟"),
    re.compile(r"\b(shutdown|reboot|poweroff|halt)\b", re.I),
]


def _agentos_check(text: str) -> Tuple[bool, List[str]]:
    """優先用 AgentOS 的規則；載不到回 (None) 讓 fallback 接手。"""
    try:
        import sys
        agentos_dir = os.environ.get("AGENTOS_DIR",
                                     str(Path.home() / "agent-sandbox"))
        if agentos_dir not in sys.path:
            sys.path.insert(0, agentos_dir)
        from orchestrator.safety import check_command
        return check_command(text)
    except Exception:
        matched = [p.pattern for p in _FALLBACK_PATTERNS if p.search(text)]
        return bool(matched), matched


def _allowed_tools() -> frozenset:
    extra = os.environ.get("NEURALIS_TOOL_ALLOW", "")
    return READONLY_SAFE | {t.strip() for t in extra.split(",") if t.strip()}


def check(tool: str, prompt: str) -> Tuple[bool, str]:
    """回 (allowed, reason)。reason 只在拒絕時有內容。"""
    if tool not in _allowed_tools():
        reason = f"工具 {tool} 未批准（唯讀組以外需列入 NEURALIS_TOOL_ALLOW）"
        _audit(tool, prompt, reason)
        return False, reason
    blocked, matches = _agentos_check(prompt)
    if blocked:
        reason = f"危險內容: {matches}"
        _audit(tool, prompt, reason)
        return False, reason
    return True, ""


def _audit(tool: str, prompt: str, reason: str) -> None:
    try:
        with AUDIT_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "tool": tool,
                                "prompt": prompt[:200], "denied": reason},
                               ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[SafetyGate] 審計寫入失敗: {e}")
    logger.warning(f"[SafetyGate] DENY {tool}: {reason}")
