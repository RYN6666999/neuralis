#!/usr/bin/env python3
"""scream patch 健康檢查 — 每次 scream-code 更新後跑，少任何 patch 就大聲報警。

痛點：scream 是 npm 編譯後的 bundle，`npm update` 會換掉 dist 檔、把所有 neuralis
patch 洗掉（且檔名 hash 變）。過去這是靜默壞掉——Aris 整合沒了卻沒人知道。這支把
它變成大聲失敗：讀 active bundle，逐一檢查每個 patch-scream-*.py 的 MARK 在不在，
缺的就 ❌ + exit 1。

升級儀式：`npm update scream-code` → 重跑所有 patch → 本檢查全 ✅ → 才重啟 Scream。
本檢查 ❌ = 該 patch 錨點對不上新版，重錨後再用（別在半殘狀態開 Aris）。
"""
import re
import sys
from pathlib import Path

DIST = Path("/opt/homebrew/lib/node_modules/scream-code/dist")
SCRIPTS = Path(__file__).resolve().parent


def _active_bundle() -> Path | None:
    """main.mjs 指向的 app-*.mjs（active bundle，非 .bak）。"""
    main = DIST / "main.mjs"
    if main.exists():
        m = re.search(r"app-[A-Za-z0-9]+\.mjs", main.read_text("utf-8"))
        if m and (DIST / m.group(0)).exists():
            return DIST / m.group(0)
    cands = [p for p in DIST.glob("app-*.mjs") if not p.name.endswith(".bak")]
    return cands[0] if cands else None


def _expected_marks() -> dict:
    """從每個 patch-scream-*.py 抽 MARK = "..."（自維護，不硬編）。"""
    marks = {}
    for p in sorted(SCRIPTS.glob("patch-scream-*.py")):
        m = re.search(r'^MARK\s*=\s*[\'"]([^\'"]+)[\'"]', p.read_text("utf-8"), re.M)
        if m:
            marks[p.name] = m.group(1)
    return marks


def main() -> int:
    bundle = _active_bundle()
    if bundle is None:
        print(f"❌ 找不到 active bundle（{DIST}）— scream 裝了嗎？")
        return 1
    content = bundle.read_text("utf-8", errors="replace")
    marks = _expected_marks()
    if not marks:
        print("⚠️ 找不到任何 patch-scream-*.py 的 MARK")
        return 1

    print(f"scream bundle: {bundle.name}\n")
    missing = []
    for patch, mark in marks.items():
        ok = mark in content
        print(f"  {'✅' if ok else '❌'} {patch}  (MARK: {mark})")
        if not ok:
            missing.append(patch)

    if missing:
        print(f"\n❌ {len(missing)}/{len(marks)} patch 不在 bundle — Aris 整合半殘。")
        print("   重跑該 patch；若 loud-fail『找不到錨點』= scream 改版了，需重錨。")
        print("   別在半殘狀態開 Aris。")
        return 1
    print(f"\n✅ 全部 {len(marks)} 個 patch 都在。Aris 整合完整。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
