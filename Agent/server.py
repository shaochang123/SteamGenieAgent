import json
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from Agent import Agent
from config import history_path, vector_path
from mcp_client import MCPClientManager
from profile_store import ProfileStore
from steam_service import SteamService


store = ProfileStore()

app = FastAPI()

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


@app.get("/")
def root() -> dict[str, Any]:
    return {"message": "server running", "profiles": len(store.list_profiles())}


@app.get("/profiles")
def list_profiles() -> dict[str, Any]:
    return {"profiles": store.list_profiles()}


@app.post("/profiles")
def create_profile(req: CreateProfileRequest) -> dict[str, Any]:
    try:
        profile = store.create_profile(req.displayName)
        return {"profile": profile}
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/profiles/{profile_id}")
def get_profile(profile_id: str) -> dict[str, Any]:
    return {"profile": resolve_profile(profile_id)}


@app.delete("/profiles/{profile_id}")
def delete_profile(profile_id: str) -> dict[str, Any]:
    resolve_profile(profile_id)
    store.delete_profile(profile_id)
    return {"deleted": True, "profileId": profile_id}


@app.patch("/profiles/{profile_id}/config")
def update_profile_config(profile_id: str, req: ProfileConfigRequest) -> dict[str, Any]:
    resolve_profile(profile_id)
    try:
        profile = store.update_profile_config(profile_id, ai=req.ai, steam=req.steam)
        return {"profile": profile}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/profiles/{profile_id}/messages")
def get_profile_messages(profile_id: str) -> dict[str, Any]:
    resolve_profile(profile_id)
    return {"messages": store.load_messages(profile_id)}


@app.post("/chat")
def chat(req: ChatRequest) -> dict[str, Any]:
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="消息不能为空。")

    agent = build_agent(req.profileId)
    try:
        answer = agent.Call(question=req.question.strip(), k=req.k)
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

    profile = resolve_profile(req.profileId)
    steam = profile.get("steam", {})
    has_steam_creds = bool(steam.get("apiKey") and steam.get("steamId"))

    mcp_client = None
    if has_steam_creds:
        try:
            mcp_client = MCPClientManager(profile)
            await mcp_client.start()
        except Exception:
            mcp_client = None

    agent = build_agent(req.profileId, mcp_client=mcp_client)

    async def event_generator():
        try:
            if mcp_client is not None:
                for event in agent.Call_stream_with_tools(question=req.question.strip(), k=req.k):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            else:
                for event in agent.Call_stream(question=req.question.strip(), k=req.k):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except RuntimeError as exc:
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)}, ensure_ascii=False)}\n\n"
        finally:
            if mcp_client is not None:
                await mcp_client.stop()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/profiles/{profile_id}/steam/overview")
def get_steam_overview(profile_id: str) -> dict[str, Any]:
    profile = resolve_profile(profile_id)
    return SteamService(profile).get_overview()


@app.get("/profiles/{profile_id}/steam/deals")
def get_steam_deals(profile_id: str) -> dict[str, Any]:
    profile = resolve_profile(profile_id)
    return SteamService(profile).get_deals()


@app.get("/profiles/{profile_id}/knowledge")
def get_knowledge(profile_id: str) -> dict[str, Any]:
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
    result = agent.addKnowledge(knowledge_text, filename, profile_id=profile_id)

    return {"uploaded": True, "filename": filename, "message": result}


@app.delete("/profiles/{profile_id}/knowledge/{filename}")
def delete_knowledge(profile_id: str, filename: str) -> dict[str, Any]:
    resolve_profile(profile_id)
    try:
        store.delete_knowledge_file(profile_id, filename)
        return {"deleted": True, "filename": filename}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
