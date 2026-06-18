import uuid
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from backend.app.core.database import get_db
from backend.app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
)
from backend.app.repositories.user_repository import UserRepository

router = APIRouter(prefix="/auth", tags=["auth"])
DEFAULT_CSV_CUSTOMER_PASSWORD = "852456"


class LoginRequest(BaseModel):
    email: str  # Can be email or phone number
    password: str


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str
    phone: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    repo = UserRepository(db)
    input_str = body.email.strip()
    try:
        user = await asyncio.wait_for(
            repo.get_by_email(input_str.lower()), timeout=8
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Authentication service timed out while checking user",
        )
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Authentication service unavailable (database issue)",
        )

    if not user:
        # Fallback: check if it's a phone number
        try:
            user = await asyncio.wait_for(
                repo.get_by_phone(input_str), timeout=8
            )
        except Exception:
            pass

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(body.password, user.password_hash):
        role_value = user.role.value if hasattr(user.role, "value") else user.role
        # Self-heal legacy CSV imports where CUSTOMER temporary password hash drifted.
        if (
            role_value == "CUSTOMER"
            and int(getattr(user, "must_change_password", 0) or 0) == 1
            and body.password == DEFAULT_CSV_CUSTOMER_PASSWORD
        ):
            await db.execute(
                text(
                    "UPDATE users SET password_hash = :ph, must_change_password = 1 WHERE id = :uid"
                ),
                {
                    "ph": get_password_hash(DEFAULT_CSV_CUSTOMER_PASSWORD),
                    "uid": user.id,
                },
            )
            await db.commit()
            await db.refresh(user)
        else:
            raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account inactive")
    payload = {
        "sub": user.id,
        "role": user.role.value if hasattr(user.role, "value") else user.role,
    }
    return {
        "access_token": create_access_token(payload),
        "refresh_token": create_refresh_token(payload),
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role.value if hasattr(user.role, "value") else user.role,
            "must_change_password": getattr(user, "must_change_password", 0),
        },
    }


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = UserRepository(db)
    user = await repo.get_by_id(current_user.id)
    if not user or not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid current password")

    await db.execute(
        text(
            "UPDATE users SET password_hash = :ph, must_change_password = 0 WHERE id = :uid"
        ),
        {"ph": get_password_hash(body.new_password), "uid": user.id},
    )
    await db.commit()
    return {"message": "Password updated"}


@router.post("/register")
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    repo = UserRepository(db)
    email = body.email.strip().lower()
    try:
        existing = await asyncio.wait_for(repo.get_by_email(email), timeout=8)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Registration service timed out while checking user",
        )
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Registration service unavailable (database issue)",
        )

    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    try:
        user = await asyncio.wait_for(
            repo.create_user(
                {
                    "id": str(uuid.uuid4()),
                    "name": body.name,
                    "email": email,
                    "password_hash": get_password_hash(body.password),
                    "role": body.role,
                    "phone": body.phone,
                }
            ),
            timeout=8,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Registration service timed out while creating user",
        )
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Registration service unavailable while creating user",
        )

    return {"message": "Registered successfully", "user_id": user.id}


@router.post("/refresh")
async def refresh(body: RefreshRequest):
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    new_payload = {"sub": payload["sub"], "role": payload["role"]}
    return {
        "access_token": create_access_token(new_payload),
        "refresh_token": create_refresh_token(new_payload),
        "token_type": "bearer",
    }


@router.post("/logout")
async def logout():
    # Stateless JWT — client drops the token
    return {"message": "Logged out"}
