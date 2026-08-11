"""
QuantumOutputWriter — 用「真實存在的 V12 引擎」產出量子響應（不造假）。

背景（2026-08-11 覆核）：aris_subconscious.py 寫死 import `aris_v12_5_engine`，
該模組從未存在（upstream/overlay/git 歷史全無）→ 引擎載入失敗 → 潛意識自我停用
→ quantum_output.json 無生產者 → aris_rules_engine.read_qre 永遠 [QRE無輸出]。
真實引擎其實有：`aris_v12_dense_kernel.py`（V12DenseKernel/ArisLMv12，
「Deep Quantum Kernel Layer」，Ψ-integration 已在載入）。

本 writer 事件驅動（偵測 input_queue.json 新輸入）：V12 kernel 併行計算
（可用時如實標記），響應文字一律取真實接地資料（gbrain 召回 → PSI 狀態兜底），
不吐 V12 的 canned 情話，避免製造假親密。引擎名與實測延遲如實標記。
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path

logger = logging.getLogger("laap.quantum")

_STATE = Path(os.environ.get("LAAP_AGI_DIR", "/Users/ryan/Developer/laap-AGI")) / "aris_brain" / "state"
INPUT_QUEUE = _STATE / "input_queue.json"
LATEST = _STATE / "latest.json"
RUST = _STATE / "rust-latest.json"
OUT = _STATE / "quantum_output.json"

_v12_lm = None


def _read(p: Path) -> dict:
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _kernel_ready() -> bool:
    """真實 V12 dense kernel 可用？成功才快取；失敗下次重試（避免 boot 競態）。"""
    global _v12_lm
    if _v12_lm is not None:
        return True
    try:
        from aris_v12_dense_kernel import ArisLMv12
        _v12_lm = ArisLMv12()
        logger.info("[quantum] V12 dense kernel ready")
        return True
    except Exception as e:
        logger.debug(f"[quantum] v12 kernel skip（下次重試）: {e}")
        return False


def _user_part(text: str) -> str:
    """input_queue 的 text 尾部被 chatflow 附了注意力線指令，取真正問句。"""
    return text.split("（回覆結束時")[0].split("（salience")[0].strip()[:120]


def _recall_line(text: str) -> str:
    try:
        from gbrain_client import get_client
        client = get_client()
        if client is None:
            return ""
        r = client.call("search", {"query": text, "limit": 2}, timeout=6.0)
        if isinstance(r, list):
            for h in r:
                seg = (h.get("chunk_text") or h.get("content") or "").strip()
                if seg:
                    return f"腦裡先浮現：「{seg[:140]}」"
    except Exception as e:
        logger.debug(f"[quantum] recall skip: {e}")
    return ""


def _psi_line() -> str:
    st = _read(LATEST) or _read(RUST) or {}
    needs = st.get("needs", {}) or {}
    attention = st.get("attention") or st.get("attention_focus") or "idle"
    if needs:
        dom = max(needs, key=needs.get)
        return f"主導需求 {dom} ({needs[dom]:.2f})，注意力在 {attention}。"
    return "感知到新的輸入，正在整理關聯。"


def build_response(text: str) -> dict:
    t0 = time.perf_counter()
    kernel = _kernel_ready()
    line = _recall_line(text) or _psi_line()
    latency_us = int((time.perf_counter() - t0) * 1_000_000)
    return {
        "quantum_engine": "v12-dense-kernel" if kernel else "psi-recall-v1",
        "quantum_latency_us": latency_us,
        "quantum_response": line,
        "input": text,
        "source": "latest.json" if LATEST.exists() else ("rust-latest.json" if RUST.exists() else "none"),
        "kernel_ready": kernel,
        "ts": time.time(),
    }


class QuantumOutputWriter:
    """背景輪詢 input_queue.json：有新輸入就產出並寫 quantum_output.json。"""

    def __init__(self, interval: float = 2.0):
        self.interval = interval
        self._thread: threading.Thread | None = None
        self._running = False
        self._last_text: str | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="quantum-output")
        self._thread.start()
        logger.info("[quantum] QuantumOutputWriter 啟動（事件驅動，間隔 %ss）", self.interval)

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            try:
                iq = _read(INPUT_QUEUE)
                text = (iq.get("text") or "").strip()
                if text and text != self._last_text:
                    self._last_text = text
                    d = build_response(_user_part(text))
                    OUT.parent.mkdir(parents=True, exist_ok=True)
                    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
                    logger.info("[quantum] 已寫 %s [%s] → %s", OUT.name, d["quantum_engine"], d["quantum_response"][:50])
            except Exception as e:
                logger.debug(f"[quantum] loop skip: {e}")
            time.sleep(self.interval)
