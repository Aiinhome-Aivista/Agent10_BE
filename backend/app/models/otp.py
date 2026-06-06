import enum
from datetime import datetime
from sqlalchemy import Column, String, Enum, DateTime, Text, ForeignKey, JSON, Integer
from sqlalchemy.orm import relationship
from ..core.database import Base


class OTPStatus(str, enum.Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"


class OTPRecord(Base):
    __tablename__ = "otp_records"

    id = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False)
    customer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    otp_hash = Column(String(255), nullable=False)
    status = Column(Enum(OTPStatus), default=OTPStatus.PENDING)
    purpose = Column(String(100), default="CONSENT")
    retry_count = Column(Integer, default=0)
    resend_count = Column(Integer, default=0)
    expires_at = Column(DateTime, nullable=False)
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("Case", back_populates="otp_records")


class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False)
    customer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    otp_record_id = Column(String(36), ForeignKey("otp_records.id"), nullable=True)
    consent_type = Column(String(100), default="POLICY_CONSENT")
    consent_text = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    consented_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("Case", back_populates="consent_records")


class EscalationLevel(str, enum.Enum):
    LEVEL_1 = "LEVEL_1"
    LEVEL_2 = "LEVEL_2"
    LEVEL_3 = "LEVEL_3"


class EscalationLog(Base):
    __tablename__ = "escalation_logs"

    id = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False)
    escalation_level = Column(Enum(EscalationLevel), default=EscalationLevel.LEVEL_1)
    stage = Column(String(100), nullable=False)
    reason = Column(Text, nullable=True)
    assigned_to_role = Column(String(100), nullable=True)
    assigned_to_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    notified = Column(Integer, default=0)
    resolved = Column(Integer, default=0)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("Case", back_populates="escalations")


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(String(36), primary_key=True)
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


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    action = Column(String(200), nullable=False)
    entity_type = Column(String(100), nullable=True)
    entity_id = Column(String(36), nullable=True)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("Case", back_populates="audit_logs")


class MedicalRequest(Base):
    __tablename__ = "medical_requests"

    id = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False)
    customer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    requirements = Column(JSON, nullable=True)
    status = Column(String(50), default="PENDING")
    ops_remarks = Column(Text, nullable=True)
    reviewed_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    case = relationship("Case", back_populates="medical_requests")
    documents = relationship("MedicalDocument", back_populates="medical_request")


class MedicalDocument(Base):
    __tablename__ = "medical_documents"

    id = Column(String(36), primary_key=True)
    medical_request_id = Column(String(36), ForeignKey("medical_requests.id"), nullable=False)
    customer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    document_type = Column(String(100), nullable=False)
    file_name = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    verified = Column(Integer, default=0)
    verified_by = Column(String(36), nullable=True)

    medical_request = relationship("MedicalRequest", back_populates="documents")


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    title = Column(String(500), nullable=True)
    context_store = Column(JSON, nullable=True)   # LLM context array
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship("ConversationMessage", back_populates="session", order_by="ConversationMessage.created_at")


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id = Column(String(36), primary_key=True)
    session_id = Column(String(36), ForeignKey("conversation_sessions.id"), nullable=False)
    role = Column(String(20), nullable=False)   # user | assistant
    content = Column(Text, nullable=False)
    retrieved_chunks = Column(JSON, nullable=True)
    graph_relations = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ConversationSession", back_populates="messages")
