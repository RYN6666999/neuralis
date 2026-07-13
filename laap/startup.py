"""
neuralis startup: 全部啟動器 (延遲初始化)
=========================================
一次初始化 Aris 完整認知系統：
  心臟: PsiCore (五維需求 + 情緒梯度)
  手腳: ToolExecutor (AgentOS + gbrain + qmd + 本機工具)

用法:
    from laap.startup import ensure_psi_core, ensure_tools, startup_all
    bus, psi, tools = startup_all()
"""
import logging
logger = logging.getLogger("laap.startup")

_psi_core = None
_tool_executor = None
_bus = None


def ensure_psi_core():
    global _psi_core, _bus
    if _psi_core is not None:
        return _psi_core
    try:
        from laap.psi_core import PsiCore
        from aris_brain.psi_core_bridge import get_global_bus
        _bus = get_global_bus()
        _psi_core = PsiCore(bus=_bus, interval=1.0)
        _psi_core.start()
        logger.info("❤️ PsiCore 啟動 — Aris 有心跳了")
    except Exception as e:
        logger.warning(f"PsiCore 啟動失敗: {e}")
    return _psi_core


def ensure_tools():
    global _tool_executor, _bus
    if _tool_executor is not None:
        return _tool_executor
    try:
        from laap.tool_executor import ToolExecutor
        # 接 AgentOS executor_registry
        try:
            import sys
            sys.path.insert(0, str(__import__('pathlib').Path.home() / "agent-sandbox"))
            from orchestrator import executor_registry
            registry = executor_registry
        except Exception:
            registry = None
            logger.info("[startup] AgentOS executor_registry 不可用 (降級模式)")

        if _bus is None:
            ensure_psi_core()
        _tool_executor = ToolExecutor(bus=_bus, agentos_registry=registry)
        logger.info("🛠️  ToolExecutor 啟動 — Aris 有手腳了")
        logger.info(f"    工具數: {len(_tool_executor.list_tools())}")
    except Exception as e:
        logger.warning(f"ToolExecutor 啟動失敗: {e}")
    return _tool_executor


def startup_all():
    """一次啟動所有系統。"""
    ensure_psi_core()
    ensure_tools()
    return _bus, _psi_core, _tool_executor


def get_psi_core():
    return _psi_core

def get_tool_executor():
    return _tool_executor

def get_bus():
    return _bus