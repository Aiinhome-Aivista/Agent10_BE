"""policies.py"""
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, require_roles
from backend.app.models.all_models import Policy, Quote, Case, User, CaseStage, CaseStatus


router = APIRouter(prefix="/policies", tags=["policies"])


class CreatePolicyBody(BaseModel):
    case_id: str
    quote_id: str


@router.post("/")
async def create_policy(body: CreatePolicyBody, db: AsyncSession = Depends(get_db),
                         current_user=Depends(require_roles("BANKER", "SUPER_ADMIN"))):
    r = await db.execute(select(Case).where(Case.id == body.case_id))
    case = r.scalar_one_or_none()
    if not case: raise HTTPException(404, "Case not found")
    qr = await db.execute(select(Quote).where(Quote.id == body.quote_id))
    q = qr.scalar_one_or_none()
    if not q: raise HTTPException(404, "Quote not found")
    existing = await db.execute(select(Policy).where(Policy.case_id == body.case_id))
    if existing.scalar_one_or_none(): raise HTTPException(409, "Policy already exists")
    policy = Policy(
        id=str(uuid.uuid4()), case_id=body.case_id, quote_id=body.quote_id,
        customer_id=case.customer_id, insurer_code=q.insurer_code, insurer_name=q.insurer_name,
        product_name=q.product_name, product_code=q.product_code,
        annual_premium=q.annual_premium, sum_assured=q.sum_assured, policy_tenure=q.policy_tenure,
    )
    db.add(policy); await db.commit(); await db.refresh(policy)
    return {"policy_id": policy.id, "message": "Policy draft created"}


@router.get("/customer/{customer_id}")
async def customer_policies(customer_id: str, db: AsyncSession = Depends(get_db),
                              current_user=Depends(get_current_user)):
    r = await db.execute(select(Policy).where(Policy.customer_id == customer_id).order_by(Policy.created_at.desc()))
    policies = r.scalars().all()
    return {"policies": [{"id": p.id, "policy_number": p.policy_number, "insurer_name": p.insurer_name,
                           "product_name": p.product_name, "annual_premium": p.annual_premium,
                           "sum_assured": p.sum_assured, "status": p.status,
                           "created_at": p.created_at.isoformat() if p.created_at else None} for p in policies]}


@router.get("/")
async def all_policies(skip: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db),
                        current_user=Depends(require_roles("SUPER_ADMIN", "UNDERWRITER"))):
    r = await db.execute(select(Policy).order_by(Policy.created_at.desc()).offset(skip).limit(limit))
    policies = r.scalars().all()
    return {"policies": [{"id": p.id, "case_id": p.case_id, "policy_number": p.policy_number,
                           "insurer_name": p.insurer_name, "sum_assured": p.sum_assured,
                           "status": p.status} for p in policies]}


@router.post("/{policy_id}/issue")
async def issue_policy(
    policy_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles("SUPER_ADMIN", "UNDERWRITER"))
):
    """Issue a policy and transition case to COMPLETED stage"""
    # 1. Find and validate policy
    r = await db.execute(select(Policy).where(Policy.id == policy_id))
    policy = r.scalar_one_or_none()
    if not policy:
        raise HTTPException(404, "Policy not found")
    
    # 2. Find associated case
    cr = await db.execute(select(Case).where(Case.id == policy.case_id))
    case = cr.scalar_one_or_none()
    if not case:
        raise HTTPException(404, "Associated case not found")
    
    # 3. Validate policy is in POLICY_ISSUANCE stage
    if case.current_stage != CaseStage.POLICY_ISSUANCE:
        raise HTTPException(
            400,
            f"Policy can only be issued from POLICY_ISSUANCE stage. Current stage: {case.current_stage}"
        )
    
    # 4. Update policy status to ISSUED
    policy.status = "ISSUED"
    policy.issued_at = datetime.utcnow()
    policy.commencement_date = policy.issued_at
    if policy.policy_tenure:
        try:
            policy.maturity_date = policy.commencement_date.replace(year=policy.commencement_date.year + policy.policy_tenure)
        except ValueError:
            policy.maturity_date = policy.commencement_date.replace(year=policy.commencement_date.year + policy.policy_tenure, month=3, day=1)
    else:
        policy.maturity_date = None

    # Generate Policy Document PDF
    import os
    from configs.base import settings
    from backend.app.services.policy_pdf_service import generate_policy_pdf
    
    cust_profile = case.customer_profile or {}
    upload_dir = settings.FILE_UPLOAD_PATH
    
    try:
        pdf_path = generate_policy_pdf(policy, cust_profile, upload_dir)
        policy.policy_document_path = pdf_path
    except Exception as ex:
        import logging
        logging.getLogger(__name__).error(f"Failed to generate policy PDF: {ex}")
        pdf_path = None
    
    # 5. Update case to COMPLETED
    await db.execute(
        update(Case)
        .where(Case.id == policy.case_id)
        .values(
            current_stage=CaseStage.COMPLETED,
            status=CaseStatus.COMPLETED,
            last_activity_at=datetime.utcnow()
        )
    )
    
    db.add(policy)
    await db.commit()
    await db.refresh(policy)

    # Notify Customer & Banker
    from backend.app.services.notification_service import create_in_app_notification
    customer_res = await db.execute(select(User).where(User.id == policy.customer_id))
    customer = customer_res.scalar_one_or_none()
    if customer:
        # 1. Create In-App Notification
        await create_in_app_notification(
            db,
            recipient_id=customer.id,
            recipient_email=customer.email,
            subject="Policy Issued Successfully!",
            body=f"Your insurance policy {policy.policy_number} has been issued successfully for Case {case.case_number}. You can now view it on your dashboard.",
            reference_id=case.id,
        )

        # 2. Send email with PDF attachment asynchronously
        if pdf_path and os.path.exists(pdf_path):
            from smtp.smtp_service import smtp_service
            import asyncio
            
            email_subject = f"Your Q2P Insurance Policy Document - {policy.policy_number or policy.id}"
            email_body = f"""
            <div style="font-family:Arial,sans-serif;max-width:640px;margin:auto;padding:24px;
                        background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;">
                <h2 style="margin:0 0 12px;color:#4f46e5;">Policy Issued Successfully!</h2>
                <p style="margin:0 0 8px;color:#374151;">Hello {cust_profile.get('name', customer.name or 'Valued Customer')},</p>
                <p style="margin:0 0 8px;color:#374151;">We are pleased to inform you that your insurance policy <strong>{policy.policy_number}</strong> has been issued successfully for Case <strong>{case.case_number}</strong>.</p>
                <p style="margin:0 0 16px;color:#374151;">The official policy bond has been attached to this email. You can also view and download it directly from your Q2P dashboard under "My Policies".</p>
                <div style="background:#f3f4f6;padding:12px;border-radius:8px;margin-bottom:16px;font-size:13px;color:#374151;">
                    <strong>Policy Details:</strong><br>
                    - Insurer: {policy.insurer_name}<br>
                    - Product: {policy.product_name}<br>
                    - Sum Assured: INR {policy.sum_assured:,.2f}<br>
                    - Annual Premium: INR {policy.annual_premium:,.2f}<br>
                    - Tenure: {policy.policy_tenure} Years
                </div>
                <p style="margin:0;color:#6b7280;font-size:12px;">Thank you for choosing Q2P Insurance Platform.</p>
            </div>
            """
            asyncio.create_task(smtp_service.send_with_pdf(
                to=customer.email,
                subject=email_subject,
                html_body=email_body,
                pdf_path=pdf_path,
                pdf_filename=f"policy_{policy.policy_number or policy.id}.pdf"
            ))

    banker_res = await db.execute(select(User).where(User.id == case.banker_id))
    banker = banker_res.scalar_one_or_none()
    if banker:
        await create_in_app_notification(
            db,
            recipient_id=banker.id,
            recipient_email=banker.email,
            subject="Policy Issued Successfully",
            body=f"Policy {policy.policy_number} has been successfully issued for Case {case.case_number}.",
            reference_id=case.id,
        )
    
    return {
        "message": "Policy issued successfully",
        "policy_id": policy.id,
        "case_id": policy.case_id,
        "policy_status": policy.status,
        "issued_at": policy.issued_at.isoformat() if policy.issued_at else None
    }


@router.get("/{policy_id}/pdf")
async def view_policy_pdf(
    policy_id: str,
    token: Optional[str] = None,
    download: bool = False,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Return the policy document PDF as an inline or attachment response."""
    auth_token = token
    if not auth_token and authorization:
        if authorization.startswith("Bearer "):
            auth_token = authorization.split(" ")[1]

    if not auth_token:
        raise HTTPException(status_code=401, detail="Authentication token required")

    try:
        from backend.app.core.security import decode_token
        payload = decode_token(auth_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    from backend.app.repositories.user_repository import UserRepository
    user = await UserRepository(db).get_by_id(payload.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Unauthorized or inactive user")

    r = await db.execute(select(Policy).where(Policy.id == policy_id))
    policy = r.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    # Authorize role
    from backend.app.models.user import UserRole
    if user.role not in {UserRole.SUPER_ADMIN, UserRole.UNDERWRITER, UserRole.BANKER} and policy.customer_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden: You do not have access to this policy document")

    import os
    if not policy.policy_document_path or not os.path.exists(policy.policy_document_path):
        if policy.status == "ISSUED":
            from configs.base import settings
            from backend.app.services.policy_pdf_service import generate_policy_pdf
            
            cr = await db.execute(select(Case).where(Case.id == policy.case_id))
            case = cr.scalar_one_or_none()
            if case:
                cust_profile = case.customer_profile or {}
                upload_dir = settings.FILE_UPLOAD_PATH
                try:
                    if not policy.commencement_date:
                        policy.commencement_date = policy.issued_at or datetime.utcnow()
                    if not policy.maturity_date and policy.policy_tenure:
                        try:
                            policy.maturity_date = policy.commencement_date.replace(year=policy.commencement_date.year + policy.policy_tenure)
                        except ValueError:
                            policy.maturity_date = policy.commencement_date.replace(year=policy.commencement_date.year + policy.policy_tenure, month=3, day=1)

                    pdf_path = generate_policy_pdf(policy, cust_profile, upload_dir)
                    policy.policy_document_path = pdf_path
                    db.add(policy)
                    await db.commit()
                    await db.refresh(policy)
                except Exception as ex:
                    import logging
                    logging.getLogger(__name__).error(f"Failed to generate policy PDF on the fly: {ex}")
                    raise HTTPException(status_code=500, detail=f"Failed to generate policy PDF document: {ex}")
            else:
                raise HTTPException(status_code=404, detail="Associated case not found to generate PDF")
        else:
            raise HTTPException(status_code=404, detail="Policy PDF document not generated yet or missing on disk")

    cd_type = "attachment" if download else "inline"
    filename = f"policy_{policy.policy_number or policy_id}.pdf"
    return FileResponse(
        policy.policy_document_path,
        media_type="application/pdf",
        filename=filename,
        content_disposition_type=cd_type
    )

