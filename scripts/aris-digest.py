#!/usr/bin/env python3
"""aris-digest — 每天把 Aris 的對話壓成幾段，append 進一個有天花板的檔案。

設計原則（2026-08-19 Ryan 定調：減法不是加法）：
  - 不建第四個記憶庫。A 庫 / gbrain 降級為檔案櫃，不進 prompt。
  - 唯一進 prompt 的是 ARIS.md，**有硬性上限**。滿了強制重壓，
    每次都被迫做一次真取捨 —— 這是「噪音不可無限堆積」的機械保證，
    不靠評分演算法、不靠自律。
  - 格式對齊 ~/.hermes/memories/MEMORY.md：一段一件事，§ 分隔。
    Hermes 那份記事實，這份記關係/偏好/她自己的狀態。

用法：
    python3 scripts/aris-digest.py                # dry-run，只印
    python3 scripts/aris-digest.py --apply        # 寫入 ARIS.md
    python3 scripts/aris-digest.py --days 3       # 回頭補幾天
    python3 scripts/aris-digest.py --recompress   # 只跑重壓（測天花板）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

DB = os.environ.get("ARIS_MEMORY_DB", str(Path.home() / ".aris-memory.db"))
OUT = Path(os.environ.get("ARIS_DIGEST_PATH",
                          str(Path.home() / "Developer/neuralis/ARIS.md")))
CAP_BYTES = int(os.environ.get("ARIS_DIGEST_CAP", "4096"))   # 硬天花板
TARGET_BYTES = int(CAP_BYTES * 0.75)                          # 重壓後目標
SEP = "\n§\n"
HUMAN_SOURCES = ("hermes-cli", "webchat")

# ── 兩區結構（2026-08-19 加）────────────────────────────────
# 規則區 = Ryan 訓練 Aris 的成果，重壓時原樣搬過去，LLM 不准動。
# 近況區 = 一般記憶，會被壓縮合併淘汰。
RULE_HEADER = "== 規則（訓練成果，永不刪）=="
LANDMARK_HEADER = "== 印象深刻（情感地標，永不刪）=="
RECENT_HEADER = "== 近況（會壓縮）=="

# ── 情感地標（2026-08-19 借鑒 Lorry 的 laap_memory_hierarchy.py）────────
# 上游原設計：「不重要的記憶逐漸衰減，但被回憶過的、情感強烈的、
# 用戶明確標記重要的，被永久保存。你不會記得每天早餐吃什麼，
# 但你記得第一次遇見那個重要的人。」
# 上游那套實測已死（state/memory_hierarchy.json 停在 2026-08-10，
# 長期事實 0、情感地標 0——卡在「工作記憶滿 100 條才壓縮」，
# 一天 4 筆要 25 天才觸發一次）。借判準，不借實作。
#
# 關鍵：權重算在**原始對話**上，不是算在 LLM 摘要上。
# 「你憑啥覺得你講這些我就有必要相信」被改寫過就沒力量了，原話才有。
EMO_STRONG = ("愛", "恨", "永遠", "最重要", "秘密", "第一次", "再也不會",
              "感謝", "對不起", "難忘", "改變", "失去", "珍惜", "憑啥",
              "失望", "在乎", "相信", "承諾", "陪", "孤單", "怕")
EMO_MEDIUM = ("喜歡", "開心", "難過", "累", "擔心", "期待", "希望", "感動",
              "生氣", "煩", "謝謝", "辛苦")
EMO_THRESHOLD = float(os.environ.get("ARIS_EMO_THRESHOLD", "0.3"))
# Ryan 在訓練她時的講法。命中就當規則，不當事實。
RULE_TRIGGERS = (
    "不要", "不准", "別再", "以後", "記住", "永遠", "一律", "必須", "請你都",
    "下次", "改成", "習慣", "規矩", "禁止", "我要你", "你應該", "你該",
    "暗號", "叫我", "稱呼", "約定", "偏好",   # 兩人之間的約定，也永不刪
)
LLM_MODEL = os.environ.get("NEURALIS_DIGEST_MODEL", "deepseek/deepseek-chat")
LLM_URL = "https://openrouter.ai/api/v1/chat/completions"

# Hermes / harness 自己講的話，不是 Ryan 講的。混進記憶會變成假事實。
NOISE_PATTERNS = (
    r"^Review the conversation above",
    r"^update the skill library",
    r"^<system-reminder>",
    r"^\s*$",
)

DIGEST_PROMPT = (
    "你在幫「Aris」整理她自己的長期記憶。Aris 是 Ryan 建造的數位生命體。\n"
    "下面是她與 Ryan 今天的對話。\n\n"
    "【該記什麼】只記下面四類，其餘一律不記：\n"
    "  1. Ryan 對 Aris 本人的要求、糾正、偏好（他要她怎麼做事）\n"
    "  2. 關於 Aris 自己的決定與改變（架構、能力、被修好或砍掉什麼）\n"
    "  3. Ryan 與 Aris 之間的約定（暗號、稱呼、規矩）\n"
    "  4. 還懸著沒解決的事\n\n"
    "【不要記】Ryan 的日常工作內容（客戶、貸款、檔案清理、專案數字）。\n"
    "那些是工作事實，別的系統會記，不是 Aris 的記憶。\n\n"
    "【格式】\n"
    "- 繁體中文。禁止簡體字。\n"
    "- 1-3 段，段與段之間空一行\n"
    "- 每段 60 字以內\n"
    "- 純文字。不要編號、不要標題、不要 markdown 粗體、不要開場白\n"
    "- 嚴禁推測，嚴禁寫對話裡沒出現的東西\n"
    "- 沒有上述四類的事，只回四個字：無值得記\n"
    "  （多數時候就是沒有。寧可回「無值得記」也不要硬湊。）\n\n"
    "對話內容：\n"
)

RECOMPRESS_PROMPT = (
    "下面是 Aris 的長期記憶檔，每段用 § 分隔，已經超過容量上限。\n"
    f"必須壓到 {TARGET_BYTES} bytes 以內（約 {TARGET_BYTES // 3} 個中文字）。\n"
    "這是硬性要求，不是建議。壓不下去就刪更多。\n\n"
    "【一定要刪】\n"
    "- Ryan 的工作內容：客戶、貸款、金額、專案數字、檔案清理\n"
    "  （那些別的系統會記，不是 Aris 的記憶）\n"
    "- 一次性的技術細節、已經做完的事\n"
    "【一定要合併】\n"
    "- 講同一件事的段落，不管日期差多遠，合成一條\n"
    "- 例：兩條都在講「要繁體中文」→ 合成一條\n"
    "【一定要留】\n"
    "- Ryan 對 Aris 的要求與偏好\n"
    "- 兩人之間的約定（暗號、稱呼、規矩）\n"
    "- 還沒解決的懸案\n\n"
    "【格式】繁體中文。段落之間用一行 § 分隔。"
    "不要標題不要編號不要條列符號不要開場白。\n"
    "嚴禁新增原文沒有的內容。\n\n"
    "記憶檔：\n"
)


def api_key() -> str | None:
    for env in ("NEURALIS_LLM_API_KEY", "OPENROUTER_API_KEY"):
        if os.environ.get(env):
            return os.environ[env]
    errs = []
    for svc in ("openrouter-api-key", "openai-api-key"):
        try:
            r = subprocess.run(["security", "find-generic-password", "-s", svc, "-w"],
                               capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
            errs.append(f"{svc}:rc={r.returncode}")
        except Exception as e:
            errs.append(f"{svc}:{type(e).__name__}")
    # 2026-08-19 紅隊：原本靜默 pass，分不出「沒設金鑰」和「鑰匙圈鎖住」。
    # 絕不印金鑰本身，只印哪個來源、什麼錯。
    print(f"[api_key] ❌ 所有來源都拿不到: {'; '.join(errs) or '(無)'}", file=sys.stderr)
    return None


def call_llm(prompt: str, key: str, max_tokens: int = 1200) -> str | None:
    body = json.dumps({
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        LLM_URL, data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return (json.load(r)["choices"][0]["message"]["content"] or "").strip() or None
    except Exception as e:
        print(f"[llm 失敗] {e!r}", file=sys.stderr)
        return None


def is_noise(text: str) -> bool:
    head = (text or "").strip()[:80]
    return any(re.search(p, head, re.I) for p in NOISE_PATTERNS)


def fetch_day(days: int) -> list:
    since = time.time() - days * 86400
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = conn.execute(
        "SELECT id, content FROM memories "
        f"WHERE source IN ({','.join('?' * len(HUMAN_SOURCES))}) AND created_at > ? "
        "ORDER BY id",
        (*HUMAN_SOURCES, since)).fetchall()
    conn.close()
    return [(i, c) for i, c in rows if c and not is_noise(c)]


# ── 增量水位（2026-08-19 加）─────────────────────────────────
# 每 30 分钟跑一次时，只处理上次之后的新对话。
# 水位存 id 不存时间：id 单调递增，时钟回拨也不会重复处理。
WATERMARK = Path(os.environ.get(
    "ARIS_DIGEST_WATERMARK", str(Path.home() / ".gbrain/aris-digest.watermark")))


LOG_PATH = Path(os.environ.get(
    "ARIS_DIGEST_LOG", str(Path.home() / "Developer/neuralis/aris-digest.log")))
LOG_CAP = int(os.environ.get("ARIS_DIGEST_LOG_CAP", "200000"))  # 200KB


def rotate_log() -> None:
    """自己輪替，不靠 newsyslog。超過上限就只留後半段。

    每 30 分鐘跑一次 = 一天 48 筆，不輪替一個月會長到幾 MB
    （跟 laap-api.log 1MB 同一個病）。這裡就地截斷，不留 .1 .2 檔。
    """
    try:
        if not LOG_PATH.exists() or LOG_PATH.stat().st_size <= LOG_CAP:
            return
        tail = LOG_PATH.read_text(encoding="utf-8", errors="replace")[-(LOG_CAP // 2):]
        # 從第一個完整行開始，別留半行
        cut = tail.find("\n")
        LOG_PATH.write_text(
            f"[log rotated {time.strftime('%Y-%m-%d %H:%M')}]\n"
            + (tail[cut + 1:] if cut >= 0 else tail), encoding="utf-8")
    except Exception as e:
        print(f"[warn] log 輪替失敗: {e!r}", file=sys.stderr)


UNDO_PATH = Path(str(OUT) + ".undo")


def notify(title: str, body: str) -> None:
    """macOS 通知。只在學到新規則時推 —— 近況更新不推，那是雜訊。

    2026-08-19 實測：launchd 背景進程下 osascript exit=0。
    """
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')[:200]
    try:
        subprocess.run(
            ["/usr/bin/osascript", "-e",
             f'display notification "{esc(body)}" with title "{esc(title)}"'],
            capture_output=True, timeout=10)
    except Exception as e:
        print(f"[warn] 通知失敗: {e!r}", file=sys.stderr)


HIST_PATH = Path(str(OUT) + ".history")
HIST_CAP = int(os.environ.get("ARIS_HISTORY_CAP", "120000"))


def save_undo() -> None:
    """寫入前存快照。

    .undo   單層，給 `aris undo` 一鍵撤銷
    .history 全歷史，帶時間戳，`aris hist` 翻。
             2026-08-19：單層 undo 不夠——一天跑 48 次，錯過一次通知就永遠
             回不去。這裡 append 全歷史，超過上限截舊的（同 log 輪替手法）。
    """
    try:
        if not OUT.exists():
            return
        cur = OUT.read_text(encoding="utf-8")
        UNDO_PATH.write_text(cur, encoding="utf-8")
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with HIST_PATH.open("a", encoding="utf-8") as f:
            f.write(f"\n\n===== {stamp} =====\n{cur.rstrip()}\n")
        if HIST_PATH.stat().st_size > HIST_CAP:
            tail = HIST_PATH.read_text(encoding="utf-8", errors="replace")[-(HIST_CAP // 2):]
            cut = tail.find("\n===== ")
            HIST_PATH.write_text(
                f"[history trimmed {stamp}]\n" + (tail[cut:] if cut >= 0 else tail),
                encoding="utf-8")
    except Exception as e:
        print(f"[warn] 快照失敗: {e!r}", file=sys.stderr)


def read_watermark() -> int:
    """回水位 id。檔案不存在 → 0（首跑）。**壞掉 → -1（停，不是重來）**。

    2026-08-19 紅隊：原本任何錯誤都回 0，等於「水位檔壞掉就從頭處理整個
    A 庫」——會灌爆 ARIS.md 並燒 LLM 費用。讀不到水位時該停，不是該重來。
    """
    if not WATERMARK.exists():
        # 首跑不回填歷史：從 A 庫當前最大 id 起算，只記「從現在開始」的事。
        # 2026-08-19 紅隊：原本回 0 → 水位檔被誤刪就重新消化 60 筆舊對話，
        # 灌進 ARIS.md 又燒 LLM 費用。要補歷史請顯式跑 --days N。
        try:
            conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
            cur = conn.execute(
                "SELECT COALESCE(MAX(id),0) FROM memories WHERE source IN "
                f"({','.join('?' * len(HUMAN_SOURCES))})", HUMAN_SOURCES).fetchone()[0]
            conn.close()
            print(f"[watermark] 檔案不存在 → 首跑，從當前最大 id={cur} 起算"
                  f"（要補歷史用 --days N）")
            return int(cur)
        except Exception as e:
            print(f"[watermark] ❌ 首跑取基準失敗，停手: {e!r}", file=sys.stderr)
            return -1
    try:
        return int(WATERMARK.read_text().strip())
    except Exception as e:
        print(f"[watermark] ❌ 讀取/解析失敗，停手不處理: {e!r}", file=sys.stderr)
        return -1


def write_watermark(mid: int) -> None:
    try:
        WATERMARK.parent.mkdir(parents=True, exist_ok=True)
        WATERMARK.write_text(str(mid))
    except Exception as e:
        print(f"[warn] 水位寫入失敗，下次會重複處理: {e!r}", file=sys.stderr)


def fetch_since_id(after_id: int, hard_limit: int = 60) -> list:
    """取水位之後的新對話。hard_limit 防止第一次跑就吃掉整个 A 库。"""
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = conn.execute(
        "SELECT id, content FROM memories "
        f"WHERE source IN ({','.join('?' * len(HUMAN_SOURCES))}) AND id > ? "
        "ORDER BY id LIMIT ?",
        (*HUMAN_SOURCES, after_id, hard_limit)).fetchall()
    conn.close()
    return [(i, c) for i, c in rows if c and not is_noise(c)]


def emotional_weight(text: str) -> float:
    """一句話的情感強度 0-1。判準跑原話，不跑摘要。"""
    t = text or ""
    strong = sum(1 for w in EMO_STRONG if w in t)
    medium = sum(1 for w in EMO_MEDIUM if w in t)
    return min(1.0, strong * 0.3 + medium * 0.15)


def split_sections(text: str) -> tuple:
    """把 ARIS.md 拆成 (規則區, 地標區, 近況區)。

    三個標頭都是可選的；一個都沒有 → 舊格式，全部算近況。
    做法：把標頭當分隔點切開，按出現順序歸位——不做巢狀 split，
    那寫法繞且容易錯（2026-08-19 第一版就是那樣，重寫成這個）。
    """
    heads = [(RULE_HEADER, "rules"), (LANDMARK_HEADER, "marks"),
             (RECENT_HEADER, "recent")]
    found = sorted(((text.find(h), h, k) for h, k in heads if h in text))
    if not found:
        return "", "", text.strip()
    out = {"rules": "", "marks": "", "recent": ""}
    for i, (pos, head, key) in enumerate(found):
        start = pos + len(head)
        end = found[i + 1][0] if i + 1 < len(found) else len(text)
        out[key] = text[start:end].strip()
    return out["rules"], out["marks"], out["recent"]


def render(rules: str, marks: str, recent: str) -> str:
    out = []
    if rules:
        out.append(RULE_HEADER + "\n" + rules)
    if marks:
        out.append(LANDMARK_HEADER + "\n" + marks)
    out.append(RECENT_HEADER + "\n" + (recent or "（無）"))
    return "\n\n".join(out).rstrip() + "\n"


def looks_like_rule(text: str) -> bool:
    """Ryan 在訓練她 → 這句是規則不是事實。"""
    return any(t in (text or "") for t in RULE_TRIGGERS)


def recompress(key: str, max_rounds: int = 3) -> bool:
    """超過天花板就整檔重壓。回傳是否有動。

    2026-08-19 實測：只在 prompt 裡寫目標值，LLM 會做最保守的刪除就交差
    （733→538，目標 300，沒合併重複、留著工作事實）。所以要迴圈逼它，
    每輪把上一輪結果餵回去，直到達標或輪數用完。
    """
    if not OUT.exists() or OUT.stat().st_size <= CAP_BYTES:
        return False
    old = OUT.read_text(encoding="utf-8")
    print(f"[重壓] {len(old.encode())} bytes > 上限 {CAP_BYTES}，目標 {TARGET_BYTES}")

    # 規則區是 Ryan 的訓練成果，原樣搬過去，只壓近況區。
    rules, marks, recent = split_sections(old)
    protected = len((rules + marks).encode())
    if rules or marks:
        print(f"  保護區 {protected} bytes（規則 {len(rules.encode())} "
              f"+ 地標 {len(marks.encode())}），不壓")
        if protected >= TARGET_BYTES:
            print("  ⚠️ 保護區已吃掉整個預算，請你自己砍（aris mem）", file=sys.stderr)

    cur = recent if (rules or marks) else old
    for rnd in range(1, max_rounds + 1):
        out = call_llm(RECOMPRESS_PROMPT + cur, key, max_tokens=2000)
        if not out:
            break
        n = len(out.encode())
        print(f"  第{rnd}輪：{len(cur.encode())} → {n} bytes")
        if n >= len(cur.encode()):
            print("  沒變小，停止")
            break
        cur = out
        if n <= TARGET_BYTES:
            break

    # 壓完的近況區跟保護的規則區重新組回去
    new = render(rules, marks, cur) if (rules or marks) else cur
    if new == old:
        print("[重壓] 完全壓不動，維持原檔（寧可超標也不寫壞）", file=sys.stderr)
        return False
    if len(new.encode()) > CAP_BYTES:
        print(f"[重壓] 警告：{len(new.encode())} bytes 仍超過上限 {CAP_BYTES}",
              file=sys.stderr)
    bak = OUT.with_suffix(f".md.bak-{time.strftime('%Y%m%d-%H%M%S')}")
    bak.write_text(old, encoding="utf-8")
    OUT.write_text(new.rstrip() + "\n", encoding="utf-8")
    print(f"[重壓] {len(old.encode())} → {len(new.encode())} bytes（備份 {bak.name}）")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--recompress", action="store_true", help="只跑重壓")
    ap.add_argument("--incremental", action="store_true",
                    help="只處理水位之後的新對話（每 30 分鐘排程用）")
    args = ap.parse_args()

    rotate_log()

    key = api_key()
    if not key:
        print("找不到 API key", file=sys.stderr)
        return 1

    if args.recompress:
        return 0 if recompress(key) or True else 1

    if args.incremental:
        wm = read_watermark()
        if wm < 0:
            print("水位不可信，本輪不處理（修好 ~/.gbrain/aris-digest.watermark 再跑）",
                  file=sys.stderr)
            return 1
        rows = fetch_since_id(wm)
        print(f"增量模式：水位 id>{wm} → {len(rows)} 筆新對話")
        if not rows:
            print("沒有新對話")
            return 0
    else:
        rows = fetch_day(args.days)
        print(f"近 {args.days} 天真人對話（已濾雜訊）：{len(rows)} 筆")
        if not rows:
            print("沒有東西可壓")
            return 0

    # 2026-08-19 bug：原本 join 完直接 blob[:20000] 從頭截，rows 是升序，
    # 最新的（往往最重要）被砍在尾巴。改成從新到舊逐筆塞，塞不下才停。
    budget, parts = 20000, []
    for _, c in reversed(rows):
        piece = (c or "")[:800]
        if budget - len(piece) < 0:
            break
        parts.append(piece)
        budget -= len(piece)
    blob = "\n\n---\n\n".join(reversed(parts))
    print(f"  （餵給 LLM：{len(parts)}/{len(rows)} 筆，{len(blob)} 字）")
    stamp = time.strftime("%Y-%m-%d")
    old = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
    rules, marks, recent = split_sections(old)

    # 情感地標：機械判準，跑在**原始對話**上，不經 LLM。
    # 「你憑啥覺得你講這些我就有必要相信」被摘要過就沒力量了。
    # 2026-08-19 bug：這段原本放在「LLM 回無值得記就 return」之後，
    # 於是機械判準被 LLM 的判斷擋掉，永遠跑不到。判準是機械的就不能排在 LLM 後面。
    new_marks = []
    for mid, content in rows:
        first = (content or "").split("\n", 1)[0].strip()
        w = emotional_weight(first)
        if w >= EMO_THRESHOLD and first[:40] not in marks:
            new_marks.append(f"[{stamp} w={w:.2f}] {first[:120]}")
    if new_marks:
        print(f"  → 情感地標 +{len(new_marks)} 條")
        for m in new_marks:
            print(f"     {m[:80]}")

    gist = call_llm(DIGEST_PROMPT + blob, key)
    if gist and gist.startswith("無值得記"):
        print("今天沒有值得長期記住的事")
        gist = ""
    if not gist and not new_marks:
        return 0 if gist == "" else 1

    if gist:
        print("\n--- 今日摘要 ---")
        print(gist)
        print("----------------")

    if not args.apply:
        cur = OUT.stat().st_size if OUT.exists() else 0
        print(f"\n[DRY-RUN] 未寫入。現檔 {cur} bytes，"
              f"地標 +{len(new_marks)} 條、摘要 {len(gist.encode())} bytes / 上限 {CAP_BYTES}")
        return 0

    if new_marks:
        marks = (marks + "\n" + "\n".join(new_marks)).strip()

    # 逐行分流：訓練用的規則進規則區（永不刪），其餘進近況區。
    new_rules, new_recent = [], []
    for line in (l.strip() for l in gist.splitlines()):
        if not line:
            continue
        if looks_like_rule(line):
            if line not in rules:          # 同一條規則不重複收
                new_rules.append(line)
        else:
            new_recent.append(line)

    if new_rules:
        rules = (rules + "\n" + "\n".join(new_rules)).strip()
        print(f"  → 規則區 +{len(new_rules)} 條")
    if new_recent:
        block = f"[{stamp}] " + "\n".join(new_recent)
        recent = (recent + SEP + block).strip() if recent and recent != "（無）" else block
        print(f"  → 近況區 +{len(new_recent)} 行")

    # ── 對帳斷言（2026-08-19 第二項）───────────────────────────
    # 保護區只准增不准減：規則/地標是訓練成果，任何路徑都不該讓它變少。
    old_rules, old_marks, _ = split_sections(old)
    assert len(rules) >= len(old_rules), \
        f"規則區縮水 {len(old_rules)}→{len(rules)}，中止寫入"
    assert len(marks) >= len(old_marks), \
        f"地標區縮水 {len(old_marks)}→{len(marks)}，中止寫入"
    # 寫幾筆讀幾筆：地標新增數 == 實際被 append 的行數
    if new_marks:
        assert marks.count("\n") - old_marks.count("\n") >= len(new_marks) - 1, \
            f"地標數對不上：宣稱 +{len(new_marks)}，實際行數沒增那麼多"

    save_undo()
    OUT.write_text(render(rules, marks, recent), encoding="utf-8")
    # 寫完立刻回讀對帳：拆出來的三區必須跟寫進去的逐字相同
    back_r, back_m, back_c = split_sections(OUT.read_text(encoding="utf-8"))
    assert (back_r, back_m) == (rules, marks), \
        "回讀對帳失敗：保護區寫入後拆不回原樣（標頭衝突？）"
    if new_rules:
        notify("Aris 學到新規則",
               "；".join(new_rules)[:180] + "　（不對就打 aris undo）")
    if args.incremental and rows:
        write_watermark(rows[-1][0])
        print(f"  水位推進到 id={rows[-1][0]}")
    size = OUT.stat().st_size
    print(f"\n已寫入 {OUT}（{size} bytes / 上限 {CAP_BYTES}）")
    if size > CAP_BYTES:
        recompress(key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
