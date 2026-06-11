import hashlib
import json
import os
import sys
from datetime import datetime
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
    user_knowledge_path,
    vector_path,
)
from http_utils import fetch_json, fetch_stream

_public_knowledge_loaded = False


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
        self._load_user_knowledge(self.session_id)

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

    def clear(self) -> None:
        self._write_messages([])

    def _get_vector_store(self) -> Chroma:
        embedding_function = OllamaEmbeddings(model=embedding_model_name)
        return Chroma(
            collection_name="SteamGames",
            embedding_function=embedding_function,
            persist_directory=str(self.vector_root),
        )

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

    def addKnowledge(self, knowledge: str, filename: str, profile_id: str = "shared") -> str:
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
            return "No related references"

        return "\n\n".join(
            [f"Reference {index + 1}:\n{doc.page_content}" for index, doc in enumerate(docs)]
        )

    def _retrieve_context(self, question: str, k: int, profile_id: str | None = None) -> str:
        try:
            search_kwargs: dict[str, Any] = {"k": k}
            if profile_id:
                search_kwargs["filter"] = {"profile_id": {"$in": ["shared", profile_id]}}
            retriever = self._get_vector_store().as_retriever(search_kwargs=search_kwargs)
            docs = retriever.invoke(question)
            return self.format_func(docs)
        except Exception:
            return "No related references"

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
                self.addKnowledge(content, json_file.name, profile_id="shared")
            except Exception:
                pass

    def _load_user_knowledge(self, profile_id: str) -> None:
        user_dir = Path(user_knowledge_path) / profile_id
        if not user_dir.exists():
            return

        for json_file in user_dir.glob("*.json"):
            try:
                content = json_file.read_text(encoding="utf-8")
                self.addKnowledge(content, json_file.name, profile_id=profile_id)
            except Exception:
                pass

    def _build_messages(self, question: str, context: str) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": system_prompt.format(context=context)}]
        for message in self.messages[-10:]:
            role = "assistant" if message.get("role") == "assistant" else "user"
            messages.append({"role": role, "content": message.get("content", "")})
        messages.append({"role": "user", "content": question})
        return messages

    def _call_ollama(self, messages: list[dict[str, str]]) -> str:
        ai_settings = self.settings.get("ai", {})
        ollama_settings = ai_settings.get("ollama", {})
        base_url = (ollama_settings.get("baseUrl") or ollama_base_url).rstrip("/")
        chat_model = (ollama_settings.get("model") or model_name).strip() or model_name
        payload = {"model": chat_model, "messages": messages, "stream": False}
        response = fetch_json(f"{base_url}/api/chat", method="POST", payload=payload)
        return response.get("message", {}).get("content", "").strip()

    def _call_ollama_stream(self, messages: list[dict[str, str]]):
        ai_settings = self.settings.get("ai", {})
        ollama_settings = ai_settings.get("ollama", {})
        base_url = (ollama_settings.get("baseUrl") or ollama_base_url).rstrip("/")
        chat_model = (ollama_settings.get("model") or model_name).strip() or model_name
        payload = {"model": chat_model, "messages": messages, "stream": True}
        resp = fetch_stream(f"{base_url}/api/chat", method="POST", payload=payload)
        try:
            for line in resp:
                raw = line.decode("utf-8").strip()
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
        finally:
            resp.close()

    def _call_openai_compatible(self, messages: list[dict[str, str]]) -> str:
        ai_settings = self.settings.get("ai", {})
        openai_settings = ai_settings.get("openaiCompatible", {})
        api_key = (openai_settings.get("apiKey") or "").strip()
        base_url = (openai_settings.get("baseUrl") or "").rstrip("/")
        chat_model = (openai_settings.get("model") or "").strip()

        if not api_key or not base_url or not chat_model:
            raise RuntimeError("OpenAI 兼容接口缺少 apiKey、baseUrl 或 model。")

        payload = {"model": chat_model, "messages": messages}
        response = fetch_json(
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

    def _call_openai_compatible_stream(self, messages: list[dict[str, str]]):
        ai_settings = self.settings.get("ai", {})
        openai_settings = ai_settings.get("openaiCompatible", {})
        api_key = (openai_settings.get("apiKey") or "").strip()
        base_url = (openai_settings.get("baseUrl") or "").rstrip("/")
        chat_model = (openai_settings.get("model") or "").strip()

        if not api_key or not base_url or not chat_model:
            raise RuntimeError("OpenAI 兼容接口缺少 apiKey、baseUrl 或 model。")

        payload = {"model": chat_model, "messages": messages, "stream": True}
        resp = fetch_stream(
            f"{base_url}/chat/completions",
            method="POST",
            payload=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        try:
            for line in resp:
                raw = line.decode("utf-8").strip()
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
        finally:
            resp.close()

    def _call_ollama_with_tools(
        self, messages: list[dict[str, Any]], tool_defs: list[dict[str, Any]]
    ):
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
        response = fetch_json(f"{base_url}/api/chat", method="POST", payload=payload)
        msg = response.get("message", {})
        if msg.get("tool_calls"):
            tc = msg["tool_calls"][0]
            func = tc.get("function", {})
            return {
                "id": tc.get("id", ""),
                "name": func.get("name", ""),
                "arguments": func.get("arguments", {}),
            }
        return msg.get("content", "").strip()

    def _call_openai_compatible_with_tools(
        self, messages: list[dict[str, Any]], tool_defs: list[dict[str, Any]]
    ):
        ai_settings = self.settings.get("ai", {})
        openai_settings = ai_settings.get("openaiCompatible", {})
        api_key = (openai_settings.get("apiKey") or "").strip()
        base_url = (openai_settings.get("baseUrl") or "").rstrip("/")
        chat_model = (openai_settings.get("model") or "").strip()

        if not api_key or not base_url or not chat_model:
            raise RuntimeError("OpenAI 兼容接口缺少 apiKey、baseUrl 或 model。")

        payload = {"model": chat_model, "messages": messages, "tools": tool_defs}
        response = fetch_json(
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
            tc = msg["tool_calls"][0]
            func = tc.get("function", {})
            args = func.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            return {"id": tc.get("id", ""), "name": func.get("name", ""), "arguments": args}
        return str(msg.get("content", "")).strip()

    def _call_provider_with_tools(
        self, messages: list[dict[str, Any]], tool_defs: list[dict[str, Any]]
    ):
        provider = self.settings.get("ai", {}).get("provider", "ollama")
        if provider == "openai-compatible":
            return self._call_openai_compatible_with_tools(messages, tool_defs)
        return self._call_ollama_with_tools(messages, tool_defs)

    def _call_provider(self, messages: list[dict[str, str]]) -> str:
        provider = self.settings.get("ai", {}).get("provider", "ollama")
        if provider == "openai-compatible":
            return self._call_openai_compatible(messages)
        return self._call_ollama(messages)

    def _call_provider_stream(self, messages: list[dict[str, str]]):
        provider = self.settings.get("ai", {}).get("provider", "ollama")
        if provider == "openai-compatible":
            yield from self._call_openai_compatible_stream(messages)
        else:
            yield from self._call_ollama_stream(messages)

    def Call(self, question: str, k: int = 3, verbose: bool = False) -> str:
        context = self._retrieve_context(question, k, profile_id=self.session_id)
        messages = self._build_messages(question, context)
        response = self._call_provider(messages)
        history = self.messages
        timestamp = datetime.utcnow().isoformat()
        history.extend(
            [
                {"role": "user", "content": question, "timestamp": timestamp},
                {
                    "role": "assistant",
                    "content": response,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            ]
        )
        self._write_messages(history)
        if verbose:
            print(response, end="", flush=True)
        return response

    def Call_stream(self, question: str, k: int = 3):
        context = self._retrieve_context(question, k, profile_id=self.session_id)
        messages = self._build_messages(question, context)

        timestamp = datetime.utcnow().isoformat()
        yield {"type": "meta", "user_message": question, "timestamp": timestamp}

        full_response = ""
        try:
            for token in self._call_provider_stream(messages):
                full_response += token
                yield {"type": "token", "content": token}
        except Exception as exc:
            yield {"type": "error", "content": str(exc)}
            return

        yield {"type": "done", "content": full_response}

        history = self.messages
        history.extend(
            [
                {"role": "user", "content": question, "timestamp": timestamp},
                {
                    "role": "assistant",
                    "content": full_response,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            ]
        )
        self._write_messages(history)

    async def Call_with_tools(self, question: str, k: int = 3) -> str:
        context = self._retrieve_context(question, k, profile_id=self.session_id)
        messages: list[dict[str, Any]] = self._build_messages(question, context)

        if self._mcp_client is None:
            return self._call_provider(messages)

        tool_defs = self._mcp_client.get_tool_definitions()

        for _turn in range(5):
            result = self._call_provider_with_tools(messages, tool_defs)

            if isinstance(result, str):
                response = result
                break

            tool_name = result.get("name", "")
            tool_args = result.get("arguments", {})
            try:
                tool_result = await self._mcp_client.call_tool(tool_name, tool_args)
            except Exception as exc:
                tool_result = f"工具调用失败: {exc}"

            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": result.get("id", "call_1"),
                    "type": "function",
                    "function": {"name": tool_name, "arguments": json.dumps(tool_args, ensure_ascii=False)},
                }],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": result.get("id", "call_1"),
                "content": tool_result,
            })
        else:
            messages.append({
                "role": "user",
                "content": "请基于以上工具调用结果给出最终答案。",
            })
            response = self._call_provider(messages)

        history = self.messages
        timestamp = datetime.utcnow().isoformat()
        history.extend([
            {"role": "user", "content": question, "timestamp": timestamp},
            {"role": "assistant", "content": response, "timestamp": datetime.utcnow().isoformat()},
        ])
        self._write_messages(history)
        return response

    def Call_stream_with_tools(self, question: str, k: int = 3):
        # This is a synchronous generator that wraps the async tool loop.
        # For SSE streaming, we run the async loop internally and yield events.
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(self._async_stream_with_tools(question, k))
            for event in result:
                yield event
        finally:
            loop.close()

    async def _async_stream_with_tools(self, question: str, k: int = 3):
        context = self._retrieve_context(question, k, profile_id=self.session_id)
        messages: list[dict[str, Any]] = self._build_messages(question, context)

        timestamp = datetime.utcnow().isoformat()
        yield {"type": "meta", "user_message": question, "timestamp": timestamp}

        if self._mcp_client is None:
            full = ""
            try:
                for token in self._call_provider_stream(messages):
                    full += token
                    yield {"type": "token", "content": token}
            except Exception as exc:
                yield {"type": "error", "content": str(exc)}
                return
            yield {"type": "done", "content": full}
            self._persist_stream_chat(question, full, timestamp)
            return

        tool_defs = self._mcp_client.get_tool_definitions()

        for _turn in range(5):
            result = self._call_provider_with_tools(messages, tool_defs)

            if isinstance(result, str):
                full = ""
                try:
                    for token in self._call_provider_stream(messages):
                        full += token
                        yield {"type": "token", "content": token}
                except Exception as exc:
                    yield {"type": "error", "content": str(exc)}
                    return
                yield {"type": "done", "content": full}
                self._persist_stream_chat(question, full, timestamp)
                return

            tool_name = result.get("name", "")
            tool_args = result.get("arguments", {})
            yield {"type": "tool_start", "tool": tool_name}

            try:
                tool_result = await self._mcp_client.call_tool(tool_name, tool_args)
            except Exception as exc:
                tool_result = f"工具调用失败: {exc}"

            yield {"type": "tool_result", "tool": tool_name, "result": tool_result}

            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": result.get("id", "call_1"),
                    "type": "function",
                    "function": {"name": tool_name, "arguments": json.dumps(tool_args, ensure_ascii=False)},
                }],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": result.get("id", "call_1"),
                "content": tool_result,
            })

        messages.append({
            "role": "user",
            "content": "请基于以上工具调用结果给出最终答案。",
        })
        full = ""
        try:
            for token in self._call_provider_stream(messages):
                full += token
                yield {"type": "token", "content": token}
        except Exception as exc:
            yield {"type": "error", "content": str(exc)}
            return
        yield {"type": "done", "content": full}
        self._persist_stream_chat(question, full, timestamp)

    def _persist_stream_chat(self, question: str, response: str, timestamp: str) -> None:
        history = self.messages
        history.extend([
            {"role": "user", "content": question, "timestamp": timestamp},
            {"role": "assistant", "content": response, "timestamp": datetime.utcnow().isoformat()},
        ])
        self._write_messages(history)


if __name__ == "__main__":
    SteamAgent = Agent("system")

    input_question = sys.argv[1]
    SteamAgent.Call(input_question)
