"""
memory_store — top-level module for laap-AGI's bare import.

aris_cognitive_bridge.py / laap_integrator.py / state_snapshot.py do:
    from memory_store import MemoryStore, MemoryFragment

作者在 MemoryStore 實例上呼叫的方法（實測掃描）:
    store(fragment) / get(id) / get_stats() -> {'core','episodic',...}
    get_memory_embedding(query=, layer=, top_k=) -> 384-dim float32

Phase 1（gbrain 記憶後端）:
  - backend 由 NEURALIS_MEMORY_BACKEND 控制: auto（預設）| gbrain | local
  - auto/gbrain: store→gbrain put_page（laap/memory/<layer>/<id> 頁）、
    recall→gbrain search（全腦 1868+ 頁語意檢索）、get_stats→gbrain page_count、
    get_memory_embedding→檢索結果的 deterministic hash embedding（384-dim）
  - gbrain 不可用（binary 缺 / 呼叫失敗）→ 每次呼叫自動 fallback 到 in-process，
    作者端介面與行為不變。local 強制純 in-process（Phase 0 行為）。
"""
import hashlib
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger("memory_store")

EMBED_DIM = 384  # 作者 get_memory_embedding 契約：384-dim float32

_GBRAIN_NS = "laap/memory"          # gbrain 頁面命名空間: laap/memory/<layer>/<id>
_STATS_TTL = 60.0                   # gbrain get_stats 快取（desire engine 每輪都問）

# 檢索端情緒加權（Damasio somatic marker：情緒強的記憶該優先浮現）。
# final = base_score × (1 + WEIGHT × emotion_intensity)。emotion∈[0,1]，故最多 +WEIGHT。
# 只對 laap/memory/* 的 hit 生效（帶 emotion_intensity frontmatter）；全腦頁 emotion=0 不受影響。
_EMOTION_RECALL_WEIGHT = float(os.environ.get("NEURALIS_EMOTION_RECALL_WEIGHT", 0.3))
_EMOTION_TTL = 120.0                # slug→emotion 快取（consolidation 改動慢，同輪 recall/embedding 復用）
_emotion_cache: Dict[str, tuple] = {}


def _emotion_intensity_for(client, slug: str) -> float:
    """抓某 laap 記憶頁的 emotion_intensity（帶 TTL 快取）。非 laap slug 或查不到回 0.0。
    ponytail: search hit 不帶 frontmatter → 逐頁 get_page 補；laap hit 在 top-N 裡通常
    只有 0-3 個，成本低。升級路徑=gbrain 上游讓 hit 直接帶 frontmatter。"""
    if not slug.startswith(_GBRAIN_NS + "/"):
        return 0.0
    now = time.time()
    cached = _emotion_cache.get(slug)
    if cached and now - cached[0] < _EMOTION_TTL:
        return cached[1]
    try:
        page = client.call("get_page", {"slug": slug}, timeout=10.0)
        val = float((page.get("frontmatter") or {}).get("emotion_intensity", 0) or 0)
    except Exception:
        val = 0.0
    if len(_emotion_cache) > 256:
        _emotion_cache.clear()
    _emotion_cache[slug] = (now, val)
    return val


def _emotion_rerank(client, hits: List[Dict]) -> List[Dict]:
    """對 gbrain hits 按情緒強度加權重排。穩定：emotion=0 的 hit 乘 1、順序不變。"""
    if not hits or _EMOTION_RECALL_WEIGHT <= 0:
        return hits
    for h in hits:
        emo = _emotion_intensity_for(client, h.get("slug", ""))
        h["_score_adj"] = float(h.get("score", 0.0)) * (1.0 + _EMOTION_RECALL_WEIGHT * emo)
    return sorted(hits, key=lambda h: h.get("_score_adj", 0.0), reverse=True)


def _backend_mode() -> str:
    mode = os.environ.get("NEURALIS_MEMORY_BACKEND", "auto").lower()
    return mode if mode in ("auto", "gbrain", "local") else "auto"


def _gbrain():
    """回 gbrain client 或 None（不可用 / 強制 local）。import 放函式內避免循環。"""
    if _backend_mode() == "local":
        return None
    try:
        from gbrain_client import get_client
        return get_client()
    except Exception as e:
        logger.debug(f"[memory_store] gbrain client unavailable: {e}")
        return None


def emotion_intensity() -> float:
    """寫入當下的情緒強度 |valence|×arousal（Damasio somatic marker：情緒強的記憶
    該被記得更牢）。PsiCore 沒起就 0.0。固化循環用它做升層/保留判斷。
    ponytail: 檢索端 re-rank 未做（search hit 不帶 frontmatter，逐頁抓太慢）—
    目前情緒只影響寫入 importance 與固化決策。"""
    try:
        from laap.startup import get_psi_core
        psi = get_psi_core()
        if psi is not None:
            e = psi.get_state()["emotion"]
            return round(abs(e["valence"]) * e["arousal"], 3)
    except Exception:
        pass
    return 0.0


def _hash_embed(text: str) -> np.ndarray:
    """Deterministic feature-hashing embedding（384-dim，L2 normalized）。
    中英混排：CJK 逐字 + 英數 token。同文字同向量；相近文字向量相近（詞袋級）。
    ponytail: 天花板是詞袋語意。升級路徑=gbrain 曝露原生向量後做 3072→384 投影。"""
    vec = np.zeros(EMBED_DIM, dtype=np.float32)
    for tok in re.findall(r"[一-鿿]|[a-z0-9]+", text.lower()):
        idx = int(hashlib.md5(tok.encode()).hexdigest(), 16) % EMBED_DIM
        vec[idx] += 1.0
    norm = float(np.linalg.norm(vec))
    return vec / norm if norm > 0 else vec


@dataclass
class MemoryFragment:
    """記憶片段。作者以 r.content[:50] 取用，故 content 必為 str。"""
    id: str = ""
    content: str = ""
    tags: List[str] = field(default_factory=list)
    importance: float = 0.5
    layer: str = "episodic"  # 'core' | 'episodic'
    ts: float = field(default_factory=time.time)


class MemoryStore:
    """階層記憶儲存（core / episodic）。gbrain 為真後端，in-process 為快取 + fallback。"""

    _stats_cache: Optional[Dict[str, int]] = None   # class-level：作者會 new 多個實例
    _stats_cache_at: float = 0.0
    _stats_lock = threading.Lock()

    def __init__(self, capacity: int = 1000):
        self.capacity = capacity
        self._items: List[MemoryFragment] = []
        logger.info(f"[memory_store] 初始化 capacity={capacity} backend={_backend_mode()}")

    # ── store ──────────────────────────────────────────────────

    def store(self, fragment: MemoryFragment) -> str:
        if not fragment.id:
            digest = hashlib.md5(f"{fragment.content}:{fragment.ts}".encode()).hexdigest()[:6]
            fragment.id = f"mem-{int(fragment.ts)}-{digest}"
        # importance >= 0.7 視為核心記憶
        if fragment.layer == "episodic" and fragment.importance >= 0.7:
            fragment.layer = "core"
        self._store_local(fragment)
        client = _gbrain()
        if client is not None:
            try:
                client.call("put_page", {
                    "slug": f"{_GBRAIN_NS}/{fragment.layer}/{fragment.id}",
                    "content": self._to_markdown(fragment),
                }, timeout=30.0)
            except Exception as e:
                logger.warning(f"[memory_store] gbrain store 失敗（已存 in-process）: {e}")
        return fragment.id

    def _store_local(self, fragment: MemoryFragment) -> None:
        self._items.append(fragment)
        if len(self._items) > self.capacity:
            # 丟最舊的 episodic，保留 core
            for i, m in enumerate(self._items):
                if m.layer == "episodic":
                    self._items.pop(i)
                    break

    @staticmethod
    def _to_markdown(f: MemoryFragment) -> str:
        tags = ", ".join(f.tags) if f.tags else ""
        return (
            f"---\n"
            f"title: laap memory {f.id}\n"
            f"tags: [{tags}]\n"
            f"importance: {f.importance}\n"
            f"layer: {f.layer}\n"
            f"emotion_intensity: {emotion_intensity()}\n"
            f"source: laap-runtime\n"
            f"---\n\n"
            f"{f.content}\n"
        )

    # ── get / recall ───────────────────────────────────────────

    def get(self, mem_id: str) -> Optional[MemoryFragment]:
        return next((m for m in self._items if m.id == mem_id), None)

    def recall(self, query: str = "", top_k: int = 5, layer: Optional[str] = None) -> List[MemoryFragment]:
        local = self._recall_local(query, top_k, layer)
        if not query:
            # 無 query = 「最近/最重要」語意，本 session 的 in-process 快取就是對的來源
            return local
        client = _gbrain()
        if client is None:
            return local
        try:
            # hybrid（vec+lex→lex）降級檢索; 無 OPENAI_API_KEY 時 vec 退化只剩 lex
            hits = hybrid_hits_any(client, query, max(top_k * 2, 10))
        except Exception as e:
            logger.warning(f"[memory_store] gbrain recall 失敗，用 in-process: {e}")
            return local
        hits = _emotion_rerank(client, hits)  # 情緒強的記憶優先浮現（Damasio）
        remote = [self._hit_to_fragment(h) for h in hits]
        if layer is not None:
            remote = [f for f in remote if f.layer == layer]
        # 本 session 剛存的可能還沒進索引 → local 優先，slug/id 去重
        seen = {f.id for f in local}
        merged = local + [f for f in remote if f.id not in seen]
        return merged[:top_k]

    def _recall_local(self, query: str, top_k: int, layer: Optional[str]) -> List[MemoryFragment]:
        pool = [m for m in self._items if layer is None or m.layer == layer]
        if query:
            # 2026-08-12 修復：舊版整句 substring→自然問句永遠 0；改用 token 命中
            toks = _query_tokens(query).split()
            scored = []
            for m in pool:
                c = m.content.lower()
                hit = sum(1 for t in toks if t in c)
                if hit > 0:
                    scored.append((hit, m.importance, m.ts, m))
            scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
            pool = [m for _, _, _, m in scored]
        else:
            pool.sort(key=lambda m: (m.importance, m.ts), reverse=True)
        return pool[:top_k]

    @staticmethod
    def _clean_markdown(text: str) -> str:
        """讀取層清洗：剝掉 markdown 樣板，保留實際內容。

        為什麼修在這裡：gbrain 2251 頁混合 Ryan 知識庫 + Aris 記憶，寫入時清洗會
        誤傷知識庫原文。讀取時清洗只影響 Aris 記憶注入，立即生效、不用重跑。
        前科：markdown 分隔線（-----------）被 `[:50]` 切到、callout 語法
        （> [!note]）、frontmatter、`## Transcript` 標題都被當成記憶內容。
        """
        if not text:
            return text
        lines = text.split("\n")
        out = []
        in_frontmatter = False
        for ln in lines:
            s = ln.strip()
            # frontmatter 區塊：--- 開頭 → --- 結尾
            if s == "---" and not in_frontmatter and len(out) == 0:
                in_frontmatter = True
                continue
            if in_frontmatter:
                if s == "---":
                    in_frontmatter = False
                continue
            # callout / blockquote 語法
            if s.startswith(">"):
                if "[!" in s:
                    s = s.split("]", 1)[-1].lstrip(" >")
                else:
                    s = s.lstrip("> ")
            # 純分隔線（全部是 - / = / * 且長度 ≥ 3）
            if s and set(s.replace(" ", "")) <= set("-=*") and len(s) >= 3:
                continue
            out.append(s)
        # 清洗後完全空 → 回空字串，由消費端決定跳過。
        # 2026-08-10 原本回「(此記憶內容為格式樣板，無實質文字)」占位句，怕空輸出被
        # 讀成「沒有」。但那句會一路穿透到 prompt，Aris 於是說「這讓我想起：這段沒有
        # 內容」—— 比不說更糟。占位句解決的是「訊號歧義」，代價是製造假記憶；
        # 正解是消費端跳過空的（get_memory_context / _memory_gist 都已處理）。
        return "\n".join(x for x in out if x).strip()

    @staticmethod
    def _hit_to_fragment(hit: Dict) -> MemoryFragment:
        slug = hit.get("slug", "")
        if slug.startswith(f"{_GBRAIN_NS}/"):
            mem_id = slug.rsplit("/", 1)[-1]
            layer = "core" if slug.startswith(f"{_GBRAIN_NS}/core/") else "episodic"
        else:
            # 腦庫既有知識頁 = 長期記憶 → core
            mem_id, layer = slug, "core"
        return MemoryFragment(
            id=mem_id,
            content=MemoryStore._clean_markdown(
                hit.get("chunk_text", "") or hit.get("title", "")),
            importance=min(1.0, float(hit.get("score", 0.5))),
            layer=layer,
        )

    # ── stats ──────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, int]:
        core = sum(1 for m in self._items if m.layer == "core")
        episodic = sum(1 for m in self._items if m.layer == "episodic")
        stats = {"core": core, "episodic": episodic, "working": 0, "total": len(self._items)}
        gbrain_pages = self._gbrain_page_count()
        if gbrain_pages is not None:
            stats["gbrain_pages"] = gbrain_pages
            stats["total"] += gbrain_pages
        return stats

    @classmethod
    def _gbrain_page_count(cls) -> Optional[int]:
        client = _gbrain()
        if client is None:
            return None
        with cls._stats_lock:
            now = time.time()
            if cls._stats_cache is not None and now - cls._stats_cache_at < _STATS_TTL:
                return cls._stats_cache
            try:
                stats = client.call("get_stats", {}, timeout=10.0)
                cls._stats_cache = int(stats.get("page_count", 0))
                cls._stats_cache_at = now
                return cls._stats_cache
            except Exception as e:
                logger.warning(f"[memory_store] gbrain get_stats 失敗: {e}")
                return cls._stats_cache  # 過期快取也比 None 好

    # ── embedding ──────────────────────────────────────────────

    def get_memory_embedding(self, query: str = "", layer: str = "core", top_k: int = 3) -> "np.ndarray":
        """檢索該層記憶 → deterministic hash embedding 加權平均（384-dim）。
        召回為空 → 零向量（作者端 np.linalg.norm<0.01 會自動降級到情景層，契約保留）。"""
        frags = self.recall(query=query, top_k=top_k, layer=layer)
        if not frags:
            return np.zeros(EMBED_DIM, dtype=np.float32)
        acc = np.zeros(EMBED_DIM, dtype=np.float32)
        for f in frags:
            acc += _hash_embed(f.content) * max(0.1, f.importance)
        norm = float(np.linalg.norm(acc))
        return acc / norm if norm > 0 else acc


# ── GBRAIN_BACKEND ─────────────────────────────────────────────
# Phase 1 已接上（見模組 docstring）。強制舊行為: NEURALIS_MEMORY_BACKEND=local

# /v1/recall_memory（laap_recall_memory tool）走作者的 laap_semantic_memory，
# 不走本模組 — 在這裡掛替身是因為 memory_store 是 boot 必經的 neuralis 模組。
if _backend_mode() != "local":
    try:
        from semantic_memory_gbrain import install as _install_semantic
        _install_semantic()
    except Exception as _e:  # 安裝失敗不影響 memory_store 本體
        logger.debug(f"[memory_store] semantic gbrain 掛載跳過: {_e}")


def _query_tokens(query: str, limit: int = 8) -> str:
    """把自然問句轉成 gbrain 可用的關鍵字查詢（2026-08-12）。

    背景：gbrain 搜尋是詞彙型，整句自然語言命中率≈0；token 切法：
      - 依空白/標點切詞（len>=2）
      - CJK 長詞（>4 字）補頭尾 2 字片語（「引擎在程式裡叫什麼名字」→「引擎」「名字」）
    給本地 substring 計分與遠端 gbrain 搜尋共用。
    """
    import re as _re
    toks = [
        t for t in _re.split(r"[\s\u3000，。！？、；：,.!?;:（）()/\\_'\"\-]+", query.lower())
        if len(t) >= 2
    ]
    out = []
    for t in toks:
        out.append(t)
        if len(t) > 4 and _re.search(r"[\u4e00-\u9fff]", t):
            out.append(t[:2])
            out.append(t[-2:])
    return " ".join(out[:limit])


_STOPWORDS = {
    "告訴我", "告訴", "我們", "哪些", "什麼", "那個", "這個", "一個", "一下",
    "最近", "有沒有", "可以", "怎麼", "為什麼", "程式裡", "叫什麼", "對話",
    "全新", "無前文", "前文", "請", "幫我", "說說", "告訴", "想知道",
    "告訴", "做", "弄", "事", "存在", "沒有", "不是", "就是",
}


def hybrid_hits_any(client, query: str, limit: int) -> list:
    """整串查 + 逐 token 查併集；停用詞過濾；laap/memory 優先（2026-08-12）。

    速度優化（00:5x 實測整串查+6 token×limit15 = 21 秒太慢，LLM 兜底等不到）：
      - 不做整串查（自然句整串命中率≈0，白燒一次）
      - 鑑別性 token 優先（含英數的最有辨識度），最多 4 個
      - per-token limit 縮小
    """
    from gbrain_client import hybrid_hits
    toks = [t for t in _query_tokens(query).split() if t not in _STOPWORDS]
    if not toks:
        return []
    toks.sort(key=lambda t: (not any(ch.isascii() and ch.isalnum() for ch in t), len(t)))
    # 2026-08-12 T1：4 token × ~3.5s ≈ 15s 貼 timeout 邊緣；縮到 2 token ≈ 7s，
    # 換更穩的 weave 窗口（6s+）。召回廣度換速度——種子記憶用一個 token 就中。
    toks = toks[:2]
    seen = {}
    def _add(hs):
        for h in hs or []:
            sid = h.get("slug")
            if sid and sid not in seen:
                seen[sid] = h
    limit_i = max(limit * 2, 6)
    # 2026-08-12 T1：token 查詢並行（2-4 token × ~4s 序列 = 16s 太久，
    # weave/respond 窗口等不到）。ThreadPool 並行後 ≈ 單 token 時間。
    import concurrent.futures as _cf

    def _one(t):
        try:
            return hybrid_hits(client, t, limit_i)
        except Exception:
            return []
    try:
        with _cf.ThreadPoolExecutor(max_workers=min(len(toks), 4)) as _ex:
            for hs in _ex.map(_one, toks):
                _add(hs)
    except Exception:
        for t in toks:
            try:
                _add(hybrid_hits(client, t, limit_i))
            except Exception:
                continue
    return _memory_first(list(seen.values()))[:limit]

def _memory_first(hits: list) -> list:
    """laap/memory/*（Aris 自己的記憶頁）排前面；其餘維持原序。"""
    mem = [h for h in hits if (h.get("slug") or "").startswith("laap/memory")]
    rest = [h for h in hits if not (h.get("slug") or "").startswith("laap/memory")]
    return (mem + rest)[: max(len(hits), 10)]

