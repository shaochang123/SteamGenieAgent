import math
import re
from collections import Counter
from typing import Any

from config import (
    max_token,
    model_max_token,
    model_name,
    system_prompt,
    system_prompt_with_tools,
)
from tool_markup import looks_like_tool_markup

REFUSAL_PATTERNS = (
    "我无法直接访问", "我无法访问", "我没有权限",
    "我无法直接查看", "我无法直接获取", "我没法直接",
    "无法直接访问", "无法直接查看", "无法直接获取",
    "I can't access", "I cannot access",
)
TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+|[^\s]")
SCORE_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+")
WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def active_model_name(settings: dict[str, Any]) -> str:
    """Return the model name for the active AI provider settings."""
    ai_settings = settings.get("ai", {})
    provider = ai_settings.get("provider", "ollama")
    key = "openaiCompatible" if provider == "openai-compatible" else "ollama"
    return (ai_settings.get(key, {}).get("model") or model_name).strip() or model_name


def estimate_tokens(text: str) -> int:
    """Approximate token counts without adding a tokenizer dependency."""
    if not text:
        return 0

    total = 0
    for piece in TOKEN_RE.findall(text):
        is_word = WORD_RE.fullmatch(piece)
        total += max(1, math.ceil(len(piece) / 4)) if is_word else 1
    return total


def score_tokens(text: str) -> list[str]:
    """Extract normalized terms used for lightweight TF-IDF scoring."""
    return [
        token.lower()
        for token in SCORE_TOKEN_RE.findall(text)
        if token.strip()
    ]


def rank_context_blocks(question: str, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank knowledge and history blocks by relevance to the user question."""
    query_terms = Counter(score_tokens(question))
    if not blocks or not query_terms:
        return sorted(blocks, key=lambda item: item["fallback"], reverse=True)

    documents = [set(score_tokens(block["text"])) for block in blocks]
    doc_count = len(documents)
    document_frequency: Counter[str] = Counter()
    for terms in documents:
        document_frequency.update(terms)

    for block, terms in zip(blocks, documents):
        block_terms = Counter(score_tokens(block["text"]))
        score = 0.0
        for term, query_tf in query_terms.items():
            if term not in block_terms:
                continue
            idf = math.log((doc_count + 1) / (document_frequency[term] + 1)) + 1
            score += query_tf * block_terms[term] * idf
        block["score"] = score + block["fallback"]

    return sorted(blocks, key=lambda item: item["score"], reverse=True)


def split_knowledge_blocks(context: str) -> list[str]:
    """Split retrieved knowledge text into independently budgeted blocks."""
    return [part.strip() for part in context.split("\n\n") if part.strip()]


def render_knowledge_context(blocks: list[str]) -> str:
    """Render selected knowledge blocks for the system prompt."""
    return "## Knowledge Base (retrieved references)\n" + "\n\n".join(blocks) + "\n" if blocks else ""


def render_history_context(blocks: list[str]) -> str:
    """Render selected chat history blocks for the system prompt."""
    return "## Conversation History\n" + "\n".join(blocks) + "\n" if blocks else ""


def token_limit(settings: dict[str, Any]) -> int:
    """Return the configured context limit for the active model."""
    return int(model_max_token.get(active_model_name(settings), max_token))


def message_token_count(prompt_text: str, question: str) -> int:
    """Estimate total tokens for the system prompt plus current question."""
    return estimate_tokens(prompt_text) + estimate_tokens(question)


def make_context_candidates(
    knowledge_blocks: list[str],
    history_blocks: list[str],
) -> list[dict[str, Any]]:
    """Combine knowledge and history into scored context candidates."""
    candidates: list[dict[str, Any]] = []
    for index, text in enumerate(knowledge_blocks):
        candidates.append({
            "kind": "knowledge",
            "text": text,
            "order": index,
            "fallback": 0.01 / (index + 1),
        })

    history_count = len(history_blocks)
    for index, text in enumerate(history_blocks):
        candidates.append({
            "kind": "history",
            "text": text,
            "order": index,
            "fallback": 0.005 * (index + 1) / max(history_count, 1),
        })
    return candidates


def render_selected_context(
    selected_knowledge: list[dict[str, Any]],
    selected_history: list[dict[str, Any]],
) -> tuple[str, str]:
    """Render selected context blocks while preserving original order."""
    def ordered_text(blocks: list[dict[str, Any]]) -> list[str]:
        """Return selected block text ordered as it originally appeared."""
        return [item["text"] for item in sorted(blocks, key=lambda item: item["order"])]

    return (
        render_knowledge_context(ordered_text(selected_knowledge)),
        render_history_context(ordered_text(selected_history)),
    )


def select_context_for_budget(
    *,
    question: str,
    prompt_template: str,
    knowledge_blocks: list[str],
    history_blocks: list[str],
    settings: dict[str, Any],
) -> tuple[str, str]:
    """Select the most relevant context blocks that fit the model budget."""
    limit = token_limit(settings)
    empty_prompt = prompt_template.format(knowledge_context="", history_context="")
    if message_token_count(empty_prompt, question) > limit:
        model = active_model_name(settings)
        raise RuntimeError(f"输入内容超过当前模型 {model} 的最大上下文长度 {limit} tokens。")

    selected_knowledge: list[dict[str, Any]] = []
    selected_history: list[dict[str, Any]] = []
    candidates = make_context_candidates(knowledge_blocks, history_blocks)

    for block in rank_context_blocks(question, candidates):
        trial_knowledge = selected_knowledge[:]
        trial_history = selected_history[:]
        (trial_knowledge if block["kind"] == "knowledge" else trial_history).append(block)

        knowledge_text, history_text = render_selected_context(trial_knowledge, trial_history)
        prompt_text = prompt_template.format(
            knowledge_context=knowledge_text,
            history_context=history_text,
        )
        if message_token_count(prompt_text, question) <= limit:
            selected_knowledge = trial_knowledge
            selected_history = trial_history

    return render_selected_context(selected_knowledge, selected_history)


def history_context_blocks(messages: list[dict[str, Any]]) -> list[str]:
    """Convert recent chat history into prompt-safe context blocks."""
    blocks: list[str] = []
    for message in messages[-10:]:
        role = message.get("role", "")
        content = message.get("content", "")

        if role in ("tool_call", "tool_result", "tool"):
            continue
        if role == "assistant" and any(pattern in content for pattern in REFUSAL_PATTERNS):
            continue
        if role == "assistant" and looks_like_tool_markup(content):
            continue

        tag = "assistant" if role == "assistant" else "user"
        blocks.append(f"[{tag}]: {content}")
    return blocks


def build_prompt_messages(
    *,
    question: str,
    context: str,
    history: list[dict[str, Any]],
    settings: dict[str, Any],
    has_tools: bool,
) -> list[dict[str, str]]:
    """Build provider chat messages with budgeted RAG and history context."""
    prompt_template = system_prompt_with_tools if has_tools else system_prompt
    knowledge_context, history_context = select_context_for_budget(
        question=question,
        prompt_template=prompt_template,
        knowledge_blocks=split_knowledge_blocks(context),
        history_blocks=history_context_blocks(history),
        settings=settings,
    )
    return [
        {
            "role": "system",
            "content": prompt_template.format(
                knowledge_context=knowledge_context,
                history_context=history_context,
            ),
        },
        {"role": "user", "content": question},
    ]
