import json


class PromptManager:

    @staticmethod
    def customer_intake_normalization(raw_row: dict) -> str:
        return f"""You are a data extraction assistant for insurance customer onboarding.

Normalize the following CSV or form row into a clean customer intake JSON.

ROW:
{json.dumps(raw_row, indent=2)}

Return JSON with:
- name: string
- email: string
- phone: string
- date_of_birth: string|null
- annual_income: number|null
- dependents: number|null
- risk_appetite: LOW|MEDIUM|HIGH|null
- kyc_status: string|null
- financial_goals: list of strings
- notes: string|null

Respond ONLY with valid JSON."""

    @staticmethod
    def needs_analysis(customer_profile: dict) -> str:
        return f"""You are an expert insurance advisor.

Analyze this customer profile and generate a structured needs analysis:

CUSTOMER PROFILE:
{json.dumps(customer_profile, indent=2)}

Return a JSON with keys:
- risk_profile: LOW|MEDIUM|HIGH
- recommended_coverage_type: TERM|ENDOWMENT|ULIP|HEALTH
- suggested_sum_assured: integer
- suggested_tenure: integer (years)
- key_needs: list of strings
- justification: string

Respond ONLY with valid JSON."""

    @staticmethod
    def suitability_check(customer_profile: dict, product: dict) -> str:
        return f"""You are a compliance expert.

Check if this product is suitable for this customer:

CUSTOMER: {json.dumps(customer_profile, indent=2)}
PRODUCT:  {json.dumps(product, indent=2)}

Return JSON with:
- is_suitable: true|false
- compliance_flags: list
- eligibility_score: 0.0-1.0
- remarks: string

Respond ONLY with valid JSON."""

    @staticmethod
    def quote_comparison(quotes: list, needs: dict) -> str:
        return f"""You are an insurance comparison specialist.

Rank and compare these quotes based on the customer needs:

QUOTES:
{json.dumps(quotes, indent=2)}

CUSTOMER NEEDS:
{json.dumps(needs, indent=2)}

Return JSON with:
- ranked_quotes: [{{"insurer_code": "", "rank": 1, "score": 0.95, "reason": ""}}]
- top_recommendation: insurer_code
- recommendation_summary: string

Respond ONLY with valid JSON."""

    @staticmethod
    def rag_chat(query: str, chunks: list, graph_data: list, history: str = "") -> str:
        ctx = "\n\n".join([c.get("text", "") for c in chunks[:5]])
        graph_ctx = json.dumps(graph_data[:10], indent=2) if graph_data else "[]"
        return f"""You are an insurance knowledge assistant.

{f"CONVERSATION HISTORY:{chr(10)}{history}{chr(10)}" if history else ""}

RETRIEVED KNOWLEDGE:
{ctx}

RELATED GRAPH DATA:
{graph_ctx}

USER QUESTION:
{query}

Answer based strictly on the knowledge provided. Be concise and accurate.
If you cannot answer from the context, say so clearly."""

    @staticmethod
    def exception_analysis(case_data: dict) -> str:
        return f"""You are an insurance exception specialist.

Analyze this case for compliance exceptions or anomalies:

CASE DATA:
{json.dumps(case_data, indent=2)}

Return JSON with:
- exceptions: list of {{type, severity, description}}
- risk_level: LOW|MEDIUM|HIGH|CRITICAL
- recommended_action: string

Respond ONLY with valid JSON."""

    @staticmethod
    def proposal_generation(case_data: dict, quote: dict) -> str:
        return f"""You are an insurance proposal writer.

Generate a structured proposal for this case and selected quote:

CASE: {json.dumps(case_data, indent=2)}
QUOTE: {json.dumps(quote, indent=2)}

Return JSON with:
- proposal_summary: string
- key_benefits: list
- premium_breakdown: dict
- terms_highlights: list
- next_steps: list

Respond ONLY with valid JSON."""

    @staticmethod
    def quote_comparison_personalized(quotes: list, needs: dict, kb_context: str, customer_profile: dict) -> str:
        return f"""You are an expert insurance advisor and comparison specialist.

Your task is to rank and compare the following insurance quotes specifically tailored for this customer.
Ensure your recommendation is highly personalized based on the customer's unique profile (such as their age, income, dependents, risk appetite, and goals) and the relevant knowledge base context.

CUSTOMER PROFILE:
{json.dumps(customer_profile, indent=2)}

CUSTOMER NEEDS:
{json.dumps(needs, indent=2)}

RETRIEVED KNOWLEDGE BASE CONTEXT:
{kb_context}

AVAILABLE QUOTES:
{json.dumps(quotes, indent=2)}

Instructions:
1. Rank the quotes based on how well they fit this customer's profile, budget, and needs.
2. For each ranked quote, provide a personalized recommendation narrative (reason) explaining why it was ranked this way and why it suits (or doesn't suit) this specific customer. Include direct references to details from the knowledge base context if relevant (e.g., specific rules, waiting periods, or limits).
3. Identify and recommend specific policy add-on options (riders) for each quote that would be highly beneficial for this specific customer based on their profile (e.g., if they have dependents, recommend accidental death or premium waiver; if they have health concerns/older age, recommend critical illness cover).
4. Do not send the same generic recommendation to every customer. Personalize the explanation using the customer's name, age, income level, and goals.

Return a valid JSON object with the following structure:
{{
  "ranked_quotes": [
    {{
      "insurer_code": "INSURER_CODE",
      "rank": 1,
      "score": 0.95,
      "reason": "Personalized narrative text detailing why this policy is recommended, referencing retrieved knowledge base facts and the customer's specific profile (e.g., name, age, income, dependents).",
      "recommended_add_ons": [
        {{
          "name": "Add-on / Rider Name",
          "reason": "Personalized reason why this add-on is recommended for this customer based on their profile."
        }}
      ]
    }}
  ],
  "top_recommendation": "INSURER_CODE",
  "recommendation_summary": "Overall summary of the personalized recommendation for the banker's review."
}}

Respond ONLY with valid JSON."""

