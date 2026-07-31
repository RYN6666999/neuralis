"""route → task_class 分類的三個性質。

背景（2026-07-31）：bridge 啟動時長期噴
`Scoring mapping unresolved routes: aris-channel, aris-request, aris-task, vision`。
它被讀成「主對話沒被 router 管、落 legacy path」，寫進了現況文件。實際不是：

  - `aris-channel/request/task` 在 agentos.json 裡的 tool 就是 bridge 自己 ——
    它們是傳輸層，不是動作類。沒有 task_class 是對的，硬塞才是憑空發明分類。
  - `vision` 是真的漏掉：它會呼叫 OpenAI GPT-4o，屬 network_call。
  - unresolved 也不等於沒閘：`classify_reversibility("unknown")` = escaping
    → lane=human，fail-closed。legacy_auto 只發生在 scoring 整個關掉時。

這三條測試把上面三件事釘住，避免下次又被 log 訊息誤導。
"""
import importlib.util
import logging
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "scripts" / "agentos-aris-bridge.py"

for _p in (_ROOT, _ROOT.parent / "laap-AGI", Path.home() / "agent-sandbox"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# bridge 只在 SCORING_ROUTER_ENABLED=1 時才 import scoring 那組模組，
# 而 _SCORING_ROUTER_ENABLED 是 import 期讀環境變數。不先設，整個模組
# 會載進來但 scoring 全關 → 測試 skip → 靜默假綠。
#
# 但 pytest 整個 session 是同一個 process：環境變數留著不還原，會害後面
# 才 import bridge 的 test_headroom_pipeline / test_headroom_bdd 也被打開
# scoring，於是 lane=human 擋掉執行、`_execute_by_route` 沒被呼叫而紅。
# （2026-07-31 真的踩過一次。）所以只在 exec_module 那一瞬間開，馬上還原。
_prev_scoring_env = os.environ.get("SCORING_ROUTER_ENABLED")
os.environ["SCORING_ROUTER_ENABLED"] = "1"
try:
    _spec = importlib.util.spec_from_file_location("bridge_under_test", _SRC)
    bridge = importlib.util.module_from_spec(_spec)
    sys.modules["bridge_under_test"] = bridge
    _spec.loader.exec_module(bridge)
finally:
    if _prev_scoring_env is None:
        os.environ.pop("SCORING_ROUTER_ENABLED", None)
    else:
        os.environ["SCORING_ROUTER_ENABLED"] = _prev_scoring_env

pytestmark = pytest.mark.skipif(
    not getattr(bridge, "_SCORING_IMPORT_OK", False),
    reason="scoring router 依賴（pydantic / agent-sandbox）不在此直譯器",
)


def test_vision_is_classified_as_network_call():
    """vision 會打 OpenAI GPT-4o，是對外呼叫，不是 unknown。"""
    assert bridge._task_class_for_route("vision") == "network_call"


def test_vision_classification_does_not_widen_its_lane():
    """補分類不等於放行 —— network_call 是 escaping，lane 仍是 human。"""
    from router.reversibility import classify_reversibility

    assert classify_reversibility("network_call") == "escaping"


def test_unknown_task_class_fails_closed_to_human():
    """unresolved route 不是漏網。這條掉了，上面兩條的安全前提就沒了。"""
    from contracts.verdict_v2 import ActionRequest
    from router.reversibility import classify_reversibility
    from router.scoring import score

    assert classify_reversibility("unknown") == "escaping"
    verdict = score(ActionRequest(
        action_id="test-unknown",
        task_class="unknown",
        declared_reversibility="escaping",
        cost_estimate={"tokens": 100},
    ))
    assert verdict.lane == "human"


def test_transport_routes_are_not_reported_as_unresolved(caplog, monkeypatch):
    """傳輸層 route 不進 unresolved 名單 —— 它們沒有動作可分類。"""
    monkeypatch.setattr(bridge, "_SCORING_ROUTER_ENABLED", True)
    monkeypatch.setattr(bridge, "_SCORING_IMPORT_OK", True)
    monkeypatch.setattr(
        bridge, "_ROUTES",
        {k: "agentos-aris-bridge" for k in bridge._TRANSPORT_ROUTES}
        | {"vision": "image-preprocessor"},
    )

    with caplog.at_level(logging.WARNING):
        bridge._validate_scoring_mappings()

    unresolved = [r.message for r in caplog.records if "unresolved routes" in r.message]
    assert unresolved == [], f"傳輸層不該被當成漏分類: {unresolved}"


def test_genuinely_unmapped_route_is_still_reported(caplog, monkeypatch):
    """真的漏掉的 route 還是要叫 —— 別把警報一起關掉了。"""
    monkeypatch.setattr(bridge, "_SCORING_ROUTER_ENABLED", True)
    monkeypatch.setattr(bridge, "_SCORING_IMPORT_OK", True)
    monkeypatch.setattr(bridge, "_ROUTES", {"brand-new-thing": "some-tool"})

    with caplog.at_level(logging.WARNING):
        bridge._validate_scoring_mappings()

    assert any("brand-new-thing" in r.message for r in caplog.records)
