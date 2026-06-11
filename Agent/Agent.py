import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

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
    max_split_char_number,
    md5_path,
    model_name,
    ollama_base_url,
    separators,
    system_prompt,
    system_prompt_with_tools,
    user_knowledge_path,
    vector_path,
)
from http_utils import async_fetch_json, async_fetch_stream_lines

logger = logging.getLogger("Agent")

# Embedding models and Chroma handles are expensive to build. Keep them at
# module scope so each profile request can share the same underlying objects.
_public_knowledge_loaded = False
_user_knowledge_loaded: set[str] = set()
_embedding_model: OllamaEmbeddings | None = None
_vector_store_cache: dict[str, Chroma] = {}


class Agent:
    def __init__(
        self,
        session_id: str,
        storage_path: str | os.PathLike[str] = history_path,
        vector_root: str | os.PathLike[str] = vector_path,
        settings: dict[str, Any] | None = None,
        mcp_client: Any = None,
    ) -> None:
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
        return self._read_messages()

    def _read_messages(self) -> list[dict[str, Any]]:
        """Load chat history in the current persisted message format."""
        if not self.file_path.exists():
            return []

        with self.file_path.open("r", encoding="utf-8") as handle:
            raw_messages = json.load(handle)

        normalized: list[dict[str, Any]] = []
        if not isinstance(raw_messages, list):
            return normalized

        for item in raw_messages:
            if isinstance(item, dict) and "role" in item and "content" in item:
                normalized.append(
                    {
                        "role": item["role"],
                        "content": item["content"],
                        "timestamp": item.get("timestamp"),
                    }
                )

        return normalized

    def _write_messages(self, messages: list[dict[str, Any]]) -> None:
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
        if profile_id == "shared":
            return Path(md5_path)
        md5_dir = Path(md5_path).parent / "md5"
        md5_dir.mkdir(parents=True, exist_ok=True)
        return md5_dir / f"{profile_id}.txt"

    def _md5_files_for_check(self, profile_id: str = "shared") -> list[Path]:
        targets = [Path(md5_path)]
        if profile_id != "shared":
            targets.append(Path(md5_path).parent / "md5" / f"{profile_id}.txt")
        return targets

    def _hash_text(self, input_str: str, encoding: str = "utf-8") -> str:
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
        md5_hex = self._hash_text(input_str, encoding=encoding)
        with open(self._md5_file(profile_id), "a", encoding="utf-8") as handle:
            handle.write(f"{md5_hex}\n")

    def remove_md5(self, input_str: str, encoding: str = "utf-8", profile_id: str = "shared") -> bool:
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
        """Index one JSON knowledge file and tag it as shared or profile-owned."""
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
        """Delete one indexed knowledge file from the vector store and md5 cache."""
        vector_store = self._get_vector_store()
        vector_store.delete(where={"$and": [{"source": filename}, {"profile_id": profile_id}]})
        self.remove_md5(knowledge, profile_id=profile_id)
        return f"[Success]Remove {filename} from vector database"

    def format_func(self, docs: list[Document]) -> str:
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
            return self.format_func(docs)
        except Exception as exc:
            # Retrieval is optional context. Chat should degrade to history-only
            # instead of failing when Chroma/Ollama embeddings are unavailable.
            logger.warning("RAG retrieval failed for profile=%s: %s", profile_id, exc)
            return ""

    async def _retrieve_async(self, question: str, k: int, profile_id: str | None = None) -> str:
        """Async wrapper — runs the synchronous Chroma query in a thread executor
        so it doesn't block the FastAPI event loop."""
        return await asyncio.to_thread(self._retrieve, question, k, profile_id)

    def _load_public_knowledge(self) -> None:
        global _public_knowledge_loaded
        if _public_knowledge_loaded:
            return
        _public_knowledge_loaded = True

        public_dir = Path(knowledge_path)
        if not public_dir.exists():
            return

        for json_file in public_dir.glob("*.json"):
            try:
                content = json_file.read_text(encoding="utf-8")
                self.add_knowledge(content, json_file.name, profile_id="shared")
            except Exception:
                pass

    def _load_user_knowledge(self, profile_id: str) -> None:
        user_dir = Path(user_knowledge_path) / profile_id
        if not user_dir.exists():
            return

        for json_file in user_dir.glob("*.json"):
            try:
                content = json_file.read_text(encoding="utf-8")
                self.add_knowledge(content, json_file.name, profile_id=profile_id)
            except Exception:
                pass

    def _build_messages(
        self, question: str, context: str, has_tools: bool = False
    ) -> list[dict[str, str]]:
        """Build provider messages from system prompt, RAG context, and history."""
        prompt_template = system_prompt_with_tools if has_tools else system_prompt

        # ── Knowledge context: RAG results from public + user vector stores ──
        if context:
            knowledge_context = (
                "## Knowledge Base (retrieved references)\n"
                f"{context}\n"
            )
        else:
            knowledge_context = ""

        # ── History context: recent conversation as a labeled text block ──
        _refusal_patterns = [
            "我无法直接访问", "我无法访问", "我没有权限",
            "我无法直接查看", "我无法直接获取", "我没法直接",
            "无法直接访问", "无法直接查看", "无法直接获取",
            "I can't access", "I cannot access",
        ]
        filtered: list[str] = []
        for message in self.messages[-10:]:
            role = message.get("role", "")
            content = message.get("content", "")

            # Tool traces are useful in the UI/history but too noisy for the
            # next prompt. They are already reflected in the assistant answer.
            if role in ("tool_call", "tool_result", "tool"):
                continue
            # Skip common "I cannot access..." answers so one degraded turn does
            # not teach future turns to refuse the same Steam/MCP request.
            if role == "assistant" and any(p in content for p in _refusal_patterns):
                continue

            tag = "assistant" if role == "assistant" else "user"
            filtered.append(f"[{tag}]: {content}")

        if filtered:
            history_context = (
                "## Conversation History\n"
                + "\n".join(filtered)
                + "\n"
            )
        else:
            history_context = ""

        # ── Assemble prompt ──
        prompt_text = prompt_template.format(
            knowledge_context=knowledge_context,
            history_context=history_context,
        )
        return [
            {"role": "system", "content": prompt_text},
            {"role": "user", "content": question},
        ]

    def _provider_config(self) -> dict[str, Any]:
        provider = self.settings.get("ai", {}).get("provider", "ollama")
        if provider == "openai-compatible":
            settings = self.settings.get("ai", {}).get("openaiCompatible", {})
            api_key = (settings.get("apiKey") or "").strip()
            base_url = (settings.get("baseUrl") or "").rstrip("/")
            chat_model = (settings.get("model") or "").strip()
            if not api_key or not base_url or not chat_model:
                raise RuntimeError("OpenAI 兼容接口缺少 apiKey、baseUrl 或 model。")
            return {
                "provider": provider,
                "url": f"{base_url}/chat/completions",
                "model": chat_model,
                "headers": {"Authorization": f"Bearer {api_key}"},
            }

        settings = self.settings.get("ai", {}).get("ollama", {})
        base_url = (settings.get("baseUrl") or ollama_base_url).rstrip("/")
        chat_model = (settings.get("model") or model_name).strip() or model_name
        if not base_url or not chat_model:
            raise RuntimeError("Ollama 接口缺少 baseUrl 或 model。")
        return {
            "provider": "ollama",
            "url": f"{base_url}/api/chat",
            "model": chat_model,
            "headers": None,
        }

    def _content_to_text(self, content: Any) -> str:
        if isinstance(content, list):
            return "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            ).strip()
        return str(content or "").strip()

    def _parse_tool_calls(self, raw_calls: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
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

    async def _provider_chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tool_defs: list[dict[str, Any]] | None = None,
        stream: bool = False,
    ) -> dict[str, Any] | AsyncIterator[str]:
        config = self._provider_config()
        payload: dict[str, Any] = {
            "model": config["model"],
            "messages": messages,
            "stream": stream,
        }
        if tool_defs:
            payload["tools"] = tool_defs

        if stream:
            async def token_stream() -> AsyncIterator[str]:
                async for line in async_fetch_stream_lines(
                    config["url"],
                    method="POST",
                    payload=payload,
                    headers=config["headers"],
                ):
                    raw = line.strip()
                    if not raw:
                        continue

                    try:
                        if config["provider"] == "openai-compatible":
                            if not raw.startswith("data: "):
                                continue
                            data_str = raw[6:]
                            if data_str == "[DONE]":
                                break
                            chunk = json.loads(data_str)
                            choices = chunk.get("choices") or []
                            if not choices:
                                continue
                            content = choices[0].get("delta", {}).get("content", "")
                        else:
                            chunk = json.loads(raw)
                            content = chunk.get("message", {}).get("content", "")
                            if chunk.get("done", False):
                                break
                    except json.JSONDecodeError:
                        continue

                    if content:
                        yield content

            return token_stream()

        response = await async_fetch_json(
            config["url"],
            method="POST",
            payload=payload,
            headers=config["headers"],
        )
        message = self._message_from_response(config["provider"], response)
        return {
            "content": self._content_to_text(message.get("content", "")),
            "tool_calls": self._parse_tool_calls(message.get("tool_calls")),
        }

    def _message_from_response(self, provider: str, response: dict[str, Any]) -> dict[str, Any]:
        if provider == "openai-compatible":
            choice = (response.get("choices") or [None])[0]
            if not choice:
                raise RuntimeError("OpenAI 兼容接口未返回结果。")
            return choice.get("message", {})
        return response.get("message", {})

    # ------------------------------------------------------------------
    # Tool-calling helpers
    # ------------------------------------------------------------------

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

    async def chat_stream(self, question: str, k: int = 3):
        """Async generator: yield SSE events for streaming chat with MCP tools."""
        context = await self._retrieve_async(question, k, profile_id=self.session_id)
        tool_defs: list[dict[str, Any]] = []
        if self._mcp_client is not None:
            tool_defs = self._mcp_client.get_tool_definitions()

        messages: list[dict[str, Any]] = self._build_messages(
            question,
            context,
            has_tools=bool(tool_defs),
        )
        timestamp = datetime.now(timezone.utc).isoformat()
        tool_history: list[dict[str, Any]] = []
        yield {"type": "meta", "user_message": question, "timestamp": timestamp}

        async def emit_final_answer():
            full = ""
            try:
                token_source = await self._provider_chat(messages, stream=True)
                async for token in token_source:
                    full += token
                    yield {"type": "token", "content": token}
            except Exception as exc:
                yield {"type": "error", "content": str(exc)}
                return
            yield {"type": "done", "content": full}
            self._persist_chat(question, full, timestamp, tool_history)

        if not tool_defs:
            logger.info("Streaming without MCP tools")
            async for event in emit_final_answer():
                yield event
            return

        print(f"[Agent] MCP client ready, {len(tool_defs)} tool definitions", flush=True)
        logger.info("MCP streaming with %d tool definitions", len(tool_defs))

        # Tool calls must be resolved before the final answer can be streamed.
        for _turn in range(5):
            result = await self._provider_chat(messages, tool_defs=tool_defs)
            tool_calls = result.get("tool_calls") or []

            if not tool_calls:
                async for event in emit_final_answer():
                    yield event
                return

            entries = self._build_tool_call_messages(messages, tool_calls)
            for entry in entries:
                tool_history.append({"role": "tool_call", "content": json.dumps(entry, ensure_ascii=False)})

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

        messages.append({
            "role": "user",
            "content": "请基于以上工具调用结果给出最终答案。",
        })
        async for event in emit_final_answer():
            yield event

    # ------------------------------------------------------------------
    # Chat persistence
    # ------------------------------------------------------------------

    def _persist_chat(
        self,
        question: str,
        response: str,
        timestamp: str,
        tool_history: list[dict[str, Any]] | None = None,
    ) -> None:
        """Save user question, assistant response, and any tool messages to history."""
        history = self.messages
        history.append({"role": "user", "content": question, "timestamp": timestamp})
        if tool_history:
            history.extend(tool_history)
        history.append({
            "role": "assistant",
            "content": response,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self._write_messages(history)

