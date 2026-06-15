"""MCP client manager — spawns the TypeScript MCP server as a subprocess
and communicates via stdio using the Python MCP SDK."""

import logging
import os
from pathlib import Path
from typing import Any


# Fields in JSON Schema that Ollama rejects in tool parameters.
_SCHEMA_REJECTED_KEYS = frozenset({"$schema", "additionalProperties", "title"})
logger = logging.getLogger("MCP")


def _strip_schema_meta(schema: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in schema.items() if key not in _SCHEMA_REJECTED_KEYS}


def _clean_schema(params: dict[str, Any]) -> dict[str, Any]:
    """Remove JSON Schema meta fields that cause Ollama 400 errors."""
    out: dict[str, Any] = {}
    for key, value in params.items():
        if key in _SCHEMA_REJECTED_KEYS:
            continue
        if key == "properties" and isinstance(value, dict):
            out[key] = {
                name: _strip_schema_meta(schema) if isinstance(schema, dict) else schema
                for name, schema in value.items()
            }
        else:
            out[key] = value
    return out


def _tool_value(tool: Any, key: str, default: Any = "") -> Any:
    if hasattr(tool, key):
        return getattr(tool, key)
    return tool.get(key, default) if isinstance(tool, dict) else default


async def _safe_exit_context(ctx: Any) -> None:
    try:
        await ctx.__aexit__(None, None, None)
    except Exception:
        pass


class MCPClientManager:
    def __init__(self, profile: dict[str, Any]) -> None:
        self._profile = profile
        self._session = None
        self._tools: list[Any] = []
        self._ctx = None
        self._read = None
        self._write = None

    @property
    def tools(self) -> list[Any]:
        return self._tools

    @property
    def is_running(self) -> bool:
        return self._session is not None

    def _server_path(self) -> Path:
        project_dir = Path(__file__).resolve().parent.parent
        src_dir = project_dir / "src"
        dist_js = project_dir / "dist" / "index.js"
        if dist_js.exists():
            return dist_js
        src_ts = src_dir / "index.ts"
        if src_ts.exists():
            return src_ts
        raise FileNotFoundError(
            f"MCP server not found at {dist_js} or {src_ts}. "
            "Run 'npm run build' in the project root first."
        )

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        steam = self._profile.get("steam", {})
        env["STEAM_API_KEY"] = steam.get("apiKey", "")
        env["STEAM_ID"] = steam.get("steamId", "")
        env["STEAM_CURRENCY"] = "CNY"
        steam_path = steam.get("steamPath", "").strip()
        if steam_path:
            env["STEAM_PATH"] = steam_path
        proxy = steam.get("proxy", "").strip()
        if proxy:
            env["HTTP_PROXY"] = proxy
            env["HTTPS_PROXY"] = proxy
        return env

    async def start(self) -> list[Any]:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            raise RuntimeError("Python MCP SDK not installed. Run: pip install mcp")

        server_path = self._server_path()
        env = self._build_env()

        if str(server_path).endswith(".ts"):
            command = "npx"
            args = ["tsx", str(server_path)]
        else:
            command = "node"
            args = [str(server_path)]

        server_params = StdioServerParameters(command=command, args=args, env=env)
        self._ctx = stdio_client(server_params)
        self._read, self._write = await self._ctx.__aenter__()

        self._session = ClientSession(self._read, self._write)
        await self._session.__aenter__()
        await self._session.initialize()

        result = await self._session.list_tools()
        self._tools = result.tools
        return self._tools

    async def stop(self) -> None:
        if self._session:
            await _safe_exit_context(self._session)
            self._session = None
        if self._ctx:
            await _safe_exit_context(self._ctx)
            self._ctx = None
        self._read = None
        self._write = None

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        if not self._session:
            raise RuntimeError("MCP client not started. Call start() first.")
        result = await self._session.call_tool(name, arguments)
        texts: list[str] = []
        for block in result.content:
            if hasattr(block, "text"):
                texts.append(block.text)
            elif isinstance(block, dict) and "text" in block:
                texts.append(block["text"])
        return "\n".join(texts)

    async def ping(self) -> bool:
        if not self._session:
            return False
        try:
            await self._session.list_tools()
            return True
        except Exception:
            return False

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        definitions: list[dict[str, Any]] = []
        for tool in self._tools:
            params = _tool_value(tool, "inputSchema", {})
            # Ollama rejects $schema, additionalProperties, and other JSON Schema
            # meta fields that the MCP SDK includes. Strip them to avoid 400 errors.
            if isinstance(params, dict):
                params = _clean_schema(params)

            definitions.append({
                "type": "function",
                "function": {
                    "name": _tool_value(tool, "name"),
                    "description": _tool_value(tool, "description"),
                    "parameters": params,
                },
            })
        return definitions


class PersistentMCPClientManager:
    """Long-lived MCP client wrapper that reuses a single subprocess across
    multiple requests for the same profile.  Includes a health-check that
    auto-restarts the subprocess if it has died."""

    def __init__(self, profile: dict[str, Any]) -> None:
        self._profile = profile
        self._manager: MCPClientManager | None = None

    async def start(self) -> list[Any]:
        if self._manager is not None:
            return self._manager.tools
        self._manager = MCPClientManager(self._profile)
        return await self._manager.start()

    async def stop(self) -> None:
        if self._manager is not None:
            await self._manager.stop()
            self._manager = None

    async def health_check(self) -> bool:
        """Return True if the underlying MCP subprocess is still alive."""
        if self._manager is None:
            return False
        return await self._manager.ping()

    async def ensure_healthy(self) -> None:
        """Restart the MCP subprocess if health check fails."""
        if not await self.health_check():
            logger.warning("MCP health check failed, restarting subprocess...")
            await self.stop()
            await self.start()

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        await self.ensure_healthy()
        if self._manager is None:
            raise RuntimeError("MCP client not started.")
        return await self._manager.call_tool(name, arguments)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        if self._manager is None:
            return []
        return self._manager.get_tool_definitions()

    @property
    def is_running(self) -> bool:
        return self._manager is not None and self._manager.is_running
