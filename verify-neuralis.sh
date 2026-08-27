#!/usr/bin/env bash
# verify-neuralis.sh — 在 Ryan 本機補齊沙盒驗不到的三件事
#
# 沙盒缺：cargo、gbrain binary、:11547、launchctl、macOS keychain vault
# 這支腳本只做「量測與回報」，不改動 repo、不 commit、不清資料。
#
# 用法：
#   cd ~/Developer/neuralis
#   bash verify-neuralis.sh              # 全部
#   bash verify-neuralis.sh cargo        # 只跑其中一段
#
# 輸出：終端摘要 + verify-report-<日期>.md（貼回頻道給我）

set -uo pipefail   # 故意不用 -e：某段失敗不該中止其餘量測

REPO="$(pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
REPORT="$REPO/verify-report-$STAMP.md"
SECTION="${1:-all}"

log()  { printf '%s\n' "$*" | tee -a "$REPORT"; }
head2() { log ""; log "## $*"; log ""; }

# ── 0. 安全檢查：絕不在有未提交變更的 repo 上跑 ──────────────
if [ ! -d .git ]; then
  echo "✗ 這裡不是 git repo。請 cd 到 neuralis 根目錄再跑。"; exit 2
fi
DIRTY="$(git status --porcelain)"
HEAD_BEFORE="$(git rev-parse HEAD)"

{
  echo "# neuralis 本機驗證報告"
  echo ""
  echo "- 時間：$(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "- 主機：$(hostname)"
  echo "- HEAD：\`$(git rev-parse --short HEAD)\`"
  echo "- macOS：$(sw_vers -productVersion 2>/dev/null || echo 'n/a')"
  echo "- Python：$(python3 -V 2>&1)"
  echo "- 工作區：$([ -z "$DIRTY" ] && echo '乾淨' || echo '⚠️ 有未提交變更')"
} > "$REPORT"

if [ -n "$DIRTY" ]; then
  log ""
  log "> ⚠️ 偵測到未提交變更。量測仍會進行，但如果有腳本污染了工作區，"
  log "> 你將無法區分那是它造成的還是你原本的改動。建議先 stash。"
fi

# ── 1. cargo：README:82 / ROADMAP:41 宣稱 45 passed，沙盒完全沒驗過 ──
if [ "$SECTION" = all ] || [ "$SECTION" = cargo ]; then
  head2 "1. Rust / cargo（沙盒完全未驗證的一段）"
  if ! command -v cargo >/dev/null 2>&1; then
    log "⚪ 沒裝 cargo — 沒驗到，不是通過也不是失敗。"
  else
    log "cargo: \`$(cargo --version)\`"
    RUSTDIR=""
    for d in rust engine psi-engine crates .; do
      [ -f "$d/Cargo.toml" ] && RUSTDIR="$d" && break
    done
    if [ -z "$RUSTDIR" ]; then
      log "⚪ 找不到 Cargo.toml — 請告訴我 Rust crate 的實際路徑。"
    else
      log "crate 目錄：\`$RUSTDIR\`"
      log ""
      log '```'
      ( cd "$RUSTDIR" && cargo test 2>&1 | tail -25 ) | tee -a "$REPORT"
      log '```'
      log ""
      log "**對照 README:82 宣稱的「45 passed」—— 上面實際數字是多少？**"
    fi
  fi
fi

# ── 2. 27 支自檢：沙盒 14 綠 13 紅，紅的多為環境性 ──────────────
if [ "$SECTION" = all ] || [ "$SECTION" = checks ]; then
  head2 "2. 自檢腳本（沙盒 14 綠 / 13 紅，多數紅是缺依賴）"
  log "| 腳本 | exit | 判讀 |"
  log "|---|---|---|"
  PASS=0; FAIL=0; TIMEOUT=0
  for f in scripts/check-*.py; do
    [ -e "$f" ] || continue
    # 200s：沙盒實測 check-watchdog 需 26s，25s 會誤判成 timeout
    if command -v gtimeout >/dev/null 2>&1; then TO=gtimeout; else TO=""; fi
    if [ -n "$TO" ]; then
      out="$($TO 200 python3 "$f" 2>&1)"; rc=$?
    else
      out="$(python3 "$f" 2>&1)"; rc=$?
    fi
    case $rc in
      0)   note="🟢 綠"; PASS=$((PASS+1)) ;;
      124) note="⏱ 逾時 200s（沙盒沒發生過，值得追）"; TIMEOUT=$((TIMEOUT+1)) ;;
      *)   note="🔴 紅"; FAIL=$((FAIL+1)) ;;
    esac
    # 抓出「明明 SKIP 卻回 0」——這正是 Engineer 那條線在修的病
    if [ $rc -eq 0 ] && printf '%s' "$out" | grep -qiE 'SKIP|不存在|not found|unavailable'; then
      note="⚠️ **回綠但內容有 SKIP** ← 綠燈說謊"
    fi
    log "| \`$(basename "$f")\` | $rc | $note |"
  done
  log ""
  log "**小計：🟢 $PASS / 🔴 $FAIL / ⏱ $TIMEOUT**"
  log ""
  log "沙盒基準是 14 綠 13 紅。你機器上綠的應該更多（有 gbrain / vault / launchctl）。"
  log "特別注意標 ⚠️ 的：那是 exit 0 但內容自己說 SKIP —— 綠燈說謊，Engineer 正在修。"
fi

# ── 3. S_span 真實資料體檢（只讀，不動資料） ──────────────────
if [ "$SECTION" = all ] || [ "$SECTION" = sspan ]; then
  head2 "3. S_span 評估資料體檢（唯讀）"
  AUDIT=""
  for p in _internal/agency-audit.jsonl agency-audit.jsonl \
           "$HOME/Library/Application Support/neuralis/agency-audit.jsonl"; do
    [ -f "$p" ] && AUDIT="$p" && break
  done
  if [ -z "$AUDIT" ]; then
    log "⚪ 找不到 \`agency-audit.jsonl\`。它在 \`.gitignore:31\`，只存在你本機。"
    log "如果路徑不同，請告訴我實際位置 —— **不要刪除或重建它**。"
  else
    N="$(wc -l < "$AUDIT" | tr -d ' ')"
    log "檔案：\`$AUDIT\`"
    log "筆數：**$N**"
    log ""
    if   [ "$N" -lt 100 ]; then log "🔴 **< 100，還不能下任何結論。** 真的有學習也只有約 50% 檢出率。"
    elif [ "$N" -lt 300 ]; then log "🟡 **≥ 100，可以下結論但不穩。** 建議累積到 300。"
    else                        log "🟢 **≥ 300，樣本足夠。** 判準在此區間誤判率約 4% 或更低。"
    fi
    log ""
    log "最舊 / 最新各一筆（確認是真實決策而非測試污染）："
    log '```'
    { head -1 "$AUDIT"; echo "..."; tail -1 "$AUDIT"; } | cut -c1-300 | tee -a "$REPORT"
    log '```'
    log ""
    log "> ⚠️ 如果內容長得像 \`\"echo test\"\` 這種，那是測試污染，不能用來評估 S_span。"
    if python3 -c "import laap.s_span_bench" 2>/dev/null; then
      log ""
      log "偵測到已套用 s_span patch，跑判準："
      log '```'
      python3 - "$AUDIT" <<'PY' 2>&1 | tee -a "$REPORT"
import json, sys
from laap.s_span_bench import learning_verdict
recs = []
for line in open(sys.argv[1]):
    line = line.strip()
    if line:
        try: recs.append(json.loads(line))
        except Exception: pass
v = learning_verdict(recs)
for k in ("n_records", "n_choices", "advantage", "null_p95", "learned", "underpowered"):
    print(f"{k:14} = {v.get(k)}")
print()
if v.get("underpowered"):
    print(">>> underpowered=True：樣本不足，'learned' 這個值不要當結論看。")
elif v.get("learned"):
    print(">>> 檢出學習訊號，且已超過虛無分布 95 百分位。")
else:
    print(">>> 樣本足夠但沒檢出學習訊號 —— 這是真結論，不是測不出來。")
PY
      log '```'
    else
      log ""
      log "⚪ \`laap.s_span_bench\` 匯入失敗 —— 還沒套 \`p1-fix.patch\`，判準是舊的（誤判率 40%）。"
    fi
  fi
fi

# ── 4. 收尾：確認這支腳本自己沒污染 repo ────────────────────
head2 "4. 這支腳本有沒有弄髒你的 repo"
HEAD_AFTER="$(git rev-parse HEAD)"
if [ "$HEAD_BEFORE" != "$HEAD_AFTER" ]; then
  log "🔴 **HEAD 被移動了**：\`${HEAD_BEFORE:0:7}\` → \`${HEAD_AFTER:0:7}\`"
  log "有腳本 commit 了東西（\`check-mechanisms.py\` 舊版會這樣）。回復："
  log "\`\`\`bash"
  log "git reset --hard $HEAD_BEFORE"
  log "\`\`\`"
else
  log "🟢 HEAD 未動（\`${HEAD_BEFORE:0:7}\`）"
fi
NEWFILES="$(git status --porcelain | grep -v "verify-report-" || true)"
if [ -n "$NEWFILES" ] && [ "$NEWFILES" != "$DIRTY" ]; then
  log ""
  log "⚠️ 工作區有新的變動（可能是某支自檢留下的）："
  log '```'
  printf '%s\n' "$NEWFILES" | tee -a "$REPORT"
  log '```'
else
  log "🟢 工作區沒有新增非預期檔案"
fi

log ""
log "---"
log "報告：\`$REPORT\` —— 把內容貼回頻道給 Principal Investigator。"

echo ""
echo "✅ 完成。報告寫在：$REPORT"
