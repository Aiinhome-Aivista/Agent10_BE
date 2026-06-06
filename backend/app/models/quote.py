import enum
from datetime import datetime
from sqlalchemy import Column, String, Enum, DateTime, Text, ForeignKey, JSON, Float, Integer
from sqlalchemy.orm import relationship
from ..core.database import Base


class QuoteStatus(str, enum.Enum):
    PENDING = "PENDING"
    RETRIEVED = "RETRIEVED"
    SELECTED = "SELECTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class Quote(Base):
    __tablename__ = "quotes"

    id = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False)
    insurer_code = Column(String(50), nullable=False)
    insurer_name = Column(String(200), nullable=False)
    product_name = Column(String(200), nullable=False)
    product_code = Column(String(100), nullable=False)

    # Quote details
    annual_premium = Column(Float, nullable=False)
    sum_assured = Column(Float, nullable=False)
    policy_tenure = Column(Integer, nullable=False)
    premium_frequency = Column(String(50), default="ANNUAL")

    # Coverage details
    coverage_details = Column(JSON, nullable=True)
    riders = Column(JSON, nullable=True)
    exclusions = Column(JSON, nullable=True)
    waiting_period_days = Column(Integer, nullable=True)

    # UW requirements
    underwriting_requirements = Column(JSON, nullable=True)
    medical_requirements = Column(JSON, nullable=True)

    # AI ranking
    ai_rank = Column(Integer, nullable=True)
    ai_score = Column(Float, nullable=True)
    ai_recommendation_text = Column(Text, nullable=True)

    # Raw response from insurer
    raw_response = Column(JSON, nullable=True)

    status = Column(Enum(QuoteStatus), default=QuoteStatus.RETRIEVED)
    retrieved_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    case = relationship("Case", back_populates="quotes")
