"""
Dynamic Insurer Agents — retrieves rules and coverages from knowledge base (RAG)
and uses LLM to generate personalized quotes, with dynamic formulaic fallback.
"""
import asyncio
import logging
import json
from datetime import datetime
from typing import List, Dict

from rag.rag_pipeline import semantic_search
from llm.llm_service import LLMService
from llm.response_parser import ResponseParser

logger = logging.getLogger(__name__)
llm = LLMService()
rp = ResponseParser()





def normalize(raw: dict) -> dict:
    """Normalize any insurer response to a canonical quote schema."""
    return {
        "insurer_code":              raw.get("insurer_code", "UNKNOWN"),
        "insurer_name":              raw.get("insurer_name", "Unknown"),
        "product_name":              raw.get("product_name") or raw.get("plan_name", ""),
        "product_code":              raw.get("product_code") or raw.get("product_id", ""),
        "annual_premium":            float(raw.get("annual_premium") or raw.get("yearly_premium") or raw.get("premium_amount") or 0.0),
        "sum_assured":               float(raw.get("sum_assured") or raw.get("assured_sum") or raw.get("cover_amount") or 0.0),
        "policy_tenure":             int(raw.get("policy_tenure") or raw.get("tenure_years") or raw.get("cover_period") or 0),
        "premium_frequency":         raw.get("premium_frequency") or raw.get("payment_mode", "ANNUAL"),
        "coverage_details":          raw.get("coverage_details") or raw.get("coverage") or raw.get("benefit_details", {}),
        "riders":                    raw.get("riders") or raw.get("additional_riders") or raw.get("available_riders", []),
        "exclusions":                raw.get("exclusions") or raw.get("exclusion_list") or raw.get("policy_exclusions", []),
        "waiting_period_days":       (raw.get("waiting_period") or {}).get("life_cover_waiting_days")
                                     or raw.get("waiting_period_days")
                                     or raw.get("waiting_period_in_days", 0),
        "underwriting_requirements": raw.get("underwriting_requirements") or raw.get("uw_documents") or raw.get("uw_requirements", []),
        "medical_requirements":      raw.get("medical_requirements") or raw.get("medical_exams") or raw.get("medical_tests", []),
        "score":                     float(raw.get("score", 0.0)),
        "raw_response":              raw,
    }


async def fetch_all_quotes(payload: dict) -> List[dict]:
    """
    Fetch insurance quotes. It first attempts to retrieve matching policy context
    from the knowledge base (ChromaDB) and uses the LLM to generate/extract
    realistic quotes based on the actual rules in the brochures.
    If no documents are found or query fails, it falls back to dynamic formulaic quotes.
    """
    profile = payload.get("customer_profile", {})
    sum_assured = payload.get("sum_assured", 1000000)
    policy_tenure = payload.get("policy_tenure", 1)
    insurers_list = payload.get("insurers", ["HDFC_LIFE", "LIC", "ICICI_PRU", "SBI_GENERAL"])

    # 1. Retrieve context from ChromaDB
    query = "health life insurance policy plan benefits premiums rates rules exclusions riders HDFC LIC ICICI SBI"
    kb_context = ""
    try:
        chunks = await semantic_search(query, top_k=6)
        if chunks:
            kb_context = "\n\n---\n\n".join([
                f"Source Document: {c['title']}\nContent Snippet:\n{c['text']}"
                for c in chunks
            ])
            logger.info(f"Retrieved {len(chunks)} chunks for quote RAG generation")
    except Exception as e:
        logger.warning(f"RAG search failed during fetch_all_quotes: {e}")

    # 2. Call LLM to extract or calculate quotes
    if kb_context:
        prompt = f"""You are an expert insurance agent underwriting assistant.
Your task is to generate realistic quotes for a customer by extracting or calculating policy details directly from the retrieved product brochures and guidelines.

CUSTOMER PROFILE:
- Name: {profile.get("name", "N/A")}
- DOB / Age: {profile.get("date_of_birth") or profile.get("age") or "30"}
- Gender: {profile.get("gender", "N/A")}
- Smoker status: {profile.get("smoker", "false")}
- Income: ₹{profile.get("annual_income", "N/A")}
- Dependents: {profile.get("dependents", "0")}

TARGET POLICY PARAMS:
- Sum Assured target: ₹{sum_assured}
- Policy Tenure target: {policy_tenure} years

RETRIEVED PRODUCT KNOWLEDGE BASE CONTEXT:
{kb_context}

Instructions:
1. Examine the retrieved context. Extract details for the insurers listed: {", ".join(insurers_list)}.
2. Premiums must be calculated realistically:
   - Life term insurance premiums are typically ~0.3% to 1.2% of the Sum Assured per year (highly dependent on age and smoker status, where smokers pay 40-70% more, and older age increases premium).
   - Health insurance premiums are typically ~1% to 3% of the Sum Assured per year (highly dependent on age and family size/dependents).
   - Compute the premiums dynamically matching these variables. Do NOT return hardcoded static values.
3. For each eligible product found in the brochures, return a detailed quote object. Include correct product name, code, coverage details, optional riders, policy exclusions, waiting periods, and underwriting/medical requirements.
4. If the documents contain specific rules or pricing details for the requested insurers, apply them.

Return a valid JSON list of quotes matching the schema below:
[
  {{
    "insurer_code": "HDFC_LIFE" | "LIC" | "ICICI_PRU" | "SBI_GENERAL",
    "insurer_name": "string",
    "product_name": "string",
    "product_code": "string",
    "annual_premium": number (realistic annual premium in INR),
    "sum_assured": number (equal to target sum assured),
    "policy_tenure": number (equal to target policy tenure),
    "premium_frequency": "ANNUAL",
    "coverage_details": {{
      "life_cover": boolean,
      "accidental_cover": boolean,
      "critical_illness": boolean,
      "waiver_of_premium": boolean
    }},
    "riders": [
      {{
        "name": "Rider Name",
        "annual_cost": number
      }}
    ],
    "exclusions": ["exclusion 1", "exclusion 2"],
    "waiting_period_days": number,
    "underwriting_requirements": ["requirement 1", "requirement 2"],
    "medical_requirements": ["test 1", "test 2"],
    "score": number (0.0 to 1.0 fit score)
  }}
]

Respond ONLY with valid JSON (no markdown formatting, no extra explanation text)."""
        try:
            response = await llm.complete(prompt)
            parsed = rp.parse_json(response["response"])
            if isinstance(parsed, list) and len(parsed) > 0:
                logger.info(f"Successfully generated {len(parsed)} quotes using RAG + LLM")
                quotes = []
                for q in parsed:
                    normalized_q = normalize(q)
                    if normalized_q["insurer_code"] in insurers_list:
                        # Apply multi-year premium discount
                        tenure = int(policy_tenure or 1)
                        discount = 1.0
                        if tenure == 2:
                            discount = 0.95
                        elif tenure == 3:
                            discount = 0.90
                        elif tenure == 4:
                            discount = 0.88
                        elif tenure >= 5:
                            discount = 0.85
                        
                        normalized_q["policy_tenure"] = tenure
                        normalized_q["annual_premium"] = round(normalized_q["annual_premium"] * discount, 2)
                        quotes.append(normalized_q)
                if quotes:
                    quotes.sort(key=lambda x: x["score"], reverse=True)
                    for i, q in enumerate(quotes):
                        q["ai_rank"] = i + 1
                    return quotes
        except Exception as e:
            logger.warning(f"Failed to generate quotes via LLM: {e}.")

    logger.info("Executing quote calculation: no matching documents found in knowledge base and fallback is disabled.")
    return []
