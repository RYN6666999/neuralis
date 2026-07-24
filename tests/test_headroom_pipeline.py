"""E2E tests for the Headroom compression pipeline in AgentOS Aris Bridge.

Tests the full pipeline (classify → execute → compress → gate → log)
with mocked Aris channel — no running Headroom proxy required.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import ANY, MagicMock, call, patch

# ── Load the bridge module from its source path ─────────────────────

_SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
_BRIDGE_PATH = os.path.join(_SCRIPTS_DIR, "agentos-aris-bridge.py")

spec = importlib.util.spec_from_file_location("agentos_aris_bridge", _BRIDGE_PATH)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

# Ensure the module is importable by name for @patch targets
sys.modules["agentos_aris_bridge"] = bridge


# ── Helpers ─────────────────────────────────────────────────────────

_SMALL_TEXT = "x" * 100  # < HEADROOM_MIN_COMPRESS_SIZE (2000)
_LARGE_TEXT = "x" * 5000  # > HEADROOM_MIN_COMPRESS_SIZE


def _make_mock_response(status: int = 200, data: dict | None = None) -> MagicMock:
    """Create a mock urllib.response object."""
    mock = MagicMock()
    mock.status = status
    mock.read.return_value = json.dumps(data or {}).encode()
    return mock


def _reset_module_state() -> None:
    """Reset module-level mutable state between tests."""
    bridge.HEADROOM_CTR = 0
    bridge.HEADROOM_PROXY_LAUNCHED = False
    bridge._learn_fail_count = 0
    bridge._learn_last_run = 0.0


# ── 1. TestCompressWithHeadroom ────────────────────────────────────

class TestCompressWithHeadroom(unittest.TestCase):
    """Unit tests for _compress_with_headroom()."""

    def setUp(self):
        _reset_module_state()

    def test_skipped_too_small(self):
        """Text < 2000 bytes returns skipped=True with reason 'too_small'."""
        result = bridge._compress_with_headroom(_SMALL_TEXT)
        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "too_small")
        self.assertEqual(result["compressed"], _SMALL_TEXT)

    @patch("agentos_aris_bridge.urllib.request.urlopen")
    def test_compress_success(self, mock_urlopen: MagicMock):
        """Mock HTTP returns compressed response; verify tokens/ratio/ccr."""
        mock_resp = _make_mock_response(200, {
            "messages": [{"content": "compressed x"}],
            "tokens_before": 500,
            "tokens_after": 200,
            "compression_ratio": 0.4,
            "ccr_hashes": ["abc123def456"],
        })
        mock_urlopen.return_value = mock_resp

        result = bridge._compress_with_headroom(_LARGE_TEXT)

        self.assertFalse(result["skipped"])
        self.assertEqual(result["compressed"], "compressed x")
        self.assertGreater(result["tokens_before"], result["tokens_after"])
        self.assertEqual(result["tokens_before"], 500)
        self.assertEqual(result["tokens_after"], 200)
        self.assertEqual(result["tokens_saved"], 300)
        self.assertEqual(result["ratio"], 0.4)
        self.assertEqual(result["ccr_hash"], "abc123def456")
        self.assertEqual(result["ctr"], 1)

        # Verify the request was built correctly
        mock_urlopen.assert_called_once()
        call_args = mock_urlopen.call_args[0][0]
        self.assertIsInstance(call_args, bridge.urllib.request.Request)
        self.assertEqual(call_args.full_url, bridge.HEADROOM_COMPRESS_URL)
        self.assertEqual(call_args.headers.get("Content-type"), "application/json")
        # Verify payload
        payload = json.loads(call_args.data.decode())
        self.assertEqual(payload["model"], "bridge-compress")
        self.assertEqual(payload["messages"][0]["content"], _LARGE_TEXT)

    @patch("agentos_aris_bridge.urllib.request.urlopen")
    def test_proxy_unreachable(self, mock_urlopen: MagicMock):
        """urlopen raises exception → skipped=True with error reason."""
        mock_urlopen.side_effect = ConnectionError("proxy refused")

        result = bridge._compress_with_headroom(_LARGE_TEXT)

        self.assertTrue(result["skipped"])
        self.assertIn("proxy refused", result["reason"])

    @patch("agentos_aris_bridge.urllib.request.urlopen")
    def test_http_error(self, mock_urlopen: MagicMock):
        """HTTP 503 → skipped=True with reason 'http_503'."""
        mock_resp = _make_mock_response(503)
        mock_urlopen.return_value = mock_resp

        result = bridge._compress_with_headroom(_LARGE_TEXT)

        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "http_503")


# ── 2. TestCompressStage ───────────────────────────────────────────

class TestCompressStage(unittest.TestCase):
    """Unit tests for _compress_stage()."""

    def setUp(self):
        _reset_module_state()

    def test_failed_execution_skips(self):
        """success=False result passes through unchanged."""
        result = {"success": False, "error": "something broke"}
        got = bridge._compress_stage(result, "task", "code")
        self.assertIs(got, result)
        self.assertNotIn("_original_output", got)
        self.assertNotIn("_headroom", got)

    @patch("agentos_aris_bridge._compress_with_headroom")
    def test_small_output_skips(self, mock_compress: MagicMock):
        """Output < 2000 bytes → no compression attempted."""
        result = {"success": True, "output": _SMALL_TEXT}
        got = bridge._compress_stage(result, "task", "code")
        self.assertIs(got, result)
        mock_compress.assert_not_called()

    @patch("agentos_aris_bridge._compress_with_headroom")
    def test_large_output_compressed(self, mock_compress: MagicMock):
        """Output > 2000 bytes → _original_output and _headroom set."""
        mock_compress.return_value = {
            "compressed": "compressed result",
            "skipped": False,
            "tokens_before": 800,
            "tokens_after": 300,
            "tokens_saved": 500,
            "ratio": 0.375,
            "ccr_hash": "ccr123",
            "ctr": 1,
        }
        result = {"success": True, "output": _LARGE_TEXT}
        got = bridge._compress_stage(result, "task", "code")

        self.assertEqual(got["output"], "compressed result")
        self.assertEqual(got["_original_output"], _LARGE_TEXT)
        self.assertEqual(got["_original_size"], len(_LARGE_TEXT))
        self.assertEqual(got["_headroom"]["tokens_before"], 800)
        self.assertEqual(got["_headroom"]["tokens_saved"], 500)
        self.assertEqual(got["_headroom"]["ccr_hash"], "ccr123")
        mock_compress.assert_called_once_with(_LARGE_TEXT, content_type=ANY)

    @patch("agentos_aris_bridge._compress_with_headroom")
    def test_content_type_routing(self, mock_compress: MagicMock):
        """Verify correct type_hints for each route key."""
        mock_compress.return_value = {
            "compressed": "x", "skipped": False,
            "tokens_before": 10, "tokens_after": 5,
            "tokens_saved": 5, "ratio": 0.5,
            "ccr_hash": "", "ctr": 1,
        }
        output = "x" * 3000
        base = {"success": True, "output": output}

        pairs = [
            ("code", "json_code_search"),
            ("research", "web_search_results"),
            ("read", "source_code_file"),
            ("bash", "shell_output"),
        ]
        for route_key, expected_type in pairs:
            mock_compress.reset_mock()
            bridge._compress_stage(dict(base), "task", route_key)
            mock_compress.assert_called_once_with(output, content_type=expected_type)


# ── 3. TestFailureTracking ─────────────────────────────────────────

class TestFailureTracking(unittest.TestCase):
    """Unit tests for _track_failure() and _headroom_learn_async()."""

    def setUp(self):
        _reset_module_state()
        # Ensure learn is enabled
        bridge.HEADROOM_LEARN_ENABLED = True

    @patch("agentos_aris_bridge.subprocess.Popen")
    @patch("agentos_aris_bridge.time.time")
    def test_failure_tracking_threshold(self, mock_time: MagicMock, mock_popen: MagicMock):
        """5 failures trigger learn; count resets to 0."""
        mock_time.return_value = 1000000.0  # far past last_run (0.0)

        for i in range(5):
            bridge._track_failure("code", f"error #{i+1}")

        # After 5 failures, learn should have been triggered
        mock_popen.assert_called_once()
        call_args = mock_popen.call_args[0][0]
        self.assertEqual(call_args[0], "headroom")
        self.assertEqual(call_args[1], "learn")
        self.assertEqual(bridge._learn_fail_count, 0)  # reset

    @patch("agentos_aris_bridge.subprocess.Popen")
    def test_failure_tracking_below_threshold(self, mock_popen: MagicMock):
        """4 failures do NOT trigger learn."""
        for i in range(4):
            bridge._track_failure("code", f"error #{i+1}")

        mock_popen.assert_not_called()
        self.assertEqual(bridge._learn_fail_count, 4)

    @patch("agentos_aris_bridge.subprocess.Popen")
    def test_learn_disabled(self, mock_popen: MagicMock):
        """HEADROOM_LEARN_ENABLED=False → no tracking, no learn."""
        bridge.HEADROOM_LEARN_ENABLED = False

        for i in range(10):
            bridge._track_failure("code", f"error #{i+1}")

        mock_popen.assert_not_called()

    @patch("agentos_aris_bridge.subprocess.Popen")
    @patch("agentos_aris_bridge.time.time")
    def test_learn_interval_throttling(self, mock_time: MagicMock, mock_popen: MagicMock):
        """Learn ran recently → 5 failures throttle (skip)."""
        now = 1000000.0
        bridge._learn_last_run = now - 1  # 1 second ago
        mock_time.return_value = now

        for i in range(5):
            bridge._track_failure("code", f"error #{i+1}")

        # 5 failures, but last_run was 1s ago (< 3600s interval)
        # and _learn_fail_count (5) < 15, so throttled
        mock_popen.assert_not_called()

    @patch("agentos_aris_bridge.subprocess.Popen")
    @patch("agentos_aris_bridge.time.time")
    def test_learn_forced_high_failure(self, mock_time: MagicMock, mock_popen: MagicMock):
        """15 failures override throttle → learn triggered."""
        now = 1000000.0
        bridge._learn_last_run = now - 1  # 1 second ago (within interval)
        mock_time.return_value = now

        for i in range(15):
            bridge._track_failure("code", f"error #{i+1}")

        # 15 failures >= HEADROOM_LEARN_FAIL_THRESHOLD * 3 (15)
        # so throttle is overridden
        mock_popen.assert_called_once()
        self.assertEqual(bridge._learn_fail_count, 0)  # reset


# ── 4. TestRouteClassification ─────────────────────────────────────

class TestRouteClassification(unittest.TestCase):
    """Unit tests for _classify_by_route()."""

    @classmethod
    def setUpClass(cls):
        """Build keyword routes once before any test in this class."""
        bridge._build_keyword_routes()

    def test_sports_route(self):
        self.assertEqual(bridge._classify_by_route("NBA scores tonight"), "sports")
        self.assertEqual(bridge._classify_by_route("英超賽程"), "sports")
        self.assertEqual(bridge._classify_by_route("F1 race results"), "sports")

    def test_code_route(self):
        self.assertEqual(bridge._classify_by_route("analyze repo architecture"), "code")
        self.assertEqual(bridge._classify_by_route("查看程式碼結構"), "code")
        self.assertEqual(bridge._classify_by_route("implement the feature"), "code")

    def test_research_route(self):
        self.assertEqual(bridge._classify_by_route("search for quantum computing"), "research")
        self.assertEqual(bridge._classify_by_route("查詢最新的AI研究"), "research")
        self.assertEqual(bridge._classify_by_route("research black holes"), "research")

    def test_unknown_route(self):
        self.assertEqual(bridge._classify_by_route("hello world"), "unknown")
        self.assertEqual(bridge._classify_by_route("good morning"), "unknown")


# ── 5. TestGateScan ────────────────────────────────────────────────

class TestGateScan(unittest.TestCase):
    """Unit tests for _gate_scan()."""

    def test_block_dangerous_pattern(self):
        """Output containing 'rm -rf /' is blocked with success=False."""
        result = {"success": True, "output": "run: rm -rf /"}
        got = bridge._gate_scan(result, "task")
        self.assertFalse(got["success"])
        self.assertIn("gate blocked", got["error"])
        self.assertNotIn("output", got)

    def test_clean_passes_through(self):
        """Clean output passes through unchanged."""
        result = {"success": True, "output": "everything is fine"}
        got = bridge._gate_scan(result, "task")
        self.assertTrue(got["success"])
        self.assertEqual(got["output"], "everything is fine")


# ── 6. TestPipeline ────────────────────────────────────────────────

class TestPipeline(unittest.TestCase):
    """Integration tests for process_entry()."""

    def setUp(self):
        _reset_module_state()
        bridge._build_keyword_routes()

    @patch("agentos_aris_bridge._execute_by_route")
    @patch("agentos_aris_bridge._compress_with_headroom")
    @patch("agentos_aris_bridge._lookup_brain_context")
    @patch("agentos_aris_bridge._log_to_agentsview")
    def test_full_pipeline_compress(
        self,
        mock_log: MagicMock,
        mock_brain: MagicMock,
        mock_compress: MagicMock,
        mock_exec: MagicMock,
    ):
        """Large content → route + compress + gate all run."""
        mock_brain.return_value = ""
        mock_exec.return_value = {"success": True, "output": _LARGE_TEXT}
        mock_compress.return_value = {
            "compressed": "compressed result",
            "skipped": False,
            "tokens_before": 800,
            "tokens_after": 300,
            "tokens_saved": 500,
            "ratio": 0.375,
            "ccr_hash": "ccr123",
            "ctr": 1,
        }

        entry = {
            "id": "test-1",
            "type": "request",
            "direction": "aris→scream",
            "content": "search for AI research",
            "ts": 1234567890,
        }
        response = bridge.process_entry(entry)

        # Verify route classification
        self.assertEqual(response["context"]["route"], "research")

        # Verify execute was called
        mock_exec.assert_called_once_with("research", "search for AI research")

        # Verify compress was called (large output)
        mock_compress.assert_called_once()

        # Verify headroom metadata in response
        self.assertIsNotNone(response["context"]["headroom"])
        self.assertEqual(response["context"]["headroom"]["tokens_before"], 800)

        # Verify success
        self.assertTrue(response["context"]["success"])

        # Verify log was called
        mock_log.assert_called_once()

    @patch("agentos_aris_bridge._execute_by_route")
    @patch("agentos_aris_bridge._compress_with_headroom")
    @patch("agentos_aris_bridge._lookup_brain_context")
    @patch("agentos_aris_bridge._log_to_agentsview")
    def test_full_pipeline_small(
        self,
        mock_log: MagicMock,
        mock_brain: MagicMock,
        mock_compress: MagicMock,
        mock_exec: MagicMock,
    ):
        """Small content → compression skipped."""
        mock_brain.return_value = ""
        mock_exec.return_value = {"success": True, "output": _SMALL_TEXT}

        entry = {
            "id": "test-2",
            "type": "request",
            "direction": "aris→scream",
            "content": "hello world",
            "ts": 1234567890,
        }
        response = bridge.process_entry(entry)

        # Verify route is unknown
        self.assertEqual(response["context"]["route"], "unknown")

        # Verify compress was NOT called (small output)
        mock_compress.assert_not_called()

        # Verify no headroom metadata
        self.assertIsNone(response["context"]["headroom"])

        # Verify success
        self.assertTrue(response["context"]["success"])
        mock_log.assert_called_once()


if __name__ == "__main__":
    unittest.main()