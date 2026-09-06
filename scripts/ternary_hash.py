"""
ternary_hash.py — 三進制哈希字詞網絡原型 V3

V2 問題：線性組合 (cp + offset) % 3 只有 3 種映射，區分度太低 → 不同句子向量趨近相同。
V3 解法：FNV-1a non-cryptographic hash + 隨機投影，保留足夠的區分度又不會 avalanche 爆炸。

FNV-1a 特性：非密碼學 hash，快速、分布均勻（非加密用途因此對相近輸入的碰撞率高於 MD5）。
仍需要句子層頻率加權 + bigram 通道來提供同義容錯。
"""

import math
from typing import List, Dict, Optional, Tuple

DEFAULT_DIM = 64

# ==============================
# 核心：FNV-1a 哈希
# ==============================

def _fnv1a(data: bytes, seed: int = 2166136261) -> int:
    """FNV-1a 32-bit hash"""
    h = seed
    for byte in data:
        h ^= byte
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def _char_hash_fnv(char: str, dim_idx: int) -> int:
    """字符 + 維度索引 → FNV hash"""
    cp = ord(char)
    # 混合 Unicode 屬性作為額外種子
    cat_prefix = 0
    if '\u4e00' <= char <= '\u9fff':
        cat_prefix = 1  # CJK
    elif '\u3040' <= char <= '\u30ff':
        cat_prefix = 2  # 假名
    elif '\uac00' <= char <= '\ud7af':
        cat_prefix = 3  # 韓文
    elif 'a' <= char <= 'z' or 'A' <= char <= 'Z':
        cat_prefix = 4
    elif '0' <= char <= '9':
        cat_prefix = 5
    else:
        cat_prefix = 6

    # 種子 = cp + category + dim_idx
    seed_bytes = f"{cp}|{cat_prefix}|{dim_idx}".encode()
    return _fnv1a(seed_bytes)


def char_to_ternary(char: str, dim: int = DEFAULT_DIM) -> List[int]:
    """單字符 → 三元向量（FNV 隨機投影）"""
    vec = []
    for i in range(dim):
        h = _char_hash_fnv(char, i)
        val = h % 3
        vec.append(1 if val == 2 else (-1 if val == 1 else 0))
    return vec


# ==============================
# 句子簽名 V3
# ==============================

def _build_bag(text: str) -> Tuple[dict, dict]:
    """字元頻率表 + bigram 頻率表"""
    unigram = {}
    for ch in text:
        unigram[ch] = unigram.get(ch, 0) + 1

    bigram = {}
    for j in range(len(text) - 1):
        bg = text[j:j+2]
        bigram[bg] = bigram.get(bg, 0) + 1

    return unigram, bigram


def sentence_signature(
    text: str, dim: int = DEFAULT_DIM,
    mingram_weight: float = 0.65,   # unigram 權重
    bg_weight: float = 0.25,        # bigram 權重
    length_norm: bool = True
) -> List[int]:
    """
    V3: unigram + bigram 雙通道，FNV 隨機投影
    
    量化閾值自適應文本長度（短句用高閾值，長句用低閾值）
    """
    if not text.strip():
        return [0] * dim

    unigram, bigram = _build_bag(text)
    total_u = len(text)
    total_b = len(text) - 1 if len(text) > 1 else 1

    # 通道 A：unigram 頻率加權平均
    acc_a = [0.0] * dim
    for ch, count in unigram.items():
        vec = char_to_ternary(ch, dim)
        w = count / total_u
        for i in range(dim):
            acc_a[i] += vec[i] * w

    # 通道 B：bigram 頻率加權平均
    acc_b = [0.0] * dim
    for bg, count in bigram.items():
        # bigram 向量 = 兩個字元逐元素平均
        half_vec = [0.0] * dim
        for ch in bg:
            cv = char_to_ternary(ch, dim)
            for i in range(dim):
                half_vec[i] += cv[i]
        for i in range(dim):
            half_vec[i] /= 2
        w = count / total_b
        for i in range(dim):
            acc_b[i] += half_vec[i] * w

    # 合併雙通道
    merged = [0.0] * dim
    for i in range(dim):
        merged[i] = acc_a[i] * mingram_weight + acc_b[i] * bg_weight

    # 自適應量化閾值
    # 短句：值的範圍集中，用較高閾值確保有非零維度
    # 長句：值已平均化，用較低閾值防止全部歸零
    threshold = 0.08 if total_u > 20 else (0.12 if total_u > 10 else 0.18)

    return [_quantize(v, threshold) for v in merged]


def _quantize(x: float, threshold: float) -> int:
    if x > threshold:
        return 1
    elif x < -threshold:
        return -1
    return 0


# ==============================
# 相似度
# ==============================

def cosine_similarity(v1: List[int], v2: List[int]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


# ==============================
# 索引
# ==============================

class TernaryIndex:
    def __init__(self, dim: int = DEFAULT_DIM):
        self.dim = dim
        self._entries: List[Dict] = []

    def add(self, text: str, meta: Optional[Dict] = None) -> None:
        sig = sentence_signature(text, self.dim)
        self._entries.append({"text": text, "sig": sig, "meta": meta or {}})

    def search(self, query: str, top_n: int = 5, min_score: float = 0.0) -> List[Dict]:
        q_sig = sentence_signature(query, self.dim)

        results = []
        for entry in self._entries:
            score = cosine_similarity(q_sig, entry["sig"])
            if score >= min_score:
                results.append({
                    "text": entry["text"],
                    "score": round(score, 4),
                    "meta": entry["meta"]
                })

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_n]

    def __len__(self) -> int:
        return len(self._entries)


# ==============================
# 自測
# ==============================

def self_test():
    print("=" * 55)
    print("三進制哈希 V3 — 基本自測")
    print("=" * 55)

    # 1. 同一句
    s1 = "今天天氣很好"
    s2 = "今天天氣很好"
    v1 = sentence_signature(s1)
    v2 = sentence_signature(s2)
    cs = cosine_similarity(v1, v2)
    print(f"同一句:              {cs:.4f}  {'✅' if cs > 0.99 else '❌'}  (期望≈1.0)")

    # 2. 同義改寫
    s3 = "今天的氣候很棒"
    v3 = sentence_signature(s3)
    cs = cosine_similarity(v1, v3)
    print(f"同義改寫:            {cs:.4f}  {'✅' if cs > 0.2 else '❌'}  (期望>0.2)")

    # 3. 完全無關
    s4 = "我昨天買了一台新電腦"
    v4 = sentence_signature(s4)
    cs = cosine_similarity(v1, v4)
    print(f"完全無關:            {cs:.4f}  {'✅' if cs < 0.4 else '❌'}  (期望<0.4)")

    # 4. 錯字（氣→汽）
    s5 = "今天汽候很好"
    v5 = sentence_signature(s5)
    cs = cosine_similarity(v1, v5)
    print(f"錯字(汽→氣):        {cs:.4f}  {'✅' if cs > 0.1 else '❌'}  (期望>0.1)")

    # 5. 長短句同主題
    s6 = "天氣好適合出遊"
    s6_full = "今天天氣很好適合出遊散步"
    v6_short = sentence_signature(s6)
    v6_full = sentence_signature(s6_full)
    cs = cosine_similarity(v6_short, v6_full)
    print(f"長短句同主題:        {cs:.4f}  {'✅' if cs > 0.15 else '❌'}  (期望>0.15)")

    # 6. 多義字區分 — 河/和/合/荷
    s_he1 = "河邊的風景很美"
    s_he2 = "合約的條款很嚴格"
    v_he1 = sentence_signature(s_he1)
    v_he2 = sentence_signature(s_he2)
    cs_he = cosine_similarity(v_he1, v_he2)
    print(f"多義字(河vs合約):   {cs_he:.4f}  {'✅' if cs_he < 0.3 else '❌'}  (期望<0.3)")

    # 7. 檢索測試
    idx = TernaryIndex()
    phrases = [
        "今天天氣很好適合出遊",
        "今天的氣候不錯適合出去玩",
        "蘋果手機很好用",
        "安卓系統也很穩定",
        "我昨天買了一台筆記型電腦",
        "氣溫舒爽很適合戶外活動踏青",
        "這台電腦的處理器效能很棒",
        "華為手機的拍照效果也不錯",
        "昨天天氣陰陰的沒有出門",
        "新筆電的螢幕解析度很高",
        "河邊的風景很美適合散步",
        "和他一起吃飯很開心",
        "合約的條款需要仔細審閱",
        "荷塘裡的荷花盛開了",
    ]
    for p in phrases:
        idx.add(p)

    queries = [
        ("天氣適合出遊", "今天天氣很好適合出遊"),
        ("新電腦效能不錯", "這台電腦的處理器效能很棒"),
        ("手機很好用", "蘋果手機很好用"),
        ("河邊散步", "河邊的風景很美適合散步"),
        ("合約條款", "合約的條款需要仔細審閱"),
        ("荷花", "荷塘裡的荷花盛開了"),
    ]

    print("\n--- 檢索測試 ---")
    print(f"{'查詢':<20} {'Top-1 結果':<30} {'分數':<6} {'命中':<6}")
    print("-" * 62)
    for q, expected in queries:
        results = idx.search(q, top_n=1)
        if results:
            hit = "✅" if results[0]["text"] == expected else "❌"
            print(f"{q:<20} {results[0]['text'][:28]:<30} {results[0]['score']:<6.3f} {hit}")

    # 檢查排名（如果第一沒中，看第幾）
    print("\n--- 排名檢查（前3）---")
    for q, expected in queries:
        results = idx.search(q, top_n=3)
        rank = next((i+1 for i, r in enumerate(results) if r["text"] == expected), None)
        if rank:
            print(f"「{q}」→ 目標在第 {rank} 名 (top-3: {' | '.join(r['text'][:20] for r in results)})")
        else:
            print(f"「{q}」→ ❌ 目標未進前3 (top-3: {' | '.join(r['text'][:20] for r in results)})")

    print("\n✅ 自測完成")


if __name__ == "__main__":
    self_test()