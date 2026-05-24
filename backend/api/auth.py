from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])

DEMO_USERS = {
    "worker": {
        "password": "123456",
        "role": "worker",
        "display_name": "检修人员",
    },
    "expert": {
        "password": "123456",
        "role": "expert",
        "display_name": "专家",
    },
    "admin": {
        "password": "123456",
        "role": "admin",
        "display_name": "管理员",
    },
}


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(request: LoginRequest) -> dict[str, Any]:
    user = DEMO_USERS.get(request.username)
    if not user or user["password"] != request.password:
        return {
            "success": False,
            "message": "用户名或密码错误",
        }

    return {
        "success": True,
        "token": f"fake-token-{request.username}",
        "role": user["role"],
        "username": request.username,
        "display_name": user["display_name"],
    }


@router.post("/logout")
def logout() -> dict[str, bool]:
    return {"success": True}


@router.get("/me")
def me() -> dict[str, Any]:
    return {
        "success": True,
        "message": "演示系统使用前端 localStorage 保存当前用户状态",
    }
