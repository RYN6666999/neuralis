"""
SafetyGate — Phase 4a：工具執行安全閘（外部審查紅線：煞車先於能力）。

三層，全部 0 LLM：
  0. 委派 path-DENY（甲/乙 硬防線，最先跑、不可 env 繞過、不受工具批准影響）：
     委派工具（scream-task…）指向 neuralis 認知碼 laap/** 一律 DENY，fail-closed。
     Scream 永不得改 Aris 自己的腦 — 這是「甲不滑進乙」的物理防線。
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

READONLY_SAFE = frozenset({"gbrain", "qmd", "file-search", "scream-ask", "scream-task",
                           "stream-test"})  # stream-test: 固定 echo/sleep 指令，不吃使用者輸入
# 來自 AgentOS executor_registry 的唯讀工具（實測驗證過：DuckDuckGo 搜尋，無副作用）
AGENTOS_READONLY: frozenset = frozenset({"web-search"})
_ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = _ROOT / "safety-audit.jsonl"
APPROVED_PATH = _ROOT / "approved-tools.txt"      # 一行一工具，人工簽名（4b 批准閘）
PENDING_PATH = _ROOT / "approvals-pending.jsonl"  # 被拒工具排隊等人批

# AgentOS 不可用時的內建縮小版（與 orchestrator/safety.py 同源精神）
_FALLBACK_PATTERNS = [
    re.compile(r"\brm\s+-[rf]{1,2}\b", re.I),
    re.compile(r"drop\s+table", re.I),
    re.compile(r"truncate\s+\w", re.I),
    re.compile(r"push\s+(--force|-f)\b", re.I),
    re.compile(r"清空資料庫|格式化硬碟|格式化磁碟"),
    re.compile(r"\b(shutdown|reboot|poweroff|halt)\b", re.I),
]


# ── 層 0：委派 path-DENY（甲/乙 硬防線）────────────────────────────
# 委派工具把工作交給外部執行體（Scream）— 那有「手」能寫檔。禁止委派指向
# neuralis 認知碼，否則 Aris 能（直接或被誘導）改寫自己的腦 = 乙（RSI），已否決。
# 設計：fail-closed 子串比對（寧誤擋不漏放）；base set 只能 env 擴充、不能縮；
# 最先跑、不受工具批准影響（就算 scream-task 被 approve，指向 laap/ 仍 DENY）。
_DELEGATION_BASE = frozenset({"scream-task"})


def _delegation_tools() -> frozenset:
    """委派工具集。base 不可縮，env NEURALIS_DELEGATION_TOOLS_EXTRA 只能加。"""
    extra = {t.strip() for t in
             os.environ.get("NEURALIS_DELEGATION_TOOLS_EXTRA", "").split(",") if t.strip()}
    return _DELEGATION_BASE | extra


def _protected_fragments() -> list:
    """受保護認知碼比對片段。base = neuralis laap/（相對簽名 + 絕對路徑）。
    env NEURALIS_PROTECTED_PATHS（逗號分隔）只能擴、不能縮。"""
    frags = ["laap/", str(_ROOT / "laap")]
    frags += [p.strip() for p in
              os.environ.get("NEURALIS_PROTECTED_PATHS", "").split(",") if p.strip()]
    return frags


def _targets_protected_path(prompt: str) -> Tuple[bool, str]:
    """委派內容是否指向受保護認知碼。fail-closed 子串比對。"""
    for frag in _protected_fragments():
        if frag and frag in prompt:
            return True, frag
    return False, ""


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


def _file_approved() -> frozenset:
    """approved-tools.txt：一行一工具，# 開頭是註解。每次讀（免重啟生效，檔案小）。"""
    try:
        lines = APPROVED_PATH.read_text(encoding="utf-8").splitlines()
        return frozenset(l.strip() for l in lines if l.strip() and not l.startswith("#"))
    except FileNotFoundError:
        return frozenset()


def _allowed_tools() -> frozenset:
    extra = os.environ.get("NEURALIS_TOOL_ALLOW", "")
    return READONLY_SAFE | AGENTOS_READONLY \
         | {t.strip() for t in extra.split(",") if t.strip()} | _file_approved()


def classify(tool: str) -> str:
    """回 "readonly_builtin" / "readonly_agentos" / "write"。

    工具分類 chokepoint — 單一源頭，agency/status/審計都從這裡拿分類。
    """
    if tool in READONLY_SAFE:
        return "readonly_builtin"
    if tool in AGENTOS_READONLY:
        return "readonly_agentos"
    return "write"  # 所有非白名單視為 write（需 Phase 4b 批准）


def get_allowed_tools() -> list:
    """回 [{name, classification}, ...]"""
    allowed = _allowed_tools()
    return [{"name": t, "classification": classify(t)} for t in sorted(allowed)]


def get_classification_map() -> dict:
    """回 {"readonly_builtin": [...], "readonly_agentos": [...], "write": [...]}"""
    m: dict = {}
    for tool in sorted(READONLY_SAFE | AGENTOS_READONLY):
        m.setdefault(classify(tool), []).append(tool)
    return m


def _queue_pending(tool: str, prompt: str) -> None:
    """被拒的工具排進待批清單（同工具只排一次），人用 scripts/approve-tool.sh 批。"""
    try:
        if PENDING_PATH.exists() and f'"tool": "{tool}"' in PENDING_PATH.read_text(encoding="utf-8"):
            return
        with PENDING_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "tool": tool,
                                "first_prompt": prompt[:120]}, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[SafetyGate] 待批清單寫入失敗: {e}")


def check(tool: str, prompt: str) -> Tuple[bool, str]:
    """回 (allowed, reason)。reason 只在拒絕時有內容。"""
    # 層 0：委派 path-DENY（甲/乙 硬防線）— 最先跑，不可被工具批准/env 繞過。
    if tool in _delegation_tools():
        hit, frag = _targets_protected_path(prompt)
        if hit:
            reason = (f"[安全閘] 委派指向受保護認知碼（{frag}）— 甲不滑進乙硬防線，"
                      f"DENY。Scream 永不得改 neuralis/laap/**。")
            _audit(tool, prompt, reason, grade="delegation_path_denied")
            return False, reason
    if tool not in _allowed_tools():
        _queue_pending(tool, prompt)
        reason = (f"工具 {tool} 未批准 — 已排入待批清單，"
                  f"批准: scripts/approve-tool.sh {tool}")
        _audit(tool, prompt, reason)
        return False, reason
    blocked, matches = _agentos_check(prompt)
    if blocked:
        reason = f"危險內容: {matches}"
        _audit(tool, prompt, reason)
        return False, reason
    return True, ""


def _audit(tool: str, prompt: str, reason: str, grade: str = "") -> None:
    if not grade:
        grade = classify(tool)
    try:
        with AUDIT_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "tool": tool,
                                "prompt": prompt[:200], "denied": reason,
                                "grade": grade},
                               ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[SafetyGate] 審計寫入失敗: {e}")
    logger.warning(f"[SafetyGate] DENY {tool}: {reason}")
