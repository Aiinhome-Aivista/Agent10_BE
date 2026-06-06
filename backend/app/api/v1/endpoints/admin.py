"""admin.py"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from backend.app.core.database import get_db
from backend.app.core.security import require_roles, get_password_hash
from backend.app.models.all_models import User, UserRole, AuditLog, EscalationLog

router = APIRouter(prefix="/admin", tags=["admin"])


class CreateUserBody(BaseModel):
    name: str; email: EmailStr; password: str; role: str; phone: Optional[str] = None


@router.get("/stats")
async def platform_stats(db: AsyncSession = Depends(get_db),
                          current_user=Depends(require_roles("SUPER_ADMIN"))):
    from backend.app.models.all_models import Case
    cases_r = await db.execute(select(Case))
    cases   = cases_r.scalars().all()
    users_r = await db.execute(select(User))
    users   = users_r.scalars().all()
    esc_r   = await db.execute(select(EscalationLog).where(EscalationLog.resolved == 0))
    escalations = esc_r.scalars().all()
    return {
        "total_users": len(users),
        "total_cases": len(cases),
        "active_cases": sum(1 for c in cases if str(c.status).endswith("ACTIVE")),
        "completed_cases": sum(1 for c in cases if str(c.status).endswith("COMPLETED")),
        "open_escalations": len(escalations),
    }


@router.get("/users")
async def list_users(db: AsyncSession = Depends(get_db),
                      current_user=Depends(require_roles("SUPER_ADMIN"))):
    r = await db.execute(select(User).order_by(User.created_at.desc()))
    return {"users": [{"id": u.id, "name": u.name, "email": u.email,
                        "role": u.role.value if hasattr(u.role, 'value') else u.role,
                        "is_active": bool(u.is_active),
                        "created_at": u.created_at.isoformat() if u.created_at else None}
                       for u in r.scalars().all()]}


@router.post("/users")
async def create_user(body: CreateUserBody, db: AsyncSession = Depends(get_db),
                       current_user=Depends(require_roles("SUPER_ADMIN"))):
    r = await db.execute(select(User).where(User.email == body.email))
    if r.scalar_one_or_none():
        raise HTTPException(409, "Email already registered")
    user = User(id=str(uuid.uuid4()), name=body.name, email=body.email,
                password_hash=get_password_hash(body.password), role=body.role, phone=body.phone)
    db.add(user); await db.commit()
    return {"message": "User created", "user_id": user.id}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, db: AsyncSession = Depends(get_db),
                       current_user=Depends(require_roles("SUPER_ADMIN"))):
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
    return {"message": "User deleted"}


@router.patch("/users/{user_id}/toggle-active")
async def toggle_user(user_id: str, db: AsyncSession = Depends(get_db),
                       current_user=Depends(require_roles("SUPER_ADMIN"))):
    r = await db.execute(select(User).where(User.id == user_id))
    u = r.scalar_one_or_none()
    if not u: raise HTTPException(404, "User not found")
    await db.execute(update(User).where(User.id == user_id).values(is_active=0 if u.is_active else 1))
    await db.commit()
    return {"message": "Toggled"}


@router.get("/audit-logs")
async def audit_logs(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db),
                      current_user=Depends(require_roles("SUPER_ADMIN", "COMPLIANCE"))):
    r = await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).offset(skip).limit(limit))
    logs = r.scalars().all()
    return {"logs": [{"id": l.id, "case_id": l.case_id, "user_id": l.user_id,
                       "action": l.action, "entity_type": l.entity_type,
                       "ip_address": l.ip_address,
                       "created_at": l.created_at.isoformat() if l.created_at else None} for l in logs]}


@router.get("/escalations")
async def get_escalations(db: AsyncSession = Depends(get_db),
                           current_user=Depends(require_roles("SUPER_ADMIN", "OPS_ADMIN"))):
    r = await db.execute(select(EscalationLog).where(EscalationLog.resolved == 0).order_by(EscalationLog.created_at.desc()))
    escs = r.scalars().all()
    return {"escalations": [{"id": e.id, "case_id": e.case_id, "level": e.escalation_level,
                              "stage": e.stage, "reason": e.reason,
                              "assigned_to_role": e.assigned_to_role,
                              "created_at": e.created_at.isoformat() if e.created_at else None} for e in escs]}
