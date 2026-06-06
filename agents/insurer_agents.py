"""
Mock Insurer Agents — realistic enterprise response structures for
HDFC Life, LIC, ICICI Prudential.
"""
import asyncio
import random
from typing import List, Dict


# ─── HDFC Life ────────────────────────────────────────────────────────

async def hdfc_quote(payload: dict) -> Dict:
    await asyncio.sleep(0.1)
    base_premium = payload.get("sum_assured", 1000000) * 0.008
    return {
        "insurer_code":  "HDFC_LIFE",
        "insurer_name":  "HDFC Life Insurance",
        "product_name":  "HDFC Life Click 2 Protect Super",
        "product_code":  "HDFC-C2PS-2024",
        "plan_type":     "TERM",
        "annual_premium": round(base_premium * random.uniform(0.9, 1.1), 2),
        "sum_assured":    payload.get("sum_assured", 1000000),
        "policy_tenure":  payload.get("policy_tenure", 20),
        "premium_frequency": "ANNUAL",
        "coverage_details": {
            "life_cover":       True,
            "accidental_cover": True,
            "critical_illness": False,
            "waiver_of_premium": True,
        },
        "riders": [
            {"name": "Accidental Death Benefit", "annual_cost": 1200},
            {"name": "Waiver of Premium",        "annual_cost": 800},
        ],
        "exclusions":     ["Suicide within 1 year", "Self-inflicted injury"],
        "waiting_period_days": 90,
        "underwriting_requirements": ["Age proof", "Income proof", "Medical report"],
        "medical_requirements":      ["Blood test", "ECG if age > 45"],
        "min_age": 18, "max_age": 65,
        "tax_benefit": "80C",
        "claim_settlement_ratio": 0.9866,
        "score": round(random.uniform(0.80, 0.95), 4),
    }


# ─── LIC ─────────────────────────────────────────────────────────────

async def lic_quote(payload: dict) -> Dict:
    await asyncio.sleep(0.1)
    base_premium = payload.get("sum_assured", 1000000) * 0.009
    return {
        "insurer_code":   "LIC",
        "insurer_name":   "Life Insurance Corporation of India",
        "product_name":   "LIC Tech Term Plan",
        "product_code":   "LIC-TECH-TERM-854",
        "policy_variant": "TERM",
        "yearly_premium": round(base_premium * random.uniform(0.9, 1.1), 2),
        "annual_premium": round(base_premium * random.uniform(0.9, 1.1), 2),
        "assured_sum":    payload.get("sum_assured", 1000000),
        "sum_assured":    payload.get("sum_assured", 1000000),
        "tenure_years":   payload.get("policy_tenure", 20),
        "policy_tenure":  payload.get("policy_tenure", 20),
        "payment_mode":   "YEARLY",
        "premium_frequency": "ANNUAL",
        "coverage": {
            "basic_life":        True,
            "accidental_death":  True,
            "disability_rider":  True,
            "health_rider":      False,
        },
        "additional_riders": [
            {"rider_name": "Accidental & Disability Benefit", "premium_per_year": 950},
        ],
        "exclusion_list": ["Suicide within 12 months", "War-related death"],
        "waiting_period_in_days": 0,
        "uw_documents":    ["ID proof", "Address proof", "Latest ITR"],
        "medical_exams":   ["BMI check", "Blood pressure", "Blood sugar"],
        "entry_age_min":   18,
        "entry_age_max":   65,
        "tax_section":     "80C and 10(10D)",
        "csr_ratio":       0.9859,
        "score": round(random.uniform(0.75, 0.92), 4),
    }


# ─── ICICI Prudential ────────────────────────────────────────────────

async def icici_quote(payload: dict) -> Dict:
    await asyncio.sleep(0.1)
    base_premium = payload.get("sum_assured", 1000000) * 0.0075
    return {
        "insurer_code":    "ICICI_PRU",
        "insurer_name":    "ICICI Prudential Life Insurance",
        "plan_name":       "ICICI Pru iProtect Smart",
        "product_name":    "ICICI Pru iProtect Smart",
        "product_id":      "ICICI-IPS-2024",
        "product_code":    "ICICI-IPS-2024",
        "plan_category":   "PURE_PROTECTION",
        "premium_amount":  round(base_premium * random.uniform(0.88, 1.05), 2),
        "annual_premium":  round(base_premium * random.uniform(0.88, 1.05), 2),
        "cover_amount":    payload.get("sum_assured", 1000000),
        "sum_assured":     payload.get("sum_assured", 1000000),
        "cover_period":    payload.get("policy_tenure", 20),
        "policy_tenure":   payload.get("policy_tenure", 20),
        "premium_paying_frequency": "ANNUAL",
        "premium_frequency":        "ANNUAL",
        "benefit_details": {
            "life_protection":       True,
            "terminal_illness":      True,
            "accidental_death_cover": True,
            "critical_illness_cover": True,
        },
        "available_riders": [
            {"rider_name": "Critical Illness Benefit",   "annual_premium": 2100},
            {"rider_name": "Accidental Death Benefit",   "annual_premium": 1100},
            {"rider_name": "Waiver of Premium on CI",    "annual_premium":  600},
        ],
        "policy_exclusions": ["Suicide within first year", "Self-harm"],
        "waiting_period": {"ci_waiting_days": 90, "life_cover_waiting_days": 0},
        "uw_requirements": ["PAN card", "Salary slips (3 months)", "Medical certificate"],
        "medical_tests":   ["Treadmill test if sum > 5Cr", "Full blood panel"],
        "minimum_age": 18, "maximum_age": 60,
        "applicable_tax_benefit": "Section 80C",
        "claim_settlement_percentage": 97.82,
        "score": round(random.uniform(0.82, 0.97), 4),
    }


# ─── SBI General Insurance ───────────────────────────────────────────

async def sbi_quote(payload: dict) -> Dict:
    await asyncio.sleep(0.1)
    base_premium = payload.get("sum_assured", 1000000) * 0.007
    return {
        "insurer_code":    "SBI_GENERAL",
        "insurer_name":    "SBI General Insurance",
        "product_name":    "SBI General Health Insurance Policy",
        "product_code":    "SBI-GHIP-2024",
        "plan_type":       "HEALTH",
        "annual_premium":  round(base_premium * random.uniform(0.9, 1.1), 2),
        "sum_assured":     payload.get("sum_assured", 1000000),
        "policy_tenure":   payload.get("policy_tenure", 20),
        "premium_frequency": "ANNUAL",
        "coverage_details": {
            "life_cover":       False,
            "accidental_cover": True,
            "critical_illness": True,
            "waiver_of_premium": False,
        },
        "riders": [
            {"name": "Critical Illness Benefit Rider", "annual_cost": 1500},
            {"name": "Accidental Death Benefit", "annual_cost": 1000},
        ],
        "exclusions":     ["Pre-existing diseases for 3 years", "Cosmetic surgery"],
        "waiting_period_days": 30,
        "underwriting_requirements": ["Age proof", "Proposal form", "Medical test if age > 55"],
        "medical_requirements":      ["Blood sugar", "Urine analysis", "ECG"],
        "min_age": 18, "max_age": 65,
        "tax_benefit": "80D",
        "claim_settlement_ratio": 0.9650,
        "score": round(random.uniform(0.85, 0.97), 4),
    }


# ─── Normalization ───────────────────────────────────────────────────

def normalize(raw: dict) -> dict:
    """Normalize any insurer response to a canonical quote schema."""
    return {
        "insurer_code":              raw.get("insurer_code", "UNKNOWN"),
        "insurer_name":              raw.get("insurer_name", "Unknown"),
        "product_name":              raw.get("product_name") or raw.get("plan_name", ""),
        "product_code":              raw.get("product_code") or raw.get("product_id", ""),
        "annual_premium":            raw.get("annual_premium") or raw.get("yearly_premium") or raw.get("premium_amount", 0),
        "sum_assured":               raw.get("sum_assured") or raw.get("assured_sum") or raw.get("cover_amount", 0),
        "policy_tenure":             raw.get("policy_tenure") or raw.get("tenure_years") or raw.get("cover_period", 0),
        "premium_frequency":         raw.get("premium_frequency") or raw.get("payment_mode", "ANNUAL"),
        "coverage_details":          raw.get("coverage_details") or raw.get("coverage") or raw.get("benefit_details", {}),
        "riders":                    raw.get("riders") or raw.get("additional_riders") or raw.get("available_riders", []),
        "exclusions":                raw.get("exclusions") or raw.get("exclusion_list") or raw.get("policy_exclusions", []),
        "waiting_period_days":       (raw.get("waiting_period") or {}).get("life_cover_waiting_days")
                                     or raw.get("waiting_period_days")
                                     or raw.get("waiting_period_in_days", 0),
        "underwriting_requirements": raw.get("underwriting_requirements") or raw.get("uw_documents") or raw.get("uw_requirements", []),
        "medical_requirements":      raw.get("medical_requirements") or raw.get("medical_exams") or raw.get("medical_tests", []),
        "score":                     raw.get("score", 0.0),
        "raw_response":              raw,
    }


async def fetch_all_quotes(payload: dict) -> List[dict]:
    """Fetch from selected insurers (present in knowledge base) and normalize."""
    insurers = payload.get("insurers")
    if insurers is None:
        insurers = ["HDFC_LIFE", "LIC", "ICICI_PRU"]
    
    tasks = []
    if "SBI_GENERAL" in insurers:
        tasks.append(sbi_quote(payload))
    if "HDFC_LIFE" in insurers:
        tasks.append(hdfc_quote(payload))
    if "LIC" in insurers:
        tasks.append(lic_quote(payload))
    if "ICICI_PRU" in insurers:
        tasks.append(icici_quote(payload))
        
    if not tasks:
        return []

    raw_results = await asyncio.gather(*tasks, return_exceptions=True)
    quotes = []
    for raw in raw_results:
        if isinstance(raw, Exception) or not isinstance(raw, dict):
            continue
        quotes.append(normalize(raw))
    # Sort by score descending
    quotes.sort(key=lambda q: q["score"], reverse=True)
    for i, q in enumerate(quotes):
        q["ai_rank"] = i + 1
    return quotes

