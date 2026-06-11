"""MCP client manager — spawns the TypeScript MCP server as a subprocess
and communicates via stdio using the Python MCP SDK."""

import os
from pathlib import Path
from typing import Any


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
            try:
                await self._session.__aexit__(None, None, None)
            except Exception:
                pass
            self._session = None
        if self._ctx:
            try:
                await self._ctx.__aexit__(None, None, None)
            except Exception:
                pass
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

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        definitions: list[dict[str, Any]] = []
        for tool in self._tools:
            params = {}
            if hasattr(tool, "inputSchema"):
                params = tool.inputSchema
            elif isinstance(tool, dict) and "inputSchema" in tool:
                params = tool["inputSchema"]

            name = tool.name if hasattr(tool, "name") else tool.get("name", "")
            desc = tool.description if hasattr(tool, "description") else tool.get("description", "")
            definitions.append({
                "type": "function",
                "function": {"name": name, "description": desc, "parameters": params},
            })
        return definitions
