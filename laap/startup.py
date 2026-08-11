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
import os
import shutil
from pathlib import Path

logger = logging.getLogger("laap.startup")

_psi_core = None
_tool_executor = None
_bus = None

_PSI_DEF_NAMES = ("core_identity.psi", "core_psi.psi", "core_language.psi")


def ensure_psi_defs() -> None:
    """agi_kernel 的 PsiLangCore 需要三個 .psi 核心定義檔（作者端缺失，一缺整組失敗）。
    缺哪個就從 laap/psi_defs/ 補上「標示為 bootstrap 佔位」的最小版 — 只補結構，
    不替作者定義人格內容。作者已有的檔一律不碰。"""
    laap_dir = os.environ.get("LAAP_AGI_DIR", str(Path(__file__).resolve().parents[2] / "laap-AGI"))
    brain = Path(laap_dir) / "aris_brain"
    if not brain.is_dir():
        return
    src_dir = Path(__file__).resolve().parent / "psi_defs"
    for name in _PSI_DEF_NAMES:
        dst = brain / name
        if not dst.exists():
            try:
                shutil.copyfile(src_dir / name, dst)
                logger.info(f"[startup] 補 bootstrap 佔位: {dst.name}")
            except Exception as e:
                logger.warning(f"[startup] 無法補 {name}: {e}")


def ensure_psi_core():
    global _psi_core, _bus
    if _psi_core is not None:
        return _psi_core

    backend = os.environ.get("NEURALIS_PSI_BACKEND", "python").lower()

    if backend == "rust":
        try:
            from laap.psi_backend import RustPsiBackend
            _psi_core = RustPsiBackend()
            _psi_core.start()
            if _psi_core.healthy():
                logger.info("❤️ RustPsiBackend 啟動 — Aris 有心跳了（Rust 引擎）")
                return _psi_core
            else:
                logger.warning("RustPsiBackend daemon 未就緒，回退 Python")
                _psi_core = None
        except Exception as e:
            logger.warning(f"RustPsiBackend 啟動失敗，回退 Python: {e}")
            _psi_core = None
        # fallthrough to Python path

    # Default: Python PsiCore
    try:
        from laap.psi_core import PsiCore
        from laap.psi_backend import PythonPsiBackend
        from aris_brain.psi_core_bridge import get_global_bus
        _bus = get_global_bus()
        raw = PsiCore(bus=_bus, interval=1.0)
        _psi_core = PythonPsiBackend(raw)
        _psi_core.start()
        logger.info("❤️ PsiBackend 啟動 — Aris 有心跳了")
    except Exception as e:
        logger.warning(f"PsiCore 啟動失敗: {e}")
    return _psi_core


def ensure_tools():
    global _tool_executor, _bus
    if _tool_executor is not None:
        return _tool_executor
    try:
        from laap.tool_executor import ToolExecutor
        # 接 AgentOS executor_registry（路徑可用 AGENTOS_DIR 覆蓋）
        try:
            import os, sys
            agentos_dir = os.environ.get(
                "AGENTOS_DIR", str(__import__('pathlib').Path.home() / "agent-sandbox"))
            if agentos_dir not in sys.path:
                sys.path.insert(0, agentos_dir)
            from orchestrator import executor_registry
            registry = executor_registry
        except Exception:
            registry = None
            logger.info("[startup] AgentOS executor_registry 不可用 (降級模式)")

        if _bus is None:
            ensure_psi_core()
        if _bus is None:
            # PsiCore 起不來（如 psi_core_bridge 缺）→ 工具層仍該活：裸 bus 頂上
            from laap.agi.cognitive_bus import CognitiveBus
            _bus = CognitiveBus()
            logger.info("[startup] PsiCore 不可用，ToolExecutor 用獨立 CognitiveBus")
        _tool_executor = ToolExecutor(bus=_bus, agentos_registry=registry)
        logger.info("🛠️  ToolExecutor 啟動 — Aris 有手腳了")
        logger.info(f"    工具數: {len(_tool_executor.list_tools())}")
    except Exception as e:
        logger.warning(f"ToolExecutor 啟動失敗: {e}")
    return _tool_executor


_agency = None


def ensure_agency():
    """Phase 6 agency loop：需求→行動→結果→記憶。NEURALIS_AGENCY=off 可關。
    psi 或 tools 缺任一 → 不起（迴路兩端都要在）。"""
    global _agency
    if _agency is not None:
        return _agency
    if os.environ.get("NEURALIS_AGENCY", "on").lower() in ("off", "0", "false"):
        logger.info("[startup] AgencyLoop 已由 NEURALIS_AGENCY=off 停用")
        return None
    if _psi_core is None or _tool_executor is None:
        logger.info("[startup] AgencyLoop 不起（psi 或 tools 缺）")
        return None
    try:
        from laap.agency import AgencyLoop
        _agency = AgencyLoop(psi=_psi_core, tools=_tool_executor, bus=_bus)
        _agency.start()
        logger.info("🔄 AgencyLoop 啟動 — Aris 會自主行動了（唯讀白名單 + AgentOS web-search + rate cap）")
    except Exception as e:
        logger.warning(f"AgencyLoop 啟動失敗: {e}")
    return _agency


_consolidation = None


def ensure_consolidation():
    """Phase 5 記憶固化循環（睡眠）。NEURALIS_CONSOLIDATION=off 可關。
    不依賴 psi（沒心跳也能打掃，只是少了 arousal 睡眠窗判斷）。"""
    global _consolidation
    if _consolidation is not None:
        return _consolidation
    if os.environ.get("NEURALIS_CONSOLIDATION", "on").lower() in ("off", "0", "false"):
        logger.info("[startup] ConsolidationLoop 已由 NEURALIS_CONSOLIDATION=off 停用")
        return None
    try:
        from laap.consolidation import ConsolidationLoop
        _consolidation = ConsolidationLoop(psi=_psi_core)
        _consolidation.start()
        logger.info("😴 ConsolidationLoop 啟動 — Aris 會睡覺整理記憶了")
    except Exception as e:
        logger.warning(f"ConsolidationLoop 啟動失敗: {e}")
    return _consolidation


_status_writer = None


def ensure_status():
    """產品向可觀測層：定期寫 status.json。NEURALIS_STATUS=off 可關。"""
    global _status_writer
    if _status_writer is not None:
        return _status_writer
    if os.environ.get("NEURALIS_STATUS", "on").lower() in ("off", "0", "false"):
        return None
    try:
        from laap.status import StatusWriter
        _status_writer = StatusWriter()
        _status_writer.start()
    except Exception as e:
        logger.warning(f"StatusWriter 啟動失敗: {e}")
    return _status_writer


_quantum_writer = None


def ensure_quantum():
    """量子輸出 writer：真實 V12 dense kernel + gbrain 召回 → quantum_output.json。"""
    global _quantum_writer
    if _quantum_writer is not None:
        return _quantum_writer
    try:
        from laap.quantum_output import QuantumOutputWriter
        _quantum_writer = QuantumOutputWriter()
        _quantum_writer.start()
    except Exception as e:
        logger.warning(f"QuantumOutputWriter 啟動失敗: {e}")
    return _quantum_writer


def startup_all():
    """一次啟動所有系統。"""
    ensure_psi_defs()
    ensure_psi_core()
    ensure_tools()
    ensure_agency()
    ensure_consolidation()
    ensure_status()
    ensure_quantum()
    # 對話流攔截：必須在作者 app.router.add_post 之前 patch（startup 早於 runpy 起 API）
    try:
        from laap.chatflow import install as _install_chatflow
        _install_chatflow()
    except Exception as e:
        logger.warning(f"chatflow hook 跳過: {e}")
    return _bus, _psi_core, _tool_executor


def get_psi_core():
    return _psi_core

def get_tool_executor():
    return _tool_executor

def get_bus():
    return _bus

def get_agency():
    return _agency

def get_consolidation():
    return _consolidation