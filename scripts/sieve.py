#!/usr/bin/env python3
"""
sieve.py — 層層沙漏：把「已標記對錯」的糾錯語料篩成教訓，漏進 mistake_catalog（Q1 scope）

原理（層層沙漏 / 大數據洗練）：
  砂塘(頂層) = 所有「已知對錯」的糾錯事件
     │  篩層1: 聚類成「家族」  → 反覆出現的錯誤類別
     │  篩層2: 家族→教訓       → 每個家族提煉一句「可動作 lesson」
     v  篩層3: 寫入 mistake_catalog → 接 fail-predictor 世界模型 → 影響 tulpa 加權
  精砂(底) = 系統真的在用的教訓

鐵則（遵循 codebase-design-audit 閉環 + breeding 陷阱11）：
  - 只吃「系統/你已標記對錯」的料（dbp fix 配對、decision success、mistake outcome）
  - 不做「沒標籤料的硬判」（那會污染世界模型訓練）
  - dbp 的 bug(114筆) 多數是機器噪音，不量；open+done 配對(24筆) 才是真值源

用法：
  python3 scripts/sieve.py                    # 完整: 過篩+聚類+提煉+寫入
  python3 scripts/sieve.py report             # 只看會篩出什麼, 不寫入
  python3 scripts/sieve.py --dry-run          # 同 report
"""
import argparse, sqlite3, json, glob, re, datetime
from pathlib import Path
from collections import defaultdict

HOME = Path.home()
DEBUGPEDIA = HOME / ".debugpedia"
TULPA_DB = HOME / "Developer/neuralis/data/tulpa_memory.db"

# ── 家族指紋：從事件 wha/t 抽「錯誤類別關鍵字」 → 家族名 ──
# 刻意用可解釋的規則聚類（bread 陷阱4：小數據別過度工程）。足量後再上 embedding。
_FAMILY_RULES = [
    (re.compile(r"hook|pre_llm|post_llm|shell_hook", re.I), "harness/hook 管線"),
    (re.compile(r"exit=(1|2|137)|nonzero|exit 1|指令失敗", re.I), "指令失敗/exit碼"),
    (re.compile(r"memory|記憶|recall|wake|11551", re.I), "記憶系統"),
    (re.compile(r"tulpa|18428|競爭|weight|migration", re.I), "tulpa競爭/權重"),
    (re.compile(r"psi|情緒|需求|attention|11546", re.I), "PSI/情緒引擎"),
    (re.compile(r"confirm|確認|loop|重複|重疊|duplicate", re.I), "確認循環/重複"),
    (re.compile(r"domain|領域|wrong_domain|route", re.I), "領域路由"),
    (re.compile(r"verif|驗證|claim|audit|審計|鋼人|ponytail", re.I), "驗證/審計"),
    (re.compile(r"cron|launchd|plist|schedule|排程|daemon|probe", re.I), "排程/常駐"),
    # 補: 從 tags + 語意讓未分類 13 筆歸隊（避免 embedding over-engineering）
    (re.compile(r"iron-law|ag\.md|AGENTS\.md|地圖不是狀態|三鐵律|§現況|stale-checkout|checkout", re.I), "法條/文件校準"),
    (re.compile(r"metric|converge|convergence|閘門|gate|指標|發散|收斂", re.I), "指標/收斂度量"),
    (re.compile(r"relay|history|回放|board_to_channel|channel_to_aris|task-executor", re.I), "資料通道/中繼"),
    (re.compile(r"branch|分支|git", re.I), "git/分支管理"),
    (re.compile(r"stale|過期|overdue|超齡|落後", re.I), "過期/落後狀態"),
    (re.compile(r"architecture|架構|設計", re.I), "架構設計"),
]

def _all_dbp():
    """讀所有 dbp 週檔 → 列出 bug/open/done。"""
    rows=[]
    for f in glob.glob(str(DEBUGPEDIA / "2026-W*.jsonl")):
        for line in open(f, encoding="utf-8"):
            line=line.strip()
            if not line: continue
            try: rows.append(json.loads(line))
            except: continue
    return rows

def _family(text, tags=""):
    """從事件內容聚類到家族。回 (家族名, 是否命中)。"""
    src = f"{text} {tags}"
    for rx, name in _FAMILY_RULES:
        if rx.search(src):
            return name, True
    return "未分類", False

def _sieve(rows):
    """篩層1+2：把有修正史的 open+done 配對聚類成家族, 每家族提煉教訓。"""
    # 建立 closes→done 對應
    dones = {d.get("closes"): d for d in rows if d.get("kind")=="done" and d.get("closes")}
    # 只取「有 done 修正」的 open（= 已知對錯的真值源）
    family_cnt = defaultdict(int)
    family_lessons = defaultdict(list)
    for r in rows:
        if r.get("kind")!="open": continue
        rid = r["id"]
        if rid not in dones: continue  # 沉默拋棄：沒修正史 = 沒 ground truth
        fam, hit = _family(r.get("what","") or "", r.get("tags",""))
        family_cnt[fam]+=1
        fix_what = dones[rid].get("what","")
        family_lessons[fam].append(fix_what[:120])
    # 提煉教訓：每個家族取記錄數 + 多數人怎麼修
    lessons=[]
    for fam, cnt in family_cnt.items():
        if cnt < 1: continue
        fixs = family_lessons[fam]
        # 教訓 = 這個家族的人怎麼修的（取最短可動作, 去掉空）
        actionable = [f for f in fixs if len(f.strip())>4]
        lesson = actionable[0] if actionable else (fixs[0] if fixs else "")
        lessons.append({"family":fam, "count":cnt, "lesson":lesson})
    return lessons

def _report(lessons):
    print("="*60); print("沙漏: dbp 修正史 → 家族 → 教訓 (Q1 scope)"); print("="*60)
    rows = _all_dbp()
    opens=[r for r in rows if r.get("kind")=="open"]
    dones=[r for r in rows if r.get("kind")=="done"]
    pairing=sum(1 for o in opens if o["id"] in {d.get("closes") for d in dones if d.get("closes")})
    print(f"\ndbp 存量: bug={sum(1 for r in rows if r.get('kind')=='bug')} "
          f"open={len(opens)} done={len(dones)} 已配對={pairing}")
    print(f"\n篩出家族教訓: {len(lessons)} 個")
    for i,l in enumerate(lessons,1):
        print(f"\n  {i}. [{l['family']}] ×{l['count']}")
        print(f"     lesson: {l['lesson'][:90]}")
    return lessons

def _write(lessons):
    """篩層3: 把家族教訓寫入 mistake_catalog。
    - 新教訓: 家族名未對應 → 新增
    - 同步:   家族規則演進後, 該家族教訓若已不存在 → 從 catalog 移除（避免死教訓堆積）
    """
    db=sqlite3.connect(TULPA_DB)
    now=datetime.datetime.utcnow().isoformat()
    wrote=0; removed=0
    family_patterns = {l["family"] for l in lessons}
    for l in lessons:
        # family 名不變、lesson 已存在 → 跳過（不重複）
        exists=db.execute(
            "SELECT id FROM mistake_catalog WHERE input_pattern=?",
            (f"dbp-family#{l['family']}",)).fetchone()
        if exists:
            continue
        db.execute(
            "INSERT INTO mistake_catalog (input_pattern, error_type, domain_path, tulpa_name, lesson, triggered_count, last_triggered, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (f"dbp-family#{l['family']}", "family_pattern", "", "",
             l["lesson"], l["count"], now, now))
        wrote+=1
    # 淘汰: catalog 中所有 dbp-family 教訓, 若家族名已不在當下 rules → 移除
    family_rows=db.execute(
        "SELECT id, input_pattern FROM mistake_catalog WHERE error_type='family_pattern'").fetchall()
    for rid, pat in family_rows:
        fam = pat.replace("dbp-family#","")
        if fam not in family_patterns:
            db.execute("DELETE FROM mistake_catalog WHERE id=?", (rid,))
            removed+=1
    db.commit()
    db.close()
    print(f"\n✅ 寫入 mistake_catalog: {wrote} 條新教訓, 淘汰 {removed} 條過期家族教訓")
    return wrote

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只看不寫")
    args=ap.parse_args()
    rows=_all_dbp()
    lessons=_sieve(rows)
    if args.dry_run:
        _report(lessons)
    else:
        lessons=_report(lessons) if lessons else None
        _write(lessons or [])

if __name__=="__main__":
    main()