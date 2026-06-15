from fastapi import APIRouter
from backend.app.api.v1.endpoints import (
    auth,
    cases,
    quotes,
    policies,
    otp,
    rag,
    admin,
    underwriting,
    medical,
    documents,
    kyc,
    queries,
    compliance,
    workflow,
    banker,
    notifications,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(cases.router)
api_router.include_router(quotes.router)
api_router.include_router(policies.router)
api_router.include_router(otp.router)
api_router.include_router(rag.router)
api_router.include_router(admin.router)
api_router.include_router(underwriting.router)
api_router.include_router(medical.router)
api_router.include_router(documents.router)
api_router.include_router(kyc.router)
api_router.include_router(queries.router)
api_router.include_router(compliance.router)
api_router.include_router(workflow.router)
api_router.include_router(banker.router)
api_router.include_router(notifications.router)
