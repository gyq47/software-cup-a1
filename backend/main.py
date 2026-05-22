from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.chat import router as chat_router
from backend.api.health import router as health_router
from backend.api.manual import router as manual_router
from backend.api.search import router as search_router
from backend.core.config import API_PREFIX, PROJECT_NAME

app = FastAPI(title=PROJECT_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=API_PREFIX)
app.include_router(manual_router, prefix=API_PREFIX)
app.include_router(search_router, prefix=API_PREFIX)
app.include_router(chat_router, prefix=API_PREFIX)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "Software Cup A1 Backend Running",
        "project": "设备检修知识检索与作业系统",
    }
