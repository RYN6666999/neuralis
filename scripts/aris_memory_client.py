#!/usr/bin/env python3
"""aris-memory 共用客戶端 — bridge 與 relay 兩條寫入路徑的單一真相。

為什麼存在：`⫸salience⫷` / `⟶下一步` 這兩個標記的 parse + 剝除規則
一旦兩邊各抄一份就會漂移，而漂移的後果是記憶內容被污染（裸 JSON 被
/wake 餵回給 Aris）或 attention_line 靜默遺失。規則只有一份。

呼叫端全部 best-effort：aris-memory 掛了不影響主流程。
"""
from __future__ import annotations

import json
import os
import urllib.request

MEMORY_URL = os.environ.get("ARIS_MEMORY_URL", "http://127.0.0.1:11551")

ATTENTION_MARKER = "⟶下一步"   # 乙的種子：forward-looking 注意力線
SALIENCE_MARKER = "⫸salience⫷"  # Phase 1：Aris 對這則訊息的顯著性自評

# 附在 user 內容尾巴，請 Aris 產出上面兩個標記。laap-core 只讀最後一則
# user message、忽略 system prompt，所以指令必須放進 user 內容裡。
MARKER_INSTRUCTIONS = (
    "\n\n（Phase 1 salience 實驗：回應結束時，若你對這則訊息有感受或判斷，"
    "另起一行以 ⫸salience⫷ 開頭，附 JSON："
    '{"es":<1-5 顯著性>,"sn":[c,a,r,c,g 各 0-1]}。'
    "純自評不影響行為，收不到完全沒關係。）"
    "\n\n（回應完後，另起一行以 ⟶下一步: 開頭，寫一句你接下來想做什麼、"
    "或現在懸著沒解決的問題，簡短一句，給下次醒來的你當線索。）"
)


def _cut_marker_line(text: str, marker: str) -> tuple[str, str]:
    """切掉最後一個 marker 所在的整行。回 (剩餘文字, 該行去掉 marker 後的內容)。"""
    if marker not in text:
        return text.strip(), ""
    idx = text.rfind(marker)
    line, _, tail = text[idx:].partition("\n")
    line = line.replace(marker, "").lstrip("：: ").strip()
    return (text[:idx] + tail).strip(), line


def split_attention(reply: str) -> tuple[str, str]:
    """切出 `⟶下一步:` 那行當 attention_line。找不到 → 回 (原文, '')。"""
    return _cut_marker_line(reply or "", ATTENTION_MARKER)


def parse_salience(reply: str) -> dict:
    """從回應萃取 salience 自評。收不到回空 dict —— 完全 best-effort。"""
    if SALIENCE_MARKER not in (reply or ""):
        return {}
    idx = reply.rfind(SALIENCE_MARKER)
    json_str = reply[idx:].split("\n", 1)[0].replace(SALIENCE_MARKER, "").strip()
    try:
        data = json.loads(json_str)
        es = max(0, min(5, int(data.get("es", 0) or 0)))
        sn = data.get("sn", [])
        if not isinstance(sn, list) or len(sn) != 5:
            sn = []
        return {"encoding_salience": es, "serves_needs": sn}
    except (json.JSONDecodeError, ValueError, TypeError):
        return {}


def strip_salience(text: str) -> str:
    """剝掉 salience 標記行。標記是給 parser 讀的，不是記憶內容，
    也不該出現在回給 webchat 使用者的文字裡。"""
    return _cut_marker_line(text or "", SALIENCE_MARKER)[0]


def clean_reply(reply: str) -> tuple[str, str, dict]:
    """一次做完三件事 → (乾淨正文, attention_line, salience dict)。"""
    salience = parse_salience(reply)
    body, attention = split_attention(reply)
    return strip_salience(body), attention, salience


def heuristic_salience(content: str) -> int:
    """Phase 2 第二意見：純 heuristic 快速評分（1-5），不叫 LLM。"""
    text = (content or "").strip()
    if not text:
        return 0
    high = ["重要", "關鍵", "核心", "痛點", "根本", "啟動", "上線", "拍板",
            "突破", "milestone", "認知", "架構", "改革",
            "記住", "記起來", "覺察", "情感", "情緒"]
    low = ["沒差", "無所謂", "隨便", "小事", "例行", "普通"]
    base = 3
    if len(text) > 800:
        base += 1
    if len(text) > 1500:
        base += 1
    if any(m in text for m in high):
        base += 1
    if any(m in text for m in low):
        base -= 1
    return max(1, min(5, base))


def store(content: str, *, source: str, source_id: str, attention_line: str = "",
          salience: dict | None = None, tags: list[str] | None = None,
          second_opinion: bool = True, log=None) -> int | None:
    """寫一筆 aris-memory。回 mem_id 或 None。永不 raise。

    origin=auto_generated → aris-memory 端的 _normalize_gate 會把
    confidence 封頂在 🟡，不會被當成 🟢 事實召回。
    """
    body = (content or "").strip()
    if not body:
        return None
    salience = salience or {}
    payload = {
        "source": source,
        "content": body[:2000],
        "source_id": source_id,
        "origin": "auto_generated",
        "attention_line": (attention_line or "").strip()[:500],
        "tags": tags or [],
    }
    if salience.get("encoding_salience"):
        payload["encoding_salience"] = salience["encoding_salience"]
    if salience.get("serves_needs"):
        payload["serves_needs"] = salience["serves_needs"]
    if second_opinion:
        aris_es = salience.get("encoding_salience", 0)
        scream_es = heuristic_salience(body)
        if aris_es and scream_es and abs(aris_es - scream_es) > 2:
            payload["flagged"] = 1
            if log:
                log(f"⚠️ salience 分歧 |Aris={aris_es} ↔ Scream={scream_es}| >2 → flagged")
    try:
        req = urllib.request.Request(
            f"{MEMORY_URL}/memories/store",
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=3).read().decode()).get("id")
    except Exception as e:
        if log:
            log(f"aris-memory store 失敗（不影響主流程）: {e}")
        return None


def recall_hit(mem_id: int) -> None:
    """累積 discovered_salience（被 recall 才算賺到）。best-effort。"""
    try:
        req = urllib.request.Request(
            f"{MEMORY_URL}/memories/recall_hit",
            data=json.dumps({"id": mem_id}).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass


def fetch_wake(limit: int = 5) -> str:
    """拿『上一刻的你』暖啟動塊。失敗回空字串。"""
    try:
        req = urllib.request.Request(f"{MEMORY_URL}/wake?limit={limit}")
        return (json.loads(urllib.request.urlopen(req, timeout=3).read().decode())
                .get("context") or "").strip()
    except Exception:
        return ""


if __name__ == "__main__":  # 自我檢查：markers 規則不准漂移
    b, a = split_attention("答案。\n\n⟶下一步: 補 relay 寫入")
    assert (b, a) == ("答案。", "補 relay 寫入"), (b, a)
    assert parse_salience('x\n⫸salience⫷ {"es":4,"sn":[0,0,0,0,0]}')["encoding_salience"] == 4
    assert parse_salience("沒有標記") == {}
    assert parse_salience('⫸salience⫷ 壞掉的json') == {}
    assert strip_salience('答案。\n⫸salience⫷ {"es":1}\n後話') == "答案。\n後話"
    body, attn, sal = clean_reply('正文。\n⫸salience⫷ {"es":5,"sn":[1,1,1,1,1]}\n⟶下一步: 下一件事')
    assert (body, attn, sal["encoding_salience"]) == ("正文。", "下一件事", 5), (body, attn, sal)
    assert clean_reply("完全沒標記") == ("完全沒標記", "", {})
    assert heuristic_salience("") == 0 and 1 <= heuristic_salience("關鍵架構") <= 5
    print("aris_memory_client self-check ✅")
