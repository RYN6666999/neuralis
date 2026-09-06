#!/usr/bin/env python3
"""
fail-predictor.py — 貝氏失敗風險預測器（世界模型，v2）

架構：JEPA 式「在潛在特徵空間預測」，非輸出空間規則。
從歷史失敗訊號學一顆可解釋的計數式貝氏模型，
對「沒見過的新輸入」也敢給 P(失敗) 風險分。

特徵空間 (S) 維度（低維，breed 陷阱4：小數據別過度工程）：
  - domain_path   : 領域樹路徑（exact）
  - tulpa_name    : 候選/贏家 tulpa
  - error_type    : 歷史錯誤類型（做平滑先驗）
  - route_class   : decision_log 的 route 歸類（鋼人/普通）

預測：P(失敗 | s)  用 Laplace 平滑的計數式貝氏（冷啟動也有意義）

用法：
  python3 fail-predictor.py report            # 事後統計盤點（v1 功能保留）
  python3 fail-predictor.py predict --domain 除錯方法論 --tulpa 本我理性
  python3 fail-predictor.py predict --domain 客戶經營/約客戶 --tulpa 自我理性
  # feeel free 不加 flag 就是力求讀出所有輸入的風險評分
"""
import argparse, sqlite3, sys
from pathlib import Path
from collections import defaultdict

HOME = Path.home()
TULPA_DB = HOME / "Developer/neuralis/data/tulpa_memory.db"
ARIS_DB = HOME / ".aris-memory.db"
ALPHA = 1.0  # Laplace 平滑強度（先驗權重）


def _conn(path):
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


# ── Ryan 常用模型（A 方案：只對這些算風險, 收斂單純） ──
# 世界模型的 model 維度只認這幾個, 其他模型一律視為"未觀測"回 fallback
KNOWN_MODELS = ("deepseek-v4-flash", "deepseek-v4-pro", "agnes-n", "agnes-n2.5", "gemini")


class FailureModel:
    """計數式貝氏失敗模型。

    P(fail | s) = (count_fail(s) + α·P0) / (count_total(s) + α)
    P0 = 全域基準失敗率（新增先驗，讓冷啟動也有意義）

    維度: domain × tulpa × route × model
        model 維度只對 KNOWN_MODELS 有感（A 方案）。
    """

    def __init__(self):
        self.fail_by = defaultdict(int)   # feature_value -> 失敗次數
        self.total_by = defaultdict(int)  # feature_value -> 出現次數
        self.err_by = defaultdict(int)    # error_type -> 次數
        self.ground_prior = 0.1           # 全域基準失敗率（無任何訊號時的起點）

    def add_observation(self, feature: str, failed: bool):
        self.total_by[feature] += 1
        if failed:
            self.fail_by[feature] += 1

    def observe_mistake(self, error_type: str, domain: str, tulpa: str,
                        model: str = "", count: int = 1):
        """從 mistake_catalog 學：某領域+tulpa+model 近期犯過哪類錯（= 失敗訊號）。"""
        self.err_by[error_type] += count
        if domain:
            self.add_observation(f"domain:{domain}", failed=True)
        if tulpa:
            self.add_observation(f"tulpa:{tulpa}", failed=True)
        if model in KNOWN_MODELS:
            self.add_observation(f"model:{model}", failed=True)

    def observe_domain(self, path: str, hits: int, corrections: int):
        if hits > 0 and corrections > 0:
            self.add_observation(f"domain:{path}", failed=True)
            # 校正多的領域明顯高風險
        self.total_by[f"domain:{path}"] += hits

    def observe_decision(self, route: str, success: int, model: str = ""):
        failed = (success == 0)
        self.add_observation(f"route:{route}", failed=failed)
        if model in KNOWN_MODELS:
            self.add_observation(f"model:{model}", failed=failed)
        # 學習全域基準
        self.ground_prior = 0.85 * self.ground_prior + 0.15 * (1 if failed else 0)

    # ── 預測核心 ──
    def predict(self, domain: str | None, tulpa: str | None, route: str | None,
                model: str | None = None) -> float:
        """回傳 P(失敗) ∈ [0,1]。沒見過的輸入用先驗平滑。"""
        # 收集相關特徵 + 各自平滑後失敗率
        probs = []
        weights = []
        features = []
        if domain:
            features.append(f"domain:{domain}")
        if tulpa:
            features.append(f"tulpa:{tulpa}")
        if route:
            features.append(f"route:{route}")
        if model and model in KNOWN_MODELS:
            features.append(f"model:{model}")

        if not features:
            return self.ground_prior

        for f in features:
            total = self.total_by[f]
            fail = self.fail_by[f]
            # Laplace 平滑: (fail + α·prior)/(total + α)
            p = (fail + ALPHA * self.ground_prior) / max(total + ALPHA, 1e-9)
            probs.append(p)
            # 權重 = 證據量: 觀測越多的特徵越可信（避免 1/1 壓過 0/28）
            weights.append(total)

        # 依證據量的貝氏模型平均（不是 max——避免單一少量樣本支配）
        wsum = sum(weights) or 1.0
        return sum(p * w for p, w in zip(probs, weights)) / wsum

    def explain(self, domain, tulpa, route=None) -> str:
        bits = []
        d = f"domain:{domain}" if domain else None
        t = f"tulpa:{tulpa}" if tulpa else None
        r = f"route:{route}" if route else None
        for lbl, key in [("領域", d), ("tulpa", t), ("route", r)]:
            if not key:
                continue
            total = self.total_by[key]
            fail = self.fail_by[key]
            bits.append(f"{lbl}「{key.split(':')[-1]}」歷史{fail}/{total} 失敗")
        if not bits:
            return "無任何直接歷史訊號 → 回退全域先驗"
        return "，".join(bits)


def _load_model():
    m = FailureModel()
    tc = _conn(TULPA_DB)
    ac = _conn(ARIS_DB)

    # mistake_catalog: 高風險訊號（重複觸發 = 反覆失敗），帶 model
    for r in tc.execute("SELECT error_type, domain_path, tulpa_name, model, triggered_count FROM mistake_catalog"):
        m.observe_mistake(r["error_type"], r["domain_path"] or "", r["tulpa_name"] or "",
                           r["model"] or "", r["triggered_count"])

    # mistake_outcome: 真實 label（人類/工具裁定）——閉環核心
    #   recurred(再犯) → 高風險；avoided(已避免) → 低風險
    for r in tc.execute("""
        SELECT o.outcome, o.evidence, cat.domain_path, cat.tulpa_name, cat.model
        FROM mistake_outcome o
        JOIN mistake_catalog cat ON cat.id = o.mistake_id
    """):
        dom = r["domain_path"] or ""
        tul = r["tulpa_name"] or ""
        mdl = r["model"] or ""
        if r["outcome"] == "recurred":
            m.observe_mistake("marked_recurred", dom, tul, mdl, 2)  # 加權 2：再犯是強訊號
        elif r["outcome"] == "avoided":
            # 已避免 → 在同一 domain/tulpa 加「成功觀測」，壓低失敗率
            m.add_observation(f"domain:{dom}", failed=False) if dom else None
            m.add_observation(f"tulpa:{tul}", failed=False) if tul else None
            if mdl in KNOWN_MODELS:
                m.add_observation(f"model:{mdl}", failed=False)

    # domain_optimization: 命中 vs 校正 → 失敗率
    for r in tc.execute("SELECT path, total_hits, corrections FROM domain_optimization"):
        if r["total_hits"] > 0:
            m.observe_domain(r["path"], r["total_hits"], r["corrections"] or 0)

    # decision_log: route 成功率
    for r in ac.execute("SELECT route, success, count(*) c FROM decision_log GROUP BY route, success"):
        for _ in range(r["c"]):
            m.observe_decision(r["route"], r["success"])

    tc.close(); ac.close()
    return m


def cmd_report():
    """v1 保留：事後統計盤點。"""
    tc = _conn(TULPA_DB); ac = _conn(ARIS_DB)
    print("="*60); print("失敗訊號源盤點（事後統計，v1）"); print("="*60)
    mlist = tc.execute("SELECT error_type, triggered_count FROM mistake_catalog").fetchall()
    print(f"\nmistake_catalog: {len(mlist)} 筆")
    v_all = tc.execute("SELECT count(*) c FROM verification_log").fetchone()["c"]
    v_p = tc.execute("SELECT count(*) c FROM verification_log WHERE verdict='pending'").fetchone()["c"]
    print(f"verification_log: {v_all} 筆, 已判決 {v_all-v_p}, 僵屍(pending) {v_p}")
    if v_p == v_all and v_all > 0:
        print("  ⚠️ learning rate=0 根因: 驗收端沒在判, 所有 label 卡 pending")
    alerts = tc.execute("SELECT count(*) c FROM observer_insights").fetchone()["c"]
    print(f"observer_insights: {alerts} 筆")
    tc.close(); ac.close()


def cmd_predict(m, domain, tulpa, route, model=None):
    risk = m.predict(domain, tulpa, route, model if model in KNOWN_MODELS else None)
    if risk >= 0.5:
        tag = "🔴 高風險"
    elif risk >= 0.3:
        tag = "🟡 中風險"
    else:
        tag = "🟢 低風險"
    print(f"輸入 S=[domain={domain or '-'} | tulpa={tulpa or '-'} | route={route or '-'}]")
    print(f"  → P(失敗) = {risk:.2f}  {tag}")
    print(f"  依據: {m.explain(domain, tulpa, route)}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("report")
    p = sub.add_parser("predict")
    p.add_argument("--domain")
    p.add_argument("--tulpa")
    p.add_argument("--route")
    p.add_argument("--model", default=None)
    args = ap.parse_args()

    if args.cmd == "report" or not args.cmd:
        cmd_report()
        return
    if args.cmd == "predict":
        m = _load_model()
        cmd_predict(m, args.domain, args.tulpa, args.route, args.model)


if __name__ == "__main__":
    main()