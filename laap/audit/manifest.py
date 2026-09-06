"""從 Aris 的輸出文字中抽出 [AUDIT_MANIFEST] 宣告。

設計約束
--------
* **不用正則抽 JSON。** 正則無法處理巢狀物件，也吃不到換行 —— 舊版
  `re.findall(r"\\[AUDIT_MANIFEST\\]\\s*(\\{.*?\\})")` 的後果是：manifest 一
  換行就完全不匹配（靜默放行），一巢狀就被截斷（假紅）。這裡改用括號配對
  掃描，字串內的括號與跳脫字元都會被跳過。
* **解析失敗必須留痕，不能靜默跳過。** 一個壞掉的 manifest 是 INVALID，
  會進入 verdict 列表，不會消失。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

TAG = "[AUDIT_MANIFEST]"


@dataclass(frozen=True)
class Manifest:
    """一筆結案宣告。`raw` 保留原文供稽核軌跡對帳。"""

    raw: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.data is not None

    @property
    def task_id(self) -> str:
        if not self.data:
            return "<unparseable>"
        return str(self.data.get("task_id") or "<no-task-id>")


def _scan_json_object(text: str, start: int) -> Optional[str]:
    """從 text[start] 的 '{' 開始做括號配對，回傳完整 JSON 物件字串。

    字串字面值內的括號不計數，反斜線跳脫的字元直接跳過。找不到配對回 None。
    """
    if start >= len(text) or text[start] != "{":
        return None

    depth = 0
    in_string = False
    escaped = False

    for i in range(start, len(text)):
        ch = text[i]

        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return None


def extract(text: str) -> List[Manifest]:
    """抽出文字中所有 [AUDIT_MANIFEST] 宣告，依出現順序。

    找不到標籤回空 list。找得到標籤但 JSON 壞掉，回一筆 error 非 None 的
    Manifest —— 呼叫端必須把它當 FAIL 處理，不是當作沒看見。
    """
    if not text or TAG not in text:
        return []

    out: List[Manifest] = []
    cursor = 0

    while True:
        idx = text.find(TAG, cursor)
        if idx == -1:
            break
        cursor = idx + len(TAG)

        brace = text.find("{", cursor)
        if brace == -1:
            # 標籤後完全沒有 JSON —— 這是散文在提到標籤（例如 SKILL.md 在
            # 說明格式），不是一筆宣告。判成 INVALID 會製造假紅，而假紅比
            # 沒有更糟：人會學會無視紅燈。
            break

        # 標籤與 '{' 之間只允許空白，否則視為誤報（例如文件在說明格式）
        between = text[cursor:brace]
        if between.strip():
            continue

        blob = _scan_json_object(text, brace)
        if blob is None:
            out.append(Manifest(raw=text[idx:brace + 80], error="JSON 物件括號未配對"))
            break

        cursor = brace + len(blob)

        try:
            parsed = json.loads(blob)
        except json.JSONDecodeError as exc:
            out.append(Manifest(raw=blob, error=f"JSON 解析失敗: {exc}"))
            continue

        if not isinstance(parsed, dict):
            out.append(Manifest(raw=blob, error="manifest 必須是 JSON 物件"))
            continue

        out.append(Manifest(raw=blob, data=parsed))

    return out
