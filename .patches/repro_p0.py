import sys, json, random; sys.path.insert(0, '.')
from laap import agency as A

class FakePsi:
    def get_last_input(self): return "光錐"
    def get_cognitive_bias(self): return {"risk_seeking": 0.0, "attention_narrowing": 0.0}
    def post_affective_event(self, *a, **k): pass
class FakeTools:
    def execute(self, tool, prompt, timeout=30):
        return "[0.95] 命中 作法 光錐" if "作法" in prompt else "[0.05] 光錐 經驗"

def fresh():
    a = A.AgencyLoop.__new__(A.AgencyLoop)
    for k, v in dict(_need_stats={}, _trust_scores={"user": 0.3}, _exploration_rate=0.15,
                     _rpe_buffer=[], _rpe_total=0.0, _rpe_count=0, _recent_queries=[],
                     _seed_snippet="光錐", _cycle_guard=False, _last_was_self_initiated=False,
                     _self_cycle_count=0, _cycle_max=3, skipped_stale=0, _state_loaded=False,
                     _task_queue=[], _task_index=0, _goal_spec="", psi=FakePsi(),
                     tools=FakeTools(), actions_taken=0, _action_times=[], _action_ts=[]).items():
        setattr(a, k, v)
    return a

PAIR = A._pair_key("competence", "gbrain") if hasattr(A, "_pair_key") else ("competence", "gbrain")

# ── A：學到的權重，選角度時讀得到嗎 ──
a = fresh(); random.seed(7)
for i in range(30):
    try: a._act("competence", 0.8, "gbrain", f"光錐 作法 v{i}")
    except AttributeError: pass
read_back = a._get_angle_weights("competence")
print("A1 30 次高分回饋後，選角度時讀到:", read_back)
okA = read_back.get("作法", 1.0) > 1.0
print("A  判定:", "PASS（學到的讀得到）" if okA else "FAIL ← 學到的讀不到（全是初始 1.0）")

# ── B：expected 的 pair 層 round-trip 撐過重啟嗎 ──
b = fresh(); b._state_loaded = True
try: b._act("competence", 0.8, "gbrain", "光錐 作法")
except AttributeError: pass
before = b._need_stats.get(PAIR, {}).get("expected")
print(f"B1 pair key: {PAIR!r}")
try:                                               # 模擬 gbrain 存讀
    wire = json.loads(json.dumps({"need_stats": b._need_stats}))
except TypeError as e:
    print(f"B2 !! _need_stats 無法 JSON 序列化: {e}")
    print("B  判定: FAIL ← key 不是 JSON-safe，_save_state 必須做型別轉換（漂移的根源）")
    wire = None
if wire is None:
    after = None; c = None
else:
    c = fresh(); c._need_stats = wire["need_stats"]
    after = c._need_stats.get(PAIR, {}).get("expected")
okB = before is not None and before == after
if wire is not None:
    print(f"B2 重啟前 expected={before} → 重啟後 expected={after}")
    print("B  判定:", "PASS（撐過重啟）" if okB else "FAIL ← 重啟後查不到，走冷啟動 0.3")

# ── C：角度權重也要撐過重啟 ──
w_before = b._need_stats.get("competence", {}).get("angle_weights", {}).get("作法")
w_after = c._need_stats.get("competence", {}).get("angle_weights", {}).get("作法") if c else None
print(f"C1 angle_weights['作法'] 重啟前={w_before} → 重啟後={w_after}")
okC = w_before is not None and w_before == w_after
print("C  判定:", "PASS" if okC else "FAIL")

print("\n總判定:", "ALL PASS" if (okA and okB and okC) else "FAIL")
