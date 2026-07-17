#!/usr/bin/env python3
"""將 TaskSpec（來自 intention-convergence）注入 Aris 的任務佇列。

用法：
    from laap.goal_bridge import inject_task_spec
    inject_task_spec(task_spec_text)  # True=成功
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

logger = logging.getLogger("laap.goal_bridge")


def inject_task_spec(task_spec_text: str) -> bool:
    """解析 TaskSpec 文字區塊並設為 agency 目標。

    先嘗試直接設定 agency（同 process 情境），
    失敗則透過 Aris API 餵入（跨 process 情境）。

    接受 intention-convergence 技能輸出的 TaskSpec 格式：
      why: <目標說明>
      target_system: <系統>
      io_example: <範例>
      acceptance_tests: <驗收測試>

    回 True=已注入，False=全部失敗。
    """
    spec = _parse_spec(task_spec_text)

    # 方式 A：直接設定 agency（同 process）
    from laap.startup import get_agency
    ag = get_agency()
    if ag is not None:
        ag.set_goal(spec)
        logger.info(f"[goal_bridge] 直接注入成功: {spec['why'][:60]}")
        return True

    # 方式 B：透過 Aris API（跨 process）
    return _inject_via_api(spec)


def _parse_spec(task_spec_text: str) -> dict:
    why = re.search(r'[Ww]hy:\s*(.*?)(?:\n|$)', task_spec_text)
    target = re.search(r'[Tt]arget_[Ss]ystem:\s*(.*?)(?:\n|$)', task_spec_text)
    io = re.search(r'[Ii][Oo]_[Ee]xample:\s*(.*?)(?:\n|$)', task_spec_text)
    tests = re.search(r'[Aa]cceptance_[Tt]ests:\s*(.*?)(?:\n|$)', task_spec_text)
    return {
        "why": why.group(1).strip() if why else "",
        "target_system": target.group(1).strip() if target else "",
        "io_example": io.group(1).strip() if io else "",
        "acceptance_tests": tests.group(1).strip() if tests else "",
        "task_list": [
            {"idx": 0,
             "description": f"實作: {io.group(1).strip() if io else '依規格實作'}"},
            {"idx": 1,
             "description": f"驗證: {tests.group(1).strip() if tests else '執行驗證'}"},
        ],
    }


def _inject_via_api(spec: dict) -> bool:
    """透過 Aris API 餵入目標，讓 agency 在下次 _evaluate() 時拾取。"""
    import urllib.request
    import json as _json
    import os as _os
    goal_text = _json.dumps(spec, ensure_ascii=False)
    # 先寫到 task state 檔，讓 agency 的 _evaluate() 去讀
    state_path = "/tmp/aris-scream-task-state.json"
    state = {"goal_spec": spec.get("why", ""),
             "task_queue": spec.get("task_list", []),
             "task_index": 0, "goal_completed": False}
    with open(state_path, "w") as f:
        _json.dump(state, f)
    # 同時餵 Aris API，觸發 psi 更新
    payload = _json.dumps({
        "model": "laap-core",
        "messages": [
            {"role": "system",
             "content": "你收到了一個新目標。agency 會接手處理。"},
            {"role": "user",
             "content": f"新目標: {spec['why']}"},
        ],
        "max_tokens": 100,
    }).encode()
    api_url = "http://localhost:11546/v1/chat/completions"
    try:
        req = urllib.request.Request(
            api_url, data=payload,
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
        logger.info(f"[goal_bridge] API 注入成功: {spec['why'][:60]}")
        return True
    except Exception as e:
        logger.warning(f"[goal_bridge] API 注入失敗: {e}")
        return False


def inject_raw(why: str, task_descriptions: list[str]) -> bool:
    """直接注入目標（不需 TaskSpec 格式，供程式化呼叫）。"""
    from laap.startup import get_agency

    spec = {
        "why": why,
        "task_list": [
            {"idx": i, "description": desc}
            for i, desc in enumerate(task_descriptions)
        ],
    }
    ag = get_agency()
    if ag is None:
        return False
    ag.set_goal(spec)
    logger.info(f"[goal_bridge] 原始目標已注入: {why[:60]} ({len(task_descriptions)} tasks)")
    return True