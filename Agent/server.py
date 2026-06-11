import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Ensure logs are visible — uvicorn does NOT configure the root logger by default.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    stream=sys.stdout,
    force=True,
)

if TYPE_CHECKING:
    from Agent.Agent import Agent
else:
    from Agent import Agent
from config import history_path, vector_path
from http_utils import close_async_client
from mcp_client import PersistentMCPClientManager
from profile_store import ProfileStore
from steam_service import SteamService

logger = logging.getLogger("Server")

store = ProfileStore()

# Per-profile persistent MCP manager pool — subprocess is reused across
# requests and only restarted when credentials change.
_profile_mcp_managers: dict[str, PersistentMCPClientManager] = {}


async def get_or_create_mcp_client(profile_id: str) -> PersistentMCPClientManager | None:
    """Return a cached MCP manager for *profile_id*, or create one if the
    profile has Steam credentials configured."""
    profile = store.get_profile(profile_id)
    steam = profile.get("steam", {})
    api_key = steam.get("apiKey", "")
    steam_id = steam.get("steamId", "")
    has_creds = bool(api_key and steam_id)

    logger.info(
        "MCP check for %s — apiKey=%s steamId=%s has_creds=%s",
        profile_id,
        "***" if api_key else "(empty)",
        steam_id or "(empty)",
        has_creds,
    )
    # Fail-safe print — ensures visibility even if logging is misconfigured.
    print(
        f"[MCP] check profile={profile_id} has_creds={has_creds} "
        f"apiKey={'***' if api_key else 'missing'} "
        f"steamId={steam_id or 'missing'}",
        flush=True,
    )

    # Invalidate cached manager if it exists for a profile that no longer has creds
    if not has_creds:
        old = _profile_mcp_managers.pop(profile_id, None)
        if old is not None:
            logger.info("Removing MCP client for %s (credentials removed)", profile_id)
            await old.stop()
        logger.info("MCP skipped for %s — missing Steam credentials", profile_id)
        print(f"[MCP] skipped profile={profile_id} — missing Steam credentials", flush=True)
        return None

    manager = _profile_mcp_managers.get(profile_id)
    if manager is not None:
        return manager

    logger.info("Starting MCP client for profile %s...", profile_id)
    manager = PersistentMCPClientManager(profile)
    try:
        tools = await manager.start()
        tool_names = [getattr(t, "name", str(t)) for t in tools]
        logger.info(
            "MCP client ready for %s — %d tools: %s",
            profile_id,
            len(tools),
            ", ".join(tool_names) if tool_names else "(none)",
        )
    except Exception:
        logger.warning("Failed to start MCP client for profile %s", profile_id, exc_info=True)
        return None

    _profile_mcp_managers[profile_id] = manager
    return manager


async def invalidate_mcp_client(profile_id: str) -> None:
    """Stop and remove the cached MCP manager for *profile_id*."""
    manager = _profile_mcp_managers.pop(profile_id, None)
    if manager is not None:
        await manager.stop()


async def stop_all_mcp_clients() -> None:
    """Stop all cached MCP managers (called on app shutdown)."""
    for profile_id in list(_profile_mcp_managers.keys()):
        manager = _profile_mcp_managers.pop(profile_id)
        await manager.stop()


@asynccontextmanager
async def app_lifespan(_app: FastAPI):
    """FastAPI lifespan — cleanup async resources on shutdown."""
    yield
    await stop_all_mcp_clients()
    await close_async_client()


app = FastAPI(lifespan=app_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateProfileRequest(BaseModel):
    displayName: str = Field(..., min_length=1, max_length=60)


class ProfileConfigRequest(BaseModel):
    ai: dict[str, Any] | None = None
    steam: dict[str, Any] | None = None


class ChatRequest(BaseModel):
    profileId: str
    question: str
    k: int = 3


def resolve_profile(profile_id: str) -> dict[str, Any]:
    try:
        return store.get_profile(profile_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def build_agent(profile_id: str, mcp_client=None) -> Agent:
    profile = resolve_profile(profile_id)
    return Agent(
        profile_id,
        storage_path=history_path,
        vector_root=vector_path,
        settings=profile,
        mcp_client=mcp_client,
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/")
async def root() -> dict[str, Any]:
    return {"message": "server running", "profiles": len(store.list_profiles())}


@app.get("/mcp/status")
async def mcp_status() -> dict[str, Any]:
    """Diagnostic endpoint — shows MCP state for all profiles."""
    result: dict[str, Any] = {}
    for pid in (p["id"] for p in store.list_profiles()):
        profile = store.get_profile(pid)
        steam = profile.get("steam", {})
        has_creds = bool(steam.get("apiKey") and steam.get("steamId"))
        manager = _profile_mcp_managers.get(pid)
        result[pid] = {
            "hasSteamCreds": has_creds,
            "mcpRunning": manager is not None and manager.is_running,
            "mcpCached": manager is not None,
        }
    return {"profiles": result}


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


@app.get("/profiles")
async def list_profiles() -> dict[str, Any]:
    return {"profiles": store.list_profiles()}


@app.post("/profiles")
async def create_profile(req: CreateProfileRequest) -> dict[str, Any]:
    try:
        profile = store.create_profile(req.displayName)
        return {"profile": profile}
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/profiles/{profile_id}")
async def get_profile(profile_id: str) -> dict[str, Any]:
    return {"profile": resolve_profile(profile_id)}


@app.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str) -> dict[str, Any]:
    resolve_profile(profile_id)
    store.delete_profile(profile_id)
    await invalidate_mcp_client(profile_id)
    return {"deleted": True, "profileId": profile_id}


@app.patch("/profiles/{profile_id}/config")
async def update_profile_config(profile_id: str, req: ProfileConfigRequest) -> dict[str, Any]:
    resolve_profile(profile_id)
    try:
        profile = store.update_profile_config(profile_id, ai=req.ai, steam=req.steam)
        # Credentials may have changed — invalidate cached MCP so next request
        # spawns a fresh subprocess with the new config.
        await invalidate_mcp_client(profile_id)
        return {"profile": profile}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


@app.get("/profiles/{profile_id}/messages")
async def get_profile_messages(profile_id: str) -> dict[str, Any]:
    resolve_profile(profile_id)
    return {"messages": store.load_messages(profile_id)}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


@app.post("/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="消息不能为空。")

    mcp_client = await get_or_create_mcp_client(req.profileId)
    agent = build_agent(req.profileId, mcp_client=mcp_client)

    try:
        answer = await agent.chat(question=req.question.strip(), k=req.k)
        return {
            "answer": answer,
            "messages": store.load_messages(req.profileId),
        }
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="消息不能为空。")

    mcp_client = await get_or_create_mcp_client(req.profileId)
    agent = build_agent(req.profileId, mcp_client=mcp_client)

    async def event_generator():
        try:
            # chat_stream handles both MCP and non-MCP paths
            # using fully async I/O — never blocks the event loop.
            async for event in agent.chat_stream(question=req.question.strip(), k=req.k):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except RuntimeError as exc:
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Steam
# ---------------------------------------------------------------------------


@app.get("/profiles/{profile_id}/steam/overview")
async def get_steam_overview(profile_id: str) -> dict[str, Any]:
    profile = resolve_profile(profile_id)
    service = SteamService(profile)
    return await service.async_get_overview()


@app.get("/profiles/{profile_id}/steam/deals")
async def get_steam_deals(profile_id: str) -> dict[str, Any]:
    profile = resolve_profile(profile_id)
    service = SteamService(profile)
    return await service.async_get_deals()


# ---------------------------------------------------------------------------
# Knowledge
# ---------------------------------------------------------------------------


@app.get("/profiles/{profile_id}/knowledge")
async def get_knowledge(profile_id: str) -> dict[str, Any]:
    resolve_profile(profile_id)
    return store.list_knowledge_files(profile_id)


@app.post("/profiles/{profile_id}/knowledge")
async def upload_knowledge(profile_id: str, file: UploadFile):
    resolve_profile(profile_id)

    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="仅支持上传 .json 文件。")

    content = await file.read()
    try:
        json.loads(content.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="文件内容不是有效的 JSON。")

    filename = file.filename
    target = store.save_knowledge_file(profile_id, filename, content)

    agent = build_agent(profile_id)
    knowledge_text = target.read_text(encoding="utf-8")
    result = agent.add_knowledge(knowledge_text, filename, profile_id=profile_id)

    return {"uploaded": True, "filename": filename, "message": result}


@app.delete("/profiles/{profile_id}/knowledge/{filename}")
async def delete_knowledge(profile_id: str, filename: str) -> dict[str, Any]:
    resolve_profile(profile_id)
    try:
        store.delete_knowledge_file(profile_id, filename)
        return {"deleted": True, "filename": filename}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
