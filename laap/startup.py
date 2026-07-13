"""
neuralis startup: PsiCore 啟動器 (延遲初始化)
==============================================
用法:
    from laap.startup import ensure_psi_core
    psi = ensure_psi_core()  # 只第一次會實際建立
"""
import logging
logger = logging.getLogger("laap.startup")
_psi_core = None


def ensure_psi_core():
    global _psi_core
    if _psi_core is not None:
        return _psi_core
    try:
        from laap.psi_core import PsiCore
        from aris_brain.psi_core_bridge import get_global_bus
        bus = get_global_bus()
        _psi_core = PsiCore(bus=bus, interval=1.0)
        _psi_core.start()
        logger.info("❤️ PsiCore 啟動 — Aris 有心跳了")
    except Exception as e:
        logger.warning(f"PsiCore 啟動失敗: {e}")
    return _psi_core


def get_psi_core():
    return _psi_core
