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

logger = logging.getLogger("laap.agency")

READONLY_WHITELIST = frozenset({"gbrain", "qmd", "file-search"})
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
        self._last_was_gbrain: bool = False
        self._self_cycle_count: int = 0
        self._cycle_max: int = int(os.environ.get("NEURALIS_AGENCY_CYCLE_MAX", "3"))
        self._cycle_guard: bool = os.environ.get("NEURALIS_AGENCY_CYCLE_GUARD", "on").lower() not in ("off", "0", "false")
        # ── 持久化狀態 ──
        self._checkpoint_counter: int = 0
        self._state_loaded: bool = False   # True=成功讀回 or 全新首存；False=禁存
        self._loaded_once: bool = False     # loop 層只載入一次

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
            arousal = getattr(self.psi.emotion, "arousal", 0.3)
        except Exception:
            arousal = 0.3
        # arousal 0.3 → factor 1.0, arousal 0.9 → factor 0.3
        factor = max(0.3, 1.0 - (arousal - 0.3) * 1.2)
        effective = self.interval * factor
        return effective

    def _evaluate(self) -> None:
        now = time.time()
        while self._action_ts and now - self._action_ts[0] > 3600:
            self._action_ts.popleft()
        if len(self._action_ts) >= self.max_per_hour:
            return  # rate cap

        # 催產素：信任衰減
        for entity in self._trust_scores:
            self._trust_scores[entity] = max(0.0, self._trust_scores[entity] - self._trust_decay_rate)

        drives = self.psi.needs.get_drives()
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

    # ── 意圖形成（v1 = 規則表 + 種子優先序 + 去重，仍不是認知） ──
    # 種子優先序：真對話 > 上次記憶延伸（聯想鏈）> 無 → 不硬查（減空轉垃圾）。
    # 舊版沒種子時退回固定模板反覆刷同一查詢，是重複垃圾記憶的根源。

    _ANGLE = {"certainty": "", "growth": "延伸 新方向", "competence": "作法 經驗", "relatedness": "你 我們 陪伴 一起 感覺"}

    def _score_result(self, result: str) -> float:
        """量產 gbrain 結果的品質分數 0-1。

        拆成分數線的 hit 數 + 平均分數 + 內容長度三個訊號。
        ponytail: 簡化版，不考慮語義相關性。升級路徑 = semantic score 取代線性組合。
        """
        if not result or result == "無結果":
            return 0.0
        scores = []
        for line in result.splitlines():
            m = re.match(r'^\[([\d.]+)\]', line)
            if m:
                scores.append(float(m.group(1)))
        if not scores:
            # 有結果但無解析分數：給基礎分（有內容就是一種結果）
            return min(0.4, len(result) / 500)
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

    def _form_intent(self, need: str):
        if need not in self._ANGLE:
            return None  # autonomy：v0 無唯讀動作可做。relatedness v0.2 已加查詢角度
        topic = (getattr(self.psi, "last_input", "") or "").strip()[:80]
        seed = topic or self._seed_snippet   # 真對話優先，否則從上次記憶聯想
        # 自我強化循環防護：連續多次無使用者輸入 + gbrain 查詢 → 閒置
        if self._cycle_guard and not topic and self._last_was_gbrain and self._seed_snippet:
            self._self_cycle_count += 1
            if self._self_cycle_count >= self._cycle_max:
                self._seed_snippet = ""
                self.skipped_stale += 1
                return None
        else:
            self._self_cycle_count = 0
        if not seed:
            self.skipped_stale += 1          # 無新鮮種子 → 閒著，不刷模板
            return None
        # RPE 角度選擇：依權重抽樣（epsilon-greedy）
        weights = self._get_angle_weights(need)
        if not weights or not self._ANGLE.get(need, ""):
            angle = ""
        elif random.random() < self._exploration_rate:
            angle = random.choice(list(weights.keys()))  # 探索
        else:
            angle = max(weights, key=weights.get)       # 利用
        query = f"{seed} {angle}".strip()
        if self._too_similar(query):
            self.skipped_stale += 1
            return None
        self._recent_queries.append(self._norm(query))
        return ("gbrain", query)

    @staticmethod
    def _norm(text: str) -> str:
        return " ".join(text.lower().split())

    def _too_similar(self, query: str) -> bool:
        """跟近期查詢 token Jaccard ≥ 0.7 視為太像（抓模板變體，不只完全相同）。"""
        q = set(self._norm(query).split())
        if not q:
            return True
        for prev in self._recent_queries:
            p = set(prev.split())
            if p and len(q & p) / len(q | p) >= 0.7:
                return True
        return False

    # ── 行動 + RPE + 回寫 + 審計 ──

    def _act(self, need: str, drive: float, tool: str, prompt: str) -> None:
        if tool not in READONLY_WHITELIST:
            logger.warning(f"[Agency] 拒絕非白名單工具: {tool}")
            return
        # 自我強化循環防護：記錄上次工具類型
        if self._cycle_guard:
            self._last_was_gbrain = (tool == "gbrain")
        now = time.time()
        result = self.tools.execute(tool, prompt, timeout=30)
        ok = bool(result) and not result.startswith(("[錯誤]", "[未知工具]", "[AgentOS 錯誤]")) \
            and result != "無結果"

        # ── RPE 計算 ──
        outcome = self._score_result(result) if ok else 0.0
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
            aw = stats["angle_weights"]
            old = aw.get(used_angle, 1.0)
            aw[used_angle] = max(0.1, min(3.0, old + rpe * 0.5))

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
                emo = self.psi.emotion.to_dict()
                importance = min(0.5, 0.25 + 0.25 * emo["arousal"])
                mem_id = memory_bridge.store_important(
                    f"[自主行動:{need}] 查詢「{prompt}」→\n{result[:500]}",
                    tags=["agency", need], importance=importance)
                self.psi.needs.satisfy_all({self._need_type(need): 0.2})
                self._seed_snippet = self._extract_seed(result)
            except Exception as e:
                logger.warning(f"[Agency] 回寫失敗: {e}")

        self._action_ts.append(now)
        self._need_last_action[need] = now
        self.actions_total += 1
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
    def _need_type(name: str):
        from laap.psi_core import NeedType
        return NeedType(name)

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

    @staticmethod
    def _audit(entry: dict) -> None:
        try:
            with AUDIT_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[Agency] 審計寫入失敗: {e}")
