import re
from typing import Any

HIDDEN_TOOL_MARKUP_MESSAGE = "模型输出了内部工具调用标记，已在界面隐藏。请重新提问。"

FINAL_ANSWER_ONLY_INSTRUCTION = (
    "No more tool calls are available in this final-answer step. "
    "Do not call any more tools. Do not output DSML/XML/JSON tool-call markup. "
    "Based only on the tool results above, give the final answer."
)

_TOOL_MARKUP_PATTERNS = (
    re.compile(r"DSML.{0,80}tool_calls", re.IGNORECASE | re.DOTALL),
    re.compile(r"DSML.{0,80}invoke", re.IGNORECASE | re.DOTALL),
    re.compile(r"<\s*(tool_calls|invoke)\b", re.IGNORECASE),
    re.compile(r'"tool_calls"\s*:', re.IGNORECASE),
)


def looks_like_tool_markup(text: str) -> bool:
    """Detect provider-specific tool-call markup that should not reach users."""
    return bool(text and any(pattern.search(text[:800]) for pattern in _TOOL_MARKUP_PATTERNS))


def should_buffer_tool_markup(text: str) -> bool:
    """Delay suspicious prefixes until there is enough text to classify them."""
    stripped = text.lstrip()
    if not stripped:
        return True
    return stripped.startswith(("<", "`", "{", "[")) and len(stripped) < 160


def hide_tool_markup(role: str, content: str) -> str:
    """Replace raw assistant tool-call markup with a safe UI message."""
    if role == "assistant" and looks_like_tool_markup(content):
        return HIDDEN_TOOL_MARKUP_MESSAGE
    return content


def tool_markup_fallback(tool_history: list[dict[str, Any]]) -> str:
    """Build a fallback answer when a model prints tool calls as text."""
    recent_results = [
        entry.get("content", "")
        for entry in tool_history
        if entry.get("role") == "tool_result" and entry.get("content")
    ][-3:]
    if not recent_results:
        return (
            "模型尝试输出内部工具调用标记，而不是最终回答；这段标记已被拦截。"
            "请重新提问，或换用支持原生 tool_calls 的模型。"
        )

    result_lines = []
    for result in recent_results:
        trimmed = result.replace("\n", " ").strip()
        result_lines.append(f"- {trimmed[:220]}")
    return (
        "模型尝试继续输出内部工具调用标记，而不是最终回答；这段标记已被拦截。\n\n"
        "这通常表示当前模型没有稳定使用 OpenAI-compatible 的原生 tool_calls。"
        "已获取到的最近工具结果如下：\n"
        + "\n".join(result_lines)
    )
