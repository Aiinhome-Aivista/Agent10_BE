"""workflow.py — workflow status and trigger"""

from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, require_roles
from backend.app.models.all_models import Case, CaseStage, Quote, WorkflowStageLog, User
from backend.app.repositories.user_repository import UserRepository
from backend.app.services.notification_service import (
    queue_and_send_email,
    stage_message,
)
from agents.orchestrator_agent import (
    WorkflowState,
    node_needs_analysis,
    node_suitability,
    node_quote_retrieval,
    node_comparison,
    node_recommendation,
)

router = APIRouter(prefix="/workflow", tags=["workflow"])

ALL_STAGES = [s.value for s in CaseStage]


def _stage_name(value):
    return value.value if hasattr(value, "value") else str(value)


@router.get("/case/{case_id}/status")
async def workflow_status(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    r = await db.execute(select(Case).where(Case.id == case_id))
    c = r.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Case not found")
    stage_val = (
        c.current_stage.value
        if hasattr(c.current_stage, "value")
        else str(c.current_stage)
    )
    idx = ALL_STAGES.index(stage_val) if stage_val in ALL_STAGES else 0
    return {
        "case_id": case_id,
        "case_number": c.case_number,
        "current_stage": stage_val,
        "status": str(c.status),
        "progress_percent": round(idx / (len(ALL_STAGES) - 1) * 100),
        "all_stages": ALL_STAGES,
        "stage_index": idx,
        "last_activity_at": (
            c.last_activity_at.isoformat() if c.last_activity_at else None
        ),
    }


async def _record_stage(
    db: AsyncSession, case_id: str, from_stage, to_stage, remarks: str | None = None
):
    db.add(
        WorkflowStageLog(
            id=str(uuid.uuid4()),
            case_id=case_id,
            from_stage=_stage_name(from_stage),
            to_stage=_stage_name(to_stage),
            triggered_by=None,
            remarks=remarks,
        )
    )


async def _persist_case_stage(
    db: AsyncSession, case_id: str, stage, values: dict | None = None
):
    payload = {"current_stage": stage, "stage_entered_at": datetime.utcnow()}
    if values:
        payload.update(values)
    await db.execute(update(Case).where(Case.id == case_id).values(**payload))


async def _save_quotes(db: AsyncSession, case_id: str, quotes: list[dict]):
    await db.execute(delete(Quote).where(Quote.case_id == case_id))
    for index, quote in enumerate(quotes, start=1):
        db.add(
            Quote(
                id=str(uuid.uuid4()),
                case_id=case_id,
                insurer_code=quote["insurer_code"],
                insurer_name=quote["insurer_name"],
                product_name=quote["product_name"],
                product_code=quote["product_code"],
                annual_premium=quote["annual_premium"],
                sum_assured=quote["sum_assured"],
                policy_tenure=quote["policy_tenure"],
                premium_frequency=quote.get("premium_frequency", "ANNUAL"),
                coverage_details=quote.get("coverage_details"),
                riders=quote.get("riders"),
                exclusions=quote.get("exclusions"),
                waiting_period_days=quote.get("waiting_period_days"),
                underwriting_requirements=quote.get("underwriting_requirements"),
                medical_requirements=quote.get("medical_requirements"),
                ai_rank=index,
                ai_score=quote.get("score", 0.0),
                ai_recommendation_text=quote.get("reason"),
                raw_response=quote,
            )
        )


def is_insurer_match(code1: str, code2: str) -> bool:
    if not code1 or not code2:
        return False
    c1 = code1.upper().replace("_", "").replace(" ", "")
    c2 = code2.upper().replace("_", "").replace(" ", "")
    if c1 == c2:
        return True
    if "SBI" in c1 and "SBI" in c2:
        return True
    if "HDFC" in c1 and "HDFC" in c2:
        return True
    if "ICICI" in c1 and "ICICI" in c2:
        return True
    if "LIC" in c1 and "LIC" in c2:
        return True
    return False


def get_rider_cost_info(rider_name: str, available_riders: list) -> str:
    if not rider_name or not available_riders:
        return ""
    r_name_clean = rider_name.lower().strip()
    for r in available_riders:
        name = r.get("name") or r.get("rider_name") or ""
        if not name:
            continue
        name_clean = name.lower().strip()
        if r_name_clean in name_clean or name_clean in r_name_clean:
            cost = r.get("annual_cost") or r.get("annual_premium") or r.get("premium_per_year")
            if cost is not None:
                return f" (Cost: ₹{cost}/year)"
    return ""


async def _update_quotes_with_comparison(db: AsyncSession, case_id: str, comparison: dict):
    if not comparison:
        return

    r = await db.execute(select(Quote).where(Quote.case_id == case_id))
    db_quotes = r.scalars().all()

    # Sort DB quotes by score or rank to know the top quote as fallback
    db_quotes_sorted = sorted(db_quotes, key=lambda x: x.ai_rank or 99)

    parse_err = comparison.get("parse_error", False)
    raw_text = comparison.get("raw_response", "")

    for q in db_quotes:
        # Find matching ranked quote by insurer_code
        match = None
        if not parse_err and "ranked_quotes" in comparison:
            for rq in comparison["ranked_quotes"]:
                if is_insurer_match(rq.get("insurer_code"), q.insurer_code):
                    match = rq
                    break
        
        if match:
            q.ai_rank = match.get("rank", q.ai_rank)
            q.ai_score = match.get("score", q.ai_score)
            
            reason = match.get("reason", "")
            add_ons = match.get("recommended_add_ons", [])
            
            rec_text = reason
            if add_ons:
                rec_text += "\n\nRecommended Add-ons / Riders:\n"
                for addon in add_ons:
                    name = addon.get("name") or addon.get("rider_name") or ""
                    r_reason = addon.get("reason") or ""
                    cost_str = get_rider_cost_info(name, q.riders or [])
                    rec_text += f"• {name}{cost_str}: {r_reason}\n"
            
            q.ai_recommendation_text = rec_text.strip()
        else:
            # Fallback if no match was found for this quote, but this is the top quote in the list
            fallback_done = False
            if not parse_err and db_quotes_sorted and q.id == db_quotes_sorted[0].id:
                summary = comparison.get("recommendation_summary")
                if summary:
                    q.ai_recommendation_text = summary
                    fallback_done = True
            
            # Fallback if parsing failed or no match found
            # If this is the top ranked quote, set the raw LLM response as the recommendation text
            if not fallback_done and parse_err and db_quotes_sorted and q.id == db_quotes_sorted[0].id:
                import re
                cleaned_text = re.sub(r"```(?:json)?\s*([\s\S]*?)```", r"\1", raw_text).strip()
                q.ai_recommendation_text = cleaned_text



async def _run_workflow_bg(case_id: str):
    from backend.app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Case).where(Case.id == case_id))
        case = r.scalar_one_or_none()
        if not case:
            return

        profile = case.customer_profile or {}
        profile["sum_assured"] = case.sum_assured or profile.get("sum_assured") or 1000000
        profile["premium_budget"] = case.premium_budget or profile.get("premium_budget") or 50000
        profile["policy_tenure"] = case.policy_tenure or profile.get("policy_tenure") or 20

        state: WorkflowState = {
            "case_id": case_id,
            "customer_profile": profile,
            "needs_analysis": {},
            "suitability_result": {},
            "quotes": [],
            "comparison": {},
            "recommendation": {},
            "banker_approved": False,
            "proposal": {},
            "exceptions": [],
            "stage": str(case.current_stage),
            "llm_context": [],
            "error": None,
        }

        previous_stage = case.current_stage

        state = await node_needs_analysis(state)
        await _persist_case_stage(
            db,
            case_id,
            CaseStage.NEEDS_ANALYSIS,
            {"needs_analysis": state["needs_analysis"]},
        )
        await _record_stage(
            db, case_id, previous_stage, CaseStage.NEEDS_ANALYSIS, "workflow"
        )
        await db.commit()
        previous_stage = CaseStage.NEEDS_ANALYSIS

        state = await node_suitability(state)
        await _persist_case_stage(
            db,
            case_id,
            CaseStage.SUITABILITY_VALIDATION,
            {"suitability_result": state["suitability_result"]},
        )
        await _record_stage(
            db, case_id, previous_stage, CaseStage.SUITABILITY_VALIDATION, "workflow"
        )
        await db.commit()
        previous_stage = CaseStage.SUITABILITY_VALIDATION

        state = await node_quote_retrieval(state)
        await _save_quotes(db, case_id, state["quotes"])
        await _persist_case_stage(db, case_id, CaseStage.QUOTE_RETRIEVAL)
        await _record_stage(
            db, case_id, previous_stage, CaseStage.QUOTE_RETRIEVAL, "workflow"
        )
        await db.commit()
        previous_stage = CaseStage.QUOTE_RETRIEVAL

        state = await node_comparison(state)
        await _update_quotes_with_comparison(db, case_id, state["comparison"])
        await _persist_case_stage(db, case_id, CaseStage.QUOTE_COMPARISON)
        await _record_stage(
            db, case_id, previous_stage, CaseStage.QUOTE_COMPARISON, "workflow"
        )
        await db.commit()
        previous_stage = CaseStage.QUOTE_COMPARISON

        state = await node_recommendation(state)
        await _persist_case_stage(
            db,
            case_id,
            CaseStage.RECOMMENDATION,
            {"recommendation": state["recommendation"]},
        )
        await _record_stage(
            db, case_id, previous_stage, CaseStage.RECOMMENDATION, "workflow"
        )
        await db.commit()

        banker = await UserRepository(db).get_by_id(case.banker_id)
        if banker:
            subject, body = stage_message(
                case.case_number,
                "BANKER_APPROVAL",
                "The recommendation is ready. Please review and approve to continue.",
            )
            await queue_and_send_email(
                db,
                banker.email,
                subject,
                body,
                recipient_id=banker.id,
                reference_type="CASE",
                reference_id=case_id,
            )

        await _persist_case_stage(db, case_id, CaseStage.BANKER_APPROVAL)
        await _record_stage(
            db, case_id, CaseStage.RECOMMENDATION, CaseStage.BANKER_APPROVAL, "workflow"
        )
        await db.commit()


@router.post("/case/{case_id}/run")
async def trigger_workflow(
    case_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles("BANKER", "SUPER_ADMIN")),
):
    r = await db.execute(select(Case).where(Case.id == case_id))
    if not r.scalar_one_or_none():
        raise HTTPException(404, "Case not found")
    background_tasks.add_task(_run_workflow_bg, case_id)
    return {"message": "Workflow triggered", "case_id": case_id}
