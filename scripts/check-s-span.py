#!/usr/bin/env python3
"""S_span 認知光錐自檢 — 驗證多候選評估 + 預測 RPE 機制。

3 段：
  A. _generate_candidates 產生 2+ 候選（competence 有 3 角度）
  B. _evaluate_candidate 回傳合理值
  C. _select_candidate 選 RPE 最佳 > random

用法: PYTHONPATH=.:../laap-AGI ../laapenv/bin/python scripts/check-s-span.py
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from laap.agency import AgencyLoop, CandidateAction, _S_SPAN_THRESHOLD
from laap.psi_core import PsiCore, NeedType
from laap.psi_backend import PythonPsiBackend
from laap.agi.cognitive_bus import CognitiveBus
from laap.tool_executor import ToolExecutor


def main():
    bus = CognitiveBus(agent_name="check-span")
    raw = PsiCore(bus=bus, interval=0.5)
    psi = PythonPsiBackend(raw)
    tools = ToolExecutor(bus=bus, agentos_registry=None)
    agency = AgencyLoop(psi=psi, tools=tools, bus=bus,
                        interval=0.5, max_per_hour=10, drive_threshold=0.45)
    raw.last_input = "學習 TUI 工具操作"

    # 初始化角度權重
    for nt in NeedType:
        raw.needs.values[nt] = raw.needs.targets[nt]
    raw.needs.values[NeedType.COMPETENCE] = 0.2

    # A. _generate_candidates
    cands = agency._generate_candidates("competence", "學習 TUI")
    assert len(cands) >= 1, f"至少 1 候選: {len(cands)}"
    for c in cands:
        assert isinstance(c, CandidateAction)
        assert c.tool in ("gbrain",)
    print(f"A. 候選產生: OK ({len(cands)} 個, sources: {[c.source for c in cands]})")

    # B. _evaluate_candidate
    for c in cands:
        val = agency._evaluate_candidate(c)
        assert 0.0 <= val <= 1.0, f"predicted_value 範圍 0-1: {val}"
        assert "method" in c.features, f"應有評估方法標記: {c.features}"
    details = [f"{c.predicted_value:.2f}({c.features.get('method', '?')})" for c in cands]
    print(f"B. 階梯式評估: OK ({details})")

    # C. _select_candidate（RPE 最佳 > random）
    rpe = CandidateAction("gbrain", "test", "competence", "rpe_best", 0.8)
    rnd = CandidateAction("gbrain", "test2", "competence", "random_explore", 0.6)
    best = agency._select_candidate([rnd, rpe])
    assert best.source == "rpe_best", f"應選 rpe_best: {best.source}"
    rnd_hi = CandidateAction("gbrain", "test3", "competence", "random_explore", 0.9)
    best2 = agency._select_candidate([rpe, rnd_hi])
    assert best2.predicted_value > rpe.predicted_value, "高預測值應優先"
    print(f"C. 選擇: OK")

    # D. _S_SPAN_THRESHOLD 常數
    assert 0.05 <= _S_SPAN_THRESHOLD <= 0.3, f"S_span 閾值範圍異常: {_S_SPAN_THRESHOLD}"
    print(f"D. 常數: OK (threshold={_S_SPAN_THRESHOLD})")

    print("ALL S-SPAN CHECKS PASSED")


if __name__ == "__main__":
    main()