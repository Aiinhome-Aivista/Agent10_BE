"""
Main Orchestrator Agent — LangGraph StateGraph driving the full Q2P workflow.
"""
from typing import TypedDict, Optional, List, Any
from langgraph.graph import StateGraph, END

from llm.llm_service   import LLMService
from llm.prompt_manager import PromptManager
from llm.response_parser import ResponseParser
from agents.insurer_agents import fetch_all_quotes
from rag.rag_pipeline import get_kb_context_for_customer
from backend.app.core.database import AsyncSessionLocal
from backend.app.models.all_models import KnowledgeDocument
from sqlalchemy import select


class WorkflowState(TypedDict):
    case_id:            str
    customer_profile:   dict
    needs_analysis:     dict
    suitability_result: dict
    quotes:             List[dict]
    comparison:         dict
    recommendation:     dict
    banker_approved:    bool
    proposal:           dict
    exceptions:         List[dict]
    stage:              str
    llm_context:        List[Any]
    error:              Optional[str]


llm = LLMService()
pm  = PromptManager()
rp  = ResponseParser()


# ─── Node: Profile & Needs Analysis ──────────────────────────────────

async def node_needs_analysis(state: WorkflowState) -> WorkflowState:
    prompt = pm.needs_analysis(state["customer_profile"])
    result = await llm.complete(prompt, state.get("llm_context", []))
    parsed = rp.parse_json(result["response"])
    return {
        **state,
        "needs_analysis": parsed,
        "llm_context":    result["context"],
        "stage":          "NEEDS_ANALYSIS",
    }


# ─── Node: Suitability Validation ────────────────────────────────────

async def node_suitability(state: WorkflowState) -> WorkflowState:
    products = [{"type": "TERM_LIFE", "min_age": 18, "max_age": 65}]
    results  = []
    for p in products:
        prompt = pm.suitability_check(state["customer_profile"], p)
        res    = await llm.complete(prompt, state.get("llm_context", []))
        results.append(rp.parse_json(res["response"]))
    return {
        **state,
        "suitability_result": {"products": results},
        "stage":              "SUITABILITY_VALIDATION",
    }


# ─── Node: Quote Retrieval ────────────────────────────────────────────

async def node_quote_retrieval(state: WorkflowState) -> WorkflowState:
    # Query database to find indexed insurers
    insurers_in_kb = []
    docs_exist = False
    try:
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.status == 'INDEXED'))
            docs = r.scalars().all()
            docs_exist = len(docs) > 0
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
    except Exception:
        pass
        
    if not insurers_in_kb:
        insurers_in_kb = ["HDFC_LIFE", "LIC", "ICICI_PRU"]

    payload = {
        "sum_assured":    state["customer_profile"].get("sum_assured", 1000000),
        "premium_budget": state["customer_profile"].get("premium_budget", 50000),
        "policy_tenure":  state["customer_profile"].get("policy_tenure", 20),
        "customer_profile": state["customer_profile"],
        "insurers": list(set(insurers_in_kb)),
    }
    quotes = await fetch_all_quotes(payload)
    return {**state, "quotes": quotes, "stage": "QUOTE_RETRIEVAL"}


# ─── Node: Quote Comparison ───────────────────────────────────────────

async def node_comparison(state: WorkflowState) -> WorkflowState:
    kb_context = await get_kb_context_for_customer(state["customer_profile"], state["needs_analysis"])
    prompt  = pm.quote_comparison_personalized(
        state["quotes"], 
        state["needs_analysis"], 
        kb_context, 
        state["customer_profile"]
    )
    result  = await llm.complete(prompt, state.get("llm_context", []))
    parsed  = rp.parse_json(result["response"])
    return {
        **state,
        "comparison":  parsed,
        "llm_context": result["context"],
        "stage":       "QUOTE_COMPARISON",
    }


# ─── Node: Recommendation ────────────────────────────────────────────

async def node_recommendation(state: WorkflowState) -> WorkflowState:
    ranked = state["comparison"].get("ranked_quotes", [])
    top = ranked[0] if ranked else {}
    return {
        **state,
        "recommendation": {
            "top_insurer":   top.get("insurer_code"),
            "score":         top.get("score"),
            "summary":       state["comparison"].get("recommendation_summary"),
            "add_ons":       top.get("recommended_add_ons", []),
        },
        "stage": "RECOMMENDATION",
    }


# ─── Node: HITL Banker Approval ───────────────────────────────────────

async def node_banker_approval(state: WorkflowState) -> WorkflowState:
    # Pauses here — banker_approved is set externally via API
    return {**state, "stage": "BANKER_APPROVAL"}


# ─── Node: Exception Check ────────────────────────────────────────────

async def node_exception_check(state: WorkflowState) -> WorkflowState:
    prompt  = pm.exception_analysis({"case_id": state["case_id"], "profile": state["customer_profile"]})
    result  = await llm.complete(prompt)
    parsed  = rp.parse_json(result["response"])
    return {
        **state,
        "exceptions": parsed.get("exceptions", []),
        "stage":      "EXCEPTION_HANDLING" if parsed.get("exceptions") else state["stage"],
    }


# ─── Conditional edge ────────────────────────────────────────────────

def route_after_approval(state: WorkflowState) -> str:
    if state.get("banker_approved"):
        return "exception_check"
    return END  # pause until approved


# ─── Build Graph ─────────────────────────────────────────────────────

def build_graph():
    g = StateGraph(WorkflowState)
    g.add_node("needs_analysis",  node_needs_analysis)
    g.add_node("suitability",     node_suitability)
    g.add_node("quote_retrieval", node_quote_retrieval)
    g.add_node("comparison",      node_comparison)
    g.add_node("recommendation",  node_recommendation)
    g.add_node("banker_approval", node_banker_approval)
    g.add_node("exception_check", node_exception_check)

    g.set_entry_point("needs_analysis")
    g.add_edge("needs_analysis",  "suitability")
    g.add_edge("suitability",     "quote_retrieval")
    g.add_edge("quote_retrieval", "comparison")
    g.add_edge("comparison",      "recommendation")
    g.add_edge("recommendation",  "banker_approval")
    g.add_conditional_edges("banker_approval", route_after_approval, {
        "exception_check": "exception_check",
        END:               END,
    })
    g.add_edge("exception_check", END)

    return g.compile()
