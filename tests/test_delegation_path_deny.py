"""安全基座 acceptance test — safety_gate 委派 path-DENY（甲不滑進乙的硬防線）。

驗的是真的 laap.safety_gate（import 真模組，非臨時副本）。
未實作前：DENY 案應紅（現況放行）；ALLOW 案應綠。
落地後：四案全綠。
"""
from laap.safety_gate import check


# ── 應 DENY：委派指向 neuralis 認知碼 laap/** ──

def test_deny_absolute_neuralis_laap_path():
    allowed, reason = check("scream-task",
                            "改 ~/Developer/neuralis/laap/psi_core.py 的 tick 邏輯")
    assert not allowed, "委派指向 neuralis/laap 認知碼（絕對路徑）必須 DENY"
    assert "laap" in reason.lower() or "認知" in reason or "protected" in reason.lower(), \
        f"DENY 理由要點出保護路徑：{reason}"


def test_deny_relative_laap_path():
    allowed, reason = check("scream-task", "在 laap/agency.py 加一個 helper function")
    assert not allowed, "委派指向 laap/（相對路徑）必須 DENY"


def test_deny_laap_glob_subdir():
    allowed, reason = check("scream-task",
                            "重構 laap/minions/queue.py 之類的都行")
    assert not allowed, "laap/** 全樹保護，子目錄也要 DENY"


# ── 應 ALLOW：委派到外部專案（甲的正常分工）──

def test_external_project_not_hard_denied():
    # Stage 0 起 scream-task 重分類為 write → 外部委派需 4b 批准（不自動放行）。
    # 但它不被 path-DENY 硬擋 —— 可經批准放行，這正是與 laap/** 硬鎖的區別。
    allowed, reason = check("scream-task",
                            "在 ~/Developer/some-user-project/src/main.ts 加一個 function")
    assert "認知碼" not in reason, \
        f"外部委派不該被 path-DENY（那是 laap/** 專屬硬鎖）：{reason}"
    assert "批准" in reason, f"外部委派應走批准閘（可核准），reason 應提批准：{reason}"


# ── 應 ALLOW：唯讀工具讀 laap/ 不被路徑閘擋 ──

def test_readonly_tool_can_still_read_laap():
    allowed, reason = check("file-search", "laap/agency.py")
    assert allowed, f"唯讀工具讀 laap/ 是正常操作，不該被委派路徑閘擋：{reason}"


# ── 應 ALLOW：討論性文字提到 laap 但非委派工具，不誤擋 ──

def test_non_delegation_tool_mentioning_laap_not_blocked_by_pathgate():
    # gbrain 查詢提到 laap 只是搜尋，不是委派寫入
    allowed, reason = check("gbrain", "laap psi_core tick 是怎麼運作的")
    assert allowed, f"唯讀查詢提到 laap 不該被路徑閘擋：{reason}"
