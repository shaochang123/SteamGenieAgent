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
    max_split_char_number,
    md5_path,
    model_name,
    ollama_base_url,
    separators,
    system_prompt,
    vector_path,
)
from http_utils import fetch_json


class Agent:
    def __init__(
        self,
        session_id: str,
        storage_path: str | os.PathLike[str] = history_path,
        vector_root: str | os.PathLike[str] = vector_path,
        settings: dict[str, Any] | None = None,
    ) -> None:
        self.session_id = session_id
        self.storage_path = Path(storage_path)
        self.vector_root = Path(vector_root)
        self.settings = settings or {}
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

    def check_md5(self, input_str: str, encoding: str = "utf-8") -> bool:
        if not Path(md5_path).exists():
            Path(md5_path).write_text("", encoding="utf-8")
            return False

        md5_hex = hashlib.md5(input_str.encode(encoding=encoding)).hexdigest()
        with open(md5_path, "r", encoding="utf-8") as handle:
            return any(line.strip() == md5_hex for line in handle.readlines())

    def update_md5(self, input_str: str, encoding: str = "utf-8") -> None:
        md5_hex = hashlib.md5(input_str.encode(encoding=encoding)).hexdigest()
        with open(md5_path, "a", encoding="utf-8") as handle:
            handle.write(f"{md5_hex}\n")

    def addKnowledge(self, knowledge: str, filename: str) -> str:
        if self.check_md5(knowledge):
            return f"[Failed]The {filename} already exists"

        if len(knowledge) > max_split_char_number:
            knowledge_chunks: list[str] = self.spliter.split_text(knowledge)
        else:
            knowledge_chunks = [knowledge]

        metadata = {
            "source": filename,
            "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "operator": self.session_id,
        }
        vector_store = self._get_vector_store()
        vector_store.add_texts(
            knowledge_chunks,
            metadatas=[metadata for _ in knowledge_chunks],
        )
        self.update_md5(knowledge)
        return f"[Success]Add {filename} into vector database"

    def format_func(self, docs: list[Document]) -> str:
        if not docs:
            return "No related references"

        return "\n\n".join(
            [f"Reference {index + 1}:\n{doc.page_content}" for index, doc in enumerate(docs)]
        )

    def _retrieve_context(self, question: str, k: int) -> str:
        try:
            retriever = self._get_vector_store().as_retriever(search_kwargs={"k": k})
            docs = retriever.invoke(question)
            return self.format_func(docs)
        except Exception:
            return "No related references"

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

    def _call_provider(self, messages: list[dict[str, str]]) -> str:
        provider = self.settings.get("ai", {}).get("provider", "ollama")
        if provider == "openai-compatible":
            return self._call_openai_compatible(messages)
        return self._call_ollama(messages)

    def Call(self, question: str, k: int = 3, verbose: bool = False) -> str:
        context = self._retrieve_context(question, k)
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


if __name__ == "__main__":
    SteamAgent = Agent("system")

    input_question = sys.argv[1]
    SteamAgent.Call(input_question)
