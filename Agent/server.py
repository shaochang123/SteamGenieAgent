from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from Agent import Agent
from config import (
    user,
    history_path,
    vector_path
)

# =========================
# 初始化 Agent
# =========================

SteamAgent = Agent(
    user,
    history_path,
    vector_path
)

# =========================
# FastAPI
# =========================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# 请求体
# =========================

class ChatRequest(BaseModel):
    question: str
    k: int = 3


# =========================
# 返回体
# =========================

class ChatResponse(BaseModel):
    answer: str


# =========================
# 聊天接口
# =========================

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):

    answer = SteamAgent.Call(
        question=req.question,
        k=req.k
    )

    return ChatResponse(
        answer=answer
    )

@app.get("/")
def root():
    return {"message":"server running"}

# =========================
# 启动
# =========================

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000
    )