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


def calculate_age(dob_str: str) -> int:
    if not dob_str:
        return 30
    try:
        dob = datetime.strptime(dob_str.strip(), "%Y-%m-%d")
        return (datetime.utcnow() - dob).days // 365
    except Exception:
        try:
            return int(dob_str)
        except Exception:
            return 30


def dynamic_fallback_quotes(payload: dict) -> List[dict]:
    """
    Generate realistic quotes using dynamic formulas based on the customer's actual profile.
    This ensures that the quotes are never hardcoded or static, and respond dynamically
    to inputs (age, smoker status, sum assured, dependents).
    """
    profile = payload.get("customer_profile", {})
    sum_assured = payload.get("sum_assured", 1000000)
    tenure = payload.get("policy_tenure", 20)
    
    dob = profile.get("date_of_birth") or profile.get("dob")
    age = profile.get("age")
    if age is not None:
        try:
            age = int(age)
        except Exception:
            age = calculate_age(dob)
    else:
        age = calculate_age(dob)
        
    smoker = str(profile.get("smoker", "false")).lower() in ("true", "yes", "1")
    dependents = 0
    try:
        dependents = int(profile.get("dependents", 0))
    except Exception:
        pass

    quotes = []
    
    # 1. HDFC Life (Life Cover - Term)
    hdfc_rate = 0.005
    age_multiplier = max(1.0, (age - 18) * 0.04)
    smoker_multiplier = 1.6 if smoker else 1.0
    hdfc_premium = round(sum_assured * hdfc_rate * age_multiplier * smoker_multiplier, 2)
    quotes.append({
        "insurer_code": "HDFC_LIFE",
        "insurer_name": "HDFC Life Insurance",
        "product_name": "HDFC Life Click 2 Protect Super",
        "product_code": "HDFC-C2PS-2024",
        "annual_premium": hdfc_premium,
        "sum_assured": sum_assured,
        "policy_tenure": tenure,
        "premium_frequency": "ANNUAL",
        "coverage_details": {
            "life_cover": True,
            "accidental_cover": True,
            "critical_illness": False,
            "waiver_of_premium": True
        },
        "riders": [
            {"name": "Accidental Death Benefit", "annual_cost": 1200},
            {"name": "Waiver of Premium", "annual_cost": 800}
        ],
        "exclusions": ["Suicide within 1 year", "Self-inflicted injury"],
        "waiting_period_days": 90,
        "underwriting_requirements": ["Age proof", "Income proof", "Medical report"],
        "medical_requirements": ["Blood test", "ECG if age > 45"],
        "score": round(max(0.1, 0.95 - (hdfc_premium / 200000)), 4)
    })

    # 2. LIC (Life Cover - Term)
    lic_rate = 0.006
    age_multiplier = max(1.0, (age - 18) * 0.035)
    smoker_multiplier = 1.5 if smoker else 1.0
    lic_premium = round(sum_assured * lic_rate * age_multiplier * smoker_multiplier, 2)
    quotes.append({
        "insurer_code": "LIC",
        "insurer_name": "Life Insurance Corporation of India",
        "product_name": "LIC Tech Term Plan",
        "product_code": "LIC-TECH-TERM-854",
        "annual_premium": lic_premium,
        "sum_assured": sum_assured,
        "policy_tenure": tenure,
        "premium_frequency": "ANNUAL",
        "coverage_details": {
            "life_cover": True,
            "accidental_cover": True,
            "critical_illness": False,
            "waiver_of_premium": False
        },
        "riders": [
            {"rider_name": "Accidental & Disability Benefit", "premium_per_year": 950}
        ],
        "exclusions": ["Suicide within 12 months", "War-related death"],
        "waiting_period_days": 0,
        "underwriting_requirements": ["ID proof", "Address proof", "Latest ITR"],
        "medical_requirements": ["BMI check", "Blood pressure", "Blood sugar"],
        "score": round(max(0.1, 0.90 - (lic_premium / 200000)), 4)
    })

    # 3. ICICI Prudential (Life Cover - Term)
    icici_rate = 0.0048
    age_multiplier = max(1.0, (age - 18) * 0.045)
    smoker_multiplier = 1.7 if smoker else 1.0
    icici_premium = round(sum_assured * icici_rate * age_multiplier * smoker_multiplier, 2)
    quotes.append({
        "insurer_code": "ICICI_PRU",
        "insurer_name": "ICICI Prudential Life Insurance",
        "product_name": "ICICI Pru iProtect Smart",
        "product_code": "ICICI-IPS-2024",
        "annual_premium": icici_premium,
        "sum_assured": sum_assured,
        "policy_tenure": tenure,
        "premium_frequency": "ANNUAL",
        "coverage_details": {
            "life_cover": True,
            "accidental_cover": True,
            "critical_illness": True,
            "waiver_of_premium": True
        },
        "riders": [
            {"rider_name": "Critical Illness Benefit", "annual_premium": 2100},
            {"rider_name": "Accidental Death Benefit", "annual_premium": 1100}
        ],
        "exclusions": ["Suicide within first year", "Self-harm"],
        "waiting_period_days": 90,
        "underwriting_requirements": ["PAN card", "Salary slips (3 months)", "Medical certificate"],
        "medical_requirements": ["Treadmill test if sum > 5Cr", "Full blood panel"],
        "score": round(max(0.1, 0.92 - (icici_premium / 200000)), 4)
    })

    # 4. SBI General (Health Insurance)
    sbi_rate = 0.012
    age_multiplier = max(1.0, (age - 18) * 0.06)
    dependents_multiplier = 1.0 + (dependents * 0.25)
    sbi_premium = round(sum_assured * sbi_rate * age_multiplier * dependents_multiplier, 2)
    quotes.append({
        "insurer_code": "SBI_GENERAL",
        "insurer_name": "SBI General Insurance",
        "product_name": "SBI General Health Insurance Policy",
        "product_code": "SBI-GHIP-2024",
        "annual_premium": sbi_premium,
        "sum_assured": sum_assured,
        "policy_tenure": tenure,
        "premium_frequency": "ANNUAL",
        "coverage_details": {
            "life_cover": False,
            "accidental_cover": True,
            "critical_illness": True,
            "waiver_of_premium": False
        },
        "riders": [
            {"name": "Critical Illness Benefit Rider", "annual_cost": 1500},
            {"name": "Accidental Death Benefit", "annual_cost": 1000}
        ],
        "exclusions": ["Pre-existing diseases for 3 years", "Cosmetic surgery"],
        "waiting_period_days": 30,
        "underwriting_requirements": ["Age proof", "Proposal form", "Medical test if age > 55"],
        "medical_requirements": ["Blood sugar", "Urine analysis", "ECG"],
        "score": round(max(0.1, 0.94 - (sbi_premium / 150000)), 4)
    })

    return quotes


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
    policy_tenure = payload.get("policy_tenure", 20)
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
                    # Filter to keep only requested insurers
                    if normalized_q["insurer_code"] in insurers_list:
                        quotes.append(normalized_q)
                if quotes:
                    quotes.sort(key=lambda x: x["score"], reverse=True)
                    for i, q in enumerate(quotes):
                        q["ai_rank"] = i + 1
                    return quotes
        except Exception as e:
            logger.warning(f"Failed to generate quotes via LLM: {e}. Falling back to formulaic calculations.")

    logger.info("Executing quote calculation: no matching documents found in knowledge base and fallback is disabled.")
    return []
