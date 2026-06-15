"""
quotes.py
"""

import uuid, asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, require_roles
from backend.app.models.all_models import Case, Quote, User, KnowledgeDocument
from agents.insurer_agents import fetch_all_quotes
from llm.llm_service import LLMService
from rag.rag_pipeline import get_kb_context_for_customer
from llm.prompt_manager import PromptManager
from llm.response_parser import ResponseParser
from backend.app.services.notification_service import (
    queue_and_send_email,
    stage_message,
)

router = APIRouter(prefix="/quotes", tags=["quotes"])
llm, pm, rp = LLMService(), PromptManager(), ResponseParser()


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


@router.post("/case/{case_id}/fetch")
async def fetch_quotes(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("BANKER", "SUPER_ADMIN")),
):
    r = await db.execute(select(Case).where(Case.id == case_id))
    case = r.scalar_one_or_none()
    if not case:
        raise HTTPException(404, "Case not found")

    # Find which insurers are present in document titles
    r_docs = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.status == 'INDEXED'))
    docs = r_docs.scalars().all()
    docs_exist = len(docs) > 0
    insurers_in_kb = []
    import re
    for d in docs:
        title_lower = d.title.lower()
        if re.search(r'\bsbi\b', title_lower):
            insurers_in_kb.append("SBI_GENERAL")
        if re.search(r'\bhdfc\b', title_lower):
            insurers_in_kb.append("HDFC_LIFE")
        if re.search(r'\blic\b', title_lower):
            insurers_in_kb.append("LIC")
        if re.search(r'\bicici\b', title_lower):
            insurers_in_kb.append("ICICI_PRU")

    if not insurers_in_kb and not docs_exist:
        insurers_in_kb = ["HDFC_LIFE", "LIC", "ICICI_PRU"]

    raw_quotes = await fetch_all_quotes(
        {
            "sum_assured": case.sum_assured or 1_000_000,
            "premium_budget": case.premium_budget or 50_000,
            "policy_tenure": case.policy_tenure or 20,
            "customer_profile": case.customer_profile or {},
            "insurers": list(set(insurers_in_kb)),
        }
    )

    kb_context = await get_kb_context_for_customer(case.customer_profile or {}, case.needs_analysis or {})
    prompt = pm.quote_comparison_personalized(
        raw_quotes, 
        case.needs_analysis or {}, 
        kb_context, 
        case.customer_profile or {}
    )
    llm_res = await llm.complete(prompt)
    comparison = rp.parse_json(llm_res["response"])

    # Clear old quotes first to prevent duplicates
    await db.execute(delete(Quote).where(Quote.case_id == case_id))

    # Fallback for parsing errors
    parse_err = False
    raw_text = ""
    if isinstance(comparison, dict) and comparison.get("parse_error"):
        parse_err = True
        raw_text = comparison.get("raw_response", "")

    # Sort raw_quotes by original rank to find top quote if needed
    raw_quotes_sorted = sorted(raw_quotes, key=lambda x: x.get("ai_rank") or 99)

    saved = []
    for q in raw_quotes:
        # Find matching ranked quote by insurer_code
        match = None
        if not parse_err and isinstance(comparison, dict) and "ranked_quotes" in comparison:
            for rq in comparison["ranked_quotes"]:
                if is_insurer_match(rq.get("insurer_code"), q["insurer_code"]):
                    match = rq
                    break
        
        rank = match.get("rank") if match else q.get("ai_rank")
        score = match.get("score") if match else q.get("score", 0.0)
        
        reason = match.get("reason", "") if match else ""
        add_ons = match.get("recommended_add_ons", []) if match else []
        
        rec_text = reason
        if add_ons:
            rec_text += "\n\nRecommended Add-ons / Riders:\n"
            for addon in add_ons:
                name = addon.get("name") or addon.get("rider_name") or ""
                r_reason = addon.get("reason") or ""
                cost_str = get_rider_cost_info(name, q.get("riders") or [])
                rec_text += f"• {name}{cost_str}: {r_reason}\n"
        rec_text = rec_text.strip()

        # Fallback if no match was found for this quote, but this is the top quote in the list
        if not rec_text and not parse_err and raw_quotes_sorted and q["insurer_code"] == raw_quotes_sorted[0]["insurer_code"]:
            summary = comparison.get("recommendation_summary")
            if summary:
                rec_text = summary

        # Fallback if parsing failed but we want to show raw LLM response on top quote
        if not rec_text and parse_err and raw_quotes_sorted and q["insurer_code"] == raw_quotes_sorted[0]["insurer_code"]:
            rec_text = re.sub(r"```(?:json)?\s*([\s\S]*?)```", r"\1", raw_text).strip()

        obj = Quote(
            id=str(uuid.uuid4()),
            case_id=case_id,
            insurer_code=q["insurer_code"],
            insurer_name=q["insurer_name"],
            product_name=q["product_name"],
            product_code=q["product_code"],
            annual_premium=q["annual_premium"],
            sum_assured=q["sum_assured"],
            policy_tenure=q["policy_tenure"],
            premium_frequency=q["premium_frequency"],
            coverage_details=q.get("coverage_details"),
            riders=q.get("riders"),
            exclusions=q.get("exclusions"),
            underwriting_requirements=q.get("underwriting_requirements"),
            ai_rank=rank,
            ai_score=score,
            ai_recommendation_text=rec_text if rec_text else None,
            raw_response=q["raw_response"],
        )
        db.add(obj)
        saved.append(obj)

    await db.execute(
        update(Case).where(Case.id == case_id).values(current_stage="QUOTE_COMPARISON")
    )
    await db.commit()

    banker = await db.get(User, case.banker_id)
    if banker:
        subject, body = stage_message(
            case.case_number,
            "QUOTE_COMPARISON",
            "Quotes are ready for review and comparison.",
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
    return {
        "message": "Quotes fetched",
        "count": len(saved),
        "quotes": [
            {
                "id": q.id,
                "insurer_name": q.insurer_name,
                "annual_premium": q.annual_premium,
                "ai_rank": q.ai_rank,
            }
            for q in saved
        ],
    }


@router.get("/case/{case_id}")
async def list_quotes(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    r = await db.execute(
        select(Quote).where(Quote.case_id == case_id).order_by(Quote.ai_rank)
    )
    quotes = r.scalars().all()
    return {
        "quotes": [
            {
                "id": q.id,
                "insurer_name": q.insurer_name,
                "product_name": q.product_name,
                "annual_premium": q.annual_premium,
                "sum_assured": q.sum_assured,
                "policy_tenure": q.policy_tenure,
                "ai_rank": q.ai_rank,
                "ai_score": q.ai_score,
                "coverage_details": q.coverage_details,
                "riders": q.riders,
                "ai_recommendation_text": q.ai_recommendation_text,
                "exclusions": q.exclusions,
                "waiting_period_days": q.waiting_period_days,
                "underwriting_requirements": q.underwriting_requirements,
                "medical_requirements": q.medical_requirements,
                "status": q.status.value if hasattr(q.status, "value") else q.status,
            }
            for q in quotes
        ]
    }
