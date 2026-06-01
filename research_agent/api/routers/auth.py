"""认证 API 路由 —— 注册、登录、获取用户信息。"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, EmailStr
import bcrypt

from db.database import DatabaseManager, get_db
from db.repositories.user_repo import UserRepo
from middleware.auth import create_token
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    user_id: str
    email: str
    display_name: str
    plan_type: str
    token: str


class UserInfoResponse(BaseModel):
    user_id: str
    email: str
    display_name: str
    plan_type: str
    plan_expires_at: str | None
    created_at: str | None


@router.post("/register", response_model=AuthResponse)
def register(req: RegisterRequest):
    """注册新用户。"""
    db = DatabaseManager.get_instance()
    session = db.get_session()
    try:
        repo = UserRepo(session)

        # 检查邮箱是否已注册
        existing = repo.get_by_email(req.email)
        if existing:
            raise HTTPException(status_code=409, detail="该邮箱已注册")

        # 加密密码
        hashed = bcrypt.hashpw(req.password.encode("utf-8"), bcrypt.gensalt())

        user = repo.create(
            email=req.email,
            hashed_password=hashed.decode("utf-8"),
            display_name=req.display_name,
        )

        token = create_token(user.id, user.plan_type)

        return AuthResponse(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            plan_type=user.plan_type,
            token=token,
        )
    finally:
        session.close()


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest):
    """用户登录。"""
    db = DatabaseManager.get_instance()
    session = db.get_session()
    try:
        repo = UserRepo(session)
        user = repo.get_by_email(req.email)

        if not user:
            raise HTTPException(status_code=401, detail="邮箱或密码错误")

        if not bcrypt.checkpw(req.password.encode("utf-8"), user.hashed_password.encode("utf-8")):
            raise HTTPException(status_code=401, detail="邮箱或密码错误")

        if not user.is_active:
            raise HTTPException(status_code=403, detail="账户已被禁用")

        token = create_token(user.id, user.plan_type)

        return AuthResponse(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            plan_type=user.plan_type,
            token=token,
        )
    finally:
        session.close()


@router.get("/me", response_model=UserInfoResponse)
def get_me(request: Request):
    """获取当前用户信息。"""
    user_id = getattr(request.state, "user_id", "default_user")

    if user_id == "default_user":
        return UserInfoResponse(
            user_id="default_user",
            email="default@example.com",
            display_name="访客",
            plan_type="free",
            plan_expires_at=None,
            created_at=None,
        )

    db = DatabaseManager.get_instance()
    session = db.get_session()
    try:
        repo = UserRepo(session)
        user = repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")

        return UserInfoResponse(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            plan_type=user.plan_type,
            plan_expires_at=user.plan_expires_at.isoformat() if user.plan_expires_at else None,
            created_at=user.created_at.isoformat() if user.created_at else None,
        )
    finally:
        session.close()
