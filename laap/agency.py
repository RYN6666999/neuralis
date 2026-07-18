"""
AgencyLoop — Phase 6：閉合「需求 → 行動 → 結果 → 記憶」迴路（v0）。

誠實標註：v0 的「意圖形成」是規則表（drive 超閾值 → 查詢），不是認知。
迴路是骨架；推理器官（Phase 3 過 benchmark 後）是可替換件。

煞車（先行，不是事後補）：
  - 唯讀白名單：只准 gbrain / qmd / file-search（不含寫入、不含任意 HTTP）
  - rate cap：每小時 ≤ NEURALIS_AGENCY_MAX_PER_HOUR（預設 6）
  - 每需求 cooldown 30 min（competence 在靜息值 drive 恆 0.75，沒 cooldown 會壟斷配額）
  - 審計：每次行動一行 JSONL → neuralis/agency-audit.jsonl（不進版控）
  - 總開關：NEURALIS_AGENCY=off

回寫：行動結果 → memory_bridge.store_important（→ gbrain laap/memory/*），
importance 上限 0.5（自主寫入防污染，見 handoff retention 原則）+ 情緒加權。
成功行動 satisfy 對應需求 → drive 回落 → 迴路自然靜下來，直到鬆弛再拉高。
"""
from __future__ import annotations

import json
import logging
import os
import random
import re
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

from laap.safety_gate import AGENTOS_READONLY, classify

logger = logging.getLogger("laap.agency")

READONLY_WHITELIST = frozenset({"gbrain", "qmd", "file-search", "scream-ask"}) | AGENTOS_READONLY
NEED_COOLDOWN_S = 1800.0
AUDIT_PATH = Path(__file__).resolve().parents[1] / "agency-audit.jsonl"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


class AgencyLoop:
    """背景執行緒：定期評估 PsiCore drives，超閾值就形成意圖並行動。

    v0.1 — RPE（Reward Prediction Error）：
    行動後量結果 vs 預期（檢索命中率/分數），誤差回頭調規則表權重 +
    drive 閾值/探索率。靜態規則表變會學的 bandit（誠實標註不是認知）。

    v0.2 — 神經調節物質：
    腎上腺素：arousal 縮短 agency interval。
    催產素：per-entity trust 權重，熟人 relatedness 增益更大。
    催產素 v0.2 補完：relatedness 加入查詢角度，trust 真正驅動行為。

    v0.3 — 持久化：
    RPE 學習狀態 (_need_stats, trust, exploration_rate) 定期寫入 gbrain，
    開機讀回，跨 session 累積。slug: _internal/agency-state
    """

    _STATE_SLUG = "_internal/agency-state"
    _CHECKPOINT_INTERVAL = 5  # 每 N 次行動 checkpoint

    def __init__(self, psi, tools, bus=None,
                 interval: Optional[float] = None,
                 max_per_hour: Optional[float] = None,
                 drive_threshold: Optional[float] = None):
        self.psi = psi
        self.tools = tools
        self.bus = bus
        self.interval = interval if interval is not None else _env_float("NEURALIS_AGENCY_INTERVAL", 60.0)
        self.max_per_hour = int(max_per_hour if max_per_hour is not None
                                else _env_float("NEURALIS_AGENCY_MAX_PER_HOUR", 6))
        self.drive_threshold = (drive_threshold if drive_threshold is not None
                                else _env_float("NEURALIS_AGENCY_DRIVE_THRESHOLD", 0.45))
        self._action_ts: deque = deque()          # 最近一小時行動時間戳
        self._need_last_action: dict = {}          # need name → ts
        self._recent_queries: deque = deque(maxlen=8)  # 近期查詢（normalized）去重用
        self._seed_snippet: str = ""               # 上次行動結果摘要 → 下次聯想種子
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self.actions_total = 0
        self.skipped_stale = 0                     # 因種子重複/缺席而跳過的次數（可觀測）
        # ── RPE 狀態 ──
        self._need_stats: dict = {}                # need → {expected, rpes, angle_weights}
        self._rpe_buffer = deque(maxlen=20)        # 滑動視窗 RPE，調 threshold / 探索率
        self._exploration_rate = 0.15              # 探索非最優角度的機率
        self._rpe_total = 0.0                      # 累計 RPE（儀表用）
        self._rpe_count = 0
        # ── 催產素：信任權重 ──
        self._trust_scores: dict = {"user": 0.3}   # entity → trust 0-1
        self._trust_decay_rate = 0.0005             # 每次評估衰減量
        # ── 自我強化循環防護 ──
        self._last_was_self_initiated: bool = False
        self._self_cycle_count: int = 0
        self._cycle_max: int = int(os.environ.get("NEURALIS_AGENCY_CYCLE_MAX", "3"))
        self._cycle_guard: bool = os.environ.get("NEURALIS_AGENCY_CYCLE_GUARD", "on").lower() not in ("off", "0", "false")
        # ── 持久化狀態 ──
        self._checkpoint_counter: int = 0
        self._state_loaded: bool = False   # True=成功讀回 or 全新首存；False=禁存
        self._loaded_once: bool = False     # loop 層只載入一次
        # ── T5: AgentOS 工具追蹤 ──
        self._recent_tools: deque = deque(maxlen=5)  # 最近 5 次工具名
        # ── 任務佇列模式（goal-driven execution） ──
        self._task_queue: list = []          # [{idx, description}, ...]
        self._task_index: int = 0
        self._goal_spec: str = ""
        self._goal_completed: bool = False

    # ── 生命週期 ──

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        # 持久化：開機讀回走 daemon thread（_loop 首圈），不擋 start()
        logger.info(f"[Agency] 迴路啟動 interval={self.interval}s cap={self.max_per_hour}/h "
                    f"threshold={self.drive_threshold}")

    def stop(self) -> None:
        self._save_state()  # 先存
        self._running = False

    # ── 主迴路 ──

    def _loop(self) -> None:
        while self._running:
            # 首圈：持久化讀回（在 daemon thread 裡，不擋 start）
            if not self._loaded_once:
                self._loaded_once = True
                self._load_state()
            interval = self._effective_interval()
            time.sleep(interval)
            try:
                self._evaluate()
            except Exception as e:
                # 同心跳原則：單次評估失敗不停迴路
                logger.warning(f"[Agency] 評估失敗: {e}")

    def _effective_interval(self) -> float:
        """腎上腺素：高 arousal 縮短 agency interval。

        arousal 0-1，interval 範圍 [base × 0.3, base × 1.0]。
        閒置平淡時 (arousal<0.3) 維持基礎 interval；興奮/緊張時加速評估。
        ponytail: 線性映射，不是真腎上腺素動力學。升級路徑 = 非線性曲線。
        """
        try:
            arousal = self.psi.get_state()["emotion"]["arousal"]
        except Exception:
            arousal = 0.3
        # arousal 0.3 → factor 1.0, arousal 0.9 → factor 0.3
        factor = max(0.3, 1.0 - (arousal - 0.3) * 1.2)
        effective = self.interval * factor
        return effective

    def _apply_utility_rewards(self) -> None:
        """E1.2 延遲獎勵：被 recall 用到的 agency 記憶 → 獎勵其 need/angle 權重。
        下游效用信號進學習 —— 綁『被想起』不綁長度，長垃圾騙不了。"""
        try:
            from laap import memory_utility
            from laap.constitution import get_constitution
        except Exception:
            return
        for r in memory_utility.pending_rewards():
            mem_id, need, angle = r["mem_id"], r.get("need"), r.get("angle")
            if need and angle:
                stats = self._need_stats.setdefault(
                    need, {"expected": 0.3, "rpes": [], "angle_weights": {}})
                aw = stats["angle_weights"]
                allowed = get_constitution().guard_weight(need, angle, r["reward"] * 0.5)
                aw[angle] = max(0.1, min(3.0, aw.get(angle, 1.0) + allowed))
                logger.info(f"[Agency] E1.2 延遲獎勵 {need}/{angle} +{allowed:.3f}（記憶被 recall）")
            memory_utility.mark_credited(mem_id)

    def _evaluate(self) -> None:
        self._apply_utility_rewards()   # E1.2：先發被 recall 記憶的延遲獎勵
        # 任務佇列模式：當有活躍目標時，繞過隨機驅動評估
        if self._task_queue and self._task_index < len(self._task_queue):
            self._execute_next_task()
            return
        # 檢查外部任務狀態檔（API 注入路徑）
        if not self._task_queue:
            state_path = "/tmp/aris-scream-task-state.json"
            try:
                if __import__('os').path.exists(state_path):
                    with open(state_path) as _f:
                        _s = __import__('json').load(_f)
                    if _s.get("task_queue") and not _s.get("goal_completed", False):
                        self._goal_spec = _s.get("goal_spec", "")
                        self._task_queue = _s["task_queue"]
                        self._task_index = _s.get("task_index", 0)
                        self._goal_completed = False
                        logger.info(f"[Agency] 從狀態檔載入目標: {self._goal_spec[:40]}")
                        self._execute_next_task()
                        return
            except Exception as _e:
                logger.debug(f"[Agency] 狀態檔讀取失敗: {_e}")
        now = time.time()
        while self._action_ts and now - self._action_ts[0] > 3600:
            self._action_ts.popleft()
        if len(self._action_ts) >= self.max_per_hour:
            return  # rate cap

        # 催產素：信任衰減
        for entity in self._trust_scores:
            self._trust_scores[entity] = max(0.0, self._trust_scores[entity] - self._trust_decay_rate)

        drives = self.psi.get_drives()
        # 催產素：信任權重 → relatedness 增益（最高 +50%）
        trust = self._trust_scores.get("user", 0.0)
        drives["relatedness"] = drives.get("relatedness", 0.0) * (1.0 + trust * 0.5)

        # 依 drive 高→低找第一個「超閾值 + 不在 cooldown + 規則表有招」的需求
        for need, drive in sorted(drives.items(), key=lambda kv: kv[1], reverse=True):
            if drive < self.drive_threshold:
                break
            if now - self._need_last_action.get(need, 0.0) < NEED_COOLDOWN_S:
                continue
            intent = self._form_intent(need)
            if intent is None:
                continue
            tool, prompt = intent
            self._act(need, drive, tool, prompt)
            return  # 每次評估最多一個行動

    def note_interaction(self, entity: str = "user") -> None:
        """催產素：每次使用者互動提升信任權重（從 chatflow 呼叫）。

        trust 上升快（+0.03/次），下降慢（decay 0.0005/評估週期）。
        """
        old = self._trust_scores.get(entity, 0.0)
        self._trust_scores[entity] = min(1.0, old + 0.03)
        self._self_cycle_count = 0  # 真互動重置循環計數

    # ── 持久化：RPE 學習狀態 → gbrain ──

    def _save_state(self) -> None:
        """把 RPE 學習狀態寫入 gbrain slug _internal/agency-state。

        煞車：_state_loaded=False 時禁止寫入，防止讀失敗後的空 state 覆蓋好資料。
        全新首存（get_page 回 None）會設為 True，不受影響。
        """
        if not self._state_loaded:
            return  # 讀失敗或從未嘗試 → 不蓋掉好資料
        state = {
            "need_stats": self._need_stats,
            "trust_scores": self._trust_scores,
            "exploration_rate": self._exploration_rate,
            "task_queue": self._task_queue, "task_index": self._task_index, "goal_spec": self._goal_spec,
        }
        try:
            from gbrain_client import get_client
            client = get_client()
            if client is None:
                return
            content = json.dumps(state, ensure_ascii=False)
            body = f"---\nversion: 1\n---\n{content}"
            client.call("put_page", {"slug": self._STATE_SLUG, "content": body}, timeout=10.0)
        except Exception as e:
            logger.debug(f"[Agency] 狀態存檔失敗: {e}")

    def _load_state(self) -> None:
        """開機從 gbrain 讀回 RPE 學習狀態。retry 最多 3 次（embedding 冷啟動 ~3s）。

        成功讀回 → _state_loaded=True
        頁不存在（全新安裝）→ _state_loaded=True（准首存）
        頁存在但解析失敗 → _state_loaded=False（禁存，防蓋好資料）
        """
        for attempt in range(3):
            try:
                import time as _t
                from gbrain_client import get_client, GbrainError
                client = get_client()
                if client is None:
                    _t.sleep(2)
                    continue
                try:
                    page = client.call("get_page", {"slug": self._STATE_SLUG})
                except GbrainError as e:
                    if "page_not_found" in str(e):
                        self._state_loaded = True  # 全新安裝，准首存
                        return
                    raise
                # 頁不存在 → 全新安裝，准首存
                if not page or not page.get("compiled_truth"):
                    self._state_loaded = True
                    return
                body = (page.get("compiled_truth") or "").strip()
                if body.startswith("---"):
                    parts = body.split("---", 2)
                    if len(parts) >= 3:
                        body = parts[2].strip()
                if not body:
                    self._state_loaded = True  # 全新 → 准存
                    return
                state = json.loads(body)
                self._need_stats = state.get("need_stats", self._need_stats)
                self._trust_scores = state.get("trust_scores", self._trust_scores)
                self._exploration_rate = state.get("exploration_rate", self._exploration_rate)
                self._task_queue = state.get("task_queue", [])
                self._task_index = state.get("task_index", 0)
                self._goal_spec = state.get("goal_spec", "")
                self._state_loaded = True
                for need, s in self._need_stats.items():
                    aw = s.get("angle_weights", {})
                    if aw:
                        logger.info(f"[Agency] 持久化載入: {need} angle_weights={aw}")
                logger.info(f"[Agency] 持久化載入: exploration_rate={self._exploration_rate:.3f}, "
                            f"trust={self._trust_scores}")
                return
            except Exception as e:
                if attempt < 2:
                    _t.sleep(2)
                # 頁存在但解析失敗 → _state_loaded 維持 False，禁存
                if attempt == 2:
                    logger.debug(f"[Agency] 狀態讀回失敗 (3次): {e}")

    # ── 任務佇列模式（goal-driven execution） ──

    def set_goal(self, task_spec: dict) -> None:
        self._goal_spec = task_spec.get("why", "")
        tasks = task_spec.get("task_list", [task_spec])
        self._task_queue = [
            {"idx": i, "description": t.get("description", str(t))}
            for i, t in enumerate(tasks)
        ]
        self._task_index = 0
        self._goal_completed = False
        self._write_progress("decomposing", 0)
        state = {"goal_spec": self._goal_spec, "task_queue": self._task_queue,
                 "task_index": self._task_index, "goal_completed": self._goal_completed}
        with open("/tmp/aris-scream-task-state.json", "w") as f:
            json.dump(state, f)

    def cancel_goal(self) -> None:
        self._task_queue = []; self._task_index = 0
        self._goal_spec = ""; self._goal_completed = False

    def _write_progress(self, phase: str, task_idx: int) -> None:
        entry = {"ts": __import__('time').time(), "direction": "aris→scream",
                 "type": "progress", "content": f"{phase} task {task_idx}",
                 "context": {"phase": phase, "task_index": task_idx}}
        try:
            with open("/tmp/aris-scream-channel.jsonl", "a") as f:
                f.write(__import__('json').dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _execute_next_task(self) -> None:
        task = self._task_queue[self._task_index]
        self._write_progress("executing", self._task_index)
        self._write_task_state()  # 寫入最新進度
        result = self.tools.execute("scream-task",
            f"Task {self._task_index+1}/{len(self._task_queue)}: {task['description']}")
        self._task_index += 1
        if self._task_index >= len(self._task_queue):
            self._goal_completed = True
            self._write_progress("completed", self._task_index)
            self._save_goal_memory(result)
            self.cancel_goal()
            # 清除外部狀態檔（防止 reload）
            try:
                __import__('os').remove("/tmp/aris-scream-task-state.json")
            except Exception:
                pass
        else:
            self._write_task_state()

    def _save_goal_memory(self, result: str) -> None:
        try:
            import memory_bridge
            emo = self.psi.get_state()["emotion"]
            importance = min(0.5, 0.25 + 0.25 * emo.get("arousal", 0.3))
            memory_bridge.store_important(
                f"[目標完成] {self._goal_spec}\n最終結果:\n{result[:500]}",
                tags=["agency", "goal", "scream-task"],
                importance=importance)
            logger.info(f"[Agency] 目標記憶已存: {self._goal_spec[:40]}")
        except Exception as e:
            logger.warning(f"[Agency] 目標記憶儲存失敗: {e}")

    def _write_task_state(self) -> None:
        state = {"goal_spec": self._goal_spec, "task_queue": self._task_queue,
                 "task_index": self._task_index, "goal_completed": self._goal_completed}
        try:
            with open("/tmp/aris-scream-task-state.json", "w") as f:
                __import__('json').dump(state, f)
        except Exception:
            pass

    # ── 意圖形成（v1 = 規則表 + 種子優先序 + 去重，仍不是認知） ──
    # 種子優先序：真對話 > 上次記憶延伸（聯想鏈）> 無 → 不硬查（減空轉垃圾）。
    # 舊版沒種子時退回固定模板反覆刷同一查詢，是重複垃圾記憶的根源。

    _ANGLE = {"certainty": "", "growth": "延伸 新方向", "competence": "作法 經驗 問Scream"}

    # T5: AgentOS 工具路由 — 當 exploration 觸發時，agency 可用 web-search 取代 gbrain
    _AGENTOS_TOOL_MAP = {
        "growth":     ("web-search", "最新發展 新技術 趨勢"),  # (tool, angle_suffix)
        "competence": ("web-search", "作法 教學 最佳實踐"),
        # certainty 保持 gbrain（需要個人記憶，不是網頁搜尋）
    }

    def _score_result(self, result: str, tool: str = "") -> float:
        """量產工具結果的品質分數 0-1。

        gbrain 結果拆 [score] 前綴行；AgentOS/web-search 結果是結構化 JSON，
        無 [score] 前綴，給較高基礎分（有意義的搜尋結果比空記憶有價值）。
        """
        if not result or result == "無結果":
            return 0.0
        scores = []
        for line in result.splitlines():
            m = re.match(r'^\[([\d.]+)\]', line)
            if m:
                scores.append(float(m.group(1)))
        if not scores:
            # 無 [score] 前綴（web-search 等結構化結果）：給 flat 分級基礎分。
            # 曾用 min(base, len/500) — 純長度信號 = 刷分漏洞（長垃圾 0.6 vs 短好 0.006）。
            # E1.1 拿掉長度（改 flat）；真的品質區分留給 E1.2 下游效用信號
            # （agency 寫的記憶後續有沒有被 recall 用到），不是長度。
            return 0.6 if classify(tool) in ("readonly_agentos",) else 0.4
        hit_count = len(scores)
        avg_score = sum(scores) / len(scores)
        # 組合：平均分為主 + hit 數加成（遞減），鼓勵多樣化但不鼓勵垃圾多
        hit_bonus = min(0.3, hit_count * 0.06)
        return min(1.0, avg_score + hit_bonus)

    def _get_angle_weights(self, need: str) -> dict:
        """從 RPE 歷史算每個查詢角度的權重（bandit-style）。

        回 {angle_label: weight}，weight 越高越該選。
        新角度權重 1.0（探索期）。RPE 正 → 權重升；負 → 降。
        ponytail: 簡化 bandit（epsilon-greedy），不是 Thompson sampling。
        """
        stats = self._need_stats.get(need, {"angle_weights": {}})
        weights = dict(stats.get("angle_weights", {}))
        for angle in self._ANGLE.get(need, "").split():
            if not angle:
                continue
            if angle not in weights:
                weights[angle] = 1.0  # 新角度初始權重
        return weights if weights else {"": 1.0}

    def _cache_lookup(self, need: str, seed: str):
        """C-a：決策前問 gbrain 快取有沒有相關經驗（gbrain-first）。
        記 hit/miss → 真實命中率（校準 backtest 的粗略 65%）。命中用『詞相關』
        不用原始分數（backtest 教訓）。回經驗字串或 None。
        『hit 用快取 / miss 委派 Scream』的分支是 C-b —— 這裡只做查詢 + 量測。"""
        try:
            from laap import experience_cache as ec
            from gbrain_client import get_client, hybrid_hits
            client = get_client()
            hits = hybrid_hits(client, seed[:100], 5) if client is not None else []
            r = ec.lookup(seed, hits)
            ec.record(r["hit"], need)
            return r["experience"]
        except Exception:
            return None

    def _should_delegate(self, need: str) -> bool:
        """C-b：該不該委派 Scream 做前瞻。預設休眠 —— scream-task 未批准（你沒簽名）
        就回 False，agency 照舊自查、不生成會被閘擋的委派（不毒化學習）。
        簽名批准 scream-task 後才活；再過成本閘 + 探索率。"""
        try:
            from laap.safety_gate import is_tool_allowed
            from laap.cost_ledger import within_budget
            if not is_tool_allowed("scream-task"):
                return False        # 未簽名 → C-b 休眠
            if not within_budget(want=2000):
                return False        # 成本閘（E2）
            return random.random() < self._effective_exploration()
        except Exception:
            return False

    def _form_delegation_intent(self, need: str, seed: str):
        """C-b：形成委派 Scream 前瞻的意圖（c2，走 scream-task 頻道）。記估算成本。"""
        prompt = f"針對「{seed[:60]}」做一步前瞻研究，回關鍵發現"
        try:
            from laap.cost_ledger import record
            record(2000, source="scream-task-lookahead")
        except Exception:
            pass
        self._recent_queries.append(self._norm(f"scream-task: {prompt}"))
        logger.info(f"[Agency] C-b 委派 Scream 前瞻（cache miss）: {seed[:40]}")
        return ("scream-task", prompt)

    def _form_intent(self, need: str):
        if need not in self._ANGLE:
            return None
        topic = (self.psi.get_last_input() or "").strip()[:80]
        seed = topic or self._seed_snippet
        # 自我強化循環防護：連續多次無使用者輸入 + 自主查詢 → 閒置
        if self._cycle_guard and not topic and self._last_was_self_initiated and self._seed_snippet:
            self._self_cycle_count += 1
            if self._self_cycle_count >= self._cycle_max:
                self._seed_snippet = ""
                self.skipped_stale += 1
                return None
        else:
            self._self_cycle_count = 0
        if not seed:
            self.skipped_stale += 1
            return None
        cache_exp = self._cache_lookup(need, seed)   # C-a：查快取 + 記真實命中率
        if cache_exp is None and self._should_delegate(need):
            return self._form_delegation_intent(need, seed)   # C-b：miss → 委派 Scream
        # RPE 角度選擇：依權重抽樣（epsilon-greedy，探索率被情緒偏差調變）
        weights = self._get_angle_weights(need)
        if not weights or not self._ANGLE.get(need, ""):
            angle = ""
        elif random.random() < self._effective_exploration():
            angle = random.choice(list(weights.keys()))  # 探索
        else:
            angle = max(weights, key=weights.get)       # 利用
        query = f"{seed} {angle}".strip()
        # T5: 工具路由 — exploration 觸發時選擇使用哪個工具
        if random.random() < self._effective_exploration():
            # competence: web-search 與 scream-ask 公平競爭
            if need == "competence" and "問Scream" in self._ANGLE.get("competence", ""):
                if random.random() < 0.5:
                    scream_query = f"問Scream {seed}".strip()
                    if not self._too_similar(scream_query, tool="scream-ask"):
                        self._recent_queries.append(self._norm(f"scream-ask: {scream_query}"))
                        return ("scream-ask", scream_query)
            # AgentOS 工具路由（web-search 等）
            if need in self._AGENTOS_TOOL_MAP:
                agentos_tool, agentos_angle = self._AGENTOS_TOOL_MAP[need]
                agentos_query = f"{seed} {agentos_angle}".strip()
                if not self._too_similar(agentos_query, tool=agentos_tool):
                    self._recent_queries.append(self._norm(f"{agentos_tool}: {agentos_query}"))
                    return (agentos_tool, agentos_query)
        # 預設 gbrain 路徑
        if self._too_similar(query, tool="gbrain"):
            self.skipped_stale += 1
            return None
        self._recent_queries.append(self._norm(f"gbrain: {query}"))
        return ("gbrain", query)

    def _effective_exploration(self) -> float:
        """情緒偏差調變探索率（affective 引擎的偏差接真參數 — 移植的意義所在）。

        risk_seeking 升探索、attention_narrowing 收窄探索（壓力/高喚起時聚焦利用）。
        底值仍由 RPE 自適應調（_act），這裡是情緒的即時調變層。
        """
        eff = self._exploration_rate
        try:
            biases = self.psi.get_cognitive_bias()
            eff = (eff + 0.3 * biases["risk_seeking"]) * \
                  (1.0 - 0.6 * max(0.0, biases["attention_narrowing"]))
        except Exception:
            pass  # affective 沒起 → 用底值
        return max(0.02, min(0.5, eff))

    @staticmethod
    def _norm(text: str) -> str:
        return " ".join(text.lower().split())

    def _too_similar(self, query: str, tool: str = "") -> bool:
        """跟近期查詢 token Jaccard ≥ 0.7 視為太像（包含 tool name 避免跨工具撞車）。"""
        q = set(self._norm(f"{tool}: {query}").split())
        if not q:
            return True
        for prev in self._recent_queries:
            p = set(prev.split())
            if p and len(q & p) / len(q | p) >= 0.7:
                return True
        return False

    # ── 行動 + RPE + 回寫 + 審計 ──

    def _act(self, need: str, drive: float, tool: str, prompt: str) -> None:
        # T5: 不再 hard-block 非白名單工具 — 交給 safety_gate Phase 4b 決定
        # (tools.execute() 內部已呼叫 safety_gate.check())
        # 自我強化循環防護：記錄是否為自主工具（非使用者觸發）
        if self._cycle_guard:
            self._last_was_self_initiated = (tool in READONLY_WHITELIST)
        now = time.time()
        result = self.tools.execute(tool, prompt, timeout=30)

        # SafetyGate 阻擋
        if result and result.startswith("[安全閘]"):
            # T5: 已排入待批清單 = 不 hard-block，仍計行動（Phase 4b 批准閘）
            if "已排入待批清單" in result:
                logger.info(f"[Agency] [安全閘]排隊待批 {tool}({prompt[:40]}) — 仍計行動")
            else:
                # 危險內容阻擋：不計行動、不佔 rate cap
                logger.info(f"[Agency] [安全閘]阻擋 {tool}({prompt[:40]}) — 不計行動")
                return

        ok = bool(result) and not result.startswith(("[錯誤]", "[未知工具]", "[AgentOS 錯誤]", "[安全閘]")) \
            and result != "無結果"

        # ── RPE 計算 ──
        outcome = self._score_result(result, tool=tool) if ok else 0.0
        stats = self._need_stats.setdefault(need, {
            "expected": 0.3, "rpes": [], "angle_weights": {}})
        expected = stats["expected"]
        rpe = outcome - expected
        stats["expected"] = 0.9 * expected + 0.1 * outcome  # EMA
        stats["rpes"].append(rpe)
        self._rpe_buffer.append(rpe)
        self._rpe_total += rpe
        self._rpe_count += 1

        # ── 角度權重更新 ──
        used_angle = ""
        for a in self._ANGLE.get(need, "").split():
            if a and a in prompt:
                used_angle = a
                break
        if used_angle:
            from laap.constitution import get_constitution
            aw = stats["angle_weights"]
            old = aw.get(used_angle, 1.0)
            # 憲法：權重變速上限 + 小時預算凍結（防 gbrain 分數線異常時垃圾訊號永久累積）
            allowed = get_constitution().guard_weight(need, used_angle, rpe * 0.5)
            aw[used_angle] = max(0.1, min(3.0, old + allowed))

        # ── RPE 結果 → 5 維情緒事件（行動後果塑形情緒，情緒再回頭調變探索）──
        try:
            if abs(rpe) > 0.05:
                self.psi.post_affective_event(
                    "task_success" if rpe > 0 else "task_failure",
                    intensity=min(1.0, abs(rpe) * 2))
        except Exception:
            pass

        # ── 探索率自適應 ──
        if len(self._rpe_buffer) >= 5:
            avg_rpe = sum(self._rpe_buffer) / len(self._rpe_buffer)
            if avg_rpe > 0.05:
                self._exploration_rate = min(0.30, self._exploration_rate + 0.005)
            elif avg_rpe < -0.05:
                self._exploration_rate = max(0.05, self._exploration_rate - 0.005)

        mem_id = ""
        if ok:
            try:
                import memory_bridge
                emo = self.psi.get_state()["emotion"]
                importance = min(0.5, 0.25 + 0.25 * emo["arousal"])
                mem_id = memory_bridge.store_important(
                    f"[自主行動:{need}] 查詢「{prompt}」→\n{result[:500]}",
                    tags=["agency", need], importance=importance)
                self.psi.satisfy(need, 0.2, "agency")
                self._seed_snippet = self._extract_seed(result)
                # E1.2：記 provenance（哪個 need/tool/angle 產生這條記憶）—
                # 之後這條被 recall 用到 → 發延遲效用獎勵給該 angle
                try:
                    from laap import memory_utility
                    memory_utility.tag_memory(mem_id, need, tool, used_angle)
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"[Agency] 回寫失敗: {e}")

            if ok and tool == "scream-ask":
                mem_id = memory_bridge.store_important(
                    f"[scream-ask] 問「{prompt}」→\n{result[:500]}",
                    tags=["agency", "scream", "tui-learning"],
                    importance=importance)
                if mem_id:
                    logger.info(f"[Agency] scream-ask 記憶已存: {mem_id}")

        self._action_ts.append(now)
        self._need_last_action[need] = now
        self.actions_total += 1
        self._recent_tools.append(tool)  # T5: 記錄最近工具名供 status.py 使用
        entry = {"ts": now, "need": need, "drive": round(drive, 3),
                 "tool": tool, "prompt": prompt, "ok": ok,
                 "result_len": len(result or ""), "mem_id": mem_id,
                 "outcome": round(outcome, 3), "expected": round(expected, 3),
                 "rpe": round(rpe, 3), "exploration": round(self._exploration_rate, 3)}
        self._audit(entry)
        # 持久化 checkpoint：每 N 次行動存一次
        self._checkpoint_counter += 1
        if self._checkpoint_counter >= self._CHECKPOINT_INTERVAL:
            self._checkpoint_counter = 0
            self._save_state()
        logger.info(f"[Agency] 行動#{self.actions_total} {need}(drive={drive:.2f}) "
                    f"{tool}({prompt[:40]}) ok={ok} rpe={rpe:+.3f} "
                    f"exp={self._exploration_rate:.2f} → mem={mem_id or '-'}")

    @staticmethod
    def _audit(entry: dict) -> None:
        try:
            with AUDIT_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[Agency] 審計寫入失敗: {e}")

    _SEED_PREFIX = re.compile(r"^\[[\d.]+\]\s*|^\S+/\S+\s+--\s*|^#+\s*")

    @classmethod
    def _extract_seed(cls, result: str) -> str:
        """從查詢結果抽下次種子：首個夠長、剝掉 [score]/slug--/# 前綴的行。
        前綴迴圈剝（單次 sub 因 ^ 只匹配位置 0 剝不乾淨多層）。"""
        for line in (result or "").splitlines():
            s = line.strip()
            for _ in range(3):
                new = cls._SEED_PREFIX.sub("", s).strip()
                if new == s:
                    break
                s = new
            if len(s) >= 4:
                return s[:60]
        return ""
