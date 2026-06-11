from typing import TYPE_CHECKING, Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from Agent.Agent import Agent
else:
    from Agent import Agent
from config import history_path, vector_path
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


def build_agent(profile_id: str) -> Agent:
    profile = resolve_profile(profile_id)
    return Agent(
        profile_id,
        storage_path=history_path,
        vector_root=vector_path,
        settings=profile,
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


@app.get("/profiles/{profile_id}/steam/overview")
def get_steam_overview(profile_id: str) -> dict[str, Any]:
    profile = resolve_profile(profile_id)
    return SteamService(profile).get_overview()


@app.get("/profiles/{profile_id}/steam/deals")
def get_steam_deals(profile_id: str) -> dict[str, Any]:
    profile = resolve_profile(profile_id)
    return SteamService(profile).get_deals()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
