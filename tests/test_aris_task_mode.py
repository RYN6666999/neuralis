"""_is_task_mode 的判定邊界。

為什麼要測：Aris 有兩套互斥的語氣規則（閒聊禁止列點 vs 任務要求編號步驟）。
判錯 = 人格跑掉。誤判成任務模式的代價比漏判大，所以 false positive 要嚴格盯。
"""
import pytest

from laap.llm_respond import _ADHD_RULES, _build_system_prompt, _is_task_mode


CHAT = [
    "嗨",
    "？",
    "好啊",
    "你今天感覺怎樣",
    "在嗎",
    "我有點累，想跟你聊聊",
    "你會不會覺得孤單",
    "今天天氣真好",
    "3/4 的時間我都在發呆",     # 斜線但不是路徑
    "我最近在跑步",              # 「跑」但不是「跑一下」
]

TASK = [
    "幫我修好 laap/llm_respond.py",
    "跑一下 pytest",
    "install 這個 repo",
    "報錯了，traceback 在下面",
    "改一下 config",
    "docker 起不來",
    "git push 失敗",
    "幫我實作一個 salience 閘",
    "看一下 /Users/ryan/Developer/neuralis/laap",
    "```python\nprint(1)\n```",
]


@pytest.mark.parametrize("msg", CHAT)
def test_chat_stays_in_aris_voice(msg):
    assert _is_task_mode(msg) is False, f"閒聊被誤判成任務: {msg!r}"


@pytest.mark.parametrize("msg", TASK)
def test_task_triggers_adhd_mode(msg):
    assert _is_task_mode(msg) is True, f"任務沒被認出來: {msg!r}"


def test_empty_and_short_never_trigger():
    for msg in ("", "   ", "嗯", "run"):
        assert _is_task_mode(msg) is False


def test_prompt_appends_rules_only_in_task_mode():
    state = {"emotion": {}, "needs": {}, "dominant_need": "none"}
    marker = _ADHD_RULES[1]          # "## 任務模式輸出規則..."

    chat_prompt = _build_system_prompt(state, user_msg="你今天感覺怎樣")
    task_prompt = _build_system_prompt(state, user_msg="跑一下 pytest")

    assert marker not in chat_prompt
    assert marker in task_prompt
    # 原有語氣規則在兩種模式下都必須還在（ADHD 是追加，不是取代整份 prompt）
    for p in (chat_prompt, task_prompt):
        assert "語氣規則" in p


def test_default_arg_is_backward_compatible():
    """沒傳 user_msg 的舊呼叫端不能因此進入任務模式。"""
    state = {"emotion": {}, "needs": {}, "dominant_need": "none"}
    assert _ADHD_RULES[1] not in _build_system_prompt(state)
