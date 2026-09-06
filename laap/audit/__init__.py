"""laap.audit — 結案審計閘。

核心承諾只有一句：**稽核器自己重新推導事實，不讀被稽核方寫的東西。**

用法
----
    from laap.audit import audit_text
    report = audit_text(aris_output, source="transform_llm_output")
    if report.had_claims and not report.all_passed:
        ...  # report.render() 是給人看的字串

命令列（會 exit 1，所以可以當閘用）::

    echo "$OUTPUT" | python3 -m laap.audit
    python3 -m laap.audit some_file.md

已停用的舊模組
--------------
* ``anchor.py`` —— 同目錄、同使用者、無密鑰的自簽 MD5「指紋」。被稽核方
  改完證據重簽即可過關，防不了刻意造假，只擋「改完忘了重簽」。
* ``completion_auditor.py`` —— 讀 Aris 自己寫的 log 搜 "passed"/"ok" 字串。
  真的 pytest 輸出含 "0 failed" 會被判失敗，而任何含 "token" 的垃圾會被
  判通過（"ok" 是 "token" 的子字串）。兩個方向都是錯的。
* ``interceptor.py`` —— 用正則抽 JSON（換行即失配、巢狀即截斷），而且被接
  在 ``pre_llm_call``，看到的是注入用提示詞，不是 Aris 的輸出。

這三個檔還留在磁碟上但已無人 import。它們不在版控裡，所以留給你確認後再刪。
"""

from laap.audit.gate import (
    FAIL,
    INVALID,
    PASS,
    Report,
    Verdict,
    audit_text,
    run_gate,
)
from laap.audit.manifest import TAG, Manifest, extract
from laap.audit.verifiers import Evidence, known_types

__all__ = [
    "PASS",
    "FAIL",
    "INVALID",
    "TAG",
    "Evidence",
    "Manifest",
    "Report",
    "Verdict",
    "audit_text",
    "extract",
    "known_types",
    "run_gate",
]
