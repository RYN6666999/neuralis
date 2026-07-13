"""
AnalogicalEngine — dict-based 類比推理引擎 (純 Python)

從 stub 升級為可運行的類比引擎。
管理多個域(domain)的結構映射，支援跨域類比查詢。
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("laap.agi.analogical")


class AnalogicalEngine:
    """類比推理引擎 — 跨域映射與結構對齊"""

    def __init__(self, **kwargs):
        logger.info("[Analogical] dict-based 初始化")
        self._domains: Dict[str, Dict[str, Any]] = {}  # domain_name → {items, tags, structure}

    def encode_domain(self, name: str, items: List[Dict[str, Any]]) -> None:
        """編碼一個域(domain)的知識結構。"""
        key = name.lower().strip()
        tags = set()
        structure = {}

        for item in items:
            item_key = item.get("name", str(item)).lower()
            structure[item_key] = item
            if "tags" in item:
                for t in item["tags"]:
                    tags.add(str(t))

        self._domains[key] = {
            "name": name,
            "items": items,
            "tags": list(tags),
            "structure": structure,
            "item_count": len(items),
        }
        logger.info(f"[Analogical] 域 '{name}' 編碼: {len(items)} 項目")

    def find_analogies(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """在已知域中尋找與 query 最類似的結構映射。"""
        q = query.lower().strip()
        results = []

        for dkey, domain in self._domains.items():
            score = 0.0

            # 域名匹配
            if q == dkey:
                score = 1.0
            elif q in dkey:
                score = 0.7

            # 標籤匹配
            if not score:
                for tag in domain["tags"]:
                    if q in tag.lower():
                        score = max(score, 0.5)
                        break

            # 項目內部文字匹配
            if not score:
                for item in domain["items"]:
                    item_str = str(item).lower()
                    if q in item_str:
                        score = max(score, 0.3)
                        break

            if score > 0:
                # 取該域中最相關的項目
                matched_items = []
                for s_key, s_item in domain["structure"].items():
                    if q in s_key or any(q in str(v).lower() for v in s_item.values() if isinstance(v, str)):
                        matched_items.append(s_item)

                results.append({
                    "domain": domain["name"],
                    "score": round(score, 3),
                    "item_count": domain["item_count"],
                    "matched_items": matched_items or domain["items"][:3],
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def transfer(self, source_domain: str, target_domain: str) -> List[Dict[str, Any]]:
        """從 source_domain 到 target_domain 的結構映射轉移。"""
        src = self._domains.get(source_domain.lower().strip())
        tgt = self._domains.get(target_domain.lower().strip())
        if not src or not tgt:
            return []

        transfers = []
        for s_item in src["items"]:
            base = dict(s_item)
            base["_transfer_from"] = source_domain
            base["_transfer_to"] = target_domain
            transfers.append(base)
        return transfers

    def __len__(self) -> int:
        return len(self._domains)