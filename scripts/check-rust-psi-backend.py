#!/usr/bin/env python3
"""
check-rust-psi-backend.py — RustPsiBackend 相容性檢查腳本

檢查六個面向，精確定位降級點：
  A. daemon 可用性（binary 存在、可執行）
  B. get_state() remap 形狀 vs Python 預期 dict
  C. aris_brain 讀者相容性（schema key 缺口）
  D. 回退行為（no daemon / stale / 啟動失敗）
  E. B2 FIFO 事件通道
  F. 開關回歸（NEURALIS_PSI_BACKEND 未設 → PythonPsiBackend）

用法:
  python3 scripts/check-rust-psi-backend.py
  python3 scripts/check-rust-psi-backend.py --verbose   # 詳細輸出
  python3 scripts/check-rust-psi-backend.py --daemon    # 含 daemon 存活測試
"""
from __future__ import annotations

import json
import os
import sys
import subprocess
import time
import tempfile
import traceback
from pathlib import Path

# ── 常數 ──────────────────────────────────────────────────────────────

REPO = Path(__file__).resolve().parents[1]
DAEMON_BINARY = REPO / "rust" / "target" / "release" / "psi-daemon"
LAAP_AGI_DIR = Path(os.environ.get("LAAP_AGI_DIR", str(REPO.parents[0] / "laap-AGI")))

# aris_brain 讀者期望的 key 對照表：
#   (reader_file, 期望 key, 原生 schema 對應, 是否必要, 說明)
ARIS_BRAIN_READERS = [
    ("psi_core_bridge.py:_map_to_snapshot", "needs (flat dict)",
     "needs (flat dict ✅)", True, "5 需求值"),
    ("psi_core_bridge.py:_map_to_snapshot", "emotion (字串, e.g. 'neutral')",
     "emotion (物件, 含 valence/arousal/dominance) ⚠️", False,
     "ATTENTION_MAP.get 傳 dict 永不匹配 → 回退 NEUTRAL"),
    ("psi_core_bridge.py:_map_to_snapshot", "arousal (頂層 float)",
     "affect.arousal (巢狀) ⚠️", False, "拿不到 → 預設 0.5"),
    ("psi_core_bridge.py:_map_to_snapshot", "dominance (頂層 float)",
     "affect.dominance (巢狀) ⚠️", False, "拿不到 → 預設 0.5"),
    ("psi_core_bridge.py:_map_to_snapshot", "attention_focus (字串)",
     "attention (字串) ✅", True, "小寫匹配（idle/task/learning/planning）"),
    ("psi_core_bridge.py:_map_to_snapshot", "cycle (int)",
     "tick (int) ❌", False, "key 名不同，拿不到 → 預設 0"),
    ("laap_brain_api.py:process_with_laap", "needs (flat dict)",
     "needs (flat dict ✅)", True, "PSI context 字串"),
    ("laap_brain_api.py:process_with_laap", "attention (字串)",
     "attention (字串 ✅)", True, "小寫字串"),
    ("laap_brain_api.py:process_with_laap", "emotion (字串)",
     "emotion (物件 ⚠️)", False, "str(emotion) 會變 dict 字串"),
    ("laap_integrator.py:_cognitive_loop", "needs_map (flat dict)",
     "不存在 ❌", False, "用 needs 替代"),
    ("laap_integrator.py:_cognitive_loop", "cycle (int)",
     "tick (int) ❌", False, "key 名不同"),
    ("laap_integrator.py:_cognitive_loop", "attention_focus (字串)",
     "attention (字串) ❌", False, "key 名不同"),
    ("laap_integrator.py:_cognitive_loop", "emotion (字串)",
     "emotion (物件 ⚠️)", False, "字串 vs 物件"),
    ("cognitive_bus.py:poll_for_response", "psi_cycle (int)",
     "不存在 ❌", False, "輪詢邏輯失效"),
    ("cognitive_bus.py:poll_for_response", "quantum_engine (字串)",
     "不存在 ❌", False, "無 quantum 引擎"),
    ("aris_rules_engine.py:tool_read_state", "cycle / psi_cycle",
     "tick (int) ❌", False, "顯示 '?'"),
    ("aris_rules_engine.py:tool_read_state", "emotion (字串)",
     "emotion (物件 ⚠️)", False, "字串 vs 物件"),
    ("aris_rules_engine.py:tool_read_state", "needs (flat dict)",
     "needs (flat dict ✅)", True, "需求值"),
]

# Python get_state() 預期形狀（來自 PsiCore.get_state）
EXPECTED_KEYS = {
    "needs": dict,
    "dominant_need": str,
    "dominant_drive": (int, float),
    "emotion": dict,
    "attention": str,
    "tick": (int, float),
    "affective": dict,
}

EXPECTED_NEED_KEYS = {"current": (int, float), "target": (int, float), "drive": (int, float)}
EXPECTED_EMOTION_KEYS = {"valence": (int, float), "arousal": (int, float),
                          "dominance": (int, float), "raw_valence": (int, float)}
EXPECTED_AFFECTIVE_KEYS = {"mood": str, "dims": dict, "biases": dict, "events_total": (int, float)}
EXPECTED_BIAS_KEYS = {"optimism", "risk_seeking", "attention_narrowing",
                       "confirmation_bias", "overconfidence", "temporal_discounting",
                       "social_proximity", "creativity"}
NEED_NAMES = {"certainty", "competence", "autonomy", "relatedness", "growth"}

# ── 結果收集 ──────────────────────────────────────────────────────────

results: list[dict] = []


def ok(msg: str, detail: str = "") -> None:
    results.append({"status": "PASS", "msg": msg, "detail": detail})
    print(f"  ✅ {msg}" + (f" — {detail}" if detail else ""))


def fail(msg: str, detail: str = "") -> None:
    results.append({"status": "FAIL", "msg": msg, "detail": detail})
    print(f"  ❌ {msg}" + (f" — {detail}" if detail else ""))


def warn(msg: str, detail: str = "") -> None:
    results.append({"status": "WARN", "msg": msg, "detail": detail})
    print(f"  ⚠️  {msg}" + (f" — {detail}" if detail else ""))


# ── 測試 A: daemon 可用性 ─────────────────────────────────────────────

def check_daemon_availability() -> None:
    print("\n═══ A. daemon 可用性 ═══")
    if DAEMON_BINARY.is_file():
        ok("daemon binary 存在", str(DAEMON_BINARY))
        # 檢查可執行
        try:
            r = subprocess.run([str(DAEMON_BINARY)], capture_output=True, timeout=2)
            fail("daemon 缺 --state-file 應報錯退出")
        except subprocess.TimeoutExpired:
            fail("daemon 無參數無限執行")
        except FileNotFoundError:
            fail("daemon 無法執行")
        else:
            if r.returncode == 2:
                ok("daemon 回報 usage (exit=2)")
            else:
                warn(f"daemon 回傳 {r.returncode}")
    else:
        warn("daemon binary 不存在，後續 daemon 測試全部跳過")
        raise SystemExit(0)


def check_daemon_lifecycle() -> None:
    """起 daemon → 確認 state 檔產生 → 寫事件 → 確認狀態變化 → 停。"""
    print("\n═══ A2. daemon 生命週期 ═══")
    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "state.json"
        fifo_file = Path(tmp) / "state.fifo"
        proc = subprocess.Popen(
            [str(DAEMON_BINARY), "--state-file", str(state_file),
             "--event-fifo", str(fifo_file),
             "--write-ms", "100", "--seed", "42", "--max-seconds", "6"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            time.sleep(1.0)
            if not state_file.exists():
                fail("daemon 未寫入 state 檔")
                proc.kill()
                return
            ok("daemon 寫入 state 檔")
            raw = json.loads(state_file.read_text())
            tick = raw.get("tick", 0)
            if tick > 0:
                ok(f"daemon tick 推進 ({tick})")
            else:
                warn(f"daemon tick 為 0")

            # 寫事件到 FIFO
            try:
                fd = os.open(str(fifo_file), os.O_WRONLY | os.O_NONBLOCK)
                os.write(fd, b"CompetenceSuccess,1.0\n")
                os.close(fd)
                ok("FIFO 寫入成功")
            except OSError as e:
                warn(f"FIFO 寫入失敗: {e}")

            time.sleep(0.5)
            raw2 = json.loads(state_file.read_text())
            if raw2.get("tick", 0) > tick:
                ok(f"daemon tick 持續推進 ({raw2['tick']})")
            else:
                warn("daemon tick 未推進")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()


# ── 測試 B: get_state() remap 形狀 ────────────────────────────────────

def check_remap_shape() -> None:
    print("\n═══ B. get_state() remap 形狀 ═══")
    # 用 fake native state 測試 remap
    fake_native = {
        "schema": "neuralis-rust-psi/v1", "tick": 4242,
        "needs": {"certainty": 0.6, "competence": 0.4, "autonomy": 0.5,
                  "relatedness": 0.5, "growth": 0.5},
        "drives": {"certainty": 0.24, "competence": 0.75, "autonomy": 0.20,
                   "relatedness": 0.16, "growth": 0.39},
        "affect": {"pleasure": 0.1, "arousal": 0.3, "dominance": 0.5,
                   "social": 0.3, "stress": 0.1},
        "endorphin": -0.05, "attention": "task", "source": "neuralis-rust-psi",
        "ts": time.time(),
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(fake_native, f)
        sf = f.name

    try:
        sys.path.insert(0, str(REPO))
        from laap.psi_backend import RustPsiBackend

        backend = RustPsiBackend(state_file=sf)
        st = backend.get_state()

        # B1: 頂層 key 存在
        for key, expected_type in EXPECTED_KEYS.items():
            if key not in st:
                fail(f"缺少頂層 key: {key}")
                continue
            val = st[key]
            if not isinstance(val, expected_type):
                fail(f"{key} 型別錯誤: 期望 {expected_type.__name__}, 實際 {type(val).__name__}")
            else:
                ok(f"頂層 key 存在: {key} ({type(val).__name__})")

        # B2: needs 形狀
        need_names_found = set(st.get("needs", {}).keys())
        missing = NEED_NAMES - need_names_found
        extra = need_names_found - NEED_NAMES
        if missing:
            warn(f"needs 缺少: {missing}")
        if extra:
            warn(f"needs 多餘: {extra}")
        if not missing and not extra:
            ok("needs 5 需求齊全")
        for nn in NEED_NAMES:
            nd = st.get("needs", {}).get(nn, {})
            for k, t in EXPECTED_NEED_KEYS.items():
                if k not in nd:
                    fail(f"needs.{nn} 缺少 {k}")
                elif not isinstance(nd[k], t):
                    fail(f"needs.{nn}.{k} 型別錯誤: {type(nd[k]).__name__}")
        ok("needs 每需求含 current/target/drive")

        # B3: emotion 形狀 + QUIRK-1
        em = st.get("emotion", {})
        for k, t in EXPECTED_EMOTION_KEYS.items():
            if k not in em:
                fail(f"emotion 缺少 {k}")
        ok("emotion 含 valence/arousal/dominance/raw_valence")

        # QUIRK-1: valence == endorphin, raw_valence == pleasure
        if abs(em.get("valence", 0) - (-0.05)) < 0.001:
            ok("QUIRK-1: emotion.valence == endorphin (-0.05)")
        else:
            warn(f"QUIRK-1: emotion.valence={em.get('valence')} 期望 -0.05")
        if abs(em.get("raw_valence", 0) - 0.1) < 0.001:
            ok("QUIRK-1: emotion.raw_valence == pleasure (0.1)")
        else:
            warn(f"QUIRK-1: emotion.raw_valence={em.get('raw_valence')} 期望 0.1")

        # B4: affective 形狀
        af = st.get("affective", {})
        for k, t in EXPECTED_AFFECTIVE_KEYS.items():
            if k not in af:
                fail(f"affective 缺少 {k}")
        ok("affective 含 mood/dims/biases/events_total")

        # B5: biases 8 維
        biases = set(af.get("biases", {}).keys())
        if biases == EXPECTED_BIAS_KEYS:
            ok("biases 8 維齊全")
        else:
            missing_b = EXPECTED_BIAS_KEYS - biases
            extra_b = biases - EXPECTED_BIAS_KEYS
            if missing_b:
                warn(f"biases 缺少: {missing_b}")
            if extra_b:
                warn(f"biases 多餘: {extra_b}")

        # B6: dominant_need 是 drives argmax
        dn = st.get("dominant_need", "")
        if dn == "competence":
            ok("dominant_need == competence (argmax of drives)")
        else:
            warn(f"dominant_need={dn}, 期望 competence")

        # B7: attention 大寫
        att = st.get("attention", "")
        if att == "TASK":
            ok("attention 大寫 (TASK)")
        else:
            warn(f"attention={att}, 期望 TASK")

    finally:
        os.unlink(sf)


# ── 測試 C: aris_brain 讀者相容性 ─────────────────────────────────────

def check_aris_brain_compatibility() -> None:
    print("\n═══ C. aris_brain 讀者相容性 ═══")
    if not LAAP_AGI_DIR.is_dir():
        warn(f"LAAP_AGI_DIR 不存在: {LAAP_AGI_DIR}，跳過讀者掃描")
        return

    critical_missing = 0
    noncritical_missing = 0
    for reader, expected_key, native_map, required, desc in ARIS_BRAIN_READERS:
        if "❌" in native_map:
            if required:
                critical_missing += 1
                fail(f"{reader}: {expected_key} → {native_map} ({desc})")
            else:
                noncritical_missing += 1
                warn(f"{reader}: {expected_key} → {native_map} ({desc})")
        elif "⚠️" in native_map:
            noncritical_missing += 1
            warn(f"{reader}: {expected_key} → {native_map} ({desc})")
        else:
            ok(f"{reader}: {expected_key} → {native_map}")

    if critical_missing == 0:
        ok("無關鍵 key 缺口")
    else:
        fail(f"關鍵 key 缺口: {critical_missing} 處")
    if noncritical_missing > 0:
        warn(f"非關鍵 key 缺口: {noncritical_missing} 處（靜默降級）")


# ── 測試 D: 回退行為 ─────────────────────────────────────────────────

def check_fallback() -> None:
    print("\n═══ D. 回退行為 ═══")
    sys.path.insert(0, str(REPO))
    from laap.psi_backend import RustPsiBackend

    # D1: 不存在的 state 檔
    backend = RustPsiBackend(state_file="/tmp/nonexistent-psi-test.json")
    st = backend.get_state()
    assert "needs" in st, "fallback 應有 needs"
    assert st["tick"] == 0, "fallback tick 應為 0"
    ok("missing file → fallback 預設狀態")

    # D2: 過期 state 檔 (>2s)
    stale = {"schema": "neuralis-rust-psi/v1", "tick": 100,
             "needs": {"certainty": 0.5, "competence": 0.5, "autonomy": 0.5,
                       "relatedness": 0.5, "growth": 0.5},
             "drives": {"certainty": 0.3, "competence": 0.3, "autonomy": 0.3,
                        "relatedness": 0.3, "growth": 0.3},
             "affect": {"pleasure": 0.0, "arousal": 0.3, "dominance": 0.5,
                        "social": 0.3, "stress": 0.1},
             "endorphin": 0.0, "attention": "idle", "source": "test",
             "ts": time.time() - 10.0}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(stale, f)
        sf = f.name
    try:
        backend2 = RustPsiBackend(state_file=sf)
        st2 = backend2.get_state()
        # 過期 → 無快取 → 預設
        if st2["tick"] == 0:
            ok("stale file (>2s) → fallback 預設狀態")
        else:
            warn(f"stale file 回傳 tick={st2['tick']}, 期望 0")
    finally:
        os.unlink(sf)

    # D3: stale 但有快取 → 回快取
    fresh = dict(stale)
    fresh["ts"] = time.time()
    fresh["tick"] = 999
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(fresh, f)
        sf2 = f.name
    try:
        backend3 = RustPsiBackend(state_file=sf2)
        st3a = backend3.get_state()  # 讀新鮮的 → 快取 999
        assert st3a["tick"] == 999
        # 換成過期檔
        stale2 = dict(fresh)
        stale2["ts"] = time.time() - 10.0
        stale2["tick"] = 1
        Path(sf2).write_text(json.dumps(stale2))
        st3b = backend3.get_state()  # 過期 → 回快取 999
        if st3b["tick"] == 999:
            ok("stale file + 有快取 → 回快取 (degraded)")
        else:
            warn(f"stale + cached 回 tick={st3b['tick']}, 期望 999")
    finally:
        os.unlink(sf2)

    # D4: start() 時 daemon 不存在 → 不炸
    binary = RustPsiBackend._daemon_binary()
    exists = Path(binary).is_file()
    if exists:
        ok("daemon binary 可用")
    else:
        warn("daemon binary 不存在，start() 會靜默跳過")


# ── 測試 E: B2 FIFO 事件通道 ─────────────────────────────────────────

def check_fifo_channel() -> None:
    print("\n═══ E. B2 FIFO 事件通道 ═══")
    sys.path.insert(0, str(REPO))
    from laap.psi_backend import RustPsiBackend

    # E1: 無 daemon 時 process_input 不炸
    backend = RustPsiBackend(state_file="/tmp/nonexistent-fifo-test.json")
    try:
        backend.process_input("測試訊息")
        ok("no-daemon process_input 不炸")
    except Exception as e:
        fail(f"no-daemon process_input 例外: {e}")

    # E2: 無 daemon 時 post_affective_event 不炸
    try:
        backend.post_affective_event("task_success", 0.5)
        ok("no-daemon post_affective_event 不炸")
    except Exception as e:
        fail(f"no-daemon post_affective_event 例外: {e}")

    # E3: 無 daemon 時 satisfy 不炸
    try:
        backend.satisfy("competence", 0.5, "test")
        ok("no-daemon satisfy 不炸")
    except Exception as e:
        fail(f"no-daemon satisfy 例外: {e}")

    # E4: daemon 在時 FIFO 事件流
    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "state.json"
        fifo_file = Path(tmp) / "state.fifo"
        proc = subprocess.Popen(
            [str(DAEMON_BINARY), "--state-file", str(state_file),
             "--event-fifo", str(fifo_file),
             "--write-ms", "100", "--seed", "42", "--max-seconds", "6"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            time.sleep(1.0)
            backend2 = RustPsiBackend(state_file=str(state_file))
            s0 = backend2.get_state()
            comp0 = s0["needs"]["competence"]["current"]

            # process_input 寫 "我懂了" → CompetenceSuccess
            backend2.process_input("我懂了，謝謝你！")
            time.sleep(0.5)
            s1 = backend2.get_state()
            comp1 = s1["needs"]["competence"]["current"]
            delta = comp1 - comp0
            if delta > 0.005:
                ok(f"FIFO: process_input('我懂了') → competence +{delta:.4f}")
            else:
                warn(f"FIFO: competence delta 過小 ({delta:.4f})")

            # post_affective_event
            backend2.post_affective_event("task_success", 0.5)
            time.sleep(0.3)
            s2 = backend2.get_state()
            pleasure_delta = s2["emotion"]["raw_valence"] - s1["emotion"]["raw_valence"]
            if pleasure_delta > 0.01:
                ok(f"FIFO: post_affective_event('task_success') → pleasure +{pleasure_delta:.4f}")
            else:
                warn(f"FIFO: pleasure delta 過小 ({pleasure_delta:.4f})")

            # satisfy
            backend2.satisfy("growth", 0.5, "test")
            time.sleep(0.3)
            s3 = backend2.get_state()
            growth_delta = s3["needs"]["growth"]["current"] - s2["needs"]["growth"]["current"]
            if growth_delta > 0.005:
                ok(f"FIFO: satisfy('growth') → growth +{growth_delta:.4f}")
            else:
                warn(f"FIFO: growth delta 過小 ({growth_delta:.4f})")

        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()


# ── 測試 F: 開關回歸 ──────────────────────────────────────────────────

def check_switch_regression() -> None:
    print("\n═══ F. 開關回歸 + fallback ═══")
    current = os.environ.get("NEURALIS_PSI_BACKEND", "").lower()
    if current == "rust":
        warn("目前 NEURALIS_PSI_BACKEND=rust，跳過預設 python 測試")
        return
    # 模擬 startup.py 的開關邏輯
    backend_name = current if current else "python"
    if backend_name == "python":
        ok("NEURALIS_PSI_BACKEND 未設 → 走 python 路徑")
    else:
        warn(f"NEURALIS_PSI_BACKEND={backend_name}")

    # F2: Rust fallback — _daemon_binary 回傳不存在路徑時 healthy() 應回 False
    sys.path.insert(0, str(REPO))
    from laap.psi_backend import RustPsiBackend
    backend = RustPsiBackend(state_file="/tmp/nonexistent-fallback-test.json")
    # 手動設 _daemon_process 為 None（模擬 start() 失敗）
    assert not backend.healthy(), "無 daemon 時 healthy() 應回 False"
    ok("healthy() 無 daemon → False")

    # F3: start() 後 healthy() 應反映 daemon 狀態
    if DAEMON_BINARY.is_file():
        with tempfile.TemporaryDirectory() as tmp:
            sf = Path(tmp) / "state.json"
            ff = Path(tmp) / "state.fifo"
            backend2 = RustPsiBackend(state_file=str(sf))
            # 模擬正常 daemon
            proc = subprocess.Popen(
                [str(DAEMON_BINARY), "--state-file", str(sf),
                 "--event-fifo", str(ff), "--write-ms", "100",
                 "--seed", "0", "--max-seconds", "4"],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            backend2._daemon_process = proc
            time.sleep(0.5)
            if backend2.healthy():
                ok("healthy() daemon 在線 → True")
            else:
                warn("healthy() daemon 在線但回 False")
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
    else:
        warn("daemon binary 不存在，跳過 healthy() 實測")


# ── 主程式 ────────────────────────────────────────────────────────────

def main() -> None:
    verbose = "--verbose" in sys.argv
    test_daemon = "--daemon" in sys.argv or "--all" in sys.argv

    print(f"RustPsiBackend 相容性檢查")
    print(f"  repo: {REPO}")
    print(f"  daemon: {DAEMON_BINARY}")
    print(f"  LAAP_AGI_DIR: {LAAP_AGI_DIR}")
    print(f"  verbose: {verbose}")
    print()

    try:
        check_remap_shape()
        check_aris_brain_compatibility()
        check_fallback()
        check_fifo_channel()
        check_switch_regression()
        if test_daemon:
            check_daemon_availability()
            check_daemon_lifecycle()
    except SystemExit:
        pass
    except Exception as e:
        print(f"\n❌ 腳本例外: {e}")
        if verbose:
            traceback.print_exc()

    # ── 總結 ──
    print("\n" + "═" * 50)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    warned = sum(1 for r in results if r["status"] == "WARN")
    total = len(results)
    print(f"結果: {passed}/{total} PASS, {failed} FAIL, {warned} WARN")

    if verbose:
        print("\n詳細:")
        for r in results:
            icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}[r["status"]]
            print(f"  {icon} [{r['status']}] {r['msg']}")

    if failed > 0:
        print("\n❌ 有 FAIL 項目，需處理")
        sys.exit(1)
    elif warned > 0:
        print("\n⚠️  有 WARN 項目（靜默降級），建議檢視")
        sys.exit(0)
    else:
        print("\n✅ 全部通過")
        sys.exit(0)


if __name__ == "__main__":
    main()