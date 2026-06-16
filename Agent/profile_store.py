import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import (
    history_path,
    knowledge_path,
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
from tool_markup import hide_tool_markup

SUPPORTED_AI_PROVIDERS = {"ollama", "openai-compatible"}
OLLAMA_DEFAULTS = {"baseUrl": ollama_base_url, "model": model_name}
OPENAI_DEFAULTS = {"apiKey": "", "baseUrl": openai_base_url, "model": openai_model_name}
STEAM_DEFAULTS = {
    "apiKey": "",
    "steamId": "",
    "steamPath": "",
    "country": steam_country,
    "language": steam_language,
    "proxy": "",
}


def utc_now() -> str:
    """Return a timezone-aware timestamp for profile and history metadata."""
    return datetime.now(timezone.utc).isoformat()


def slugify(value: str) -> str:
    """Create a stable local profile id from a user-visible display name."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "profile"


def clean_setting(
    source: dict[str, Any],
    current: dict[str, Any],
    key: str,
    default: str = "",
) -> str:
    """Read a settings field while preserving explicit empty-string clears."""
    value = source[key] if key in source else current.get(key, default)
    if value is None:
        return ""
    return str(value).strip()


def clean_settings(
    source: dict[str, Any],
    current: dict[str, Any],
    defaults: dict[str, str],
) -> dict[str, str]:
    """Normalize a settings section without overwriting deliberate blank fields."""
    return {
        key: clean_setting(source, current, key, default)
        for key, default in defaults.items()
    }


def safe_filename(filename: str) -> str:
    """Return only the basename part of a browser-provided filename."""
    return filename.replace("\\", "/").split("/")[-1]


def profile_md5_path(profile_id: str) -> Path:
    """Return the per-profile md5 marker file path."""
    return Path(md5_path).parent / "md5" / f"{profile_id}.txt"


def has_required_settings(settings: dict[str, Any], keys: tuple[str, ...]) -> bool:
    """Return True when all required keys contain non-empty text."""
    return all(str(settings.get(key) or "").strip() for key in keys)


def validate_ai_config(ai: dict[str, Any]) -> None:
    """Validate that the active AI provider has enough settings to answer."""
    provider = ai.get("provider", "ollama")
    if provider == "ollama":
        if not has_required_settings(ai.get("ollama", {}), ("baseUrl", "model")):
            raise ValueError("选择 Ollama 时需要填写 Base URL 和 Model。")
        return

    if provider == "openai-compatible":
        if not has_required_settings(
            ai.get("openaiCompatible", {}), ("apiKey", "baseUrl", "model")
        ):
            raise ValueError("选择 OpenAI 兼容接口时需要填写 API Key、Base URL 和 Model。")
        return

    raise ValueError("不支持的 AI provider。")


class ProfileStore:
    def __init__(self) -> None:
        """Initialize runtime paths and ensure local storage is ready."""
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
                "ollama": dict(OLLAMA_DEFAULTS),
                "openaiCompatible": dict(OPENAI_DEFAULTS),
            },
            "steam": dict(STEAM_DEFAULTS),
        }

    def profile_path(self, profile_id: str) -> Path:
        """Return the JSON config path for a profile."""
        return self.profiles_path / f"{profile_id}.json"

    def history_file_path(self, profile_id: str) -> Path:
        """Return the chat history path for a profile."""
        return self.history_path / f"{profile_id}.json"

    def _read_json(self, path: Path, default: Any) -> Any:
        """Read JSON from disk or return a default when the file is missing."""
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_json(self, path: Path, payload: Any) -> None:
        """Write formatted UTF-8 JSON to disk, creating parent directories."""
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
        """Return True when the active provider has required settings."""
        ai = profile.get("ai", {})
        provider = ai.get("provider", "ollama")
        if provider == "openai-compatible":
            settings = ai.get("openaiCompatible", {})
            return all(settings.get(key) for key in ("apiKey", "baseUrl", "model"))
        settings = ai.get("ollama", {})
        return all(settings.get(key) for key in ("baseUrl", "model"))

    def create_profile(self, display_name: str) -> dict[str, Any]:
        """Create a new local profile and empty history file."""
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
        """Load a profile config or raise when it does not exist."""
        profile = self._read_json(self.profile_path(profile_id), None)
        if not isinstance(profile, dict):
            raise FileNotFoundError("用户不存在。")
        return profile

    def delete_profile(self, profile_id: str) -> None:
        """Delete a profile and all profile-owned runtime sidecars."""
        profile_path = self.profile_path(profile_id)
        history_file = self.history_file_path(profile_id)
        knowledge_dir = Path(user_knowledge_path) / profile_id
        profile_md5_file = profile_md5_path(profile_id)

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

        if ai is not None:
            profile_ai = profile.setdefault("ai", {})
            provider = ai.get("provider") or profile_ai.get("provider", "ollama")
            if provider not in SUPPORTED_AI_PROVIDERS:
                raise ValueError("不支持的 AI provider。")
            profile_ai["provider"] = provider

            if isinstance(ai.get("ollama"), dict):
                current = profile_ai.setdefault("ollama", {})
                current.update(clean_settings(ai["ollama"], current, OLLAMA_DEFAULTS))

            if isinstance(ai.get("openaiCompatible"), dict):
                current = profile_ai.setdefault("openaiCompatible", {})
                current.update(clean_settings(ai["openaiCompatible"], current, OPENAI_DEFAULTS))

            validate_ai_config(profile_ai)

        if steam is not None:
            profile_steam = profile.setdefault("steam", {})
            profile_steam.update(clean_settings(steam, profile_steam, STEAM_DEFAULTS))
            profile_steam["country"] = profile_steam["country"] or steam_country
            profile_steam["language"] = profile_steam["language"] or steam_language

        profile["updatedAt"] = utc_now()
        self._write_json(self.profile_path(profile_id), profile)
        return profile

    def _chat_message(self, role: str, content: str, timestamp: str | None = None) -> dict[str, Any]:
        """Build one normalized chat message record."""
        return {"role": role, "content": content, "timestamp": timestamp or utc_now()}

    def _normalize_message(self, item: Any) -> dict[str, Any] | None:
        """Normalize current app messages and older LangChain history records."""
        if not isinstance(item, dict):
            return None

        if "role" in item and "content" in item:
            role = item["role"]
            content = hide_tool_markup(role, item["content"])
            return self._chat_message(role, content, item.get("timestamp"))

        role_map = {"human": "user", "ai": "assistant", "assistant": "assistant"}
        role = role_map.get(item.get("type"))
        payload = item.get("data", {})
        if not role or not isinstance(payload, dict):
            return None

        content = payload.get("content", "")
        if role == "assistant":
            content = hide_tool_markup(role, content)
        return self._chat_message(role, content, item.get("timestamp"))

    def load_messages(self, profile_id: str) -> list[dict[str, Any]]:
        """Load one profile's chat history and normalize legacy message shapes."""
        raw_messages = self._read_json(self.history_file_path(profile_id), [])
        if not isinstance(raw_messages, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in raw_messages:
            message = self._normalize_message(item)
            if message:
                normalized.append(message)

        return normalized

    def save_messages(self, profile_id: str, messages: list[dict[str, Any]]) -> None:
        """Persist normalized chat messages for one profile."""
        self._write_json(self.history_file_path(profile_id), messages)

    def knowledge_dir(self, profile_id: str) -> Path:
        """Return and create the profile-owned knowledge upload directory."""
        dir_path = Path(user_knowledge_path) / profile_id
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    def _knowledge_file_path(self, profile_id: str, filename: str) -> Path:
        """Return a safe path for one profile-owned knowledge file."""
        return self.knowledge_dir(profile_id) / safe_filename(filename)

    def list_knowledge_files(self, profile_id: str) -> dict[str, list[dict[str, Any]]]:
        """List public and profile-owned knowledge files for the UI."""
        public_files: list[dict[str, Any]] = []
        public_dir = Path(knowledge_path)
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
        """Validate and save one uploaded profile knowledge JSON file."""
        # Only keep the basename from the browser-provided filename. This blocks
        # path traversal while still preserving the user's visible file name.
        safe_name = safe_filename(filename)
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
        """Read a profile-owned knowledge file as UTF-8 text."""
        target = self._knowledge_file_path(profile_id, filename)
        if not target.exists():
            raise FileNotFoundError("文件不存在。")
        return target.read_text(encoding="utf-8")

    def delete_knowledge_file(self, profile_id: str, filename: str) -> None:
        """Delete one profile-owned knowledge file from runtime storage."""
        target = self._knowledge_file_path(profile_id, filename)
        if not target.exists():
            raise FileNotFoundError("文件不存在。")
        target.unlink()
