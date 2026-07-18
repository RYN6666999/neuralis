# 第三部：沙箱與能力邊界

> 對應章節：Ch 6～8
> 撰寫狀態：✅ 已完成（2026-07-18）
> 參考來源：`~/agent-sandbox/`（現有沙箱）、`laap/snapshot.py`（快照）、`laap/safety_gate.py`（path-DENY）、`laap/cost_ledger.py`（成本帳本）

---

## 6. 沙箱架構

### 6.1 現有 `agent-sandbox` 能力

`~/agent-sandbox/` 已包含：
- **orchestrator/** — 工具編排與路由
- **scripts/** — 管理腳本（`agentos.sh` health 等）
- **agentos.json** — 工具路由表
- **tests/** — 測試
- **specs/** — 規格文件
- 非隔離式：目前目錄直接在正式檔案系統中，沒有路徑限制

目前 sandbox 的定位是「開發環境」，不是「安全隔離環境」。它沒有：
- 路徑寫入限制（可以寫到 sandbox 目錄外）
- 憑證隔離（可以讀取正式 API Key）
- 自動銷毀機制
- 一次性 worktree 隔離

### 6.2 為什麼目前不算真隔離

| 面向 | 現狀 | 真隔離要求 |
|------|------|-----------|
| 工作目錄 | 直接修改正式 repo | 隔離 worktree |
| 路徑寫入 | 無限制 | 僅沙箱目錄 |
| 憑證存取 | 可讀正式 env | 正式憑證不可見 |
| 網路權限 | 全部可連 | 限制外部連線 |
| 成本追蹤 | 無 | 沙箱級成本上限 |
| 殘留清理 | 無自動清理 | 銷毀前掃描殘留 |

### 6.3 不直接修改正式 Neuralis 工作區

這是紅線。所有沙箱實驗必須在隔離的 Git worktree 中進行。正式工作區（`~/Developer/neuralis/`）只能在以下情況被修改：
- Ryan 手動合併（cherry-pick）已批准的候選方案
- 緊急安全修復（由 Ryan 手動執行）

### 6.4 一次性 Git worktree

```bash
# 建立沙箱（detached HEAD，不影響任何分支）
git worktree add --detach /tmp/aris-sandbox-<ID>/ HEAD

# 在沙箱中工作
cd /tmp/aris-sandbox-<ID>/
# ... 修改、commit、測試 ...

# 沙箱銷毀
git worktree remove /tmp/aris-sandbox-<ID>/
```

沙箱的特性：
- **detached HEAD**：不屬於任何分支，不會意外 push
- **Base commit = main HEAD**：起始點永遠是 main 最新
- **沙箱 commit 不進 main**：除非 Ryan 手動 cherry-pick
- **可同時存在多個沙箱**：每個沙箱獨立

### 6.5 沙箱分支命名

```text
sandbox/<NNN>-<kebab-case-description>
```

範例：
- `sandbox/001-fix-s-span-timeout`
- `sandbox/002-add-benchmark-retry`
- `sandbox/003-upgrade-psi-config`

規則：
- NNN = 三位數流水號，遞增
- 描述 = kebab-case，英文
- 沙箱用完不刪除 branch（保留歷史），但 worktree 要刪

### 6.6 路徑隔離

沙箱內的 Scream 操作限制於沙箱 worktree 目錄內：

```python
# 概念：沙箱路徑檢查器
class SandboxPathGuard:
    def __init__(self, sandbox_root: Path):
        self._root = sandbox_root.resolve()
    
    def is_safe_path(self, target_path: str) -> bool:
        """檢查目標路徑是否在沙箱內"""
        resolved = Path(target_path).resolve()
        return self._root in resolved.parents or resolved == self._root
    
    def assert_safe(self, target_path: str):
        if not self.is_safe_path(target_path):
            raise PermissionError(f"Paths outside sandbox are forbidden: {target_path}")
```

沙箱路徑外任何寫入操作都被拒絕。這個限制寫死在 SandboxPathGuard，不可被沙箱內的修改繞過。

### 6.7 正式憑證隔離

沙箱啟動時，正式環境變數中的敏感憑證被清除或遮蔽：

```bash
# 概念：沙箱環境變數腳本
# 正式環境變數白名單（只放行非敏感變數）
SAFE_ENV_VARS=(
  PATH HOME USER SHELL TERM
  NEURALIS_AGENCY_INTERVAL
  NEURALIS_AGENCY_MAX_PER_HOUR
  # 注意：NEURALIS_LLM_API_KEY 等正式憑證不放行
)

# 沙箱內執行指令時，只用以上變數
env -i "${SAFE_ENV_VARS[@]}" bash -c '...'
```

明確禁止的憑證類型（必須在沙箱啟動前移除）：
- `NEURALIS_LLM_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`
- 任何 `*_TOKEN`、`*_SECRET`、`*_PASSWORD` 變數
- `~/.ssh/` 中的私鑰
- `~/.config/gh/` 中的 GitHub 憑證
- gbrain 的 device_id 和 session 資料

### 6.8 網路權限限制

沙箱的網路訪問應被限制在必要的最小範圍：

| 目標 | 沙箱內 | 理由 |
|------|--------|------|
| 本機 API（localhost:11546） | 唯讀查詢 | 測試需要 |
| AgentOS executor（web-search 等） | 唯讀 | 工具執行需要 |
| GitHub（api.github.com） | 唯讀 | git fetch 需要 |
| PyPI（pypi.org） | 唯讀 | 安裝依賴需要 |
| 外部 LLM API | 拒絕 | 避免未授權呼叫 |
| 任意外部服務 | 拒絕 | 避免資料外洩 |

### 6.9 外部副作用阻擋

沙箱內禁止的操作：
- 寫入外部檔案系統（`/etc/`、`/usr/local/`、`~/.config/` 等）
- 啟動外部服務（daemon、cron、launchd）
- 修改系統設定（sysctl、launchctl、security）
- 傳送網路請求到非白名單目標
- 寫入正式 Neuralis 工作區

### 6.10 執行時間與資源限制

| 資源 | 沙箱上限 | 理由 |
|------|---------|------|
| 單次沙箱生命期 | 24 小時 | 避免沙箱僵屍 |
| 單次實驗時間 | 30 分鐘 | 避免無限執行 |
| CPU 使用率 | 80% max | 不影響主機 |
| 記憶體 | 2 GB | 避免 OOM |

超限 → 沙箱被強制終止，執行結果（到終止點為止）仍保留作為證據。

### 6.11 API 與 Token 成本上限

沙箱的 token 消耗計入成本 ledger（`laap/cost_ledger.py`），但沙箱另有獨立預算：

```python
# 概念：沙箱成本限制
SANDBOX_TOKEN_LIMIT = 50000     # 單次沙箱 token 上限
SANDBOX_API_COST_LIMIT = 0.50   # 單次沙箱 API 成本上限（USD）
```

超限 → 沙箱停止新工具呼叫，僅保留已產出的證據。

### 6.12 沙箱銷毀

沙箱關閉時：
1. 最後一次掃描殘留檔案（`find . -type f -newer sandbox-start-marker`）
2. 將所有測試證據、diff、log 打包到永久的案例分析目錄
3. 刪除 Git worktree（`git worktree remove`）
4. 刪除沙箱暫存目錄（`rm -rf /tmp/aris-sandbox-<ID>/`）
5. 記錄銷毀稽核

### 6.13 殘留檔案檢查

沙箱銷毀前，檢查是否有檔案寫入到沙箱目錄之外：

```bash
# 概念：殘留掃描
find /tmp/aris-sandbox-<ID>/ -type f -newer /tmp/aris-sandbox-<ID>/.sandbox-start
# 再檢查沙箱外是否有意外殘留
find /tmp/ -name "*aris-sandbox*" -not -path "/tmp/aris-sandbox-<ID>/*"
```

任何殘留都要記錄到稽核日誌，並嘗試清理。

---

## 7. 能力開關重新設計

### 7.1 現有兩開關機制

目前能力開關通過環境變數管理：
- `NEURALIS_AGENCY=off` — 關閉自主行動
- `NEURALIS_DELEGATION_TOOLS_EXTRA` — 擴充委派工具集
- `NEURALIS_TOOL_ALLOW` — 人工批准工具簽名
- `NEURALIS_CONSTITUTION=off` — 全放行需求憲法

問題：環境變數是全局的，沙箱與正式環境共用同一套。

### 7.2 `NEURALIS_AGENCY_DELEGATE` 的新定位

此開關轉為「沙箱模式開關」：
- **off**（預設）：Agency 維持現狀（唯讀工具）
- **sandbox**：Agency 可建立沙箱並委派 Scream 在沙箱內實作
- **注意：永遠不設 `auto-deploy` 值**——正式升級永遠由 Ryan 手動

### 7.3 開關只允許建立沙箱候選

即使 `NEURALIS_AGENCY_DELEGATE=sandbox`，Aris 也只能：
1. 建立沙箱 worktree
2. 委派 Scream 在沙箱內實作
3. 產出候選變更包
4. 提交 Ryan 審批

不能做的事：
- 直接合併到 main
- 繞過 path-DENY
- 修改正式環境設定

### 7.4 禁止直接寫入正式環境

此規則由 SafetyGate 的 path-DENY 層強制執行（`laap/safety_gate.py`）：
- `scream-task` 指向 `neuralis/laap/**` 一律 DENY
- fail-closed，不可 env 繞過
- 沙箱 worktree 在隔離路徑，不受此限制（因為不是正式環境）

### 7.5 正式升級不由環境變數自動控制

正式 upgrade 不應該由 env 決定。即使 `NEURALIS_AGENCY_DELEGATE=sandbox`，也不會自動合併任何候選方案。批准是 Ryan 的決定，不是 env 的。

### 7.6 Ryan 明確批准

正式落地的唯一途徑：
1. Ryan 在決策介面中選擇「落地」
2. 系統記錄 Ryan 的批准證明（timestamp + 決策理由）
3. Ryan 手動 cherry-pick 合併

### 7.7 Capability Manifest

取代散落的 `approved-tools.txt` 和 env 變數，所有能力開關集中管理：

```yaml
# 概念：capability-manifest.yaml
version: 1
created_at: "2026-07-18T00:00:00Z"
sandbox:
  enabled: true
  max_concurrent: 3
  max_lifetime_hours: 24
  token_budget: 50000
tools:
  readonly_safe: ["gbrain", "qmd", "file-search", "scream-ask", "web-search"]
  sandbox_write: ["scream-task"]  # 僅沙箱內可用
  production_write: []             # 永遠為空，除非 Ryan 手動批准
learning:
  enabled: true
  max_cases: 1000
  shadow_mode: true
  auto_adopt: false
```

### 7.8 舊批准狀態檢查

啟動時檢查 `approved-tools.txt` 和環境變數，將其轉換為 Capability Manifest 格式。舊機制不再直接控制行為，但保留為稽核痕跡。

### 7.9 環境變數與暫存狀態檢查

啟動時掃描以下暫存狀態，確認沒有意外放行：
- `approved-tools.txt` — 是否有未預期的批准
- `approvals-pending.jsonl` — 是否有未處理的待批項目
- 環境變數中的 `NEURALIS_TOOL_ALLOW` — 是否有非預期工具
- `agency-audit.jsonl` — 最近是否有異常的自主行動

### 7.10 啟動時權限公告

每次啟動時，Aris 應公告當前權限狀態：

```text
當前能力：
- 自主行動：開啟（6/h cap，唯讀工具）
- 沙箱試驗：關閉（需 Ryan 開啟）
- 外部參謀：關閉（需 Ryan 設定）
- 正式寫入：❌ 永遠關閉（path-DENY 在位）
```

---

## 8. 進入沙箱的條件

### 8.1 問題是否有證據

必須有至少一項客觀證據才能進沙箱：
- [ ] 有 log 記錄
- [ ] 有 test 輸出
- [ ] 有人（Ryan）親眼看到
- [ ] 有數值趨勢（benchmark 衰減、成本上升等）

沒有證據的問題 → 先蒐集證據，不進沙箱。

### 8.2 是否存在更小解法

進沙箱前先檢查：
- 調整 config 或 env 變數能否解決？
- 修改文件/說明能否解決？
- 既有工具是否已有此功能？
- 上游（lorryjovens）是否有更新已解決此問題？

有更小解法 → 先試小解法，不進沙箱。

### 8.3 預期好處是否值得代價

判斷標準：
- 好處大小：small / medium / large
- 代價大小：small / medium / large
- 好處 < 代價 → 不進沙箱
- 好處 ≈ 代價 → 謹慎評估，可能需要 Ryan 決定

### 8.4 是否能建立客觀驗收

必須有可客觀驗證的成功/失敗條件：
- 測試通過/失敗
- benchmark 分數變化
- 特定行為可觀察到（log 訊息、exit code）

無法建立客觀驗收 → 不進沙箱。

### 8.5 是否能完整回退

必須能回退到修改前的狀態：
- 程式碼修改：git revert 或 cherry-pick 反向
- 設定修改：還原 config 檔案
- 資料格式：需有 migration 回退路徑

無法完整回退 → 需要 Ryan 特批才能進沙箱。

### 8.6 是否涉及正式資料

沙箱內不可見正式資料。如果修改涉及正式資料的讀寫，則不適合沙箱實驗。

### 8.7 是否涉及外部副作用

沙箱內不可產生外部副作用。如果修改涉及：
- 寫入外部服務（API call、database write）
- 修改外部系統設定
- 啟動外部服務

則不適合沙箱實驗。

### 8.8 允許條件

全部滿足才可進沙箱：
1. ✅ 問題有客觀證據
2. ✅ 沒有更小的解法
3. ✅ 預期好處 ≥ 代價
4. ✅ 能建立客觀驗收條件
5. ✅ 能完整回退
6. ✅ 不涉及正式資料
7. ✅ 不涉及外部副作用

### 8.9 拒絕條件

任一條件滿足則拒絕進沙箱：
1. ❌ 無客觀證據
2. ❌ 有更小的解法
3. ❌ 預期好處 < 代價
4. ❌ 無法建立客觀驗收
5. ❌ 無法完整回退
6. ❌ 涉及正式資料
7. ❌ 涉及不可逆外部副作用
8. ❌ 涉及核心安全模組修改（SafetyGate、Constitution、path-DENY）

### 8.10 只觀察、不實作的條件

當證據不足但問題值得關注時，可以建立「觀察沙箱」：
- 不修改程式碼
- 只在沙箱中跑額外測試、log、benchmark
- 產出證據報告但不產出 patch
- 觀察結果可作為後續「進沙箱決策」的證據