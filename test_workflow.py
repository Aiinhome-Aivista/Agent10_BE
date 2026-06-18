import asyncio
import os
import sys
import uuid
from datetime import datetime

# Add project path to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select, update
from backend.app.core.database import AsyncSessionLocal
from backend.app.models.all_models import Case, User, UserRole, CaseStage
from backend.app.api.v1.endpoints.workflow import _run_workflow_bg

async def test():
    # 1. Get or create banker
    async with AsyncSessionLocal() as db:
        res_b = await db.execute(select(User).where(User.role == UserRole.BANKER))
        banker = res_b.scalars().first()
        if not banker:
            banker = User(
                id=str(uuid.uuid4()), name="Test Banker", email=f"banker-{uuid.uuid4()}@test.com",
                password_hash="hash", role=UserRole.BANKER
            )
            db.add(banker)
            await db.commit()
            await db.refresh(banker)
            
    # 2. Get or create customer
    async with AsyncSessionLocal() as db:
        res_c = await db.execute(select(User).where(User.role == UserRole.CUSTOMER))
        customer = res_c.scalars().first()
        if not customer:
            customer = User(
                id=str(uuid.uuid4()), name="Test Customer", email=f"customer-{uuid.uuid4()}@test.com",
                password_hash="hash", role=UserRole.CUSTOMER
            )
            db.add(customer)
            await db.commit()
            await db.refresh(customer)

    # 3. Create case
    async with AsyncSessionLocal() as db:
        case = Case(
            id=str(uuid.uuid4()),
            case_number=f"TEST-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}",
            customer_id=customer.id,
            banker_id=banker.id,
            current_stage=CaseStage.CUSTOMER_INTAKE,
            customer_profile={"name": "Test Customer", "age": 30, "income": 500000},
            sum_assured=1000000,
            premium_budget=20000,
            policy_tenure=20
        )
        db.add(case)
        await db.commit()
        print(f"1. Created case. Stage: {case.current_stage}")
        case_id = case.id

    # 4. Simulate banker Create Case & Trigger Workflow
    await _run_workflow_bg(case_id)
    
    async with AsyncSessionLocal() as db:
        res_case = await db.execute(select(Case).where(Case.id == case_id))
        case = res_case.scalar_one()
        print(f"2. Triggered initial workflow. Stage: {case.current_stage}")

        # 5. Banker Approve
        case.banker_approved = 1
        case.current_stage = CaseStage.BANKER_APPROVAL
        await db.commit()
        print(f"3. Banker approved. Stage: {case.current_stage}")

        # 6. Customer OTP consent
        case.consent_given = 1
        case.current_stage = CaseStage.OTP_CONSENT
        await db.commit()
        print(f"4. Customer OTP consented. Stage: {case.current_stage}")

        # 7. Banker clicks Submit to Underwriter
        case.current_stage = CaseStage.PROPOSAL_GENERATION
        await db.commit()
        print(f"5. Banker updated stage to PROPOSAL_GENERATION. Stage: {case.current_stage}")

    # 8. Second POST /workflow/case/{id}/run
    await _run_workflow_bg(case_id)
    
    async with AsyncSessionLocal() as db:
        res_case = await db.execute(select(Case).where(Case.id == case_id))
        case = res_case.scalar_one()
        print(f"6. Banker triggered workflow post-proposal. Stage: {case.current_stage}")

if __name__ == '__main__':
    asyncio.run(test())
