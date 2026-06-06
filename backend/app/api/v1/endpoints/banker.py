"""Banker intake endpoints for customer CSV import and manual onboarding."""

from __future__ import annotations

import asyncio
import csv
import io
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import AsyncSessionLocal, get_db
from backend.app.core.security import get_password_hash, require_roles
from backend.app.models.all_models import CustomerIntakeRecord, User, UserRole
from backend.app.repositories.user_repository import UserRepository
from backend.app.services.notification_service import (
    customer_invite_message,
    queue_and_send_email,
)
from llm.llm_service import LLMService
from llm.prompt_manager import PromptManager
from llm.response_parser import ResponseParser

router = APIRouter(prefix="/banker", tags=["banker"])

DEFAULT_CUSTOMER_PASSWORD = "852456"
DEFAULT_CUSTOMER_PASSWORD_HASH = get_password_hash(DEFAULT_CUSTOMER_PASSWORD)

llm = LLMService()
pm = PromptManager()
rp = ResponseParser()

_FIELD_ALIASES = {
    "name": ("name", "customer_name", "full_name", "customername"),
    "email": ("email", "customer_email", "email_id", "customeremail"),
    "phone": (
        "phone",
        "phone_number",
        "customer_phone",
        "contact_number",
        "mobile",
        "mobile_number",
    ),
    "date_of_birth": ("date_of_birth", "dob", "birth_date", "dateofbirth"),
    "annual_income": ("annual_income", "income", "yearly_income"),
    "dependents": ("dependents", "dependent_count"),
    "risk_appetite": ("risk_appetite", "risk", "risk_tolerance"),
    "kyc_status": ("kyc_status", "kyc"),
    "financial_goals": ("financial_goals", "financial_goal", "goals"),
    "notes": ("notes", "remark", "remarks"),
}


def _normalize_row_keys(data: Optional[dict]) -> dict:
    if not isinstance(data, dict):
        return {}
    normalized = {}
    for key, value in data.items():
        if key is None:
            continue
        key_norm = str(key).strip().lower().replace("-", "_").replace(" ", "_")
        normalized[key_norm] = value
    return normalized


def _first_value(*sources: dict, aliases: tuple[str, ...] = ()):
    for source in sources:
        for key in aliases:
            value = source.get(key)
            if value not in (None, "", []):
                return value
    return None


class ManualCustomerRequest(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    annual_income: Optional[float] = None
    dependents: Optional[int] = None
    risk_appetite: Optional[str] = None
    kyc_status: Optional[str] = None
    financial_goals: Optional[list[str]] = None
    notes: Optional[str] = None


def _canonical_payload(raw: dict, normalized: Optional[dict] = None) -> dict:
    raw_data = _normalize_row_keys(raw)
    merged = _normalize_row_keys(normalized)
    financial_goals = (
        _first_value(merged, raw_data, aliases=_FIELD_ALIASES["financial_goals"]) or []
    )
    if isinstance(financial_goals, str):
        financial_goals = [x.strip() for x in financial_goals.split(";") if x.strip()]
    return {
        "name": _first_value(merged, raw_data, aliases=_FIELD_ALIASES["name"]),
        "email": (
            (_first_value(merged, raw_data, aliases=_FIELD_ALIASES["email"]) or "")
            .strip()
            .lower()
        ),
        "phone": _first_value(merged, raw_data, aliases=_FIELD_ALIASES["phone"]),
        "date_of_birth": _first_value(
            merged, raw_data, aliases=_FIELD_ALIASES["date_of_birth"]
        ),
        "annual_income": _first_value(
            merged, raw_data, aliases=_FIELD_ALIASES["annual_income"]
        ),
        "dependents": _first_value(
            merged, raw_data, aliases=_FIELD_ALIASES["dependents"]
        ),
        "risk_appetite": _first_value(
            merged, raw_data, aliases=_FIELD_ALIASES["risk_appetite"]
        ),
        "kyc_status": _first_value(
            merged, raw_data, aliases=_FIELD_ALIASES["kyc_status"]
        ),
        "financial_goals": financial_goals,
        "notes": _first_value(merged, raw_data, aliases=_FIELD_ALIASES["notes"]),
    }


def _heuristic_normalize(raw_row: dict) -> dict:
    payload = _canonical_payload(raw_row)
    return {k: v for k, v in payload.items() if v not in (None, "", [])}


async def _normalize_with_llm(raw_row: dict) -> dict:
    try:
        result = await asyncio.wait_for(
            llm.complete(pm.customer_intake_normalization(raw_row)),
            timeout=5,
        )
        parsed = rp.parse_json(result["response"])
        if isinstance(parsed, dict) and not parsed.get("parse_error"):
            return parsed
    except Exception:
        pass
    return _heuristic_normalize(raw_row)


def _normalize_fast(raw_row: dict) -> dict:
    return _heuristic_normalize(raw_row)


async def _create_or_update_customer(
    db: AsyncSession,
    banker: User,
    raw_payload: dict,
    normalized_payload: Optional[dict] = None,
    *,
    source_type: str,
    source_filename: Optional[str] = None,
    persist: bool = True,
    send_notifications: bool = True,
    banker_email: Optional[str] = None,
    banker_id: Optional[str] = None,
    existing_user: Optional[User] = None,
) -> dict:
    payload = _canonical_payload(raw_payload, normalized_payload)
    if not payload["name"] or not payload["email"]:
        raise HTTPException(
            status_code=400, detail="Each customer row needs at least name and email"
        )

    banker_email = banker_email or str(banker.email)
    banker_id = banker_id or str(banker.id)
    
    if existing_user is not None:
        existing = existing_user
    else:
        repo = UserRepository(db)
        existing = await repo.get_by_email(payload["email"])
        
    temp_password = DEFAULT_CUSTOMER_PASSWORD
    temp_password_hash = DEFAULT_CUSTOMER_PASSWORD_HASH
    if existing:
        customer = existing
        customer.name = payload["name"] or customer.name
        customer.phone = payload["phone"] or customer.phone
        customer.password_hash = temp_password_hash
        customer.must_change_password = 1
        if customer.role != UserRole.CUSTOMER:
            customer.role = UserRole.CUSTOMER
    else:
        customer = User(
            id=str(uuid.uuid4()),
            name=payload["name"],
            email=payload["email"],
            password_hash=temp_password_hash,
            must_change_password=1,
            role=UserRole.CUSTOMER,
            phone=payload["phone"],
        )
        db.add(customer)

    intake = CustomerIntakeRecord(
        id=str(uuid.uuid4()),
        banker_id=banker_id,
        user_id=str(customer.id),
        source_type=source_type,
        source_filename=source_filename,
        raw_payload=raw_payload,
        normalized_payload=payload,
        status="ACTIVE",
        notes=payload.get("notes"),
    )
    db.add(intake)

    if persist:
        await db.commit()
        await db.refresh(customer)
        await db.refresh(intake)
        if send_notifications:
            subject, body = customer_invite_message(
                customer.name, customer.email, customer.id, temp_password
            )
            await queue_and_send_email(
                db,
                customer.email,
                subject,
                body,
                recipient_id=customer.id,
                reference_type="CUSTOMER_INTAKE",
                reference_id=intake.id,
            )

            banker_subject = f"Customer intake recorded for {customer.name}"
            banker_body = f"<p>Customer <strong>{customer.name}</strong> ({customer.email}) was added via {source_type}.</p>"
            await queue_and_send_email(
                db,
                banker_email,
                banker_subject,
                banker_body,
                recipient_id=banker_id,
                reference_id=intake.id,
            )
    else:
        # Avoid row-by-row database flushes during CSV import
        pass

    return {
        "user_id": customer.id,
        "intake_id": intake.id,
        "name": customer.name,
        "email": customer.email,
        "phone": customer.phone,
        "source_type": intake.source_type,
        "temporary_password": temp_password,
        "banker_email": banker_email,
        "banker_id": banker_id,
    }


async def _process_csv_import(
    file_bytes: bytes,
    filename: str,
    banker_id: str,
    request: Request | None = None,
) -> dict:
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return {"processed": 0, "imported": 0, "failed": 0, "errors": []}

    async with AsyncSessionLocal() as db:
        banker_repo = UserRepository(db)
        banker = await banker_repo.get_by_id(banker_id)
        if not banker:
            return {
                "processed": len(rows),
                "imported": 0,
                "failed": len(rows),
                "errors": ["banker_not_found"],
            }

        banker_id_value = str(banker.id)
        banker_email = str(banker.email)

        # Clear the read transaction opened by the banker lookup before starting the batch write.
        await db.rollback()

        imported = 0
        failed = 0
        errors: list[str] = []
        pending_notifications: list[dict] = []

        async with db.begin():
            # Batch lookup users by email to prevent N+1 queries
            emails = []
            for row in rows:
                normalized = _normalize_fast(row)
                email = normalized.get("email")
                if email:
                    emails.append(email.strip().lower())
            
            existing_users = {}
            if emails:
                result = await db.execute(select(User).where(User.email.in_(emails)))
                for u in result.scalars().all():
                    existing_users[u.email] = u

            for row in rows:
                normalized = _normalize_fast(row)
                email = normalized.get("email")
                existing_user = existing_users.get(email) if email else None
                try:
                    result = await _create_or_update_customer(
                        db,
                        banker,
                        row,
                        normalized_payload=normalized,
                        source_type="CSV",
                        source_filename=filename,
                        persist=False,
                        send_notifications=False,
                        banker_email=banker_email,
                        banker_id=banker_id_value,
                        existing_user=existing_user,
                    )
                    pending_notifications.append(result)
                    imported += 1
                except Exception as exc:
                    failed += 1
                    if len(errors) < 10:
                        errors.append(f"{type(exc).__name__}: {exc}")
            
            # Flush batch to db once
            await db.flush()

        notifications_to_queue = []
        for result in pending_notifications:
            subject, body = customer_invite_message(
                result["name"],
                result["email"],
                result["user_id"],
                result["temporary_password"],
            )
            notifications_to_queue.append({
                "recipient_id": result["user_id"],
                "recipient_email": result["email"],
                "subject": subject,
                "body": body,
                "reference_type": "CUSTOMER_INTAKE",
                "reference_id": result["intake_id"],
            })

            banker_subject = f"Customer intake recorded for {result['name']}"
            banker_body = (
                f"<p>Customer <strong>{result['name']}</strong> ({result['email']}) "
                f"was added via CSV.</p>"
            )
            notifications_to_queue.append({
                "recipient_id": result["banker_id"],
                "recipient_email": result["banker_email"],
                "subject": banker_subject,
                "body": banker_body,
                "reference_type": "CUSTOMER_INTAKE",
                "reference_id": result["intake_id"],
            })

        if notifications_to_queue:
            from backend.app.services.notification_service import queue_and_send_email_batch
            await queue_and_send_email_batch(db, notifications_to_queue)

        return {
            "processed": len(rows),
            "imported": imported,
            "failed": failed,
            "errors": errors,
        }


@router.post("/customers/manual")
async def create_customer_manual(
    body: ManualCustomerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("BANKER", "SUPER_ADMIN")),
):
    payload = body.model_dump()
    payload["email"] = (payload.get("email") or "").strip().lower()
    return await _create_or_update_customer(
        db=db,
        banker=current_user,
        raw_payload=payload,
        source_type="MANUAL",
    )


@router.post("/customers/import")
async def import_customers_csv(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(require_roles("BANKER", "SUPER_ADMIN")),
):
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise HTTPException(status_code=400, detail="CSV file is empty")

    result = await _process_csv_import(
        content,
        file.filename or "customers.csv",
        str(current_user.id),
        request=request,
    )

    return {
        "message": "Customer import completed",
        "processed": result.get("processed", len(rows)),
        "imported": result.get("imported", 0),
        "failed": result.get("failed", 0),
        "status": "COMPLETED",
        "errors": result.get("errors", []),
    }


@router.post("/customers/import/preview")
async def import_customers_preview(
    file: UploadFile = File(...),
    current_user: User = Depends(require_roles("BANKER", "SUPER_ADMIN")),
):
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise HTTPException(status_code=400, detail="CSV file is empty")

    preview = []
    for row in rows:
        normalized = await _normalize_with_llm(row)
        payload = _canonical_payload(row, normalized)
        preview.append({"raw": row, "normalized": payload})

    return {"preview": preview, "count": len(preview)}


@router.get("/customers")
async def list_customers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("BANKER", "SUPER_ADMIN")),
    q: Optional[str] = None,
):
    from sqlalchemy.orm import selectinload
    q_stmt = select(CustomerIntakeRecord).options(selectinload(CustomerIntakeRecord.customer)).order_by(
        CustomerIntakeRecord.created_at.desc()
    )
    if current_user.role != UserRole.SUPER_ADMIN:
        q_stmt = q_stmt.where(CustomerIntakeRecord.banker_id == str(current_user.id))
    if q:
        search = f"%{q.strip()}%"
        q_stmt = q_stmt.join(CustomerIntakeRecord.customer).where(
            (User.name.ilike(search))
            | (User.email.ilike(search))
            | (User.phone.ilike(search))
        )

    result = await db.execute(q_stmt)
    items = []
    for intake in result.scalars().all():
        user = intake.customer
        if not user:
            continue
        items.append(
            {
                "intake_id": intake.id,
                "user_id": user.id,
                "name": user.name,
                "email": user.email,
                "phone": user.phone,
                "role": user.role.value if hasattr(user.role, "value") else user.role,
                "source_type": intake.source_type,
                "status": intake.status,
                "source_filename": intake.source_filename,
                "raw_payload": intake.raw_payload,
                "normalized_payload": intake.normalized_payload,
                "created_at": (
                    intake.created_at.isoformat() if intake.created_at else None
                ),
            }
        )
    return {"customers": items}
