import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import (
    history_path,
    legacy_history_path,
    legacy_md5_path,
    legacy_vector_path,
    md5_path,
    model_name,
    ollama_base_url,
    openai_base_url,
    openai_model_name,
    profiles_path,
    runtime_path,
    steam_country,
    steam_language,
    user_knowledge_path,
    vector_path,
)


def utc_now() -> str:
    """Return a timezone-aware timestamp for profile and history metadata."""
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    """Create a stable local profile id from a user-visible display name."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "profile"


class ProfileStore:
    def __init__(self) -> None:
        self.runtime_path = Path(runtime_path)
        self.profiles_path = Path(profiles_path)
        self.history_path = Path(history_path)
        self.vector_path = Path(vector_path)
        self.ensure_layout()

    def ensure_layout(self) -> None:
        """Create the runtime directory tree and import any old local data."""
        self.runtime_path.mkdir(parents=True, exist_ok=True)
        self.profiles_path.mkdir(parents=True, exist_ok=True)
        self.history_path.mkdir(parents=True, exist_ok=True)
        self.vector_path.mkdir(parents=True, exist_ok=True)
        Path(user_knowledge_path).mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_data()

    def _migrate_legacy_data(self) -> None:
        """Move pre-runtime history/vector files forward without deleting them."""
        if legacy_history_path.exists():
            for legacy_file in Path(legacy_history_path).iterdir():
                if not legacy_file.is_file():
                    continue
                profile_id = slugify(legacy_file.name)
                profile_path = self.profile_path(profile_id)
                history_target = self.history_file_path(profile_id)
                if not profile_path.exists():
                    profile = self._default_profile(profile_id, legacy_file.name)
                    self._write_json(profile_path, profile)
                if not history_target.exists():
                    shutil.copy2(legacy_file, history_target)

        if legacy_vector_path.exists() and not any(self.vector_path.iterdir()):
            for entry in Path(legacy_vector_path).iterdir():
                target = self.vector_path / entry.name
                if entry.is_dir():
                    shutil.copytree(entry, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(entry, target)

        legacy_md5 = Path(legacy_md5_path)
        runtime_md5 = Path(md5_path)
        if legacy_md5.exists() and not runtime_md5.exists():
            runtime_md5.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy_md5, runtime_md5)

    def _default_profile(self, profile_id: str, display_name: str) -> dict[str, Any]:
        """Build a new profile with non-sensitive defaults only."""
        timestamp = utc_now()
        return {
            "id": profile_id,
            "displayName": display_name,
            "createdAt": timestamp,
            "updatedAt": timestamp,
            "ai": {
                "provider": "ollama",
                "ollama": {
                    "baseUrl": ollama_base_url,
                    "model": model_name,
                },
                "openaiCompatible": {
                    "apiKey": "",
                    "baseUrl": openai_base_url,
                    "model": openai_model_name,
                },
            },
            "steam": {
                "apiKey": "",
                "steamId": "",
                "country": steam_country,
                "language": steam_language,
                "proxy": "",
            },
        }

    def profile_path(self, profile_id: str) -> Path:
        return self.profiles_path / f"{profile_id}.json"

    def history_file_path(self, profile_id: str) -> Path:
        return self.history_path / f"{profile_id}.json"

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def list_profiles(self) -> list[dict[str, Any]]:
        """Return lightweight profile summaries for the sidebar."""
        profiles: list[dict[str, Any]] = []
        for path in sorted(self.profiles_path.glob("*.json")):
            profile = self._read_json(path, None)
            if not isinstance(profile, dict):
                continue
            history = self.load_messages(profile["id"])
            profiles.append(
                {
                    "id": profile["id"],
                    "displayName": profile["displayName"],
                    "createdAt": profile["createdAt"],
                    "updatedAt": profile["updatedAt"],
                    "messageCount": len(history),
                    "provider": profile.get("ai", {}).get("provider", "ollama"),
                    "hasSteamConfig": bool(
                        profile.get("steam", {}).get("apiKey")
                        and profile.get("steam", {}).get("steamId")
                    ),
                    "hasAiConfig": self._has_ai_config(profile),
                }
            )
        profiles.sort(key=lambda item: item["updatedAt"], reverse=True)
        return profiles

    def _has_ai_config(self, profile: dict[str, Any]) -> bool:
        ai = profile.get("ai", {})
        provider = ai.get("provider", "ollama")
        if provider == "openai-compatible":
            settings = ai.get("openaiCompatible", {})
            return bool(settings.get("apiKey") and settings.get("baseUrl") and settings.get("model"))
        settings = ai.get("ollama", {})
        return bool(settings.get("baseUrl") and settings.get("model"))

    def create_profile(self, display_name: str) -> dict[str, Any]:
        cleaned = display_name.strip()
        if not cleaned:
            raise ValueError("用户名不能为空。")

        profile_id = slugify(cleaned)
        if self.profile_path(profile_id).exists():
            raise FileExistsError("该用户名已存在。")

        profile = self._default_profile(profile_id, cleaned)
        self._write_json(self.profile_path(profile_id), profile)
        self.save_messages(profile_id, [])
        return profile

    def get_profile(self, profile_id: str) -> dict[str, Any]:
        profile = self._read_json(self.profile_path(profile_id), None)
        if not isinstance(profile, dict):
            raise FileNotFoundError("用户不存在。")
        return profile

    def delete_profile(self, profile_id: str) -> None:
        profile_path = self.profile_path(profile_id)
        history_file = self.history_file_path(profile_id)
        knowledge_dir = Path(user_knowledge_path) / profile_id
        profile_md5_file = Path(md5_path).parent / "md5" / f"{profile_id}.txt"

        if not profile_path.exists():
            raise FileNotFoundError("用户不存在。")

        # A profile owns several runtime sidecars. Remove them together so a
        # recreated user does not inherit old history, uploads, or md5 markers.
        profile_path.unlink(missing_ok=True)
        history_file.unlink(missing_ok=True)
        if knowledge_dir.exists():
            shutil.rmtree(knowledge_dir)
        profile_md5_file.unlink(missing_ok=True)

    def update_profile_config(
        self,
        profile_id: str,
        *,
        ai: dict[str, Any] | None = None,
        steam: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Merge partial settings updates without resetting unrelated sections."""
        profile = self.get_profile(profile_id)

        if ai:
            profile_ai = profile.setdefault("ai", {})
            provider = ai.get("provider") or profile_ai.get("provider", "ollama")
            if provider not in {"ollama", "openai-compatible"}:
                raise ValueError("不支持的 AI provider。")
            profile_ai["provider"] = provider

            if isinstance(ai.get("ollama"), dict):
                current = profile_ai.setdefault("ollama", {})
                current.update(
                    {
                        "baseUrl": ai["ollama"].get("baseUrl", current.get("baseUrl", ollama_base_url)).strip(),
                        "model": ai["ollama"].get("model", current.get("model", model_name)).strip(),
                    }
                )

            if isinstance(ai.get("openaiCompatible"), dict):
                current = profile_ai.setdefault("openaiCompatible", {})
                current.update(
                    {
                        "apiKey": ai["openaiCompatible"].get("apiKey", current.get("apiKey", "")).strip(),
                        "baseUrl": ai["openaiCompatible"].get("baseUrl", current.get("baseUrl", openai_base_url)).strip(),
                        "model": ai["openaiCompatible"].get("model", current.get("model", openai_model_name)).strip(),
                    }
                )

        if steam:
            profile_steam = profile.setdefault("steam", {})
            profile_steam.update(
                {
                    "apiKey": steam.get("apiKey", profile_steam.get("apiKey", "")).strip(),
                    "steamId": steam.get("steamId", profile_steam.get("steamId", "")).strip(),
                    "country": steam.get("country", profile_steam.get("country", steam_country)).strip() or steam_country,
                    "language": steam.get("language", profile_steam.get("language", steam_language)).strip() or steam_language,
                    "proxy": steam.get("proxy", profile_steam.get("proxy", "")).strip(),
                }
            )

        profile["updatedAt"] = utc_now()
        self._write_json(self.profile_path(profile_id), profile)
        return profile

    def load_messages(self, profile_id: str) -> list[dict[str, Any]]:
        """Load one profile's chat history and normalize legacy message shapes."""
        raw_messages = self._read_json(self.history_file_path(profile_id), [])
        normalized: list[dict[str, Any]] = []
        if not isinstance(raw_messages, list):
            return normalized

        for item in raw_messages:
            if isinstance(item, dict) and "role" in item and "content" in item:
                normalized.append(
                    {
                        "role": item["role"],
                        "content": item["content"],
                        "timestamp": item.get("timestamp") or utc_now(),
                    }
                )
                continue

            if not isinstance(item, dict):
                continue

            role = item.get("type")
            payload = item.get("data", {})
            if role == "human":
                normalized.append(
                    {
                        "role": "user",
                        "content": payload.get("content", ""),
                        "timestamp": item.get("timestamp") or utc_now(),
                    }
                )
            elif role in {"ai", "assistant"}:
                normalized.append(
                    {
                        "role": "assistant",
                        "content": payload.get("content", ""),
                        "timestamp": item.get("timestamp") or utc_now(),
                    }
                )

        return normalized

    def save_messages(self, profile_id: str, messages: list[dict[str, Any]]) -> None:
        self._write_json(self.history_file_path(profile_id), messages)

    def knowledge_dir(self, profile_id: str) -> Path:
        dir_path = Path(user_knowledge_path) / profile_id
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    def _knowledge_file_path(self, profile_id: str, filename: str) -> Path:
        safe_name = filename.replace("\\", "/").split("/")[-1]
        return self.knowledge_dir(profile_id) / safe_name

    def list_knowledge_files(self, profile_id: str) -> dict[str, list[dict[str, Any]]]:
        public_files: list[dict[str, Any]] = []
        public_dir = Path(__import__("config").knowledge_path)
        if public_dir.exists():
            for f in sorted(public_dir.glob("*.json")):
                public_files.append({"name": f.name, "size": f.stat().st_size, "source": "public"})

        user_files: list[dict[str, Any]] = []
        user_dir = self.knowledge_dir(profile_id)
        for f in sorted(user_dir.glob("*.json")):
            user_files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "source": "user",
                "uploadedAt": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
            })

        return {"public": public_files, "user": user_files}

    def save_knowledge_file(self, profile_id: str, filename: str, content: bytes) -> Path:
        # Only keep the basename from the browser-provided filename. This blocks
        # path traversal while still preserving the user's visible file name.
        safe_name = filename.replace("\\", "/").split("/")[-1]
        if not safe_name or safe_name in {".", ".."} or len(safe_name) > 160:
            raise ValueError("文件名不合法。")
        if any(char in safe_name for char in '<>:"|?*'):
            raise ValueError("文件名包含不支持的字符。")
        if not safe_name.lower().endswith(".json"):
            raise ValueError("仅支持 .json 文件。")
        target = self._knowledge_file_path(profile_id, safe_name)
        target.write_bytes(content)
        return target

    def read_knowledge_file(self, profile_id: str, filename: str) -> str:
        target = self._knowledge_file_path(profile_id, filename)
        if not target.exists():
            raise FileNotFoundError("文件不存在。")
        return target.read_text(encoding="utf-8")

    def delete_knowledge_file(self, profile_id: str, filename: str) -> None:
        target = self._knowledge_file_path(profile_id, filename)
        if not target.exists():
            raise FileNotFoundError("文件不存在。")
        target.unlink()
