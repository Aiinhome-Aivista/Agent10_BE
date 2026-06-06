import enum
from datetime import datetime
from sqlalchemy import Column, String, Enum, DateTime, Text, ForeignKey, JSON, Float, Integer
from sqlalchemy.orm import relationship
from ..core.database import Base


class PolicyStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    ISSUED = "ISSUED"
    REJECTED = "REJECTED"
    LAPSED = "LAPSED"
    CANCELLED = "CANCELLED"


class Policy(Base):
    __tablename__ = "policies"

    id = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, unique=True)
    quote_id = Column(String(36), ForeignKey("quotes.id"), nullable=False)
    customer_id = Column(String(36), ForeignKey("users.id"), nullable=False)

    policy_number = Column(String(100), unique=True, nullable=True)
    insurer_code = Column(String(50), nullable=False)
    insurer_name = Column(String(200), nullable=False)
    product_name = Column(String(200), nullable=False)
    product_code = Column(String(100), nullable=False)

    annual_premium = Column(Float, nullable=False)
    sum_assured = Column(Float, nullable=False)
    policy_tenure = Column(Integer, nullable=False)
    premium_frequency = Column(String(50), default="ANNUAL")

    status = Column(Enum(PolicyStatus), default=PolicyStatus.DRAFT)

    # Proposal & issuance
    proposal_data = Column(JSON, nullable=True)
    proposal_submitted_at = Column(DateTime, nullable=True)
    issued_at = Column(DateTime, nullable=True)

    # Underwriting
    uw_status = Column(String(50), nullable=True)
    uw_remarks = Column(Text, nullable=True)
    uw_reviewed_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    uw_reviewed_at = Column(DateTime, nullable=True)

    # Compliance
    compliance_checked = Column(Integer, default=0)
    compliance_remarks = Column(Text, nullable=True)

    # Documents
    policy_document_path = Column(String(500), nullable=True)

    commencement_date = Column(DateTime, nullable=True)
    maturity_date = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    case = relationship("Case", back_populates="policy")
    customer = relationship("User", foreign_keys=[customer_id])
