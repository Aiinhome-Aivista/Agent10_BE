import uuid
import logging
from datetime import datetime, timedelta
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from backend.app.models.all_models import Case, CaseStatus, EscalationLog, User, UserRole
from smtp.smtp_service import smtp_service
from configs.base import settings

logger = logging.getLogger(__name__)

STAGE_ROLE_MAP = {
    "BANKER_APPROVAL":       UserRole.BANKER,
    "OTP_CONSENT":           UserRole.CUSTOMER,
    "UNDERWRITING":          UserRole.UNDERWRITER,
    "MEDICAL_COORDINATION":  UserRole.OPS_ADMIN,
    "PROPOSAL_GENERATION":   UserRole.BANKER,
    "EXCEPTION_HANDLING":    UserRole.COMPLIANCE,
}


async def run_escalation_check(db: AsyncSession):
    """Check all active cases; escalate those stale for > ESCALATION_INTERVAL_MINUTES."""
    cutoff = datetime.utcnow() - timedelta(minutes=settings.ESCALATION_INTERVAL_MINUTES)

    result = await db.execute(
        select(Case).where(
            Case.status.in_(["ACTIVE", "PENDING"]),
            Case.current_stage != "COMPLETED",
            Case.stage_entered_at < cutoff,
        )
    )
    stale_cases: List[Case] = result.scalars().all()

    for case in stale_cases:
        await _escalate_case(db, case)

    logger.info(f"Escalation check: {len(stale_cases)} cases processed")


async def _escalate_case(db: AsyncSession, case: Case):
    # Count existing escalations
    res = await db.execute(
        select(EscalationLog).where(
            EscalationLog.case_id == case.id,
            EscalationLog.resolved == 0,
        )
    )
    existing = res.scalars().all()
    level_num = min(len(existing) + 1, settings.ESCALATION_MAX_LEVEL)
    level_str = f"LEVEL_{level_num}"

    role = STAGE_ROLE_MAP.get(case.current_stage.value if hasattr(case.current_stage, 'value') else case.current_stage, UserRole.SUPER_ADMIN)

    esc = EscalationLog(
        id               = str(uuid.uuid4()),
        case_id          = case.id,
        escalation_level = level_str,
        stage            = str(case.current_stage.value if hasattr(case.current_stage, 'value') else case.current_stage),
        reason           = f"Case stale for >{settings.ESCALATION_INTERVAL_MINUTES} minutes at stage {case.current_stage}",
        assigned_to_role = str(role.value if hasattr(role, 'value') else role),
    )
    db.add(esc)

    # Update case status to ESCALATED
    await db.execute(
        update(Case).where(Case.id == case.id).values(status="ESCALATED")
    )
    await db.commit()

    # Notify relevant users
    user_res = await db.execute(
        select(User).where(User.role == role, User.is_active == 1)
    )
    users = user_res.scalars().all()
    for user in users[:3]:
        await smtp_service.send_escalation(
            to=user.email,
            case_number=case.case_number,
            stage=str(case.current_stage),
            level=level_str,
        )

    logger.info(f"Escalated case {case.case_number} to {level_str}")
