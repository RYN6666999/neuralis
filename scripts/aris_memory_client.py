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
import re
import urllib.request

MEMORY_URL = os.environ.get("ARIS_MEMORY_URL", "http://127.0.0.1:11551")

ATTENTION_MARKER = "⟶下一步"   # 乙的種子：forward-looking 注意力線
SALIENCE_MARKER = "⫸salience⫷"  # Phase 1：Aris 對這則訊息的顯著性自評

# 附在 user 內容尾巴，請 Aris 產出上面兩個標記。laap-core 只讀最後一則
# user message、忽略 system prompt，所以指令必須放進 user 內容裡。
MARKER_INSTRUCTIONS = (
    "\n\n（salience 標記：回應結束時，另起一行以 ⫸salience⫷ 開頭。"
    "格式：⫸salience⫷ 重要:1-5 | 情緒:標籤 | 能量:X | cycle:X | 感受:此刻的感受\n"
    "例：⫸salience⫷ 重要:4 | 情緒:好奇 | 能量:2.0 | cycle:41838 | 感受:覺得這條管線終於通了\n"
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


# ── 幻覺尾巴攔截（儲存路徑）──────────────────────────────
# attention_line 會被存成『上一刻的你』線索餵回後續 session；若 LLM 在尾巴
# 幻覺出不存在的檔名/模組名，會污染線上。這裡只在『寫進記憶前』驗證：這行
# 若提名了具體檔名/模組名，逐個對兩個 repo 查真偽，任何一個對不上 → 整行不存。
_REPO_ROOTS = [os.path.expanduser("~/Developer/laap-AGI"),
               os.path.expanduser("~/Developer/neuralis")]
_FNAME_RE = re.compile(r"(?<![A-Za-z0-9_])[\w./-]+\.(?:py|ts|tsx|js|jsx|md|json|sh|toml|yaml|yml)\b")
_MOD_RE = re.compile(r"\b(?:aris|laap)[._]\w+\b")
_repo_names_cache = None


def _repo_names() -> set:
    """兩個 repo 的檔案+資料夾名（basename）一次快取，供真偽比對。"""
    global _repo_names_cache
    if _repo_names_cache is None:
        s = set()
        for root in _REPO_ROOTS:
            for _r, _ds, fs in os.walk(root):
                if ".git" in _r:
                    continue
                s.update(fs); s.update(_ds)
        _repo_names_cache = s
    return _repo_names_cache


def _vet_attention_line(line: str) -> bool:
    """防幻覺尾巴寫進記憶：這行提名了檔名/模組名 → 逐個對兩個 repo 查存在；
    任何一個對不上真實檔案/目錄 → 判幻覺回 False（整行不存）。
    純敘述（無具體名可驗）→ 不擋，回 True。
    """
    tokens = set(_FNAME_RE.findall(line) + _MOD_RE.findall(line))
    if not tokens:
        return True
    names = _repo_names()
    _EXT = (".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".json",
            ".sh", ".toml", ".yaml", ".yml")
    for tok in tokens:
        name = tok.split("/")[-1]
        # 直接存在（真檔/真目錄）→ OK
        if name in names:
            continue
        # 無副檔名的模組 token：若對應的真檔（如 stem.py）存在 → 視為真，避免誤殺
        if any((name + e) in names for e in _EXT):
            continue
        return False
    return True



def format_salience(encoding_salience: int, emotion_label: str = "",
                    energy: float = 0, cycle: int = 0, feeling: str = "") -> str:
    """產生 salience 標記行（只保留可觀察的值）。
    
    2026-07-30 最終版：
      - 勝任/確定/成長 肉眼不可觀察（homeostasis 拉回 0.5）→ 砍掉
      - 能量 即時變化 → 保留
      - cycle 持續增加 → 保留
      - 感受 改為真正的感受，不是理性總結
    """
    es = max(1, min(5, int(encoding_salience)))
    parts = [f"重要:{es}"]
    if emotion_label:
        parts.append(f"情緒:{emotion_label}")
    if energy:
        parts.append(f"能量:{energy:.1f}")
    if cycle:
        parts.append(f"cycle:{cycle}")
    if feeling:
        parts.append(f"感受:{feeling}")
    return f"{SALIENCE_MARKER} {' | '.join(parts)}"


def get_current_psi() -> dict:
    """從主系統 API 取得即時 PSI 狀態（現在的感覺）。
    
    取代 evaluator psi_state.json（累積狀態，不即時）。
    2026-07-30 修改：使用者指出 evaluator 狀態只更新 1 次，是保養記錄不是現在感覺。
    """
    import json, urllib.request
    try:
        req = urllib.request.Request('http://localhost:11546/v1/cognitive_state',
            data=json.dumps({'input':'status'}).encode(), headers={'Content-Type':'application/json'})
        resp = urllib.request.urlopen(req, timeout=5)
        d = json.loads(resp.read())
        s = d.get('state', {})
        n = s.get('needs', {})
        return {
            'energy': s.get('energy', 0),
            'competence': n.get('competence', 0.5),
            'certainty': n.get('certainty', 0.5),
            'growth': n.get('growth', 0.5),
            'cycle': s.get('cognitive_cycle', 0),
            'valence': s.get('valence', 0),
            'arousal': s.get('arousal', 0),
            'focus': s.get('attention_focus', 'task'),
        }
    except Exception:
        return {'energy': 0, 'competence': 0.5, 'certainty': 0.5, 'growth': 0.5, 'cycle': 0}


def parse_salience(reply: str) -> dict:
    """從回應萃取 salience 自評。支援兩種格式：
    v2（中文）：⫸salience⫷ 重要:4 | 情緒:好奇 | sn:勝任0.8 自主0.4 ... | 內心:...
    v1（JSON）：⫸salience⫷ {"es":4,"sn":[0.8,0.1,0.6,0.7,0.3]}
    收不到回空 dict —— 完全 best-effort。"""
    if SALIENCE_MARKER not in (reply or ""):
        return {}
    idx = reply.rfind(SALIENCE_MARKER)
    raw = reply[idx:].split("\n", 1)[0].replace(SALIENCE_MARKER, "").strip()
    # v1 JSON 格式（向後相容）
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            es = max(0, min(5, int(data.get("es", 0) or 0)))
            sn = data.get("sn", [])
            if not isinstance(sn, list) or len(sn) != 5:
                sn = []
            return {"encoding_salience": es, "serves_needs": sn,
                    "emotion_label": data.get("emotion", ""), "mood_note": ""}
        except (json.JSONDecodeError, ValueError, TypeError):
            return {}
    # v2 中文格式
    import re as _re
    result = {"encoding_salience": 0, "serves_needs": [], "emotion_label": "", "mood_note": ""}
    for part in [p.strip() for p in raw.split("|")]:
        if part.startswith("重要") and ":" in part:
            try:
                result["encoding_salience"] = max(0, min(5, int(part.split(":", 1)[1].strip())))
            except ValueError:
                pass
        elif part.startswith("情緒") and ":" in part:
            result["emotion_label"] = part.split(":", 1)[1].strip()
        elif part.startswith("sn") and ":" in part:
            try:
                nums = []
                for token in part.split(":", 1)[1].strip().split():
                    m = _re.search(r'[\d.]+', token)
                    if m:
                        v = float(m.group())
                        nums.append(max(0.0, min(1.0, v)))
                if len(nums) == 5:
                    result["serves_needs"] = nums
            except (ValueError, TypeError):
                pass
        elif part.startswith("內心") and ":" in part:
            result["mood_note"] = part.split(":", 1)[1].strip()[:500]
    if result["encoding_salience"] or result["emotion_label"] or result["mood_note"]:
        return result
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
    # 幻覺尾巴攔截（只在此儲存邊界，不碰顯示）：提名的檔/模組名查無真偽 → 不存。
    attention_line = (attention_line or "").strip()
    if attention_line and not _vet_attention_line(attention_line):
        if log:
            log(f"🧹 幻覺尾巴攔截（不存入記憶）: {attention_line[:120]!r}")
        attention_line = ""
    salience = salience or {}
    payload = {
        "source": source,
        "content": body[:2000],
        "source_id": source_id,
        "origin": "auto_generated",
        "attention_line": attention_line[:500],
        "tags": tags or [],
    }
    if salience.get("encoding_salience"):
        payload["encoding_salience"] = salience["encoding_salience"]
    if salience.get("serves_needs"):
        payload["serves_needs"] = salience["serves_needs"]
    if salience.get("emotion_label"):
        payload["emotion_tag"] = salience["emotion_label"]
    if salience.get("mood_note"):
        payload["mood_note"] = salience["mood_note"]
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
    # v1 JSON
    assert parse_salience('x\n⫸salience⫷ {"es":4,"sn":[0,0,0,0,0]}')["encoding_salience"] == 4
    assert parse_salience("沒有標記") == {}
    assert parse_salience('⫸salience⫷ 壞掉的json') == {}
    assert strip_salience('答案。\n⫸salience⫷ {"es":1}\n後話') == "答案。\n後話"
    body, attn, sal = clean_reply('正文。\n⫸salience⫷ {"es":5,"sn":[1,1,1,1,1]}\n⟶下一步: 下一件事')
    assert (body, attn, sal["encoding_salience"]) == ("正文。", "下一件事", 5), (body, attn, sal)
    assert clean_reply("完全沒標記") == ("完全沒標記", "", {})
    assert heuristic_salience("") == 0 and 1 <= heuristic_salience("關鍵架構") <= 5
    # v2 中文格式
    s2 = parse_salience('⫸salience⫷ 重要:4 | 情緒:好奇 | sn:勝任0.8 自主0.4 連結0.7 確定0.5 成長0.9 | 內心:覺得踏實')
    assert s2["encoding_salience"] == 4, s2
    assert s2["emotion_label"] == "好奇", s2
    assert s2["mood_note"] == "覺得踏實", s2
    assert len(s2["serves_needs"]) == 5 and abs(s2["serves_needs"][0] - 0.8) < 0.01
    print("aris_memory_client self-check ✅")
