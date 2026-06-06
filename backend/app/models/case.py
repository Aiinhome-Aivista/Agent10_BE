import enum
from datetime import datetime
from sqlalchemy import Column, String, Integer, Enum, DateTime, Text, ForeignKey, JSON, Float
from sqlalchemy.orm import relationship
from ..core.database import Base


class CaseStage(str, enum.Enum):
    CUSTOMER_INTAKE = "CUSTOMER_INTAKE"
    NEEDS_ANALYSIS = "NEEDS_ANALYSIS"
    SUITABILITY_VALIDATION = "SUITABILITY_VALIDATION"
    QUOTE_RETRIEVAL = "QUOTE_RETRIEVAL"
    QUOTE_COMPARISON = "QUOTE_COMPARISON"
    RECOMMENDATION = "RECOMMENDATION"
    BANKER_APPROVAL = "BANKER_APPROVAL"
    OTP_CONSENT = "OTP_CONSENT"
    PROPOSAL_GENERATION = "PROPOSAL_GENERATION"
    MEDICAL_COORDINATION = "MEDICAL_COORDINATION"
    UNDERWRITING = "UNDERWRITING"
    POLICY_ISSUANCE = "POLICY_ISSUANCE"
    EXCEPTION_HANDLING = "EXCEPTION_HANDLING"
    ESCALATION = "ESCALATION"
    COMPLETED = "COMPLETED"


class CaseStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    PENDING = "PENDING"
    ON_HOLD = "ON_HOLD"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ESCALATED = "ESCALATED"


class Case(Base):
    __tablename__ = "cases"

    id = Column(String(36), primary_key=True)
    case_number = Column(String(50), unique=True, nullable=False, index=True)
    customer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    banker_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    current_stage = Column(Enum(CaseStage), default=CaseStage.CUSTOMER_INTAKE, nullable=False)
    status = Column(Enum(CaseStatus), default=CaseStatus.ACTIVE, nullable=False)

    # Customer profile
    customer_profile = Column(JSON, nullable=True)
    needs_analysis = Column(JSON, nullable=True)
    suitability_result = Column(JSON, nullable=True)
    recommendation = Column(JSON, nullable=True)

    # Financial info
    sum_assured = Column(Float, nullable=True)
    premium_budget = Column(Float, nullable=True)
    policy_tenure = Column(Integer, nullable=True)

    # Banker approval
    banker_approved = Column(Integer, default=0)
    banker_remarks = Column(Text, nullable=True)
    banker_approved_at = Column(DateTime, nullable=True)

    # OTP consent
    consent_given = Column(Integer, default=0)
    consent_given_at = Column(DateTime, nullable=True)

    # Workflow timestamps
    stage_entered_at = Column(DateTime, default=datetime.utcnow)
    last_activity_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    customer = relationship("User", foreign_keys=[customer_id])
    banker = relationship("User", foreign_keys=[banker_id])
    quotes = relationship("Quote", back_populates="case", cascade="all, delete-orphan")
    policy = relationship("Policy", back_populates="case", uselist=False)
    otp_records = relationship("OTPRecord", back_populates="case")
    consent_records = relationship("ConsentRecord", back_populates="case")
    escalations = relationship("EscalationLog", back_populates="case")
    medical_requests = relationship("MedicalRequest", back_populates="case")
    audit_logs = relationship("AuditLog", back_populates="case")
