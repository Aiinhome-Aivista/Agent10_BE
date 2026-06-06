import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    Enum,
    DateTime,
    Text,
    ForeignKey,
    JSON,
    Float,
    DECIMAL,
    BigInteger,
)
from sqlalchemy.orm import relationship
from backend.app.core.database import Base

# ─────────────────────────────── ENUMS ───────────────────────────────


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    BANKER = "BANKER"
    CUSTOMER = "CUSTOMER"
    UNDERWRITER = "UNDERWRITER"
    COMPLIANCE = "COMPLIANCE"
    OPS_ADMIN = "OPS_ADMIN"


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


# ─────────────────────────────── USER ────────────────────────────────


class User(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    must_change_password = Column(Integer, default=0)
    role = Column(Enum(UserRole), nullable=False)
    phone = Column(String(20))
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─────────────────────────────── CASE ────────────────────────────────


class Case(Base):
    __tablename__ = "cases"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_number = Column(String(50), unique=True, nullable=False, index=True)
    customer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    banker_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    current_stage = Column(Enum(CaseStage), default=CaseStage.CUSTOMER_INTAKE)
    status = Column(Enum(CaseStatus), default=CaseStatus.ACTIVE)
    customer_profile = Column(JSON)
    needs_analysis = Column(JSON)
    suitability_result = Column(JSON)
    recommendation = Column(JSON)
    sum_assured = Column(Float)
    premium_budget = Column(Float)
    policy_tenure = Column(Integer)
    kyc_status = Column(String(50), default="PENDING_KYC")
    esign_status = Column(String(50), default="NOT_STARTED")
    profile_update_request = Column(Text)
    banker_approved = Column(Integer, default=0)
    banker_remarks = Column(Text)
    banker_approved_at = Column(DateTime)
    consent_given = Column(Integer, default=0)
    consent_given_at = Column(DateTime)
    stage_entered_at = Column(DateTime, default=datetime.utcnow)
    last_activity_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = relationship("User", foreign_keys=[customer_id])
    banker = relationship("User", foreign_keys=[banker_id])
    quotes = relationship("Quote", back_populates="case", cascade="all, delete-orphan")
    policy = relationship("Policy", back_populates="case", uselist=False)
    otp_records = relationship("OTPRecord", back_populates="case")
    consent_records = relationship("ConsentRecord", back_populates="case")
    escalations = relationship("EscalationLog", back_populates="case")
    medical_requests = relationship("MedicalRequest", back_populates="case")
    audit_logs = relationship("AuditLog", back_populates="case")
    stage_logs = relationship("WorkflowStageLog", back_populates="case")


# ─────────────────────────────── BANKER INTAKE ──────────────────────


class CustomerIntakeRecord(Base):
    __tablename__ = "customer_intake_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    banker_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    source_type = Column(String(50), nullable=False, default="MANUAL")
    source_filename = Column(String(255))
    raw_payload = Column(JSON)
    normalized_payload = Column(JSON)
    status = Column(String(50), default="ACTIVE")
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    banker = relationship("User", foreign_keys=[banker_id])
    customer = relationship("User", foreign_keys=[user_id])


# ─────────────────────────────── QUOTE ───────────────────────────────


class Quote(Base):
    __tablename__ = "quotes"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False)
    insurer_code = Column(String(50), nullable=False)
    insurer_name = Column(String(200), nullable=False)
    product_name = Column(String(200), nullable=False)
    product_code = Column(String(100), nullable=False)
    annual_premium = Column(Float, nullable=False)
    sum_assured = Column(Float, nullable=False)
    policy_tenure = Column(Integer, nullable=False)
    premium_frequency = Column(String(50), default="ANNUAL")
    coverage_details = Column(JSON)
    riders = Column(JSON)
    exclusions = Column(JSON)
    waiting_period_days = Column(Integer)
    underwriting_requirements = Column(JSON)
    medical_requirements = Column(JSON)
    ai_rank = Column(Integer)
    ai_score = Column(Float)
    ai_recommendation_text = Column(Text)
    raw_response = Column(JSON)
    status = Column(String(50), default="RETRIEVED")
    retrieved_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    case = relationship("Case", back_populates="quotes")


# ─────────────────────────────── POLICY ──────────────────────────────


class Policy(Base):
    __tablename__ = "policies"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, unique=True)
    quote_id = Column(String(36), ForeignKey("quotes.id"), nullable=False)
    customer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    policy_number = Column(String(100), unique=True)
    insurer_code = Column(String(50), nullable=False)
    insurer_name = Column(String(200), nullable=False)
    product_name = Column(String(200), nullable=False)
    product_code = Column(String(100), nullable=False)
    annual_premium = Column(Float, nullable=False)
    sum_assured = Column(Float, nullable=False)
    policy_tenure = Column(Integer, nullable=False)
    premium_frequency = Column(String(50), default="ANNUAL")
    status = Column(String(50), default="DRAFT")
    proposal_data = Column(JSON)
    proposal_submitted_at = Column(DateTime)
    issued_at = Column(DateTime)
    uw_status = Column(String(50))
    uw_remarks = Column(Text)
    uw_reviewed_by = Column(String(36))
    uw_reviewed_at = Column(DateTime)
    compliance_checked = Column(Integer, default=0)
    compliance_remarks = Column(Text)
    policy_document_path = Column(String(500))
    commencement_date = Column(DateTime)
    maturity_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    case = relationship("Case", back_populates="policy")
    customer = relationship("User", foreign_keys=[customer_id])


# ─────────────────────────────── OTP ─────────────────────────────────


class OTPRecord(Base):
    __tablename__ = "otp_records"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False)
    customer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    otp_hash = Column(String(255), nullable=False)
    status = Column(String(50), default="PENDING")
    purpose = Column(String(100), default="CONSENT")
    retry_count = Column(Integer, default=0)
    resend_count = Column(Integer, default=0)
    expires_at = Column(DateTime, nullable=False)
    verified_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    case = relationship("Case", back_populates="otp_records")


# ─────────────────────────────── CONSENT ─────────────────────────────


class ConsentRecord(Base):
    __tablename__ = "consent_records"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False)
    customer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    otp_record_id = Column(String(36))
    consent_type = Column(String(100), default="POLICY_CONSENT")
    consent_text = Column(Text)
    ip_address = Column(String(50))
    user_agent = Column(String(500))
    consented_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    case = relationship("Case", back_populates="consent_records")


# ─────────────────────────────── ESCALATION ──────────────────────────


class EscalationLog(Base):
    __tablename__ = "escalation_logs"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False)
    escalation_level = Column(String(20), default="LEVEL_1")
    stage = Column(String(100), nullable=False)
    reason = Column(Text)
    assigned_to_role = Column(String(100))
    assigned_to_user = Column(String(36))
    notified = Column(Integer, default=0)
    resolved = Column(Integer, default=0)
    resolved_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    case = relationship("Case", back_populates="escalations")


# ─────────────────────────────── AUDIT LOG ───────────────────────────


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id"))
    user_id = Column(String(36))
    action = Column(String(200), nullable=False)
    entity_type = Column(String(100))
    entity_id = Column(String(36))
    old_value = Column(JSON)
    new_value = Column(JSON)
    ip_address = Column(String(50))
    user_agent = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    case = relationship("Case", back_populates="audit_logs")


# ─────────────────────────────── MEDICAL ─────────────────────────────


class MedicalRequest(Base):
    __tablename__ = "medical_requests"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False)
    customer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    requirements = Column(JSON)
    status = Column(String(50), default="PENDING")
    ops_remarks = Column(Text)
    reviewed_by = Column(String(36))
    reviewed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    case = relationship("Case", back_populates="medical_requests")
    documents = relationship("MedicalDocument", back_populates="medical_request")


class MedicalDocument(Base):
    __tablename__ = "medical_documents"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    medical_request_id = Column(
        String(36), ForeignKey("medical_requests.id"), nullable=False
    )
    customer_id = Column(String(36), nullable=False)
    document_type = Column(String(100), nullable=False)
    file_name = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    file_size = Column(Integer)
    mime_type = Column(String(100))
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    verified = Column(Integer, default=0)
    verified_by = Column(String(36))
    medical_request = relationship("MedicalRequest", back_populates="documents")


# ─────────────────────────────── KNOWLEDGE ───────────────────────────


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(500), nullable=False)
    file_name = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    file_type = Column(String(50), nullable=False)
    file_size = Column(Integer)
    status = Column(String(50), default="PENDING")
    chunk_count = Column(Integer, default=0)
    uploaded_by = Column(String(36))
    indexed_at = Column(DateTime)
    error_msg = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────── CONVERSATION ────────────────────────


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    title = Column(String(500))
    context_store = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    messages = relationship(
        "ConversationMessage",
        back_populates="session",
        order_by="ConversationMessage.created_at",
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(
        String(36), ForeignKey("conversation_sessions.id"), nullable=False
    )
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    retrieved_chunks = Column(JSON)
    graph_relations = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    session = relationship("ConversationSession", back_populates="messages")


# ─────────────────────────────── WORKFLOW LOG ────────────────────────


class WorkflowStageLog(Base):
    __tablename__ = "workflow_stage_logs"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False)
    from_stage = Column(String(100))
    to_stage = Column(String(100), nullable=False)
    triggered_by = Column(String(36))
    remarks = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    case = relationship("Case", back_populates="stage_logs")


# ─────────────────────────────── NOTIFICATION ───────────────────────


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    recipient_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    recipient_email = Column(String(255), nullable=False)
    subject = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)
    notification_type = Column(String(100), default="EMAIL")
    reference_type = Column(String(100), nullable=True)
    reference_id = Column(String(36), nullable=True)
    status = Column(String(50), default="PENDING")
    sent_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────── NOTIFICATION / EMAIL ────────────────


class EmailQueue(Base):
    __tablename__ = "email_queue"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    recipient_email = Column(String(255), nullable=False)
    subject = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String(50), default="PENDING")
    reference_type = Column(String(100))
    reference_id = Column(String(36))
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    sent_at = Column(DateTime)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
