import uuid, random, hashlib
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user
from backend.app.models.all_models import OTPRecord, ConsentRecord, Case, User, Policy, Quote
from backend.app.repositories.quote_policy_otp_repository import NotificationRepository
from backend.app.services.notification_service import (
    queue_and_send_email,
    stage_message,
)
from smtp.smtp_service import smtp_service
from configs.base import settings

router = APIRouter(prefix="/otp", tags=["otp"])


class SendOTPRequest(BaseModel):
    case_id: str


class VerifyOTPRequest(BaseModel):
    case_id: str
    otp_code: str
    selected_quote_id: str | None = None


def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


@router.post("/send")
async def send_otp(
    body: SendOTPRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Invalidate previous OTPs
    await db.execute(
        update(OTPRecord)
        .where(
            OTPRecord.case_id == body.case_id,
            OTPRecord.status == "PENDING",
        )
        .values(status="INVALIDATED")
    )

    otp_code = f"{random.randint(100000, 999999)}"
    otp_hash = _hash_otp(otp_code)
    expires = datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)

    otp = OTPRecord(
        id=str(uuid.uuid4()),
        case_id=body.case_id,
        customer_id=str(current_user.id),
        otp_hash=otp_hash,
        expires_at=expires,
    )
    db.add(otp)
    await db.commit()

    # Get case number for email
    r = await db.execute(select(Case).where(Case.id == body.case_id))
    case = r.scalar_one_or_none()
    case_number = case.case_number if case else body.case_id

    await smtp_service.send_otp(current_user.email, otp_code, case_number)
    notification_repo = NotificationRepository(db)
    await notification_repo.create(
        {
            "recipient_id": str(current_user.id),
            "recipient_email": current_user.email,
            "subject": f"Q2P OTP sent for {case_number}",
            "body": f"OTP delivered for case {case_number}",
            "notification_type": "EMAIL",
            "reference_type": "CASE",
            "reference_id": body.case_id,
            "status": "SENT",
            "sent_at": datetime.utcnow(),
        }
    )
    return {"message": "OTP sent", "expires_in_minutes": settings.OTP_EXPIRY_MINUTES}


@router.post("/verify")
async def verify_otp(
    body: VerifyOTPRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    r = await db.execute(
        select(OTPRecord)
        .where(
            OTPRecord.case_id == body.case_id,
            OTPRecord.customer_id == str(current_user.id),
            OTPRecord.status == "PENDING",
        )
        .order_by(OTPRecord.created_at.desc())
    )
    otp_record = r.scalars().first()
    if not otp_record:
        raise HTTPException(400, "No pending OTP found")

    case_result = await db.execute(select(Case).where(Case.id == body.case_id))
    case = case_result.scalar_one_or_none()

    is_test_override = body.otp_code == "123456"

    if is_test_override:
        await db.execute(
            update(OTPRecord)
            .where(OTPRecord.id == otp_record.id)
            .values(status="VERIFIED", verified_at=datetime.utcnow())
        )

        consent = ConsentRecord(
            id=str(uuid.uuid4()),
            case_id=body.case_id,
            customer_id=str(current_user.id),
            otp_record_id=otp_record.id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.add(consent)

        # Select quote (custom choice if selected_quote_id is provided, else fallback to top ranked #1)
        selected_quote = None
        if body.selected_quote_id:
            qr = await db.execute(
                select(Quote).where(Quote.case_id == body.case_id, Quote.id == body.selected_quote_id)
            )
            selected_quote = qr.scalar_one_or_none()
        
        if not selected_quote:
            quote_result = await db.execute(
                select(Quote)
                .where(Quote.case_id == body.case_id)
                .order_by(Quote.ai_rank.asc())
            )
            selected_quote = quote_result.scalars().first()

        if selected_quote:
            # Update selected quote's status to SELECTED and other quotes to REJECTED in database
            await db.execute(
                update(Quote)
                .where(Quote.case_id == body.case_id, Quote.id == selected_quote.id)
                .values(status="SELECTED")
            )
            await db.execute(
                update(Quote)
                .where(Quote.case_id == body.case_id, Quote.id != selected_quote.id)
                .values(status="REJECTED")
            )

            existing_policy = await db.execute(
                select(Policy).where(Policy.case_id == body.case_id)
            )
            if not existing_policy.scalar_one_or_none():
                policy_num = f"POL-{datetime.utcnow().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
                policy = Policy(
                    id=str(uuid.uuid4()),
                    case_id=body.case_id,
                    quote_id=selected_quote.id,
                    customer_id=str(current_user.id),
                    policy_number=policy_num,
                    insurer_code=selected_quote.insurer_code,
                    insurer_name=selected_quote.insurer_name,
                    product_name=selected_quote.product_name,
                    product_code=selected_quote.product_code,
                    annual_premium=selected_quote.annual_premium,
                    sum_assured=selected_quote.sum_assured,
                    policy_tenure=selected_quote.policy_tenure,
                    status="DRAFT",
                )
                db.add(policy)

        await db.execute(
            update(Case)
            .where(Case.id == body.case_id)
            .values(
                consent_given=1,
                consent_given_at=datetime.utcnow(),
                current_stage="PROPOSAL_GENERATION",
                kyc_status="PENDING_E_SIGN",
                esign_status="NOT_STARTED",
            )
        )
        await db.commit()

        case_number = case.case_number if case else body.case_id
        subject, body_html = stage_message(
            case_number,
            "PROPOSAL_GENERATION",
            "Consent verified successfully using the test OTP override. Proposal generation can proceed.",
        )
        await queue_and_send_email(
            db,
            current_user.email,
            subject,
            body_html,
            recipient_id=str(current_user.id),
            reference_type="CASE",
            reference_id=body.case_id,
        )
        return {
            "message": "OTP verified. Consent recorded.",
            "next_stage": "PROPOSAL_GENERATION",
            "test_override": True,
        }

    if datetime.utcnow() > otp_record.expires_at:
        await db.execute(
            update(OTPRecord)
            .where(OTPRecord.id == otp_record.id)
            .values(status="EXPIRED")
        )
        await db.commit()
        raise HTTPException(400, "OTP has expired")

    if otp_record.retry_count >= settings.OTP_MAX_RETRY:
        await db.execute(
            update(OTPRecord)
            .where(OTPRecord.id == otp_record.id)
            .values(status="INVALIDATED")
        )
        await db.commit()
        raise HTTPException(400, "Maximum retry attempts exceeded")

    # Accept valid stored OTP
    if _hash_otp(body.otp_code) != otp_record.otp_hash:
        await db.execute(
            update(OTPRecord)
            .where(OTPRecord.id == otp_record.id)
            .values(retry_count=otp_record.retry_count + 1)
        )
        await db.commit()
        raise HTTPException(
            400,
            f"Invalid OTP. {settings.OTP_MAX_RETRY - otp_record.retry_count - 1} attempts left",
        )

    # OTP verified
    await db.execute(
        update(OTPRecord)
        .where(OTPRecord.id == otp_record.id)
        .values(status="VERIFIED", verified_at=datetime.utcnow())
    )

    # Create consent record
    consent = ConsentRecord(
        id=str(uuid.uuid4()),
        case_id=body.case_id,
        customer_id=str(current_user.id),
        otp_record_id=otp_record.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(consent)

    # Select quote (custom choice if selected_quote_id is provided, else fallback to top ranked #1)
    selected_quote = None
    if body.selected_quote_id:
        qr = await db.execute(
            select(Quote).where(Quote.case_id == body.case_id, Quote.id == body.selected_quote_id)
        )
        selected_quote = qr.scalar_one_or_none()
    
    if not selected_quote:
        quote_result = await db.execute(
            select(Quote)
            .where(Quote.case_id == body.case_id)
            .order_by(Quote.ai_rank.asc())
        )
        selected_quote = quote_result.scalars().first()

    if selected_quote:
        # Update selected quote's status to SELECTED and other quotes to REJECTED in database
        await db.execute(
            update(Quote)
            .where(Quote.case_id == body.case_id, Quote.id == selected_quote.id)
            .values(status="SELECTED")
        )
        await db.execute(
            update(Quote)
            .where(Quote.case_id == body.case_id, Quote.id != selected_quote.id)
            .values(status="REJECTED")
        )

        existing_policy = await db.execute(
            select(Policy).where(Policy.case_id == body.case_id)
        )
        if not existing_policy.scalar_one_or_none():
            policy_num = f"POL-{datetime.utcnow().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
            policy = Policy(
                id=str(uuid.uuid4()),
                case_id=body.case_id,
                quote_id=selected_quote.id,
                customer_id=str(current_user.id),
                policy_number=policy_num,
                insurer_code=selected_quote.insurer_code,
                insurer_name=selected_quote.insurer_name,
                product_name=selected_quote.product_name,
                product_code=selected_quote.product_code,
                annual_premium=selected_quote.annual_premium,
                sum_assured=selected_quote.sum_assured,
                policy_tenure=selected_quote.policy_tenure,
                status="DRAFT",
            )
            db.add(policy)

    # Advance case stage
    await db.execute(
        update(Case)
        .where(Case.id == body.case_id)
        .values(
            consent_given=1,
            consent_given_at=datetime.utcnow(),
            current_stage="PROPOSAL_GENERATION",
            kyc_status="PENDING_E_SIGN",
            esign_status="NOT_STARTED",
        )
    )
    await db.commit()

    case_number = case.case_number if case else body.case_id
    subject, body_html = stage_message(
        case_number,
        "PROPOSAL_GENERATION",
        "Consent verified successfully. Proposal generation can proceed.",
    )
    await queue_and_send_email(
        db,
        current_user.email,
        subject,
        body_html,
        recipient_id=str(current_user.id),
        reference_type="CASE",
        reference_id=body.case_id,
    )
    return {
        "message": "OTP verified. Consent recorded.",
        "next_stage": "PROPOSAL_GENERATION",
    }
