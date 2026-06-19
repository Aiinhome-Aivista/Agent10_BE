"""cases.py — Case management endpoint"""

import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, require_roles
from backend.app.models.all_models import (
    Case,
    CaseStage,
    CaseStatus,
    WorkflowStageLog,
    User,
    UserRole,
)
from backend.app.repositories.user_repository import UserRepository
from backend.app.services.notification_service import (
    queue_and_send_email,
    stage_message,
)

router = APIRouter(prefix="/cases", tags=["cases"])


class CreateCaseRequest(BaseModel):
    customer_id: str
    customer_profile: dict
    sum_assured: float
    premium_budget: float
    policy_tenure: int
    needs_analysis: Optional[dict] = None


class BankerApproveRequest(BaseModel):
    remarks: Optional[str] = None


class CustomerIntakeRequest(BaseModel):
    customer_profile: dict
    needs_analysis: Optional[dict] = None

class SuggestParamsRequest(BaseModel):
    customer_profile: dict
    product_type: Optional[str] = "HEALTH"
    policy_tenure: Optional[int] = 1
    sum_assured: Optional[float] = None


@router.post("/suggest-params")
async def suggest_params(
    body: SuggestParamsRequest,
    current_user: User = Depends(require_roles("BANKER", "SUPER_ADMIN")),
):
    profile = body.customer_profile
    ptype = (body.product_type or "HEALTH").upper()
    tenure = int(body.policy_tenure or 1)
    sa_override = float(body.sum_assured) if body.sum_assured else None
    
    # Robust income parsing
    raw_income = profile.get("annual_income") or profile.get("Annual_Income") or 0
    if isinstance(raw_income, str):
        cleaned = raw_income.replace("₹", "").replace(",", "").strip()
        try:
            income = float(cleaned)
        except ValueError:
            income = 0.0
    else:
        try:
            income = float(raw_income)
        except (ValueError, TypeError):
            income = 0.0
            
    # Robust dependents parsing
    raw_deps = profile.get("dependents") or profile.get("Dependents") or 0
    try:
        dependents = int(raw_deps)
    except (ValueError, TypeError):
        dependents = 0
        
    # Robust age parsing
    age = None
    for k in ["age", "Age"]:
        if profile.get(k) is not None:
            try:
                age = int(profile.get(k))
                break
            except (ValueError, TypeError):
                pass

    if age is None:
        dob = ""
        for k in ["date_of_birth", "dob", "Date_of_Birth", "Date of Birth", "birth_date", "birthdate"]:
            if profile.get(k):
                dob = str(profile.get(k))
                break
        if dob:
            try:
                parts = dob.replace("/", "-").split("-")
                birth_year = None
                for p in parts:
                    p = p.strip()
                    if len(p) == 4 and p.isdigit():
                        birth_year = int(p)
                        break
                if birth_year and 1900 <= birth_year <= datetime.utcnow().year:
                    age = datetime.utcnow().year - birth_year
            except Exception:
                pass

    if age is None or age <= 0:
        age = 30  # Fallback
        
    # Robust city parsing
    city = ""
    for k in ["city", "City", "location", "Location", "address", "Address"]:
        if profile.get(k):
            city = str(profile.get(k)).strip()
            break
    tier1_cities = {"mumbai", "delhi", "bangalore", "bengaluru", "chennai", "kolkata", "hyderabad", "pune", "ahmedabad"}
    is_tier1 = city.lower() in tier1_cities
    location_multiplier = 1.15 if is_tier1 else 1.0

    # Robust medical history parsing
    medical_history = ""
    for k in ["medical_history", "Medical_History", "Medical History", "medical_issues", "Medical_Issues", "medical", "Medical"]:
        if profile.get(k):
            medical_history = str(profile.get(k)).strip()
            break
    
    has_medical = False
    if medical_history and medical_history.lower() not in ["none", "no", "n/a", "nil", "normal", "healthy"]:
        has_medical = True
    medical_multiplier = 1.25 if has_medical else 1.0

    # Robust smoker status parsing
    smoker_status = ""
    for k in ["smoker", "Smoker", "tobacco", "Tobacco", "tobacco_user", "Tobacco_User"]:
        if profile.get(k):
            smoker_status = str(profile.get(k)).strip()
            break
    
    is_smoker = smoker_status.lower() in ["yes", "true", "y", "smoker"]
    smoker_multiplier = 1.30 if is_smoker else 1.0
    
    if ptype == "HEALTH":
        if sa_override:
            sa = sa_override
        else:
            if income <= 0:
                base_sa = 1000000
            elif income < 1000000:
                base_sa = 1000000
            elif income < 2000000:
                base_sa = 1500000
            else:
                base_sa = 2000000
                
            sa = base_sa + (dependents * 200000)
            
            # Risk-based buffer
            if is_smoker or has_medical or age > 45:
                sa += 500000
            
            # Round to nearest Lakh
            sa = int(round(sa / 100000.0) * 100000)
            
        # Base annual premium calculation
        age_multiplier = 1.0 + max(0.0, (age - 30) * 0.02)
        dep_multiplier = 1.0 + (dependents * 0.20)
        
        # Combined multiplier
        combined_mult = age_multiplier * dep_multiplier * location_multiplier * medical_multiplier * smoker_multiplier
        base_annual_rate = 0.008  # 0.8% of SA base annual premium
        base_premium_1yr = sa * base_annual_rate * combined_mult
        
        # Tenure discount
        discount = 1.0
        if tenure == 2:
            discount = 0.95
        elif tenure == 3:
            discount = 0.90
        elif tenure == 4:
            discount = 0.88
        elif tenure >= 5:
            discount = 0.85
            
        premium = round(base_premium_1yr * discount, 0)
        premium = int(round(premium / 100.0) * 100)  # Round to nearest hundred
        
        suggested_sa = sa
        suggested_premium = premium
        suggested_tenure = tenure
        
        reasoning = (
            f"Based on the customer's age ({age} years), annual income of ₹{income:,.2f}, "
            f"and {dependents} dependent(s), a health cover of ₹{sa:,} is recommended with a target premium of ₹{premium:,}/year "
            f"({tenure} year term)."
        )
    elif ptype == "LIFE":
        if sa_override:
            sa = sa_override
        else:
            if income <= 0:
                sa = 5000000
            else:
                sa = income * 10
            sa = int(round(sa / 500000.0) * 500000)
            
        age_multiplier = 1.0 + max(0.0, (age - 30) * 0.03)
        # Apply a minor multiplier for smoker / medical status on life insurance
        life_combined_mult = age_multiplier
        if is_smoker:
            life_combined_mult *= 1.50
        if has_medical:
            life_combined_mult *= 1.30
            
        premium = round(sa * 0.0015 * life_combined_mult, 0)
        premium = int(round(premium / 1000.0) * 1000)
        
        suggested_sa = sa
        suggested_premium = premium
        suggested_tenure = tenure if tenure > 1 else 20
        reasoning = f"Based on the customer's age ({age} years) and annual income of ₹{income:,.2f}, a life term cover of ₹{sa:,} is recommended with a target premium of ₹{premium:,}/year."
    else:
        suggested_sa = 500000
        suggested_premium = 10000
        suggested_tenure = 1
        reasoning = "Standard plan recommended."

    from llm.llm_service import LLMService
    from llm.response_parser import ResponseParser
    from rag.rag_pipeline import semantic_search
    
    llm = LLMService()
    rp = ResponseParser()
    
    kb_context = ""
    try:
        chunks = await semantic_search("underwriting guidelines eligibility sum assured recommendations loading rules", top_k=4)
        if chunks:
            kb_context = "\n\n---\n\n".join([
                f"Source: {c['title']}\n{c['text']}" for c in chunks
            ])
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"RAG search failed in suggest_params: {e}")

    prompt = f"""You are an AI insurance advisor suggesting recommended cover parameters for a prospect.
Analyze the customer's profile:
- Name: {profile.get("name") or profile.get("Full_Name") or "Prospect"}
- Age: {age}
- Annual Income: ₹{income:,.2f}
- Dependents: {dependents}
- Location: {city.title() if city else 'Tier-2/3 City'} (Tier-1: {'Yes' if is_tier1 else 'No'})
- Medical History: {medical_history.title() if medical_history else 'None'}
- Smoker: {'Yes' if is_smoker else 'No'}
- Risk Appetite: {profile.get("risk_appetite", "MEDIUM")}
- Product Type: {ptype}
- Policy Tenure: {tenure} years

We calculated these base parameters using actuarial formulas:
- Sum Assured: ₹{suggested_sa:,}
- Calculated Premium per Year: ₹{suggested_premium:,}
- Policy Tenure: {tenure} years

RETRIEVED UNDERWRITING GUIDELINES / KNOWLEDGE BASE:
{kb_context if kb_context else "No specific documents found. Use standard actuarial recommendation guidelines."}

Your task:
1. Review these parameters and adjust them if needed to be optimal, realistic, and compliant with any retrieved underwriting guidelines.
2. Provide a personalized reasoning sentence explaining why this Sum Assured and Premium are recommended.
3. Be specific in the reasoning about:
   - Any location loading or medical/smoker loading found in the guidelines or standard rules.
   - If the guidelines contain specific options or top-ups (e.g. Option A base cover + super top-up) for this customer's income/profile, recommend them in the reasoning text.
4. Keep the sum assured and premium budget as clean integers.

Return ONLY a valid JSON object matching the schema:
{{
  "recommended_sum_assured": number,
  "recommended_premium_budget": number,
  "recommended_policy_tenure": number,
  "reasoning": "string explaining recommendation"
}}
"""
    try:
        import asyncio
        res = await asyncio.wait_for(llm.complete(prompt), timeout=25.0)
        parsed = rp.parse_json(res["response"])
        if isinstance(parsed, dict) and "recommended_sum_assured" in parsed:
            return {
                "recommended_sum_assured": int(parsed["recommended_sum_assured"]),
                "recommended_premium_budget": int(parsed["recommended_premium_budget"]),
                "recommended_policy_tenure": int(parsed["recommended_policy_tenure"]),
                "reasoning": parsed["reasoning"],
            }
    except Exception:
        pass

    return {
        "recommended_sum_assured": suggested_sa,
        "recommended_premium_budget": suggested_premium,
        "recommended_policy_tenure": suggested_tenure,
        "reasoning": reasoning,
    }


@router.post("/")
async def create_case(
    body: CreateCaseRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("BANKER", "SUPER_ADMIN")),
):
    customer = await UserRepository(db).get_by_id(body.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    case = Case(
        id=str(uuid.uuid4()),
        case_number=f"CASE-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}",
        customer_id=body.customer_id,
        banker_id=str(current_user.id),
        customer_profile=body.customer_profile,
        sum_assured=body.sum_assured,
        premium_budget=body.premium_budget,
        policy_tenure=body.policy_tenure,
        needs_analysis=body.needs_analysis,
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)

    subject, body_html = stage_message(
        case.case_number,
        "CUSTOMER_INTAKE",
        "A new case has been created and queued for the AI workflow.",
    )
    await queue_and_send_email(
        db,
        customer.email,
        subject,
        body_html,
        recipient_id=customer.id,
        reference_type="CASE",
        reference_id=case.id,
    )
    from backend.app.api.v1.endpoints.workflow import _run_workflow_bg

    await _run_workflow_bg(case.id)
    return {
        "case_id": case.id,
        "case_number": case.case_number,
        "stage": case.current_stage,
    }


@router.get("/")
async def list_cases(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else current_user.role
    )
    from sqlalchemy.orm import selectinload
    q = select(Case).options(selectinload(Case.medical_requests))
    if role == "BANKER":
        q = q.where(Case.banker_id == str(current_user.id))
    elif role == "CUSTOMER":
        q = q.where(Case.customer_id == str(current_user.id))
    result = await db.execute(q.order_by(Case.created_at.desc()))
    cases = result.scalars().all()
    return {"cases": [_s(c) for c in cases]}


@router.get("/customer/{customer_id}")
async def list_customer_cases(
    customer_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy.orm import selectinload
    q = select(Case).where(Case.customer_id == customer_id).options(selectinload(Case.medical_requests))
    result = await db.execute(q.order_by(Case.created_at.desc()))
    cases = result.scalars().all()
    return {"cases": [_s(c) for c in cases]}


@router.get("/{case_id}")
async def get_case(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy.orm import selectinload
    r = await db.execute(select(Case).where(Case.id == case_id).options(selectinload(Case.medical_requests)))
    c = r.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Case not found")
    return _s(c)


@router.post("/{case_id}/banker-approve")
async def banker_approve(
    case_id: str,
    body: BankerApproveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("BANKER", "SUPER_ADMIN")),
):
    r = await db.execute(select(Case).where(Case.id == case_id))
    case = r.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    await db.execute(
        update(Case)
        .where(Case.id == case_id)
        .values(
            banker_approved=1,
            banker_remarks=body.remarks,
            banker_approved_at=datetime.utcnow(),
            current_stage=CaseStage.BANKER_APPROVAL,
        )
    )
    db.add(
        WorkflowStageLog(
            id=str(uuid.uuid4()),
            case_id=case_id,
            from_stage=str(case.current_stage),
            to_stage=CaseStage.BANKER_APPROVAL,
            triggered_by=str(current_user.id),
            remarks=body.remarks,
        )
    )
    await db.commit()

    customer = await UserRepository(db).get_by_id(case.customer_id)
    if customer:
        subject, body_html = stage_message(
            case.case_number,
            "BANKER_APPROVAL",
            "Your banker approved the recommendation. OTP consent is now required.",
        )
        await queue_and_send_email(
            db,
            customer.email,
            subject,
            body_html,
            recipient_id=customer.id,
            reference_type="CASE",
            reference_id=case_id,
        )
    return {"message": "Case approved", "next_stage": "BANKER_APPROVAL"}


@router.post("/{case_id}/customer-intake")
async def customer_intake_update(
    case_id: str,
    body: CustomerIntakeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    r = await db.execute(select(Case).where(Case.id == case_id))
    case = r.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if str(case.customer_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not your case")

    await db.execute(
        update(Case)
        .where(Case.id == case_id)
        .values(
            customer_profile=body.customer_profile,
            needs_analysis=body.needs_analysis or case.needs_analysis,
            kyc_status="PROFILE_SUBMITTED",
        )
    )
    await db.commit()
    return {"message": "Customer intake saved", "kyc_status": "PROFILE_SUBMITTED"}


class UpdateStageRequest(BaseModel):
    stage: str


@router.put("/{case_id}/stage")
async def update_case_stage(
    case_id: str,
    body: UpdateStageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    r = await db.execute(select(Case).where(Case.id == case_id))
    case = r.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if body.stage not in [s.value for s in CaseStage]:
        raise HTTPException(status_code=400, detail="Invalid stage")

    stages_list = [s.value for s in CaseStage]
    current_val = case.current_stage.value if hasattr(case.current_stage, 'value') else str(case.current_stage)

    current_idx = stages_list.index(current_val) if current_val in stages_list else 0
    target_idx = stages_list.index(body.stage)

    if target_idx > current_idx:
        await db.execute(
            update(Case)
            .where(Case.id == case_id)
            .values(current_stage=body.stage)
        )
        db.add(
            WorkflowStageLog(
                id=str(uuid.uuid4()),
                case_id=case_id,
                from_stage=str(case.current_stage),
                to_stage=body.stage,
                triggered_by=str(current_user.id),
                remarks="Stage updated by user action",
            )
        )
        await db.commit()
        return {"message": "Stage updated", "current_stage": body.stage}
    return {"message": "Stage update skipped (already at a later stage)", "current_stage": current_val}


@router.post("/{case_id}/banker-reject")
async def banker_reject(
    case_id: str,
    body: BankerApproveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("BANKER", "SUPER_ADMIN")),
):
    r = await db.execute(select(Case).where(Case.id == case_id))
    case = r.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    await db.execute(
        update(Case)
        .where(Case.id == case_id)
        .values(
            status=CaseStatus.CANCELLED,
            banker_remarks=body.remarks,
            current_stage=CaseStage.EXCEPTION_HANDLING,
        )
    )
    db.add(
        WorkflowStageLog(
            id=str(uuid.uuid4()),
            case_id=case_id,
            from_stage=str(case.current_stage),
            to_stage=CaseStage.EXCEPTION_HANDLING,
            triggered_by=str(current_user.id),
            remarks=body.remarks or "Rejected by banker",
        )
    )
    await db.commit()
    return {"message": "Case rejected"}


class CustomizeCaseRequest(BaseModel):
    sum_assured: float
    policy_tenure: int
    premium_budget: Optional[float] = None


@router.post("/{case_id}/customize")
async def customize_case(
    case_id: str,
    body: CustomizeCaseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("BANKER", "SUPER_ADMIN")),
):
    r = await db.execute(select(Case).where(Case.id == case_id))
    case = r.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
        
    await db.execute(
        update(Case)
        .where(Case.id == case_id)
        .values(
            sum_assured=body.sum_assured,
            policy_tenure=body.policy_tenure,
            premium_budget=body.premium_budget or case.premium_budget
        )
    )
    await db.commit()
    
    from backend.app.api.v1.endpoints.quotes import fetch_quotes
    try:
        await fetch_quotes(case_id=case_id, db=db, current_user=current_user)
    except Exception as e:
        # Fallback in case of logging import issue or failure
        import logging
        logging.getLogger(__name__).error(f"Failed to auto-refetch quotes after customization: {e}")
        
    return {"message": "Case updated and quotes refetched successfully"}


def _s(c: Case) -> dict:
    has_med = False
    if "medical_requests" in c.__dict__:
        for mr in c.medical_requests:
            remarks = mr.ops_remarks or ""
            if remarks not in {"Underwriter raised query", "Customer response to query"}:
                has_med = True
                break
    return {
        "id": c.id,
        "case_number": c.case_number,
        "customer_id": c.customer_id,
        "banker_id": c.banker_id,
        "current_stage": (
            c.current_stage.value
            if hasattr(c.current_stage, "value")
            else c.current_stage
        ),
        "status": c.status.value if hasattr(c.status, "value") else c.status,
        "customer_profile": c.customer_profile,
        "needs_analysis": c.needs_analysis,
        "sum_assured": c.sum_assured,
        "premium_budget": c.premium_budget,
        "kyc_status": c.kyc_status,
        "esign_status": c.esign_status,
        "profile_update_request": c.profile_update_request,
        "banker_approved": bool(c.banker_approved),
        "banker_remarks": c.banker_remarks,
        "banker_approved_at": c.banker_approved_at.isoformat() if c.banker_approved_at else None,
        "consent_given": bool(c.consent_given),
        "consent_given_at": c.consent_given_at.isoformat() if c.consent_given_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "last_activity_at": (
            c.last_activity_at.isoformat() if c.last_activity_at else None
        ),
        "has_medical_requests": has_med,
    }
