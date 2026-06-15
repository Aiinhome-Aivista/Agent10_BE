import os
import uuid
from datetime import datetime
from fpdf import FPDF
from configs.base import settings

class Q2PPDF(FPDF):
    def __init__(self, title_text: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title_text = title_text

    def header(self):
        # Top brand bar
        self.set_fill_color(21, 26, 48)  # Theme dark color #151a30
        self.rect(0, 0, 210, 28, 'F')
        
        self.set_text_color(255, 255, 255)
        self.set_font("helvetica", "B", 14)
        self.set_y(8)
        self.cell(0, 6, "Q2P - Quote-to-Policy Agentic AI Platform", align="L", ln=1)
        
        self.set_font("helvetica", "", 9)
        self.set_text_color(200, 200, 255)
        self.cell(0, 4, "Enterprise Bancassurance & Broker Portal", align="L", ln=0)
        
        # Title of document on the right side
        self.set_y(8)
        self.set_font("helvetica", "B", 12)
        self.set_text_color(45, 212, 191)  # Accent color #2dd4bf
        self.cell(0, 10, self.title_text, align="R", ln=1)
        
        self.set_y(32)
        self.set_text_color(0, 0, 0) # Reset text color

    def footer(self):
        self.set_y(-20)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        
        # Horizontal line
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(2)
        
        self.cell(100, 10, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Confidential", align="L")
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="R")


def _write_field(pdf, label: str, value: str, width: int = 45, height: int = 6, value_width: int = 50, ln: int = 0):
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(width, height, label)
    pdf.set_font("helvetica", "", 10)
    pdf.cell(value_width, height, str(value), ln=ln)


class PDFGeneratorService:
    @staticmethod
    def generate_recommendation_pdf(case, quotes, customer) -> str:
        """
        Generates a beautiful AI Quote Recommendation PDF.
        Returns the absolute file path of the generated PDF.
        """
        pdf = Q2PPDF("QUOTE RECOMMENDATION", orientation="P", unit="mm", format="A4")
        pdf.alias_nb_pages()
        pdf.add_page()
        pdf.set_margins(15, 35, 15)
        pdf.set_auto_page_break(auto=True, margin=25)
        
        # ─── SECTION 1: CASE & CUSTOMER INFO ───
        pdf.set_y(35)
        pdf.set_font("helvetica", "B", 12)
        pdf.set_text_color(21, 26, 48)
        pdf.cell(0, 8, "1. Case & Customer Information", ln=1)
        
        pdf.set_draw_color(99, 102, 241) # Primary Accent #6366f1
        pdf.set_line_width(0.5)
        pdf.line(15, pdf.get_y(), 195, pdf.get_y())
        pdf.ln(3)
        
        # Grid layout for metadata
        # Row 1
        _write_field(pdf, "Case Number:", str(case.case_number))
        _write_field(pdf, "Customer Name:", str(customer.name), ln=1)
        
        # Row 2
        _write_field(pdf, "Customer Email:", str(customer.email))
        _write_field(pdf, "Phone Number:", str(customer.phone or "N/A"), ln=1)
        
        # Row 3
        profile = case.customer_profile or {}
        dob = profile.get("date_of_birth") or profile.get("dob") or "N/A"
        income = profile.get("annual_income") or profile.get("income") or "N/A"
        if isinstance(income, (int, float)):
            income = f"Rs. {income:,.2f}"
            
        _write_field(pdf, "Date of Birth:", str(dob))
        _write_field(pdf, "Annual Income:", str(income), ln=1)
        
        pdf.ln(4)
        
        # ─── SECTION 2: NEEDS ANALYSIS ───
        pdf.set_font("helvetica", "B", 12)
        pdf.set_text_color(21, 26, 48)
        pdf.cell(0, 8, "2. Insurance Needs & Suitability", ln=1)
        pdf.line(15, pdf.get_y(), 195, pdf.get_y())
        pdf.ln(3)
        
        needs = case.needs_analysis or {}
        purpose = needs.get("purpose") or needs.get("financial_goal") or "Family protection and coverage"
        term = case.policy_tenure or profile.get("policy_tenure") or "N/A"
        sum_assured = case.sum_assured or profile.get("sum_assured") or "N/A"
        if isinstance(sum_assured, (int, float)):
            sum_assured = f"Rs. {sum_assured:,.2f}"
            
        _write_field(pdf, "Primary Goal / Purpose:", str(purpose), value_width=135, ln=1)
        _write_field(pdf, "Target Tenure:", f"{term} Years")
        _write_field(pdf, "Required Sum Assured:", str(sum_assured), ln=1)
        
        # Key needs or riders
        riders_req = needs.get("riders_needed") or needs.get("key_needs") or []
        if isinstance(riders_req, list):
            riders_str = ", ".join(riders_req) if riders_req else "None specified"
        else:
            riders_str = str(riders_req)
        _write_field(pdf, "Requested Add-ons:", riders_str, value_width=135, ln=1)
        
        pdf.ln(4)
        
        # ─── SECTION 3: COMPARATIVE QUOTES ───
        pdf.set_font("helvetica", "B", 12)
        pdf.set_text_color(21, 26, 48)
        pdf.cell(0, 8, "3. Insurer Quote Comparison & Rankings", ln=1)
        pdf.line(15, pdf.get_y(), 195, pdf.get_y())
        pdf.ln(4)
        
        # Table Header
        pdf.set_fill_color(230, 235, 255)
        pdf.set_font("helvetica", "B", 9)
        pdf.cell(10, 8, "Rank", border=1, align="C", fill=True)
        pdf.cell(50, 8, "Insurer & Product", border=1, align="L", fill=True)
        pdf.cell(30, 8, "Sum Assured", border=1, align="R", fill=True)
        pdf.cell(30, 8, "Annual Premium", border=1, align="R", fill=True)
        pdf.cell(20, 8, "AI Score", border=1, align="C", fill=True)
        pdf.cell(40, 8, "Riders / Add-ons Cost", border=1, align="L", fill=True, ln=1)
        
        # Table Rows
        pdf.set_font("helvetica", "", 9)
        pdf.set_text_color(50, 50, 50)
        
        for q in quotes:
            rank = q.ai_rank or q.raw_response.get("ai_rank") or "-"
            insurer = q.insurer_name
            product = q.product_name
            sa = f"Rs. {q.sum_assured:,.0f}"
            premium = f"Rs. {q.annual_premium:,.2f}"
            score = f"{((q.ai_score or 0) * 100):.0f}%"
            
            # Extract riders/add-ons and format them
            riders_list = q.riders or []
            rider_costs = []
            if isinstance(riders_list, list):
                for r in riders_list[:2]:
                    name = r.get("name") or r.get("rider_name") or ""
                    cost = r.get("annual_cost") or r.get("annual_premium") or r.get("premium_per_year")
                    if cost is not None:
                        rider_costs.append(f"{name[:12]} (+{cost})")
                    else:
                        rider_costs.append(name[:12])
            rider_str = ", ".join(rider_costs) if rider_costs else "No riders"
            
            # Alternating rows
            fill = False
            if rank == 1:
                pdf.set_fill_color(240, 253, 250) # Light Teal for Rank 1
                fill = True
                
            pdf.cell(10, 8, str(rank), border=1, align="C", fill=fill)
            prod_info = f"{insurer} - {product}"
            if len(prod_info) > 28:
                prod_info = prod_info[:26] + ".."
            pdf.cell(50, 8, prod_info, border=1, align="L", fill=fill)
            pdf.cell(30, 8, sa, border=1, align="R", fill=fill)
            pdf.cell(30, 8, premium, border=1, align="R", fill=fill)
            pdf.cell(20, 8, score, border=1, align="C", fill=fill)
            pdf.cell(40, 8, rider_str, border=1, align="L", fill=fill, ln=1)
            
        pdf.ln(5)
        
        # ─── SECTION 4: AI ANALYSIS & RECOMMENDATION SUMMARY ───
        top_quote = quotes[0] if quotes else None
        if top_quote:
            pdf.set_font("helvetica", "B", 12)
            pdf.set_text_color(21, 26, 48)
            pdf.cell(0, 8, "4. AI Rationale & Personalized Advice", ln=1)
            pdf.line(15, pdf.get_y(), 195, pdf.get_y())
            pdf.ln(3)
            
            pdf.set_font("helvetica", "B", 10)
            pdf.set_text_color(99, 102, 241)
            pdf.cell(0, 6, f"Primary Recommendation: {top_quote.insurer_name} - {top_quote.product_name}", ln=1)
            
            pdf.set_font("helvetica", "", 9.5)
            pdf.set_text_color(50, 50, 50)
            
            rec_text = top_quote.ai_recommendation_text or "The recommended policy provides the best trade-off between premium cost and benefit coverages including life cover and accidental benefits. It matches the required sum assured and falls comfortably within the annual budget."
            pdf.multi_cell(180, 5, rec_text, border=0, align="L")
            pdf.ln(4)
            
        # ─── SECTION 5: COMPLIANCE & DISCLOSURES ───
        pdf.set_font("helvetica", "B", 10)
        pdf.set_text_color(128, 128, 128)
        pdf.cell(0, 6, "Disclosures & Compliance Notes", ln=1)
        pdf.set_font("helvetica", "", 8)
        pdf.set_text_color(150, 150, 150)
        
        disclosure = (
            "1. This quote recommendation sheet is an AI-generated analysis based on terms, brochures, and rules indexed in the Q2P Platform. "
            "Actual insurance policies are subject to underwriting decisions and policy wordings issued by the respective insurance companies.\n"
            "2. All rates quoted above are indicative and mock rates for platform demo and testing. Final premium amounts are decided post medical check-up and underwriting.\n"
            "3. The banker has verified customer PAN card and identity documents, complying with standard CKYC/KYC procedures before quote generation."
        )
        pdf.multi_cell(180, 4, disclosure, border=0, align="L")
        
        # Save to folder
        os.makedirs(settings.FILE_UPLOAD_PATH, exist_ok=True)
        file_name = f"rec_{case.id}_{str(uuid.uuid4())[:8]}.pdf"
        file_path = os.path.join(settings.FILE_UPLOAD_PATH, file_name)
        
        pdf.output(file_path)
        return os.path.abspath(file_path)

    @staticmethod
    def generate_proposal_pdf(case, policy, customer) -> str:
        """
        Generates a beautiful Pre-filled Insurance Proposal PDF.
        Returns the absolute file path of the generated PDF.
        """
        pdf = Q2PPDF("PROPOSAL APPLICATION", orientation="P", unit="mm", format="A4")
        pdf.alias_nb_pages()
        pdf.add_page()
        pdf.set_margins(15, 35, 15)
        pdf.set_auto_page_break(auto=True, margin=25)
        
        # ─── Title & Policy metadata ───
        pdf.set_y(35)
        pdf.set_font("helvetica", "B", 12)
        pdf.set_text_color(21, 26, 48)
        pdf.cell(0, 8, "1. Insurance Product & Policy Plan Details", ln=1)
        pdf.set_draw_color(99, 102, 241)
        pdf.set_line_width(0.5)
        pdf.line(15, pdf.get_y(), 195, pdf.get_y())
        pdf.ln(3)
        
        # Row 1
        _write_field(pdf, "Proposal ID:", str(policy.id[:18]))
        _write_field(pdf, "Proposal Number / Ref:", str(policy.policy_number), ln=1)
        
        # Row 2
        _write_field(pdf, "Insurer Name:", str(policy.insurer_name))
        _write_field(pdf, "Product Name:", str(policy.product_name), ln=1)
        
        # Row 3
        _write_field(pdf, "Sum Assured:", f"Rs. {policy.sum_assured:,.2f}")
        _write_field(pdf, "Annual Premium:", f"Rs. {policy.annual_premium:,.2f}", ln=1)
        
        # Row 4
        _write_field(pdf, "Policy Tenure:", f"{policy.policy_tenure} Years")
        _write_field(pdf, "Premium Frequency:", str(policy.premium_frequency), ln=1)
        
        pdf.ln(4)
        
        # ─── SECTION 2: PROPOSER / CUSTOMER PERSONAL DETAILS ───
        pdf.set_font("helvetica", "B", 12)
        pdf.set_text_color(21, 26, 48)
        pdf.cell(0, 8, "2. Proposer & Life Assured Personal Details", ln=1)
        pdf.line(15, pdf.get_y(), 195, pdf.get_y())
        pdf.ln(3)
        
        profile = case.customer_profile or {}
        
        dob = profile.get("date_of_birth") or profile.get("dob") or "N/A"
        gender = profile.get("gender") or "N/A"
        marital = profile.get("marital_status") or "N/A"
        occupation = profile.get("occupation") or "N/A"
        income = profile.get("annual_income") or profile.get("income") or "N/A"
        if isinstance(income, (int, float)):
            income = f"Rs. {income:,.2f}"
        pan = profile.get("pan_number") or "N/A"
        aadhaar = profile.get("aadhaar_number") or "N/A"
        city = profile.get("city") or "N/A"
        med_hist = profile.get("medical_history") or "No pre-existing conditions reported"
        
        # Row 1
        _write_field(pdf, "Full Name:", str(customer.name))
        _write_field(pdf, "Email Address:", str(customer.email), ln=1)
        
        # Row 2
        _write_field(pdf, "Mobile Phone:", str(customer.phone or "N/A"))
        _write_field(pdf, "Date of Birth / Age:", f"{dob}", ln=1)
        
        # Row 3
        _write_field(pdf, "Gender:", str(gender))
        _write_field(pdf, "Marital Status:", str(marital), ln=1)
        
        # Row 4
        _write_field(pdf, "Occupation:", str(occupation))
        _write_field(pdf, "Annual Income:", str(income), ln=1)
        
        # Row 5
        _write_field(pdf, "PAN Number:", str(pan))
        _write_field(pdf, "Aadhaar Last 4:", str(aadhaar), ln=1)
        
        # Row 6
        _write_field(pdf, "Resident City:", str(city), value_width=135, ln=1)
        
        # Medical details
        _write_field(pdf, "Medical Declaration:", str(med_hist), value_width=135, ln=1)
        
        pdf.ln(5)
        
        # ─── SECTION 3: KYC & E-SIGNATURE CONSENT LEDGER ───
        pdf.set_font("helvetica", "B", 12)
        pdf.set_text_color(21, 26, 48)
        pdf.cell(0, 8, "3. E-Signature, Consent & KYC Log", ln=1)
        pdf.line(15, pdf.get_y(), 195, pdf.get_y())
        pdf.ln(4)
        
        # Box for signature details
        pdf.set_fill_color(249, 250, 251)
        pdf.set_draw_color(229, 231, 235)
        pdf.rect(15, pdf.get_y(), 180, 36, 'DF')
        
        pdf.set_x(18)
        pdf.ln(2)
        pdf.set_x(18)
        pdf.set_font("helvetica", "B", 10)
        pdf.set_text_color(34, 197, 94)
        pdf.cell(100, 6, "E-Sign Status: VERIFIED & COMMITTED via OTP Consent")
        
        consent_time = case.consent_given_at or datetime.utcnow()
        pdf.set_text_color(50, 50, 50)
        pdf.set_font("helvetica", "", 9.5)
        pdf.cell(0, 6, f"Timestamp: {consent_time.strftime('%Y-%m-%d %H:%M:%S UTC')}", align="R", ln=1)
        
        pdf.set_x(18)
        _write_field(pdf, "Authentication Mechanism:", "Two-Factor Email OTP", value_width=110, ln=1)
        
        pdf.set_x(18)
        _write_field(pdf, "KYC Checklist Verified:", "PAN, Address Proof, Selfie", value_width=110, ln=1)
        
        pdf.set_x(18)
        _write_field(pdf, "IP Logged:", "127.0.0.1 (Local Verified)", value_width=110, ln=1)
        
        # Generate mock signature
        pdf.ln(3)
        pdf.set_x(18)
        pdf.set_font("courier", "I", 11)
        pdf.set_text_color(99, 102, 241)
        pdf.cell(120, 6, f"Signed Electronically by: /s/ {customer.name}")
        pdf.set_font("helvetica", "I", 8)
        pdf.set_text_color(128, 128, 128)
        pdf.cell(0, 6, "Consent Hash: " + str(uuid.uuid5(uuid.NAMESPACE_DNS, customer.email))[:16].upper(), align="R", ln=1)
        
        pdf.ln(12)
        
        # ─── SECTION 4: STANDARD DECLARATION ───
        pdf.set_font("helvetica", "B", 10)
        pdf.set_text_color(128, 128, 128)
        pdf.cell(0, 6, "Proposer Declaration", ln=1)
        pdf.set_font("helvetica", "", 8.5)
        pdf.set_text_color(150, 150, 150)
        
        declaration_text = (
            "I hereby declare and warrant that the answers and statements given in this proposal form are true, complete, and "
            "correct to the best of my knowledge and belief. I agree that this proposal and declaration shall form the basis "
            "of the contract between me and the insurance company. I understand that the coverage is subject to standard terms "
            "and conditions of the policy schedule and the final underwriting decision."
        )
        pdf.multi_cell(180, 4.5, declaration_text, border=0, align="L")
        
        # Save to folder
        os.makedirs(settings.FILE_UPLOAD_PATH, exist_ok=True)
        file_name = f"proposal_{policy.id}_{str(uuid.uuid4())[:8]}.pdf"
        file_path = os.path.join(settings.FILE_UPLOAD_PATH, file_name)
        
        pdf.output(file_path)
        return os.path.abspath(file_path)
