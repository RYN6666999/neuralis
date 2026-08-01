"""RustPsiBackend 讀取面對拍測試。

背景（2026-08-01）：這個 class 原本只有 start/healthy/stop。有人在
scripts/start.sh 開 `NEURALIS_PSI_BACKEND=rust`，API 啟動就
`AttributeError: 'RustPsiBackend' object has no attribute 'get_state'`
→ :11546 全掛 → scream 顯示 provider.connection_error。

這組測試釘住的不是「Rust 引擎算得對不對」（那是 cargo test 的事），
是**「Python 這側拿得到、形狀跟 PythonPsiBackend 對得上、拿不到時不會炸」**。
沒有這組，那個 flag 就不該再被打開。

刻意不測的：daemon 真的跑起來（要 cargo build，屬 e2e），
以及數值語意正確性（要 Python↔Rust 同輸入對拍，需 B2 輸入通道，尚未存在）。
"""
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from laap.psi_backend import RustPsiBackend  # noqa: E402

_NEEDS = ("certainty", "competence", "autonomy", "relatedness", "growth")


def _native(ts=None):
    """psi-daemon 的原生 schema（neuralis-rust-psi/v1）。"""
    return {
        "ts": time.time() if ts is None else ts,
        "tick": 42,
        "needs": {n: 0.5 for n in _NEEDS} | {"competence": 0.3},
        "drives": {n: 0.1 for n in _NEEDS} | {"competence": 0.7},
        "affect": {"pleasure": 0.4, "arousal": 0.6, "dominance": 0.5,
                   "social": 0.3, "stress": 0.2},
        "endorphin": -0.25,
        "attention": "task",
    }


@pytest.fixture
def backend(tmp_path):
    f = tmp_path / "rust-latest.json"
    f.write_text(json.dumps(_native()), encoding="utf-8")
    return RustPsiBackend(state_file=str(f)), f


class TestReadPath:
    def test_get_state_has_contract_keys(self, backend):
        b, _ = backend
        st = b.get_state()
        for k in ("needs", "dominant_need", "dominant_drive",
                  "emotion", "attention", "tick", "affective"):
            assert k in st, f"缺 {k}"

    def test_needs_entries_have_three_fields(self, backend):
        b, _ = backend
        for name, entry in b.get_state()["needs"].items():
            assert set(entry) == {"current", "target", "drive"}, name

    def test_dominant_need_is_argmax_of_drives(self, backend):
        b, _ = backend
        assert b.get_dominant_need() == "competence"

    def test_get_drives_agrees_with_get_state(self, backend):
        """兩條路拿同一份數字，不一致就是接線接錯（鐵律二：換一條路驗）。"""
        b, _ = backend
        drives = b.get_drives()
        from_state = {n: e["drive"] for n, e in b.get_state()["needs"].items()}
        assert drives == from_state

    def test_cognitive_bias_agrees_with_get_state(self, backend):
        b, _ = backend
        assert b.get_cognitive_bias() == b.get_state()["affective"]["biases"]

    def test_attention_uppercased(self, backend):
        b, _ = backend
        assert b.get_state()["attention"] == "TASK"


class TestQuirk1:
    """QUIRK-1：兩個表現層方法讀不同的 valence 欄，這是刻意保留的既有行為。"""

    def test_state_label_uses_raw_valence(self, backend):
        """label 走 _STATE_LABEL_MAP，raw_valence（=affect.pleasure）決定正負面。"""
        b, _ = backend
        # dominant=competence、raw_valence=0.4（正）→ 正面那一支
        assert b.get_state_label() == "confident.helpful"

    def test_injection_shape_is_the_three_string_contract(self, backend):
        """injection 回的是 state_label/state_snippet/state_tuple 三個字串。

        我第一版斷言它回 {"valence": ...} —— 那是我自己想像的形狀，
        不是這個 class 的契約。測試要記真行為，不是記我的假設。
        """
        inj = b_inj = backend[0].format_state_injection()
        assert set(inj) == {"state_label", "state_snippet", "state_tuple"}
        assert isinstance(b_inj["state_snippet"], str)


class TestDegradation:
    def test_missing_file_falls_back_to_default_not_crash(self, tmp_path):
        b = RustPsiBackend(state_file=str(tmp_path / "nope.json"))
        st = b.get_state()
        assert st["dominant_need"] == "competence"   # 預設值
        assert st["tick"] == 0

    def test_stale_file_falls_back_to_cache(self, backend):
        b, f = backend
        fresh = b.get_state()["tick"]
        f.write_text(json.dumps(_native(ts=time.time() - 999)), encoding="utf-8")
        assert b.get_state()["tick"] == fresh, "過期應退回快取而不是讀進來"

    def test_corrupt_json_does_not_crash(self, backend):
        b, f = backend
        b.get_state()
        f.write_text("{ not json", encoding="utf-8")
        assert b.get_state()["tick"] == 42


class TestWritePathIsB2Fifo:
    """寫入面**不是** no-op —— 它把事件寫進 daemon 的 FIFO（B2 通道）。

    class docstring 原本寫「write methods are no-ops」，那是舊的。
    這幾條把真行為釘住，免得下一個人（像我今天）照 docstring 推論就寫錯。
    """

    def test_satisfy_writes_mapped_event_to_fifo(self, backend, monkeypatch):
        b, _ = backend
        sent = []
        monkeypatch.setattr(b, "_write_event", lambda n, i=1.0: sent.append((n, i)))
        b.satisfy("competence", 0.5, "test")
        assert sent and sent[0][0] == "CompetenceSuccess"

    def test_satisfy_unknown_need_writes_nothing(self, backend, monkeypatch):
        b, _ = backend
        sent = []
        monkeypatch.setattr(b, "_write_event", lambda n, i=1.0: sent.append(n))
        b.satisfy("no_such_need", 0.5, "test")
        assert sent == []

    def test_post_affective_event_returns_true(self, backend):
        """未知事件也回 True —— 契約如此（沒有呼叫端真的在看回傳值）。"""
        b, _ = backend
        assert b.post_affective_event("praise", 1.0) is True

    def test_missing_fifo_does_not_raise(self, backend):
        """daemon 沒起來時 FIFO 不存在，寫入必須靜靜失敗而不是炸掉呼叫端。"""
        b, _ = backend
        b._write_event("CompetenceSuccess", 1.0)   # 不應拋例外

    def test_process_input_records_last_input_only(self, backend):
        b, _ = backend
        b.process_input("你好")
        assert b.get_last_input() == "你好"

    def test_process_input_filters_system_injected(self, backend):
        b, _ = backend
        b.process_input("你好")
        b.process_input("<system-reminder>xx</system-reminder>")
        assert b.get_last_input() == "你好", "系統注入不該蓋掉真人輸入"


class TestContractConformance:
    """對契約 schema 驗，不對 PythonPsiBackend 驗。

    第一版是拿 PythonPsiBackend 建一份 state 來比對，但它 import numpy，
    在跑 pytest 的直譯器裡不一定有 → 測試 skip → 靜默假綠。
    改成對 `docs/contracts/psi-state.schema.json` 驗有兩個好處：
      · 不依賴環境，永遠跑得起來
      · 比互相對拍更強 —— 兩邊都對契約負責，而不是對彼此負責
        （兩邊一起偏離契約時，互相對拍會全綠）
    """

    def test_get_state_satisfies_contract_required_keys(self, backend):
        schema = json.loads(
            (Path(__file__).resolve().parents[1]
             / "docs/contracts/psi-state.schema.json").read_text(encoding="utf-8"))
        required = set(schema["required"])
        b, _ = backend
        missing = required - set(b.get_state())
        assert not missing, f"不符契約 required，呼叫端會炸: {missing}"

    def test_no_unknown_top_level_keys(self, backend):
        """多給沒關係，但不能是打錯字的欄位名。"""
        schema = json.loads(
            (Path(__file__).resolve().parents[1]
             / "docs/contracts/psi-state.schema.json").read_text(encoding="utf-8"))
        allowed = set(schema["properties"])
        b, _ = backend
        extra = set(b.get_state()) - allowed
        assert not extra, f"契約沒有這些欄位（打錯字？）: {extra}"
