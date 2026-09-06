#!/usr/bin/env python3
"""
audit-cost-asymmetry-engine.py
完整的5項排查引擎：掃描 → 五層審查 → 工作日誌 → 基因壓縮 → 前三名通報

使用方式：
  python3 audit-cost-asymmetry-engine.py scan [limit]   # 掃描審計日誌
  python3 audit-cost-asymmetry-engine.py compress        # 壓縮工作日誌為基因
  python3 audit-cost-asymmetry-engine.py top3            # 選前三名輸出報告
  python3 audit-cost-asymmetry-engine.py all [limit]     # scan → compress → top3
"""

import json
import os
import sys
import time
import hashlib
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

NEURALIS_HOME = Path.home() / "Developer/neuralis"
AUDIT_LOG = NEURALIS_HOME / "agency-audit.jsonl"
WORK_LOG = NEURALIS_HOME / "data/work-log.jsonl"
GENE_DIR = NEURALIS_HOME / "data/genes"
REPORT_DIR = NEURALIS_HOME / "data/reports"

# ─── 1. 五層審查引擎 ───

def five_layer_audit(entry: dict) -> dict:
    """對單筆審計紀錄進行五層機械審查，回傳審查結果"""
    prompt = entry.get("prompt", "")
    ok = entry.get("ok", True)
    outcome = entry.get("outcome", 0.0)
    expected = entry.get("expected", 0.0)
    drive = entry.get("drive", 0.0)
    tool = entry.get("tool", "")

    # 計算成本不對稱分數 (0~1, 越高越可疑)
    # 條件：高驅動 + 低回報 = 自信但假的
    # 條件：宣稱成功 (ok=true) 但 outcome 低於預期
    rpe = outcome - expected
    if ok and rpe < -0.2:
        asymmetry_score = min(1.0, (drive * 0.5) + (abs(rpe) * 0.5))
    elif not ok and drive > 0.5:
        asymmetry_score = min(1.0, drive * 0.8)
    else:
        asymmetry_score = 0.0

    layers = {}
    
    # 鋼人: 最強的反對論證
    steelman_clues = []
    if ok and rpe < -0.3:
        steelman_clues.append("宣稱成功但獎勵顯著低於預期，可能為假性完成")
    if not ok:
        steelman_clues.append("任務失敗但未被追究，可能被系統忽略")
    if drive > 0.8 and not ok:
        steelman_clues.append("高驅動但執行失敗，可能是認知負載過高或幻覺")
    layers["steelman"] = steelman_clues if steelman_clues else ["無顯著反對論證"]

    # 紅軍: 對手如何利用
    redteam_clues = []
    if tool == "http-get" and not ok:
        redteam_clues.append("HTTP 請求失敗可被用來偽造外部連通性")
    if ok and rpe < -0.2:
        redteam_clues.append("假性通過可累積虛假信心，影響後續決策")
    if asymmetry_score > 0.5:
        redteam_clues.append(f"成本不對稱分數 {asymmetry_score:.2f}，易於偽造證據")
    layers["redteam"] = redteam_clues if redteam_clues else ["無顯著攻擊面"]

    # Ponytail: 最簡單的解釋
    ponytail_clues = []
    if not ok:
        ponytail_clues.append("最簡單的解釋：工具呼叫失敗，未重試")
    if ok and rpe < -0.2:
        ponytail_clues.append("最簡單的解釋：結果被誇大或回報機制不準確")
    layers["ponytail"] = ponytail_clues if ponytail_clues else ["任務如預期執行"]

    # 剃刀: 不必要的假設
    razor_clues = []
    if drive > 0.9:
        razor_clues.append("高驅動假設：Agent 的自信未必反映真實品質")
    if not ok and entry.get("result_len", 0) > 0:
        razor_clues.append("有結果但標記為失敗：二值分類過度簡化")
    layers["razor"] = razor_clues if razor_clues else ["無顯著多餘假設"]

    # 陰陽眼: 相反角度
    yinyang_clues = []
    if ok:
        yinyang_clues.append("相反角度：成功是否只是沒有觸發錯誤條件？")
    if not ok:
        yinyang_clues.append("相反角度：失敗是否其實提供了有價值的負面資訊？")
    if asymmetry_score > 0.3:
        yinyang_clues.append("相反角度：這個任務是否根本不該由 AI 執行？")
    layers["yinyang"] = yinyang_clues if yinyang_clues else ["考慮任務本身是否必要"]

    return {
        "asymmetry_score": round(asymmetry_score, 3),
        "rpe": round(rpe, 3),
        "layers": layers,
        "suspicious": asymmetry_score > 0.3
    }


# ─── 2. 掃描審計日誌 → 工作日誌 ───

def get_entry_fingerprint(entry: dict) -> str:
    """為審計條目生成指紋，用於去重"""
    key = f"{entry.get('ts', '')}:{entry.get('prompt', '')}:{entry.get('tool', '')}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def load_work_log_fingerprints() -> set:
    """載入工作日誌中已有的指紋，用於去重"""
    fps = set()
    if WORK_LOG.exists():
        with open(WORK_LOG, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        if "fingerprint" in entry:
                            fps.add(entry["fingerprint"])
                    except json.JSONDecodeError:
                        continue
    return fps


def scan(limit: int = 100):
    """掃描審計日誌，找出可疑條目並寫入工作日誌"""
    if not AUDIT_LOG.exists():
        print(f"[ERROR] 審計日誌不存在: {AUDIT_LOG}")
        return

    existing_fps = load_work_log_fingerprints()
    new_count = 0
    total_entries = 0

    with open(AUDIT_LOG, "r") as f:
        lines = f.readlines()

    # 從最新往舊掃描
    for line in reversed(lines[-limit:]):
        line = line.strip()
        if not line:
            continue
        total_entries += 1
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        fp = get_entry_fingerprint(entry)
        if fp in existing_fps:
            continue

        result = five_layer_audit(entry)

        if not result["suspicious"]:
            continue

        work_entry = {
            "fingerprint": fp,
            "timestamp": entry.get("ts", time.time()),
            "prompt": entry.get("prompt", "")[:200],
            "tool": entry.get("tool", ""),
            "ok": entry.get("ok", None),
            "outcome": entry.get("outcome", 0.0),
            "expected": entry.get("expected", 0.0),
            "asymmetry_score": result["asymmetry_score"],
            "rpe": result["rpe"],
            "audit": result["layers"],
            "status": "open",
            "resolved": False
        }

        with open(WORK_LOG, "a") as wf:
            wf.write(json.dumps(work_entry, ensure_ascii=False) + "\n")
        new_count += 1
        existing_fps.add(fp)

    print(f"[SCAN] 檢查 {total_entries} 條，新增 {new_count} 條可疑記錄")


# ─── 3. 壓縮工作日誌 → 認知基因 ───

def compress():
    """掃描工作日誌，將重複失敗模式壓縮為認知基因"""
    if not WORK_LOG.exists():
        print("[COMPRESS] 工作日誌不存在")
        return

    # 讀取所有 open 狀態的條目
    entries = []
    with open(WORK_LOG, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    # 按工具分群
    by_tool = defaultdict(list)
    for e in entries:
        by_tool[e.get("tool", "unknown")].append(e)

    genes_created = 0
    for tool, items in by_tool.items():
        if len(items) < 2:
            continue  # 少於2次不構成模式

        # 計算平均不對稱分數
        avg_score = sum(item.get("asymmetry_score", 0) for item in items) / len(items)

        # 收集所有層的警告
        all_layer_s = set()
        for item in items:
            for layer, clues in item.get("audit", {}).items():
                for clue in clues:
                    all_layer_s.add(clue)

        if avg_score < 0.3:
            continue  # 不對稱不夠高
        
        now_ts = time.time()
        gene_path = GENE_DIR / f"{tool}.json"
        
        # 演化規則1：讀取舊基因，triggered_by 只增不減
        prev_triggered = 0
        if gene_path.exists():
            try:
                old = json.loads(gene_path.read_text())
                prev_triggered = old.get("triggered_by", 0)
            except (json.JSONDecodeError, IOError):
                pass
        
        gene = {
            "gene_id": f"G-{int(now_ts)}-{tool}",
            "tool": tool,
            "triggered_by": max(len(items), prev_triggered),  # 永不倒退
            "avg_asymmetry_score": round(avg_score, 3),
            "defense": f"工具 {tool} 有 {max(len(items), prev_triggered)} 次可疑紀錄，平均不對稱 {avg_score:.2f}。必須強制外部驗證。",
            "sitting_to": list({item.get("fingerprint", "") for item in items}),
            "created_at": datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat(),
            "last_seen": datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()  # 演化：時間戳
        }

        # 寫入基因檔
        GENE_DIR.mkdir(parents=True, exist_ok=True)
        with open(gene_path, "w") as gf:
            json.dump(gene, gf, indent=2, ensure_ascii=False)
        genes_created += 1

        # 將這些條目標記為 resolved
        resolved_fps = {item.get("fingerprint") for item in items}
        resolved_entries = []
        with open(WORK_LOG, "r") as rf:
            for line in rf:
                line = line.strip()
                if line:
                    try:
                        e = json.loads(line)
                        if e.get("fingerprint") in resolved_fps:
                            e["resolved"] = True
                            e["status"] = "compressed"
                        resolved_entries.append(e)
                    except json.JSONDecodeError:
                        continue

        with open(WORK_LOG, "w") as wf:
            for e in resolved_entries:
                wf.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(f"[COMPRESS] 壓縮完成，產生 {genes_created} 個認知基因")

    # 演化規則3：清除超過 7 天未更新的基因（衰減）
    now_ts = time.time()
    purged = 0
    for gene_file in GENE_DIR.glob("*.json"):
        try:
            g = json.loads(gene_file.read_text())
            last_seen_str = g.get("last_seen") or g.get("created_at", "")
            if last_seen_str:
                last_seen = datetime.fromisoformat(last_seen_str).timestamp()
                age_days = (now_ts - last_seen) / 86400
                if age_days > 7:
                    gene_file.unlink()
                    purged += 1
        except (json.JSONDecodeError, IOError, ValueError):
            continue
    if purged:
        print(f"[PURGE] 已清除 {purged} 個過期基因（>7天未更新）")


# ─── 4. 挑選前三名重大創舉 ──

def top3():
    """從認知基因和工作日誌中挑選前三名，產生報告"""
    GENE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # 讀取所有基因
    genes = []
    if GENE_DIR.exists():
        for f in GENE_DIR.glob("*.json"):
            try:
                genes.append(json.loads(f.read_text()))
            except (json.JSONDecodeError, IOError):
                continue

    # 按 triggered_by 排序（影響範圍最大的在前）
    genes.sort(key=lambda g: g.get("triggered_by", 0), reverse=True)
    top = genes[:3]

    # 讀取工作日誌統計
    open_count = 0
    compressed_count = 0
    if WORK_LOG.exists():
        with open(WORK_LOG, "r") as f:
            for line in f:
                if "status" in line:
                    if '"open"' in line:
                        open_count += 1
                    elif '"compressed"' in line:
                        compressed_count += 1

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "genes_total": len(genes),
            "work_log_open": open_count,
            "work_log_compressed": compressed_count
        },
        "top3": [
            {
                "rank": i + 1,
                "gene_id": g.get("gene_id", "unknown"),
                "tool": g.get("tool", "unknown"),
                "triggered_by": g.get("triggered_by", 0),
                "avg_asymmetry_score": g.get("avg_asymmetry_score", 0),
                "defense": g.get("defense", "")
            }
            for i, g in enumerate(top)
        ]
    }

    # 寫入報告
    report_path = REPORT_DIR / f"top3-{datetime.now().strftime('%Y%m%d')}.json"
    with open(report_path, "w") as rf:
        json.dump(report, rf, indent=2, ensure_ascii=False)

    print(f"[TOP3] 報告已寫入 {report_path}")
    for item in report["top3"]:
        print(f"  #{item['rank']} {item['gene_id']}: {item['tool']} x{item['triggered_by']} 次 | 不對稱 {item.get('avg_asymmetry_score', 0)}")


# ─── 5. 全部管線 －─

def all_pipeline(limit: int = 200):
    print("=" * 50)
    print(f"成本不對稱審計管線 ({datetime.now().isoformat()})")
    print("=" * 50)
    scan(limit=limit)
    compress()
    top3()
    print("=" * 50)
    print("管線完成")


# ── 主入口 ──

if __name__ == "__main__":
    GENE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if len(sys.argv) < 2:
        print("使用: python3 audit-cost-asymmetry-engine.py [scan|compress|top3|all] [limit]")
        sys.exit(1)

    action = sys.argv[1]
    limit_arg = int(sys.argv[2]) if len(sys.argv) > 2 else 200

    if action == "scan":
        scan(limit=limit_arg)
    elif action == "compress":
        compress()
    elif action == "top3":
        top3()
    elif action == "all":
        all_pipeline(limit=limit_arg)
    else:
        print(f"未知動作: {action}")
        sys.exit(1)