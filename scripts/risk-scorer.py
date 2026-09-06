#!/usr/bin/env python3
"""
risk-scorer.py — GitNexus-powered 8 維風險評分

用法:
  python3 risk-scorer.py --diff <git-diff-file>
  python3 risk-scorer.py --file <changed-file.py>

輸出 JSON：
  { score: 0-24, level: "🟢🟡🔴🟣", dimension_scores: {...}, evidence: [...] }

每維 0-3：
  0 = 安全，1 = 需注意，2 = 高風險，3 = 架構級警告

依賴：
  - GitNexus CLI (node .gitnexus/run.cjs)
  - git, ripgrep, or builtin file analysis
"""

import argparse, json, os, re, subprocess, sys, tempfile
from pathlib import Path

GN_ROOT = Path.home() / "Developer" / "neuralis"
GN_CLI = "node .gitnexus/run.cjs"


def _run_gn(*args: str, repo: str = str(GN_ROOT)) -> dict:
    """Run a GitNexus CLI command and return parsed JSON."""
    cmd = f"cd {repo} && {GN_CLI} {' '.join(args)} --repo {repo}"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return {"error": r.stderr[:200]}
        return json.loads(r.stdout)
    except subprocess.TimeoutExpired:
        return {"error": "GitNexus timed out"}
    except json.JSONDecodeError as e:
        return {"error": str(e)[:200]}


def _changed_symbols(diff_text: str, file_path: str) -> list[dict]:
    """Extract changed symbols from a diff + file scan.
    Falls back to scanning the file directly when diff_text is empty (--file mode).
    Returns [{name, type, file, line}]."""
    symbols = []

    # If no diff text, read the file directly for symbol extraction
    content_to_scan = diff_text
    if not diff_text.strip() and file_path and file_path != "unknown":
        try:
            with open(file_path) as _f:
                content_to_scan = _f.read()
        except (FileNotFoundError, PermissionError):
            pass  # _classify_risk handles this

    # Method/function definitions in diff
    for m in re.finditer(r'^\+.*?def (\w+)\(', content_to_scan, re.MULTILINE):
        symbols.append({"name": m.group(1), "type": "method", "line": 0})
    # Also scan non-diff-prefixed function defs (--file mode fallback)
    if not diff_text.strip():
        for m in re.finditer(r'^\s*def (\w+)\(', content_to_scan, re.MULTILINE):
            symbols.append({"name": m.group(1), "type": "method", "line": 0})
    # Class definitions
    for m in re.finditer(r'^\+.*?class (\w+)', content_to_scan, re.MULTILINE):
        symbols.append({"name": m.group(1), "type": "class", "line": 0})
    if not diff_text.strip():
        for m in re.finditer(r'^\s*class (\w+)', content_to_scan, re.MULTILINE):
            symbols.append({"name": m.group(1), "type": "class", "line": 0})
    # New global variable assignments
    for m in re.finditer(r'^\+(\w+)\s*=', diff_text, re.MULTILINE):
        name = m.group(1)
        if name.upper() == name or name.startswith("_"):
            symbols.append({"name": name, "type": "global", "line": 0})
    # New API endpoints
    for m in re.finditer(r"u\.path\s*==\s*['\"]([^'\"]+)['\"]", diff_text):
        symbols.append({"name": f"endpoint:{m.group(1)}", "type": "endpoint", "line": 0})
    for m in re.finditer(r'u\.path\s*==\s*"([^"]+)"', diff_text):
        symbols.append({"name": f"endpoint:{m.group(1)}", "type": "endpoint", "line": 0})

    return symbols


def _classify_risk(symbols: list[dict], file_path: str, repo_root: str) -> dict:
    """8 維風險分析"""
    scores = {
        "cross_process": 0,       # 跨進程邊界
        "silent_degradation": 0,  # 靜默降級
        "consumer_island": 0,     # 消費者孤島
        "cache_staleness": 0,     # 快取失效
        "format_coupling": 0,     # 格式耦合
        "lifetime_asymmetry": 0,  # 生命周期不對稱
        "concurrent_state": 0,    # 並發狀態
        "schema_rigidity": 0,     # schema 僵硬
    }
    evidence = []
    file_name = Path(file_path).name

    # ── 維度 1：跨進程邊界 ──
    # 線索：檔案含「serve」「port」「PID」「socket」
    try:
        with open(file_path) as f:
            content = f.read()
    except (FileNotFoundError, PermissionError) as _e:
        content = ""
        evidence.append(f"🟡 無法讀取 {file_path}（{_e}），跳過檔案分析維度")
    if re.search(r'(serve_forever|HTTPServer|listen|PORT\s*=|socket)', content):
        scores["cross_process"] = 3
        evidence.append("🔴 包含 HTTP/進程服務代碼（跨進程邊界高風險）")
    elif re.search(r'(nohup|background|spawn|subprocess)', content):
        scores["cross_process"] = 2
        evidence.append("🟡 有背景行程/子行程操作")

    # ── 維度 2：靜默降級 ──
    silent_count = len(re.findall(r'except\s+\w+\s*:\s*\n\s*(pass|#|"")', content))
    none_returns = len(re.findall(r'return\s+None', content))
    if silent_count > 0:
        scores["silent_degradation"] = min(3, silent_count)
        evidence.append(f"🔴 發現 {silent_count} 個空 except（例外被吞）")
    if none_returns > 0:
        scores["silent_degradation"] = max(scores["silent_degradation"], min(2, none_returns))
        evidence.append(f"🟡 {none_returns} 個 return None 路徑（可能被消費端當成功）")

    # ── 維度 3：消費者孤島（GitNexus impact analysis）──
    # 符號過多時（超過 10 個）跳過 GitNexus，避免耗時過長
    gn_analyzed = 0
    for sym in symbols:
        if sym["type"] in ("method", "class"):
            if gn_analyzed >= 10:
                evidence.append(f"🟡 符號過多（>{gn_analyzed})，跳過剩餘 GitNexus 消費者分析")
                break
            imp = _run_gn("impact", sym["name"], "--direction", "upstream", f"--repo={repo_root}")
            gn_analyzed += 1
            if imp.get("impactedCount", -1) == 0 and "No callers" in str(imp):
                scores["consumer_island"] = max(scores["consumer_island"], 2)
                evidence.append(f"🔴 {sym['name']} — GitNexus 0 callers（消費者孤島）")
            elif imp.get("risk") == "UNKNOWN":
                # 動態語言常見，不扣分但記錄
                pass
    # 靜態補充：檢查 endpoint 是否有對應的 consumer reference
    endpoints_src = re.findall(r"""['"]/([\w/]+)['"]""", content)
    for ep in endpoints_src:
        # 如果 endpoint 名稱沒出現在 import 或 consumer 引用中，可能孤島
        if not re.search(re.escape(ep.split("/")[-1]), content):
            pass  # 不夠精確，僅記錄
    # 檢查是否有未使用的 API 端點（加新端點但沒加 consumer 測試）
    new_endpoints = re.findall(r"u\.path\s*==\s*['\"]/([\w/]+)['\"]", content)
    if len(new_endpoints) > 0:
        # 加新端點時，檢查同一檔案有沒有對應的 test/consumer 引用
        test_refs = re.findall(r'/([\w/]+)', content)
        endpoints_no_ref = [e for e in new_endpoints if e not in content.replace("u.path", "")]
        if len(endpoints_no_ref) == len(new_endpoints):
            scores["consumer_island"] = max(scores["consumer_island"], 1)
            evidence.append(f"🟡 新端點無對應 consumer 引用（可能孤島）")

    # ── 維度 4：快取失效 ──
    cache_patterns = re.findall(r'(TTL|cache|_cache|mtime|timeout)', content)
    if cache_patterns:
        # 檢查是否有快取檢查
        if not re.search(r'(age|diff|mtime|fresh|expire)', content):
            scores["cache_staleness"] = 2
            evidence.append(f"🟡 有快取（{len(cache_patterns)} 處）但無過期檢查")

    # ── 維度 5：格式耦合 ──
    # 檢查 return dict 或 JSON schema 變更
    dict_returns = re.findall(r'return\s*\{', content)
    if len(dict_returns) > 1:
        scores["format_coupling"] = min(3, len(dict_returns))
        evidence.append(f"🟡 {len(dict_returns)} 個 dict return（格式耦合風險）")
    # 也檢查多層 dict/literal 構建
    multiline_dict = len(re.findall(r'return\s*\{[^}]*\n', content))
    if multiline_dict > 0:
        scores["format_coupling"] = max(scores["format_coupling"], 1)
        evidence.append(f"🟡 {multiline_dict} 個多行 dict return（回傳形狀風險）")
    # API 端點變更
    endpoints = re.findall(r"""['"]/([\w/]+)['"]""", content)
    if len(endpoints) > 5:
        scores["format_coupling"] = max(scores["format_coupling"], 2)
        evidence.append(f"🟡 {len(endpoints)} 個路由端點（API schema 耦合）")

    # ── 維度 6：生命周期不對稱 ──
    open_calls = len(re.findall(r'(\.open\(|\.connect\(|\.start\(|lock\.acquire)', content))
    close_calls = len(re.findall(r'(\.close\(|\.release\(|\.stop\(|lock\.release)', content))
    if open_calls > close_calls + 1:
        scores["lifetime_asymmetry"] = min(3, open_calls - close_calls)
        evidence.append(f"🔴 open={open_calls} close={close_calls}（資源釋放不對稱）")
    # 檢查 threading.Lock
    if re.search(r'threading\.Lock', content) and not re.search(r'release\(|with\s+self\._lock', content):
        scores["lifetime_asymmetry"] = max(scores["lifetime_asymmetry"], 1)

    # ── 維度 7：並發共享狀態 ──
    globals_written = re.findall(r'^\s*(\w+)\s*=', content, re.MULTILINE)
    module_level = [g for g in globals_written if not g.startswith("_") and g.isupper()]
    if len(module_level) > 3:
        scores["concurrent_state"] = min(3, len(module_level) // 3)
        evidence.append(f"🟡 {len(module_level)} 個 module-level 可寫變數（並發風險）")
    # 查無鎖的共享狀態
    if re.search(r'_lock|threading\.Lock', content) and len(re.findall(r'with\s+self\._lock', content)) < 3:
        scores["concurrent_state"] = max(scores["concurrent_state"], 1)
        evidence.append("🟡 有 lock 但使用次數偏少")

    # ── 維度 8：schema 僵硬 ──
    if re.search(r'(CREATE TABLE|ALTER TABLE|schema|PRAGMA)', content):
        scores["schema_rigidity"] = 2
        evidence.append("🟡 包含 schema 變更（遷移相容性需確認）")
    if re.search(r'json\.loads|json\.dump', content):
        # JSON 解析有鬆散型別，略扣
        scores["schema_rigidity"] = max(scores["schema_rigidity"], 1)

    # ── 補充維度：領域樹關鍵字交叉比對 ──
    # 從 domain-tree-keywords.json 自動讀取。領域樹新增節點/關鍵字後自動跟進。
    _dtk_path = Path(repo_root) / "references" / "domain-tree-keywords.json"
    if _dtk_path.exists():
        try:
            _dtk = json.loads(_dtk_path.read_text())
            _domain_hits = set()
            for _node in _dtk.get("nodes", []):
                _node_kws = [k.lower() for k in _node.get("keywords", [])]
                _matched = [k for k in _node_kws if k in content.lower() and len(k) >= 2]
                if _matched:
                    _domain_hits.add(_node["name"])
            if _domain_hits:
                evidence.append(f"領域樹概念命中（{len(_domain_hits)} 個域）: {', '.join(sorted(_domain_hits)[:5])}")
                # 不新增維度（不影響 8 維閾值校準），僅作為情境證據
        except (json.JSONDecodeError, FileNotFoundError, PermissionError, KeyError, TypeError) as _e:
            evidence.append(f"🟡 領域樹關鍵字載入跳過（{_e}）")

    total = sum(scores.values())
    if total <= 4:
        level = "🟢"
    elif total <= 8:
        level = "🟡"
    elif total <= 12:
        level = "🔴"
    else:
        level = "🟣"

    return {
        "score": total,
        "level": level,
        "dimensions": scores,
        "evidence": evidence,
        "symbols_analyzed": symbols,
    }


def main():
    parser = argparse.ArgumentParser(description="GitNexus-powered risk scorer")
    parser.add_argument("--diff", help="Path to git diff file")
    parser.add_argument("--file", help="Path to changed file")
    parser.add_argument("--repo", default=str(GN_ROOT), help="Repo root for GitNexus")
    args = parser.parse_args()

    if not args.diff and not args.file:
        # Last N commits diff (default mode)
        # HEAD~3 diff 可能極大（12MB+），當 timeout 或回傳非零時 fallback 到 HEAD~1
        diff_text = ""
        try:
            result = subprocess.run(
                "cd ~/Developer/neuralis && git diff HEAD~3..HEAD",
                shell=True, capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                diff_text = result.stdout
        except subprocess.TimeoutExpired:
            pass  # fall through to HEAD~1 fallback
        if not diff_text.strip():
            try:
                result = subprocess.run(
                    "cd ~/Developer/neuralis && git diff HEAD~1..HEAD",
                    shell=True, capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    diff_text = result.stdout
            except subprocess.TimeoutExpired:
                pass
        if not diff_text.strip():
            print(json.dumps({"result": "no_changes", "score": 0, "level": "🟢"}))
            return
        # Find changed files
        files = re.findall(r'^\+\+\+\s+b/(.*)', diff_text, re.MULTILINE)
        changed_files = [f.strip() for f in files if f.strip()]
        if not changed_files:
            print(json.dumps({"result": "no_changes", "score": 0, "level": "🟢"}))
            return
        file_path = os.path.join(args.repo, changed_files[0])
        if not os.path.exists(file_path):
            print(json.dumps({"error": f"file not found: {file_path}"}))
            sys.exit(1)
    elif args.diff:
        with open(args.diff) as f:
            diff_text = f.read()
        file_path = args.file or "unknown"
    else:
        diff_text = ""
        file_path = args.file

    symbols = _changed_symbols(diff_text, file_path)
    result = _classify_risk(symbols, file_path, args.repo)
    result["file"] = file_path

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()