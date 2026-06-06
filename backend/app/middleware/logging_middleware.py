import time, uuid, logging
from fastapi import Request
logger = logging.getLogger(__name__)

async def logging_middleware(request: Request, call_next):
    rid  = str(uuid.uuid4())[:8]
    start = time.time()
    resp = await call_next(request)
    elapsed = round((time.time() - start) * 1000)
    logger.info(f"[{rid}] {request.method} {request.url.path} → {resp.status_code} ({elapsed}ms)")
    return resp
