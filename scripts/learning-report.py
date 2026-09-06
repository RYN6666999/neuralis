#!/usr/bin/env python3
"""
learning-report.py — 成長曲線日報（C：掛進既有晨報，不新建 daemon）

輸出 Aris 的「學習」狀態（不是健康狀態，健康由 aris-growth-check 負責）：
  1. learning rate 是否 > 0（有沒有 label 流進來）
  2. 各錯誤類型的風險趨勢（世界模型今日 vs 上次）
  3. 最高風險教訓（看完該警惕什麼）

用法：
  python3 scripts/learning-report.py            # 完整 Markdown 報告
  python3 scripts/learning-report.py --short    # 一行摘要（可嵌入 status）
"""
import argparse, sqlite3, json, datetime
from pathlib import Path

HOME = Path.home()
TULPA_DB = HOME / "Developer/neuralis/data/tulpa_memory.db"
STATE_FILE = HOME / "Developer/neuralis/data/learning-curve.json"


def _conn():
    c = sqlite3.connect(f"file:{TULPA_DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def _snapshot():
    """抓取當前世界模型/學習迴路的關鍵狀態，儲存供隔日比對。"""
    db = _conn()
    snap = {
        "ts": datetime.datetime.now().isoformat(),
        "mistakes": {},           # error_type -> 風險權重(觸發次數+outcome)
        "labels": {"avoided": 0, "recurred": 0, "unverifiable": 0},
        "verdicts": {},
        "learning_alive": False,  # 有 label 或判決 = learning rate > 0
    }
    # mistakes + outcomes
    for r in db.execute("""
        SELECT cat.error_type, cat.triggered_count, COALESCE(o.outcome,'') oc
        FROM mistake_catalog cat
        LEFT JOIN (SELECT mistake_id, outcome, MAX(id) mo FROM mistake_outcome GROUP BY mistake_id) o
          ON o.mistake_id = cat.id
    """):
        snap["mistakes"][r["error_type"]] = snap["mistakes"].get(r["error_type"], 0) + r["triggered_count"]
        if r["oc"]:
            snap["labels"][r["oc"]] = snap["labels"].get(r["oc"], 0) + 1
    # verdicts
    for r in db.execute("SELECT verdict, count(*) c FROM verification_log GROUP BY verdict"):
        snap["verdicts"][r["verdict"]] = r["c"]
    snap["learning_alive"] = (sum(snap["labels"].values()) > 0 or
                              snap["verdicts"].get("verified", 0) > 0)
    db.close()
    # 存上次快照（本次變成本次的 baseline）
    return snap


def _delta(prev, cur):
    """對比兩次快照，抓出「改變」——成長的證據。"""
    if not prev:
        return None
    delta = {}
    # label 變化
    for k in ("avoided", "recurred"):
        d = cur["labels"].get(k, 0) - prev["labels"].get(k, 0)
        if d != 0:
            delta[f"建置label.{k}"] = f"{d:+d}"
    # 錯誤趨勢
    for k, v in cur["mistakes"].items():
        pv = prev["mistakes"].get(k, 0)
        if v > pv:
            delta[f"error.{k}"] = f"v{pv}→{v} (+{v-pv})"
    # verdicts
    for k, v in cur["verdicts"].items():
        pv = prev["verdicts"].get(k, 0)
        if v > pv:
            delta[f"verdict.{k}"] = f"+{v-pv}"
    return delta


def report(short=False):
    db = _conn()

    # 載入先前快照做對比
    prev = None
    if STATE_FILE.exists():
        try:
            prev = json.loads(STATE_FILE.read_text())
        except Exception:
            prev = None
    cur = _snapshot()
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(cur, ensure_ascii=False, indent=2))
    delta = _delta(prev, cur)

    if short:
        alive = "學習迴路活著" if cur["learning_alive"] else "⚠️ learning rate=0 - 無label"
        first = f"[learning] {alive} | label: avoided={cur['labels']['avoided']} recurred={cur['labels']['recurred']}"
        if delta:
            first += " | 今日變化:" + " ".join(f"{k}{v}" for k, v in delta.items())
        print(first)
        db.close()
        return

    print("# Aris 學習曲線日報")
    print(f"\n_生成 {cur['ts']}_")
    print("\n## 1. Learning Rate 狀態")
    if cur["learning_alive"]:
        print("✅ **learning rate > 0** — 有真實 label 流進世界模型")
    else:
        print("🔴 **learning rate = 0** — 沒有 label。\n\n> 這是「永遠不會判斷」的根因。必須有真人/工具把 `mistake_outcome` 標成 avoided/recurred，或用 `label-adapter verdict-from-tools` 判 pending claims。")
    print(f"\n- mistake_outcome: avoided={cur['labels']['avoided']}, recurred={cur['labels']['recurred']}, unverifiable={cur['labels'].get('unverifiable',0)}")
    print(f"- verification_log: " + ", ".join(f"{k}={v}" for k, v in cur["verdicts"].items()))

    print("\n## 2. 錯誤風險趨勢")
    if cur["mistakes"]:
        for k, v in sorted(cur["mistakes"].items(), key=lambda x: -x[1]):
            print(f"- 🔴 `{k}` 風險權重={v}")
    else:
        print("- （無已記錄錯誤）")

    print("\n## 3. 今日成長證據")
    if delta:
        for k, v in delta.items():
            print(f"- `{k}` {v}")
    else:
        print("- 無變化（這輪沒有新 label / 新錯誤 / 新判決）")

    print("\n## 4. 操作指引")
    print("- 標記錯誤避免/再犯：`label-adapter mark --mistake-id N --outcome avoided|recurred`")
    print("- 判 pending claims：`label-adapter verdict-from-tools`")

    db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--short", action="store_true")
    args = ap.parse_args()
    report(short=args.short)