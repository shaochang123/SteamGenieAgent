import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
        self.session_id = session_id
        self.storage_path = Path(storage_path)
        self.vector_root = Path(vector_root)
        self.settings = settings or {}
        self._mcp_client = mcp_client
        self.file_path = self.storage_path / f"{self.session_id}.json"
        self.spliter = RecursiveCharacterTextSplitter(
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
                continue

            if not isinstance(item, dict):
                continue

            role = item.get("type")
            payload = item.get("data", {})
            content = payload.get("content", "")
            if role == "human":
                normalized.append(
                    {"role": "user", "content": content, "timestamp": item.get("timestamp")}
                )
            elif role in {"ai", "assistant"}:
                normalized.append(
                    {
                        "role": "assistant",
                        "content": content,
                        "timestamp": item.get("timestamp"),
                    }
                )

        return normalized

    def _write_messages(self, messages: list[dict[str, Any]]) -> None:
        with self.file_path.open("w", encoding="utf-8") as handle:
            json.dump(messages, handle, ensure_ascii=False, indent=2)

    def _get_vector_store(self) -> Chroma:
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

    def check_md5(self, input_str: str, encoding: str = "utf-8", profile_id: str = "shared") -> bool:
        target = self._md5_file(profile_id)
        if not target.exists():
            target.write_text("", encoding="utf-8")
            return False

        md5_hex = hashlib.md5(input_str.encode(encoding=encoding)).hexdigest()
        with open(target, "r", encoding="utf-8") as handle:
            return any(line.strip() == md5_hex for line in handle.readlines())

    def update_md5(self, input_str: str, encoding: str = "utf-8", profile_id: str = "shared") -> None:
        md5_hex = hashlib.md5(input_str.encode(encoding=encoding)).hexdigest()
        with open(self._md5_file(profile_id), "a", encoding="utf-8") as handle:
            handle.write(f"{md5_hex}\n")

    def add_knowledge(self, knowledge: str, filename: str, profile_id: str = "shared") -> str:
        if self.check_md5(knowledge, profile_id=profile_id):
            return f"[Failed]The {filename} already exists"

        if len(knowledge) > max_split_char_number:
            knowledge_chunks: list[str] = self.spliter.split_text(knowledge)
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
                search_kwargs["filter"] = {"profile_id": {"$in": ["shared", profile_id]}}
            retriever = self._get_vector_store().as_retriever(search_kwargs=search_kwargs)
            docs = retriever.invoke(question)
            return self.format_func(docs)
        except Exception as exc:
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

            if role in ("tool_call", "tool_result", "tool"):
                continue
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

    async def _ollama(self, messages: list[dict[str, str]]) -> str:
        """Async version using httpx — does not block the event loop."""
        ai_settings = self.settings.get("ai", {})
        ollama_settings = ai_settings.get("ollama", {})
        base_url = (ollama_settings.get("baseUrl") or ollama_base_url).rstrip("/")
        chat_model = (ollama_settings.get("model") or model_name).strip() or model_name
        payload = {"model": chat_model, "messages": messages, "stream": False}
        response = await async_fetch_json(f"{base_url}/api/chat", method="POST", payload=payload)
        return response.get("message", {}).get("content", "").strip()

    async def _openai(self, messages: list[dict[str, str]]) -> str:
        """Async version using httpx — does not block the event loop."""
        ai_settings = self.settings.get("ai", {})
        openai_settings = ai_settings.get("openaiCompatible", {})
        api_key = (openai_settings.get("apiKey") or "").strip()
        base_url = (openai_settings.get("baseUrl") or "").rstrip("/")
        chat_model = (openai_settings.get("model") or "").strip()

        if not api_key or not base_url or not chat_model:
            raise RuntimeError("OpenAI 兼容接口缺少 apiKey、baseUrl 或 model。")

        payload = {"model": chat_model, "messages": messages}
        response = await async_fetch_json(
            f"{base_url}/chat/completions",
            method="POST",
            payload=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        choices = response.get("choices") or []
        if not choices:
            raise RuntimeError("OpenAI 兼容接口未返回结果。")

        content = choices[0].get("message", {}).get("content", "")
        if isinstance(content, list):
            return "".join(
                part.get("text", "") if isinstance(part, dict) else str(part) for part in content
            ).strip()
        return str(content).strip()

    async def _ollama_stream(self, messages: list[dict[str, str]]):
        """Async version of _call_ollama_stream using httpx."""
        ai_settings = self.settings.get("ai", {})
        ollama_settings = ai_settings.get("ollama", {})
        base_url = (ollama_settings.get("baseUrl") or ollama_base_url).rstrip("/")
        chat_model = (ollama_settings.get("model") or model_name).strip() or model_name
        payload = {"model": chat_model, "messages": messages, "stream": True}
        async for line in async_fetch_stream_lines(f"{base_url}/api/chat", method="POST", payload=payload):
            raw = line.strip()
            if not raw:
                continue
            try:
                chunk = json.loads(raw)
            except json.JSONDecodeError:
                continue
            content = chunk.get("message", {}).get("content", "")
            if content:
                yield content
            if chunk.get("done", False):
                break

    async def _openai_stream(self, messages: list[dict[str, str]]):
        """Async version of _call_openai_compatible_stream using httpx."""
        ai_settings = self.settings.get("ai", {})
        openai_settings = ai_settings.get("openaiCompatible", {})
        api_key = (openai_settings.get("apiKey") or "").strip()
        base_url = (openai_settings.get("baseUrl") or "").rstrip("/")
        chat_model = (openai_settings.get("model") or "").strip()

        if not api_key or not base_url or not chat_model:
            raise RuntimeError("OpenAI 兼容接口缺少 apiKey、baseUrl 或 model。")

        payload = {"model": chat_model, "messages": messages, "stream": True}
        headers = {"Authorization": f"Bearer {api_key}"}
        async for line in async_fetch_stream_lines(
            f"{base_url}/chat/completions", method="POST", payload=payload, headers=headers
        ):
            raw = line.strip()
            if not raw or not raw.startswith("data: "):
                continue
            data_str = raw[6:]
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta", {})
            content = delta.get("content", "")
            if content:
                yield content

    async def _provider_stream(self, messages: list[dict[str, str]]):
        """Async generator: yield tokens from the configured provider."""
        provider = self.settings.get("ai", {}).get("provider", "ollama")
        if provider == "openai-compatible":
            async for token in self._openai_stream(messages):
                yield token
        else:
            async for token in self._ollama_stream(messages):
                yield token

    async def _ollama_tools(
        self, messages: list[dict[str, Any]], tool_defs: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | str:
        """Async version using httpx — does not block the event loop."""
        ai_settings = self.settings.get("ai", {})
        ollama_settings = ai_settings.get("ollama", {})
        base_url = (ollama_settings.get("baseUrl") or ollama_base_url).rstrip("/")
        chat_model = (ollama_settings.get("model") or model_name).strip() or model_name
        payload = {
            "model": chat_model,
            "messages": messages,
            "tools": tool_defs,
            "stream": False,
        }
        logger.info(
            "Ollama tool call: model=%s tools=%d messages=%d url=%s",
            chat_model, len(tool_defs), len(messages), base_url,
        )
        print(
            f"[Agent] calling Ollama with {len(tool_defs)} tools, "
            f"{len(messages)} messages, model={chat_model}",
            flush=True,
        )
        try:
            response = await async_fetch_json(f"{base_url}/api/chat", method="POST", payload=payload)
        except Exception:
            dump_path = Path(__file__).parent / "_ollama_payload_dump.json"
            try:
                dump_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(f"[Agent] 400 payload dumped to {dump_path}", flush=True)
            except Exception:
                pass
            raise
        msg = response.get("message", {})
        if msg.get("tool_calls"):
            print(f"[Agent] Ollama returned {len(msg['tool_calls'])} tool_calls", flush=True)
            logger.info("Ollama returned %d tool_calls", len(msg["tool_calls"]))
            results: list[dict[str, Any]] = []
            for tc in msg["tool_calls"]:
                func = tc.get("function", {})
                args = func.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                results.append({
                    "id": tc.get("id", ""),
                    "name": func.get("name", ""),
                    "arguments": args,
                })
            return results
        content = msg.get("content", "").strip()
        print(f"[Agent] Ollama returned text (no tool_calls): {content[:120]}...", flush=True)
        logger.info("Ollama returned text (no tool_calls): %s", content[:200])
        return content

    async def _openai_tools(
        self, messages: list[dict[str, Any]], tool_defs: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | str:
        """Async version using httpx — does not block the event loop."""
        ai_settings = self.settings.get("ai", {})
        openai_settings = ai_settings.get("openaiCompatible", {})
        api_key = (openai_settings.get("apiKey") or "").strip()
        base_url = (openai_settings.get("baseUrl") or "").rstrip("/")
        chat_model = (openai_settings.get("model") or "").strip()

        if not api_key or not base_url or not chat_model:
            raise RuntimeError("OpenAI 兼容接口缺少 apiKey、baseUrl 或 model。")

        payload = {"model": chat_model, "messages": messages, "tools": tool_defs}
        response = await async_fetch_json(
            f"{base_url}/chat/completions",
            method="POST",
            payload=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        choice = (response.get("choices") or [None])[0]
        if not choice:
            raise RuntimeError("OpenAI 兼容接口未返回结果。")

        msg = choice.get("message", {})
        if msg.get("tool_calls"):
            results: list[dict[str, Any]] = []
            for tc in msg["tool_calls"]:
                func = tc.get("function", {})
                args = func.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                results.append({
                    "id": tc.get("id", ""),
                    "name": func.get("name", ""),
                    "arguments": args,
                })
            return results
        return str(msg.get("content", "")).strip()

    async def _provider_tools(
        self, messages: list[dict[str, Any]], tool_defs: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | str:
        """Async version — does not block the event loop."""
        provider = self.settings.get("ai", {}).get("provider", "ollama")
        if provider == "openai-compatible":
            return await self._openai_tools(messages, tool_defs)
        return await self._ollama_tools(messages, tool_defs)

    async def _provider(self, messages: list[dict[str, str]]) -> str:
        """Async version — does not block the event loop."""
        provider = self.settings.get("ai", {}).get("provider", "ollama")
        if provider == "openai-compatible":
            return await self._openai(messages)
        return await self._ollama(messages)

    # ------------------------------------------------------------------
    # Tool-calling helpers
    # ------------------------------------------------------------------

    def _build_tool_call_messages(
        self, messages: list[dict[str, Any]], tool_calls: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Append assistant tool_calls and tool result messages to *messages*.
        Returns list of (tool_name, tool_args, tool_call_id) tuples for execution."""
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

    # ------------------------------------------------------------------
    # Non-streaming tool loop
    # ------------------------------------------------------------------

    async def chat(self, question: str, k: int = 3) -> str:
        context = await self._retrieve_async(question, k, profile_id=self.session_id)
        messages: list[dict[str, Any]] = self._build_messages(question, context, has_tools=True)
        timestamp = datetime.now(timezone.utc).isoformat()

        if self._mcp_client is None:
            response = await self._provider(messages)
            self._persist_chat(question, response, timestamp, messages)
            return response

        tool_defs = self._mcp_client.get_tool_definitions()
        tool_history: list[dict[str, Any]] = []  # for persistence

        for _turn in range(5):
            result = await self._provider_tools(messages, tool_defs)

            if isinstance(result, str):
                response = result
                self._persist_chat(question, response, timestamp, messages, tool_history)
                return response

            # Multiple tool calls in one turn
            entries = self._build_tool_call_messages(messages, result)
            for entry in entries:
                tool_history.append({"role": "tool_call", "content": json.dumps(entry, ensure_ascii=False)})

            for tc in result:
                tool_name = tc.get("name", "")
                tool_args = tc.get("arguments", {})
                try:
                    tool_result = await self._mcp_client.call_tool(tool_name, tool_args)
                except Exception as exc:
                    tool_result = f"工具调用失败: {exc}"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", "call_1"),
                    "content": tool_result,
                })
                tool_history.append({"role": "tool_result", "content": tool_result})

        # Max turns reached — ask for final answer
        messages.append({
            "role": "user",
            "content": "请基于以上工具调用结果给出最终答案。",
        })
        response = await self._provider(messages)
        self._persist_chat(question, response, timestamp, messages, tool_history)
        return response

    # ------------------------------------------------------------------
    # Streaming tool loop (true async generator — no event loop nesting)
    # ------------------------------------------------------------------

    async def chat_stream(self, question: str, k: int = 3):
        """Async generator: yield SSE events for streaming chat with MCP tools."""
        context = await self._retrieve_async(question, k, profile_id=self.session_id)
        messages: list[dict[str, Any]] = self._build_messages(question, context, has_tools=True)
        timestamp = datetime.now(timezone.utc).isoformat()
        tool_history: list[dict[str, Any]] = []
        yield {"type": "meta", "user_message": question, "timestamp": timestamp}

        if self._mcp_client is None:
            print("[Agent] No MCP client — streaming without tools", flush=True)
            logger.info("No MCP client — streaming without tools")
            full = ""
            try:
                async for token in self._provider_stream(messages):
                    full += token
                    yield {"type": "token", "content": token}
            except Exception as exc:
                yield {"type": "error", "content": str(exc)}
                return
            yield {"type": "done", "content": full}
            self._persist_chat(question, full, timestamp, messages)
            return

        tool_defs = self._mcp_client.get_tool_definitions()
        print(f"[Agent] MCP client ready, {len(tool_defs)} tool definitions", flush=True)
        logger.info("MCP streaming with %d tool definitions", len(tool_defs))

        for _turn in range(5):
            result = await self._provider_tools(messages, tool_defs)

            if isinstance(result, str):
                full = ""
                try:
                    async for token in self._provider_stream(messages):
                        full += token
                        yield {"type": "token", "content": token}
                except Exception as exc:
                    yield {"type": "error", "content": str(exc)}
                    return
                yield {"type": "done", "content": full}
                self._persist_chat(question, full, timestamp, messages, tool_history)
                return

            entries = self._build_tool_call_messages(messages, result)
            for entry in entries:
                tool_history.append({"role": "tool_call", "content": json.dumps(entry, ensure_ascii=False)})

            for tc in result:
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
        full = ""
        try:
            async for token in self._provider_stream(messages):
                full += token
                yield {"type": "token", "content": token}
        except Exception as exc:
            yield {"type": "error", "content": str(exc)}
            return
        yield {"type": "done", "content": full}
        self._persist_chat(question, full, timestamp, messages, tool_history)

    # ------------------------------------------------------------------
    # Chat persistence
    # ------------------------------------------------------------------

    def _persist_chat(
        self,
        question: str,
        response: str,
        timestamp: str,
        messages: list[dict[str, Any]],
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

