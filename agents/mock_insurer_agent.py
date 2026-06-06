"""
agents/mock_insurer_agent.py — Mock insurer API integrations (HDFC, LIC, ICICI)
"""
import asyncio
import logging
import random
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# HDFC Life Mock API
# ─────────────────────────────────────────────────────────────
async def fetch_hdfc_quote(customer: dict, products: list) -> Dict[str, Any]:
    await asyncio.sleep(0.3)  # Simulate network latency
    return {
        "insurer": "HDFC Life",
        "insurer_code": "HDFC",
        "product_name": "HDFC Life Click 2 Protect Super",
        "plan_type": "Term Insurance",
        "sum_assured": customer.get("coverage_need", 5000000),
        "annual_premium": round(random.uniform(12000, 18000), 2),
        "premium_payment_term": "Regular Pay",
        "policy_tenure": 30,
        "maturity_age": 70,
        "waiting_period_months": 0,
        "riders": [
            {"name": "Accidental Death Benefit", "premium": 850},
            {"name": "Critical Illness Rider", "premium": 1200},
            {"name": "Waiver of Premium", "premium": 450},
        ],
        "exclusions": [
            "Suicide within first year",
            "Death due to pre-existing undisclosed conditions",
        ],
        "medical_requirements": {
            "required": customer.get("annual_income", 0) > 2500000,
            "tests": ["Blood Panel", "ECG", "Urine Analysis"] if customer.get("annual_income", 0) > 2500000 else [],
        },
        "underwriting_requirements": {
            "income_proof": True,
            "age_proof": True,
            "address_proof": True,
        },
        "tax_benefit": "80C and 10(10D)",
        "claim_settlement_ratio": 99.3,
        "quote_validity_days": 30,
        "api_reference": f"HDFC-Q-{random.randint(100000, 999999)}",
    }


# ─────────────────────────────────────────────────────────────
# LIC Mock API
# ─────────────────────────────────────────────────────────────
async def fetch_lic_quote(customer: dict, products: list) -> Dict[str, Any]:
    await asyncio.sleep(0.4)
    return {
        "insurer": "Life Insurance Corporation of India",
        "insurer_code": "LIC",
        "planName": "LIC Jeevan Amar",
        "planCode": "855",
        "category": "Pure Term",
        "basicSumAssured": customer.get("coverage_need", 5000000),
        "basicPremium": round(random.uniform(14000, 22000), 2),
        "premiumPaymentMode": "Yearly",
        "policyTerm": 25,
        "premiumPayingTerm": 25,
        "dateOfCommencement": "2025-04-01",
        "maturityDate": "2050-04-01",
        "waitingPeriod": {"months": 0, "conditions": "None"},
        "riderBenefits": [
            {"riderCode": "LIC-AB", "riderName": "Accident Benefit Rider", "premium": 720},
            {"riderCode": "LIC-TER", "riderName": "New Term Assurance Rider", "premium": 980},
        ],
        "exclusionList": [
            "Self-inflicted injury",
            "War or civil disturbance",
            "Undisclosed pre-existing disease",
        ],
        "medicalExamRequired": customer.get("annual_income", 0) > 2000000,
        "documentRequirements": {
            "kycDocuments": ["Aadhaar", "PAN", "Passport Size Photo"],
            "incomeProof": ["ITR", "Form 16"],
            "healthDeclaration": True,
        },
        "taxBenefit": "Section 80C",
        "claimSettlementRatio": "98.74%",
        "quotationNumber": f"LIC{random.randint(1000000, 9999999)}",
        "validTill": "2025-05-01",
    }


# ─────────────────────────────────────────────────────────────
# ICICI Prudential Mock API
# ─────────────────────────────────────────────────────────────
async def fetch_icici_quote(customer: dict, products: list) -> Dict[str, Any]:
    await asyncio.sleep(0.35)
    return {
        "provider": "ICICI Prudential Life Insurance",
        "providerCode": "IPRU",
        "solutionName": "iProtect Smart",
        "variant": "Life Cover",
        "coverageAmount": customer.get("coverage_need", 5000000),
        "annualizedPremium": round(random.uniform(11500, 17500), 2),
        "paymentFrequency": "Annual",
        "coveragePeriod": {"years": 35, "coverTill": 75},
        "pptYears": 35,
        "deferralPeriod": None,
        "addOnBenefits": [
            {"benefitCode": "ADB", "benefitName": "Accidental Death Benefit", "annualPremium": 890},
            {"benefitCode": "CI40", "benefitName": "Critical Illness (40 CI)", "annualPremium": 1450},
            {"benefitCode": "WOP", "benefitName": "Waiver of Premium on CI", "annualPremium": 520},
        ],
        "generalExclusions": [
            "Suicide (within 12 months)",
            "War and Nuclear risks",
        ],
        "medicalUnderwriting": {
            "teleMedical": True,
            "fullMedicalRequired": customer.get("annual_income", 0) > 3000000,
            "requiredTests": ["HbA1c", "Lipid Panel", "Chest X-Ray"] if customer.get("annual_income", 0) > 3000000 else [],
        },
        "documentChecklist": {
            "identity": "Aadhaar / Passport / Voter ID",
            "address": "Utility Bill / Bank Statement",
            "income": "Last 3 months salary slips or ITR",
            "photo": "2 passport size photographs",
        },
        "taxDeductions": ["80C", "80D", "10(10D)"],
        "csrFY24": "97.82%",
        "quoteId": f"IPRU-{random.randint(10000000, 99999999)}",
        "quoteGeneratedAt": "2025-04-01T10:00:00Z",
    }


# ─────────────────────────────────────────────────────────────
# Normalized quote aggregator
# ─────────────────────────────────────────────────────────────
async def fetch_all_quotes(customer: dict, products: list) -> List[Dict[str, Any]]:
    """Fetch quotes from all insurers concurrently and normalize them."""
    hdfc, lic, icici = await asyncio.gather(
        fetch_hdfc_quote(customer, products),
        fetch_lic_quote(customer, products),
        fetch_icici_quote(customer, products),
    )

    def normalize(raw: dict, code: str) -> dict:
        """Normalize insurer-specific response to a common schema."""
        premium_key = {
            "HDFC": "annual_premium",
            "LIC": "basicPremium",
            "IPRU": "annualizedPremium",
        }.get(code, "annual_premium")

        coverage_key = {
            "HDFC": "sum_assured",
            "LIC": "basicSumAssured",
            "IPRU": "coverageAmount",
        }.get(code, "sum_assured")

        return {
            "insurer_code": code,
            "insurer_name": raw.get("insurer") or raw.get("provider") or raw.get("insurer_code"),
            "product_name": raw.get("product_name") or raw.get("planName") or raw.get("solutionName"),
            "annual_premium": raw.get(premium_key, 0),
            "sum_assured": raw.get(coverage_key, 0),
            "raw_response": raw,
        }

    return [normalize(hdfc, "HDFC"), normalize(lic, "LIC"), normalize(icici, "IPRU")]
