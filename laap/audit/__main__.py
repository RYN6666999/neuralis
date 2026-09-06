"""命令列入口 —— 這是閘的「會 exit 1 的那個東西」。

    echo "$OUTPUT" | python3 -m laap.audit
    python3 -m laap.audit report.md
    python3 -m laap.audit --json < output.txt

exit code
---------
0   有宣告且全部 PASS，或完全沒有宣告（沒宣告就沒東西可驗，不是失敗）
1   有任何 FAIL / INVALID
2   用法錯誤

「沒有宣告 = exit 0」是刻意的：這個閘驗的是**被提出的宣稱**，它無法強迫
一個宣稱被提出。要擋「沒貼標籤就結案」需要接在 pre_tool_call（Hermes 唯一
能 block 的事件），那是另一件事，不要在這裡假裝做到了。
"""

from __future__ import annotations

import argparse
import json
import sys

from laap.audit.gate import audit_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m laap.audit",
        description="驗證文字中的 [AUDIT_MANIFEST] 結案宣告（自行重跑證據）",
    )
    parser.add_argument("path", nargs="?", help="要檢查的檔案，省略則讀 stdin")
    parser.add_argument("--json", action="store_true", help="輸出 JSON 而非人讀格式")
    parser.add_argument("--source", default="cli", help="寫進 ledger 的來源標記")
    args = parser.parse_args(argv)

    if args.path:
        try:
            text = open(args.path, encoding="utf-8").read()
        except OSError as exc:
            print(f"讀不到 {args.path}: {exc}", file=sys.stderr)
            return 2
    else:
        text = sys.stdin.read()

    report = audit_text(text, source=args.source)

    if args.json:
        print(
            json.dumps(
                {
                    "had_claims": report.had_claims,
                    "all_passed": report.all_passed,
                    "verdicts": [
                        {
                            "status": v.status,
                            "task_id": v.task_id,
                            "evidence_type": v.evidence_type,
                            "reason": v.reason,
                            "detail": v.detail,
                        }
                        for v in report.verdicts
                    ],
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
    else:
        if not report.had_claims:
            print("沒有 [AUDIT_MANIFEST] 宣告，無事可驗。")
        else:
            print(report.render())

    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())
