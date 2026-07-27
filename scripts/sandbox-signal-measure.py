#!/usr/bin/env python3
"""
sandbox-signal-measure.py — 沙箱 L1 第 2 步：量真 gbrain 信號變異。

在寫 A/B/C harness 之前先跑這個，回答：真 gbrain 對測試 topic 集，
角度間（作法 vs 經驗 vs bare）品質分數有沒有變異？無變異 → 停，不硬跑。

用 Aris 自己的 gbrain 工具 + agency._score_result（生產同路徑），
硬排除自寫記憶（_internal/、agency slug）。

判讀：每 topic 的「最佳角度 vs 次佳角度」平均分差。
  全部 < 0.1 → 無區辨信號 → 沙箱 L1 停跑（INCONCLUSIVE，信號問題非學習問題）。

用法:
    cd ~/Developer/neuralis
    PYTHONPATH=".:../laap-AGI" ../laapenv/bin/python scripts/sandbox-signal-measure.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TOPICS = [
    "postgres 索引", "pgvector 檢索", "embedding chunking", "MCP server",
    "docker 部署", "bun 打包", "RPE bandit 學習", "遞迴",
    "REST API 設計", "煎蛋",  # 煎蛋 = 負控制，應全低分
]
ANGLES = ["作法", "經驗", ""]   # "" = bare topic 對照
VARIANCE_THRESHOLD = 0.1        # 最佳 vs 次佳 < 此 → 該 topic 無區辨
SELF_SLUG_PAT = re.compile(r"_internal/|agency-state|_agency", re.I)


def strip_self_written(result: str) -> str:
    """硬排除 Aris 自寫記憶行（防自賺分/自我迴聲）。"""
    kept = [ln for ln in result.splitlines() if not SELF_SLUG_PAT.search(ln)]
    return "\n".join(kept)


def main():
    from laap.startup import startup_all
    from laap.agency import AgencyLoop
    bus, psi, tools = startup_all()
    scorer = AgencyLoop(psi=psi, tools=tools)

    print(f"{'topic':<22} " + " ".join(f"{a or 'bare':>8}" for a in ANGLES) + "   best-2nd")
    print("-" * 70)
    stopped = True
    rows = []
    for topic in TOPICS:
        scores = {}
        for angle in ANGLES:
            query = f"{topic} {angle}".strip()
            try:
                raw = tools.execute("gbrain", query) or ""
            except Exception as e:
                raw = ""
                print(f"  ⚠️ {query}: {e}", file=sys.stderr)
            clean = strip_self_written(raw)
            scores[angle] = scorer._score_result(clean, tool="gbrain", query=query)
        ordered = sorted(scores.values(), reverse=True)
        gap = (ordered[0] - ordered[1]) if len(ordered) > 1 else 0.0
        if gap >= VARIANCE_THRESHOLD:
            stopped = False
        rows.append((topic, scores, gap))
        cells = " ".join(f"{scores[a]:>8.3f}" for a in ANGLES)
        flag = "  ← 有區辨" if gap >= VARIANCE_THRESHOLD else ""
        print(f"{topic:<22} {cells}   {gap:>6.3f}{flag}")

    # 負控制檢查
    egg = dict(rows[-1][1])
    egg_max = max(egg.values())
    print("-" * 70)
    print(f"負控制「煎蛋」最高分 = {egg_max:.3f}"
          f"{'  ⚠️ 疑似 gbrain 亂碼高分（handoff 血訓）' if egg_max > 0.6 else '  ✅ 如預期偏低'}")
    n_discriminating = sum(1 for _, _, g in rows if g >= VARIANCE_THRESHOLD)
    print(f"\n有區辨 topic 數：{n_discriminating}/{len(TOPICS)}（閾值 {VARIANCE_THRESHOLD}）")
    if stopped:
        print("結論：全部 topic 無區辨信號 → 沙箱 L1 停跑（INCONCLUSIVE）。")
    else:
        print(f"結論：{n_discriminating} 個 topic 有區辨 → 可用這些跑 A/B/C harness。")


if __name__ == "__main__":
    main()
