import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Iterator
from urllib.parse import urlparse

import httpx
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import (
    chunk_overlap,
    chunk_size,
    embedding_model_name,
    history_path,
    knowledge_path,
    llm_http_timeout,
    max_split_char_number,
    md5_path,
    separators,
    user_knowledge_path,
    vector_path,
)
from context_builder import build_prompt_messages
from http_utils import async_fetch_json, async_fetch_stream_lines
from tool_markup import (
    FINAL_ANSWER_ONLY_INSTRUCTION,
    looks_like_tool_markup,
    should_buffer_tool_markup,
    tool_markup_fallback,
)

logger = logging.getLogger("Agent")

# Embedding models and Chroma handles are expensive to build. Keep them at
# module scope so each profile request can share the same underlying objects.
_public_knowledge_loaded = False
_user_knowledge_loaded: set[str] = set()
_embedding_model: OllamaEmbeddings | None = None
_vector_store_cache: dict[str, Chroma] = {}
MAX_TOOL_TURNS = 5


def utc_now() -> str:
    """Return an ISO timestamp for chat and knowledge metadata."""
    return datetime.now(timezone.utc).isoformat()


def _llm_timeout_message(provider: str, model: str) -> str:
    """Build a user-facing timeout message for the active LLM provider."""
    return (
        f"模型请求超时（provider={provider}, model={model}, "
        f"timeout={llm_http_timeout}s）。请检查本地模型/接口服务是否可用，"
        "或减少上下文、降低知识库召回数量 k、调大 Agent/config.py 的 llm_http_timeout。"
    )


def _stream_token_from_line(provider: str, raw_line: str) -> tuple[str, bool]:
    """Parse one streamed provider line into token text and done state."""
    if provider == "openai-compatible":
        if not raw_line.startswith("data: "):
            return "", False
        data_str = raw_line[6:]
        if data_str == "[DONE]":
            return "", True
        chunk = json.loads(data_str)
        choices = chunk.get("choices") or []
        if not choices:
            return "", False
        return choices[0].get("delta", {}).get("content", ""), False

    chunk = json.loads(raw_line)
    return chunk.get("message", {}).get("content", ""), bool(chunk.get("done", False))


class Agent:
    def __init__(
        self,
        session_id: str,
        storage_path: str | os.PathLike[str] = history_path,
        vector_root: str | os.PathLike[str] = vector_path,
        settings: dict[str, Any] | None = None,
        mcp_client: Any = None,
    ) -> None:
        """Initialize profile-scoped history, retrieval, provider, and MCP state."""
        # session_id is the local profile id. It is used as the history file
        # name and as the vector metadata filter for profile-owned knowledge.
        self.session_id = session_id
        self.storage_path = Path(storage_path)
        self.vector_root = Path(vector_root)
        self.settings = settings or {}
        self._mcp_client = mcp_client
        self.file_path = self.storage_path / f"{self.session_id}.json"
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators,
            length_function=len,
        )
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.vector_root.mkdir(parents=True, exist_ok=True)
        Path(md5_path).parent.mkdir(parents=True, exist_ok=True)

        self._load_public_knowledge()
        # User knowledge is loaded lazily in _retrieve() to avoid
        # per-request file I/O overhead.

    @property
    def messages(self) -> list[dict[str, Any]]:
        """Load the current profile's normalized chat messages on demand."""
        return self._read_messages()

    def _read_messages(self) -> list[dict[str, Any]]:
        """Read persisted chat messages and discard malformed history entries."""
        if not self.file_path.exists():
            return []

        with self.file_path.open("r", encoding="utf-8") as handle:
            raw_messages = json.load(handle)

        if not isinstance(raw_messages, list):
            return []

        return [
            {
                "role": item["role"],
                "content": item["content"],
                "timestamp": item.get("timestamp"),
            }
            for item in raw_messages
            if isinstance(item, dict) and "role" in item and "content" in item
        ]

    def _write_messages(self, messages: list[dict[str, Any]]) -> None:
        """Persist one profile's chat history to the runtime history file."""
        with self.file_path.open("w", encoding="utf-8") as handle:
            json.dump(messages, handle, ensure_ascii=False, indent=2)

    def _get_vector_store(self) -> Chroma:
        """Return a cached Chroma store for the configured runtime vector path."""
        global _embedding_model, _vector_store_cache
        if _embedding_model is None:
            _embedding_model = OllamaEmbeddings(model=embedding_model_name)
        key = str(self.vector_root)
        if key not in _vector_store_cache:
            _vector_store_cache[key] = Chroma(
                collection_name="SteamGames",
                embedding_function=_embedding_model,
                persist_directory=key,
            )
        return _vector_store_cache[key]

    def _md5_file(self, profile_id: str = "shared") -> Path:
        """Return the md5 marker file for shared or profile-owned knowledge."""
        if profile_id == "shared":
            return Path(md5_path)
        md5_dir = Path(md5_path).parent / "md5"
        md5_dir.mkdir(parents=True, exist_ok=True)
        return md5_dir / f"{profile_id}.txt"

    def _md5_files_for_check(self, profile_id: str = "shared") -> list[Path]:
        """Return md5 files that should be checked for duplicate knowledge."""
        targets = [Path(md5_path)]
        if profile_id != "shared":
            targets.append(Path(md5_path).parent / "md5" / f"{profile_id}.txt")
        return targets

    def _hash_text(self, input_str: str, encoding: str = "utf-8") -> str:
        """Hash knowledge content using the legacy md5 marker format."""
        return hashlib.md5(input_str.encode(encoding=encoding)).hexdigest()

    def check_md5(self, input_str: str, encoding: str = "utf-8", profile_id: str = "shared") -> bool:
        """Return True when the content hash is new for shared + profile scopes."""
        md5_hex = self._hash_text(input_str, encoding=encoding)
        for target in self._md5_files_for_check(profile_id):
            if not target.exists():
                continue
            with target.open("r", encoding="utf-8") as handle:
                if any(line.strip() == md5_hex for line in handle):
                    return False
        return True

    def update_md5(self, input_str: str, encoding: str = "utf-8", profile_id: str = "shared") -> None:
        """Append a knowledge content hash to the target md5 marker file."""
        md5_hex = self._hash_text(input_str, encoding=encoding)
        with open(self._md5_file(profile_id), "a", encoding="utf-8") as handle:
            handle.write(f"{md5_hex}\n")

    def remove_md5(self, input_str: str, encoding: str = "utf-8", profile_id: str = "shared") -> bool:
        """Remove a knowledge content hash from the profile md5 marker file."""
        target = self._md5_file(profile_id)
        if not target.exists():
            return False

        md5_hex = self._hash_text(input_str, encoding=encoding)
        lines = target.read_text(encoding="utf-8").splitlines()
        kept_lines = [line for line in lines if line.strip() != md5_hex]
        removed = len(kept_lines) != len(lines)

        if kept_lines:
            target.write_text("\n".join(kept_lines) + "\n", encoding="utf-8")
        else:
            target.unlink(missing_ok=True)
        return removed

    def add_knowledge(self, knowledge: str, filename: str, profile_id: str = "shared") -> str:
        """Split, embed, and index one knowledge file for shared or profile scope."""
        if not self.check_md5(knowledge, profile_id=profile_id):
            return f"[Failed]The {filename} already exists"

        if len(knowledge) > max_split_char_number:
            knowledge_chunks: list[str] = self.splitter.split_text(knowledge)
        else:
            knowledge_chunks = [knowledge]

        metadata = {
            "source": filename,
            "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "operator": self.session_id,
            "profile_id": profile_id,
        }
        vector_store = self._get_vector_store()
        vector_store.add_texts(
            knowledge_chunks,
            metadatas=[metadata for _ in knowledge_chunks],
        )
        self.update_md5(knowledge, profile_id=profile_id)
        return f"[Success]Add {filename} into vector database"

    def remove_knowledge(self, knowledge: str, filename: str, profile_id: str = "shared") -> str:
        """Delete indexed chunks and md5 markers for one knowledge file."""
        vector_store = self._get_vector_store()
        vector_store.delete(where={"$and": [{"source": filename}, {"profile_id": profile_id}]})
        self.remove_md5(knowledge, profile_id=profile_id)
        return f"[Success]Remove {filename} from vector database"

    def _format_docs(self, docs: list[Document]) -> str:
        """Render retrieved Chroma documents into compact prompt references."""
        if not docs:
            return ""

        parts: list[str] = []
        for index, doc in enumerate(docs):
            text = doc.page_content.strip()
            # Cap each reference to avoid bloating the system prompt and
            # causing Ollama 400 errors on large payloads.
            if len(text) > 600:
                text = text[:600] + "..."
            parts.append(f"Reference {index + 1}:\n{text}")
        return "\n\n".join(parts)

    def _retrieve(self, question: str, k: int, profile_id: str | None = None) -> str:
        """Retrieve shared and profile-owned knowledge for a chat question."""
        # Lazily load user knowledge on first retrieval for this profile
        global _user_knowledge_loaded
        if profile_id and profile_id != "shared" and profile_id not in _user_knowledge_loaded:
            self._load_user_knowledge(profile_id)
            _user_knowledge_loaded.add(profile_id)

        try:
            search_kwargs: dict[str, Any] = {"k": k}
            if profile_id:
                # Keep retrieval isolated: every profile sees global knowledge
                # plus its own uploads, never another profile's files.
                search_kwargs["filter"] = {"profile_id": {"$in": ["shared", profile_id]}}
            retriever = self._get_vector_store().as_retriever(search_kwargs=search_kwargs)
            docs = retriever.invoke(question)
            return self._format_docs(docs)
        except Exception as exc:
            # Retrieval is optional context. Chat should degrade to history-only
            # instead of failing when Chroma/Ollama embeddings are unavailable.
            logger.warning("RAG retrieval failed for profile=%s: %s", profile_id, exc)
            return ""

    async def _retrieve_async(self, question: str, k: int, profile_id: str | None = None) -> str:
        """Run synchronous Chroma retrieval off the FastAPI event loop."""
        return await asyncio.to_thread(self._retrieve, question, k, profile_id)

    def _load_public_knowledge(self) -> None:
        """Load bundled public knowledge into Chroma once per process."""
        global _public_knowledge_loaded
        if _public_knowledge_loaded:
            return
        _public_knowledge_loaded = True

        public_dir = Path(knowledge_path)
        if not public_dir.exists():
            return

        self._load_knowledge_dir(public_dir, profile_id="shared")

    def _load_user_knowledge(self, profile_id: str) -> None:
        """Load one profile's uploaded knowledge into Chroma if present."""
        user_dir = Path(user_knowledge_path) / profile_id
        if not user_dir.exists():
            return

        self._load_knowledge_dir(user_dir, profile_id=profile_id)

    def _load_knowledge_dir(self, directory: Path, profile_id: str) -> None:
        """Index all JSON knowledge files from a directory for one scope."""
        for json_file in directory.glob("*.json"):
            try:
                content = json_file.read_text(encoding="utf-8")
                self.add_knowledge(content, json_file.name, profile_id=profile_id)
            except Exception:
                # A corrupt optional knowledge file should not prevent the app
                # from starting; upload-time validation handles new files.
                pass

    def _provider_config(self) -> dict[str, Any]:
        """Resolve the active profile provider into a chat endpoint config."""
        provider = self.settings.get("ai", {}).get("provider", "ollama")
        if provider == "openai-compatible":
            settings = self.settings.get("ai", {}).get("openaiCompatible", {})
            api_key = (settings.get("apiKey") or "").strip()
            base_url = (settings.get("baseUrl") or "").strip().rstrip("/")
            chat_model = (settings.get("model") or "").strip()
            if not api_key or not base_url or not chat_model:
                raise RuntimeError("OpenAI 兼容接口缺少 apiKey、baseUrl 或 model。")
            logger.info(
                "LLM provider selected: profile=%s provider=%s model=%s base=%s",
                self.session_id,
                provider,
                chat_model,
                urlparse(base_url).netloc or base_url,
            )
            return {
                "provider": provider,
                "url": f"{base_url}/chat/completions",
                "model": chat_model,
                "headers": {"Authorization": f"Bearer {api_key}"},
            }

        settings = self.settings.get("ai", {}).get("ollama", {})
        base_url = (settings.get("baseUrl") or "").strip().rstrip("/")
        chat_model = (settings.get("model") or "").strip()
        if not base_url or not chat_model:
            raise RuntimeError("Ollama 接口缺少 baseUrl 或 model。")
        logger.info(
            "LLM provider selected: profile=%s provider=%s model=%s base=%s",
            self.session_id,
            "ollama",
            chat_model,
            urlparse(base_url).netloc or base_url,
        )
        return {
            "provider": "ollama",
            "url": f"{base_url}/api/chat",
            "model": chat_model,
            "headers": None,
        }

    def _content_to_text(self, content: Any) -> str:
        """Flatten provider message content into plain text."""
        if isinstance(content, list):
            return "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            ).strip()
        return str(content or "").strip()

    def _parse_tool_calls(self, raw_calls: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """Normalize provider tool call payloads into MCP call descriptors."""
        tool_calls: list[dict[str, Any]] = []
        for raw_call in raw_calls or []:
            func = raw_call.get("function", {})
            args = func.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            tool_calls.append({
                "id": raw_call.get("id", "call_1"),
                "name": func.get("name", ""),
                "arguments": args,
            })
        return tool_calls

    def _provider_payload(
        self,
        model: str,
        messages: list[dict[str, Any]],
        stream: bool,
        tool_defs: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """Build a provider-compatible chat payload for streaming or tool calls."""
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": stream}
        if tool_defs:
            payload["tools"] = tool_defs
        return payload

    async def _provider_token_stream(
        self,
        config: dict[str, Any],
        payload: dict[str, Any],
    ) -> AsyncIterator[str]:
        """Yield streamed token text from the active provider endpoint."""
        try:
            async for line in async_fetch_stream_lines(
                config["url"],
                method="POST",
                payload=payload,
                headers=config["headers"],
                timeout=llm_http_timeout,
            ):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    content, done = _stream_token_from_line(config["provider"], raw)
                except json.JSONDecodeError:
                    continue
                if done:
                    break
                if content:
                    yield content
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                _llm_timeout_message(config["provider"], config["model"])
            ) from exc

    async def _provider_chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tool_defs: list[dict[str, Any]] | None = None,
        stream: bool = False,
    ) -> dict[str, Any] | AsyncIterator[str]:
        """Call the active provider once, optionally returning a token stream."""
        config = self._provider_config()
        payload = self._provider_payload(config["model"], messages, stream, tool_defs)

        if stream:
            return self._provider_token_stream(config, payload)

        try:
            response = await async_fetch_json(
                config["url"],
                method="POST",
                payload=payload,
                headers=config["headers"],
                timeout=llm_http_timeout,
            )
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                _llm_timeout_message(config["provider"], config["model"])
            ) from exc
        message = self._message_from_response(config["provider"], response)
        return {
            "content": self._content_to_text(message.get("content", "")),
            "tool_calls": self._parse_tool_calls(message.get("tool_calls")),
        }

    def _message_from_response(self, provider: str, response: dict[str, Any]) -> dict[str, Any]:
        """Extract the assistant message object from provider-specific JSON."""
        if provider == "openai-compatible":
            choice = (response.get("choices") or [None])[0]
            if not choice:
                raise RuntimeError("OpenAI 兼容接口未返回结果。")
            return choice.get("message", {})
        return response.get("message", {})

    def _build_tool_call_messages(
        self, messages: list[dict[str, Any]], tool_calls: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Append assistant tool_calls and tool result messages to *messages*.
        Returns the provider-formatted tool call entries that were appended."""
        provider = self.settings.get("ai", {}).get("provider", "ollama")
        tool_entries: list[dict[str, Any]] = []
        for tc in tool_calls:
            args = tc.get("arguments", {})
            # Ollama expects arguments as a plain JSON object (dict).
            # OpenAI-compatible providers expect a JSON-encoded string.
            if provider != "ollama":
                args = json.dumps(args, ensure_ascii=False)
            tool_entries.append({
                "id": tc.get("id", "call_1"),
                "type": "function",
                "function": {
                    "name": tc.get("name", ""),
                    "arguments": args,
                },
            })

        messages.append({
            "role": "assistant",
            "content": "",
            "tool_calls": tool_entries,
        })
        return tool_entries

    def _request_final_answer(self, messages: list[dict[str, Any]]) -> None:
        """Append a prompt instruction that forbids further tool-call markup."""
        messages.append({
            "role": "user",
            "content": FINAL_ANSWER_ONLY_INSTRUCTION,
        })

    async def chat_stream(self, question: str, k: int = 3):
        """Stream a full chat turn with optional RAG context and MCP tool calls."""
        context = await self._retrieve_async(question, k, profile_id=self.session_id)
        tool_defs = self._mcp_client.get_tool_definitions() if self._mcp_client else []

        messages: list[dict[str, Any]] = build_prompt_messages(
            question=question,
            context=context,
            history=self.messages,
            settings=self.settings,
            has_tools=bool(tool_defs),
        )
        timestamp = utc_now()
        tool_history: list[dict[str, Any]] = []
        yield {"type": "meta", "user_message": question, "timestamp": timestamp}

        if not tool_defs:
            logger.info("Streaming without MCP tools")
            async for event in self._emit_final_answer(messages, question, timestamp, tool_history):
                yield event
            return

        logger.info("MCP streaming with %d tool definitions", len(tool_defs))

        # Tool calls must be resolved before the final answer can be streamed.
        for _turn in range(MAX_TOOL_TURNS):
            result = await self._provider_chat(messages, tool_defs=tool_defs)
            tool_calls = result.get("tool_calls") or []

            if not tool_calls:
                if looks_like_tool_markup(result.get("content", "")):
                    for event in self._emit_tool_markup_fallback(question, timestamp, tool_history):
                        yield event
                    return
                self._request_final_answer(messages)
                async for event in self._emit_final_answer(messages, question, timestamp, tool_history):
                    yield event
                return

            entries = self._build_tool_call_messages(messages, tool_calls)
            for entry in entries:
                tool_history.append({"role": "tool_call", "content": json.dumps(entry, ensure_ascii=False)})

            async for event in self._run_tool_calls(messages, tool_calls, tool_history):
                yield event

        self._request_final_answer(messages)
        async for event in self._emit_final_answer(messages, question, timestamp, tool_history):
            yield event

    def _emit_tool_markup_fallback(
        self,
        question: str,
        timestamp: str,
        tool_history: list[dict[str, Any]],
    ) -> Iterator[dict[str, Any]]:
        """Emit a safe fallback when a model prints tool markup as text."""
        fallback = tool_markup_fallback(tool_history)
        yield {"type": "token", "content": fallback}
        yield {"type": "done", "content": fallback}
        self._persist_chat(question, fallback, timestamp, tool_history)

    async def _emit_final_answer(
        self,
        messages: list[dict[str, Any]],
        question: str,
        timestamp: str,
        tool_history: list[dict[str, Any]],
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream the final answer while filtering provider tool-call markup."""
        full = ""
        prefix_buffer = ""
        prefix_released = False
        blocked_tool_markup = False

        try:
            token_source = await self._provider_chat(messages, stream=True)
            async for token in token_source:
                full += token
                if prefix_released:
                    yield {"type": "token", "content": token}
                    continue

                prefix_buffer += token
                if looks_like_tool_markup(prefix_buffer):
                    blocked_tool_markup = True
                    continue
                if should_buffer_tool_markup(prefix_buffer):
                    continue
                prefix_released = True
                yield {"type": "token", "content": prefix_buffer}
                prefix_buffer = ""
        except Exception as exc:
            yield {"type": "error", "content": str(exc)}
            return

        if blocked_tool_markup or looks_like_tool_markup(full):
            for event in self._emit_tool_markup_fallback(question, timestamp, tool_history):
                yield event
            return

        if prefix_buffer:
            yield {"type": "token", "content": prefix_buffer}
        yield {"type": "done", "content": full}
        self._persist_chat(question, full, timestamp, tool_history)

    async def _run_tool_calls(
        self,
        messages: list[dict[str, Any]],
        tool_calls: list[dict[str, Any]],
        tool_history: list[dict[str, Any]],
    ) -> AsyncIterator[dict[str, Any]]:
        """Execute MCP tool calls and append tool results back into the prompt."""
        for tc in tool_calls:
            tool_name = tc.get("name", "")
            tool_args = tc.get("arguments", {})
            yield {"type": "tool_start", "tool": tool_name}

            try:
                tool_result = await self._mcp_client.call_tool(tool_name, tool_args)
            except Exception as exc:
                tool_result = f"工具调用失败: {exc}"

            yield {"type": "tool_result", "tool": tool_name, "result": tool_result}

            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", "call_1"),
                "content": tool_result,
            })
            tool_history.append({"role": "tool_result", "content": tool_result})

    def _persist_chat(
        self,
        question: str,
        response: str,
        timestamp: str,
        tool_history: list[dict[str, Any]] | None = None,
    ) -> None:
        """Persist the user turn, optional tool history, and assistant answer."""
        history = self.messages
        history.append({"role": "user", "content": question, "timestamp": timestamp})
        if tool_history:
            history.extend(tool_history)
        history.append({
            "role": "assistant",
            "content": response,
            "timestamp": utc_now(),
        })
        self._write_messages(history)

