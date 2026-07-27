#!/usr/bin/env python3
"""memcheck.py — 記憶層健康檢查（純唯讀）

topology.yaml 驗「邊通不通」，drift.py 驗「上游動了沒」，
這支驗「記憶層裡面到底長什麼樣」。

為什麼需要：記憶層是唯一「會自己長大」的部分。邊可以 probe，
碼可以 diff，但「152 筆記憶裡有幾筆是可信的」只能算。
算出來才知道 confidence 閘 / salience 閘該不該做、做了有沒有效。

⚠️ 全程唯讀（sqlite mode=ro）。不寫、不改、不搶 :11551 的鎖。

用法：
    memcheck.py           # 人看
    memcheck.py --json    # 機器讀

exit 1 = 有紅燈。
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

DB = Path.home() / ".aris-memory.db"
GBRAIN = Path.home() / "gbrain"


def q(con, sql):
    try:
        return con.execute(sql).fetchall()
    except Exception:
        return []


def analyze() -> dict:
    if not DB.exists():
        return {"error": f"找不到 {DB}"}

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    out: dict = {"db": str(DB), "checks": []}

    total = q(con, "SELECT COUNT(*) FROM memories")[0][0]
    out["total"] = total
    out["by_source"] = dict(q(con, "SELECT source,COUNT(*) FROM memories GROUP BY source"))
    out["by_confidence"] = dict(q(con, "SELECT confidence,COUNT(*) FROM memories GROUP BY confidence"))
    out["by_origin"] = dict(q(con, "SELECT origin,COUNT(*) FROM memories GROUP BY origin"))

    row = q(con, """SELECT
        SUM(CASE WHEN total_recalls>0 THEN 1 ELSE 0 END),
        SUM(CASE WHEN discovered_salience>0 THEN 1 ELSE 0 END),
        SUM(CASE WHEN attention_line!='' THEN 1 ELSE 0 END),
        SUM(synced_to_gbrain), SUM(flagged),
        SUM(CASE WHEN encoding_salience>0 THEN 1 ELSE 0 END),
        SUM(CASE WHEN provenance!='' THEN 1 ELSE 0 END)
        FROM memories""")[0]
    recalled, ds, attn, synced, flagged, enc_sal, prov = [x or 0 for x in row]
    out.update({"recalled": recalled, "ds_gt0": ds, "attention_line": attn,
                "synced_to_gbrain": synced, "flagged": flagged,
                "encoding_salience_set": enc_sal, "has_provenance": prov})

    span = q(con, "SELECT MIN(created_at),MAX(created_at) FROM memories")[0]
    out["span_days"] = round((span[1] - span[0]) / 86400, 1) if span[0] else 0

    C = out["checks"].append

    # 1. confidence 全黃 = 閘沒在動
    y = out["by_confidence"].get("yellow", 0)
    if y == total and total:
        C({"id": "confidence_all_yellow", "level": "red",
           "msg": f"全部 {total} 筆都是 yellow，green/red 各 0 筆",
           "why": "寫入端硬閘有上（三欄都在），但四繩計算沒接 → 沒有任何記憶被判定為事實。"
                  "檢索時無法分辨『查證過的』和『推測的』。",
           "fix": "causal.yaml → confidence-gate（槓桿榜第 1 名，解鎖 5 個下游）"})
    else:
        C({"id": "confidence_all_yellow", "level": "ok",
           "msg": f"confidence 有分佈：{out['by_confidence']}"})

    # 2. origin 全 auto = 沒有人類錨點
    a = out["by_origin"].get("auto_generated", 0)
    if a == total and total:
        C({"id": "origin_all_auto", "level": "red",
           "msg": f"全部 {total} 筆 origin=auto_generated，human 0 筆",
           "why": "沒有任何記憶標記為人類來源。AI 自己講的和 Ryan 講的在庫裡等價 → "
                  "自我強化風險：Aris 可能把自己的推測當成你的意見。",
           "fix": "relay/bridge 寫入時，人類輸入標 origin=human"})
    else:
        C({"id": "origin_all_auto", "level": "ok",
           "msg": f"origin 有分佈：{out['by_origin']}"})

    # 3. gbrain 同步
    n_gb = len(list(GBRAIN.rglob("*.md"))) if GBRAIN.exists() else 0
    out["gbrain_md_files"] = n_gb
    if synced == 0 and total:
        C({"id": "gbrain_never_synced", "level": "red",
           "msg": f"synced_to_gbrain 全為 0（{total} 筆都沒同步），"
                  f"而 gbrain 有 {n_gb} 個 md",
           "why": "L3 長期記憶（SQLite）與 L2 語意記憶（gbrain）是兩個孤島。"
                  "海馬→皮質的升格路徑實際上沒有在跑。",
           "fix": "causal.yaml → 固化cron（被 confidence-gate 卡住）"})
    else:
        C({"id": "gbrain_never_synced", "level": "ok",
           "msg": f"已同步 {synced}/{total} 筆"})

    # 4. provenance
    if prov == 0 and total:
        C({"id": "no_provenance", "level": "yellow",
           "msg": f"provenance 全空（{total} 筆）",
           "why": "schema 註解寫『指不回 → 應為 red』，但全部都是 yellow。"
                  "規則宣告了沒執行。",
           "fix": "寫入端補 provenance，或讓無 provenance 者自動降 red"})
    else:
        C({"id": "no_provenance", "level": "ok", "msg": f"{prov}/{total} 筆有 provenance"})

    # 5. recall 健康（這個是好消息）
    if total:
        rate = round(recalled / total * 100)
        lv = "ok" if recalled else "yellow"
        C({"id": "recall_alive", "level": lv,
           "msg": f"{recalled}/{total}（{rate}%）被召回過，ds>0 有 {ds} 筆",
           "why": "recalled 與 ds_gt0 數字一致 → discovered_salience 只由真 recall 賺到，"
                  "沒有自我膨脹。這正是 topology.yaml 的 recall_not_selfinflated 契約。"})

    # 6. attention_line
    if total:
        rate = round(attn / total * 100)
        C({"id": "attention_line", "level": "ok" if rate >= 50 else "yellow",
           "msg": f"{attn}/{total}（{rate}%）有 attention_line",
           "why": "乙的種子 — 醒來暖啟動讀這欄。覆蓋率越高，跨 session 接續越順。"})

    con.close()
    return out


LV = {"ok": "🟢", "yellow": "🟡", "red": "🔴"}


def main() -> int:
    d = analyze()
    if "error" in d:
        print(f"❌ {d['error']}")
        return 2

    if "--json" in sys.argv[1:]:
        print(json.dumps(d, ensure_ascii=False, indent=2))
    else:
        print("\n" + "=" * 58)
        print("  記憶層健康檢查（唯讀）")
        print("=" * 58)
        print(f"\n{d['total']} 筆記憶 · 跨 {d['span_days']} 天 · "
              f"gbrain {d.get('gbrain_md_files', '?')} 個 md")
        print(f"\n來源分佈：{d['by_source']}")
        print(f"信心分佈：{d['by_confidence']}")
        print(f"出處分佈：{d['by_origin']}")
        print()
        for c in d["checks"]:
            print(f"{LV[c['level']]} {c['id']}")
            print(f"   {c['msg']}")
            if c.get("why"):
                print(f"   → {c['why']}")
            if c.get("fix"):
                print(f"   修法：{c['fix']}")
            print()
        reds = [c for c in d["checks"] if c["level"] == "red"]
        if reds:
            print(f"⚠️  {len(reds)} 個紅燈。共同點：**閘宣告了但沒接線**。")
            print("   schema 欄位都在（有人設計過），但沒有邏輯在填 →")
            print("   記憶在長，但沒有品質分級。這就是 confidence-gate 為何是第 1 槓桿。")
        print()
    return 1 if any(c["level"] == "red" for c in d["checks"]) else 0


if __name__ == "__main__":
    sys.exit(main())
