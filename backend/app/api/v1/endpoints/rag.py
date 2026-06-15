import uuid, json, os, time, logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header
from pydantic import BaseModel

logger = logging.getLogger(__name__)
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, require_roles
from backend.app.models.all_models import (
    KnowledgeDocument, ConversationSession, ConversationMessage, User
)
from rag.rag_pipeline  import ingest_document, semantic_search, list_documents, delete_document
from rag.graph_retriever import retrieve_related
from llm.llm_service    import LLMService
from llm.prompt_manager  import PromptManager
from configs.base import settings

router = APIRouter(prefix="/rag", tags=["rag"])
llm = LLMService()
pm  = PromptManager()


def generate_chronological_id(offset_ms: int = 0) -> str:
    prefix = f"{int(time.time() * 1000000) + offset_ms:016d}"
    suffix = uuid.uuid4().hex[:19]
    return f"{prefix}-{suffix}"



# ─── Document Upload & Ingestion ─────────────────────────────────────

@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "BANKER", "UNDERWRITER", "COMPLIANCE", "OPS_ADMIN")),
):
    os.makedirs(settings.FILE_UPLOAD_PATH, exist_ok=True)
    doc_id    = str(uuid.uuid4())
    save_path = os.path.join(settings.FILE_UPLOAD_PATH, f"{doc_id}_{file.filename}")

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    doc = KnowledgeDocument(
        id=doc_id, title=title,
        file_name=file.filename, file_path=save_path,
        file_type=os.path.splitext(file.filename)[1].lower(),
        file_size=len(content), status="PROCESSING",
        uploaded_by=str(current_user.id),
    )
    db.add(doc)
    await db.commit()

    try:
        chunk_count = await ingest_document(save_path, doc_id, title)
        await db.execute(update(KnowledgeDocument).where(KnowledgeDocument.id == doc_id).values(
            status="INDEXED", chunk_count=chunk_count
        ))
        await db.commit()
        return {"message": "Document indexed", "doc_id": doc_id, "chunks": chunk_count}
    except Exception as e:
        await db.execute(update(KnowledgeDocument).where(KnowledgeDocument.id == doc_id).values(
            status="FAILED", error_msg=str(e)
        ))
        await db.commit()
        raise HTTPException(500, f"Indexing failed: {e}")


@router.post("/documents/suggest-title")
async def suggest_document_title(
    file: UploadFile = File(...),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "BANKER", "UNDERWRITER", "COMPLIANCE", "OPS_ADMIN")),
):
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()

    content_bytes = await file.read()

    text_sample = ""
    try:
        if ext == ".pdf":
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(content_bytes))
            if len(reader.pages) > 0:
                text_sample = reader.pages[0].extract_text() or ""
        elif ext in (".docx", ".doc"):
            import io
            import docx2txt
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp:
                temp.write(content_bytes)
                temp_path = temp.name
            try:
                text_sample = docx2txt.process(temp_path)
            finally:
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
        else:
            text_sample = content_bytes.decode("utf-8", errors="ignore")
    except Exception as e:
        text_sample = ""

    text_sample = text_sample.strip()[:1500]

    if not text_sample:
        fallback_title = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").title()
        return {"suggested_title": fallback_title}

    prompt = (
        "You are an AI assistant helping organize an insurance knowledge base. "
        "Analyze the following document snippet and generate a very brief, concise, professional document title (maximum 5-6 words). "
        "Return ONLY the plain title text, nothing else (no introductory phrases, no quotes, no periods).\n\n"
        f"Document snippet:\n{text_sample}\n\n"
        "Suggested Title:"
    )
    try:
        suggested_title = await llm.complete_text(prompt)
        suggested_title = suggested_title.strip().strip('"').strip("'").strip()
        if not suggested_title or len(suggested_title) > 100:
            suggested_title = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").title()
    except Exception:
        suggested_title = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").title()

    return {"suggested_title": suggested_title}


@router.get("/documents")
async def list_kb_documents(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    r = await db.execute(select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc()))
    docs = r.scalars().all()
    return {"documents": [{"id": d.id, "title": d.title, "file_name": d.file_name,
                           "status": d.status, "chunk_count": d.chunk_count,
                           "created_at": d.created_at.isoformat() if d.created_at else None} for d in docs]}


@router.delete("/documents/{doc_id}")
async def remove_document(doc_id: str, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(require_roles("SUPER_ADMIN", "BANKER", "UNDERWRITER", "COMPLIANCE", "OPS_ADMIN"))):
    await delete_document(doc_id)
    from sqlalchemy import delete as sql_delete
    await db.execute(sql_delete(KnowledgeDocument).where(KnowledgeDocument.id == doc_id))
    await db.commit()
    return {"message": "Document removed"}


@router.get("/documents/{doc_id}/view")
async def view_document(
    doc_id: str,
    token: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import FileResponse
    from backend.app.core.security import decode_token
    from backend.app.repositories.user_repository import UserRepository

    auth_token = token
    if not auth_token and authorization:
        if authorization.startswith("Bearer "):
            auth_token = authorization.split(" ")[1]

    if not auth_token:
        raise HTTPException(status_code=401, detail="Authentication token required")

    try:
        payload = decode_token(auth_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await UserRepository(db).get_by_id(payload.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Unauthorized or inactive user")

    r = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id))
    doc = r.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    media_type = "application/octet-stream"
    if doc.file_type == ".pdf":
        media_type = "application/pdf"
    elif doc.file_type == ".txt":
        media_type = "text/plain"

    return FileResponse(
        doc.file_path,
        media_type=media_type,
        filename=doc.file_name,
        content_disposition_type="inline"
    )


# ─── RAG Chat ────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message:    str
    session_id: Optional[str] = None


@router.post("/chat")
async def rag_chat(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Get or create session
    session = None
    if body.session_id:
        r = await db.execute(select(ConversationSession).where(ConversationSession.id == body.session_id))
        session = r.scalar_one_or_none()

    if not session:
        session = ConversationSession(
            id=str(uuid.uuid4()),
            user_id=str(current_user.id),
            title=body.message[:80],
            context_store="[]",
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)

    # Load LLM context
    llm_context = json.loads(session.context_store or "[]")

    # Semantic + graph retrieval
    chunks      = await semantic_search(body.message, top_k=5)
    query_terms = body.message.split()[:5]
    graph_data  = retrieve_related(query_terms)

    # Build history string (last 4 messages)
    hist_r   = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session.id)
        .order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc()).limit(4)
    )
    history_msgs = list(hist_r.scalars().all())
    # Sort ascending in memory using (created_at, id) for robust sequencing
    history_msgs.sort(key=lambda m: (m.created_at or datetime.min, m.id))
    history_str  = "\n".join([f"{m.role.upper()}: {m.content}" for m in history_msgs])

    prompt  = pm.rag_chat(body.message, chunks, graph_data, history_str)
    try:
        llm_res = await llm.complete(prompt, llm_context)
        ai_response = llm_res["response"]
        new_context = llm_res["context"]
    except Exception as e:
        logger.error(f"RAG chat LLM call failed: {e}")
        ai_response = "I apologize, but the LLM service is currently offline or unreachable. Please try again later."
        new_context = llm_context

    # Persist messages with sequential timestamps and chronological IDs to guarantee exact order
    user_time = datetime.utcnow()
    user_msg_id = generate_chronological_id(offset_ms=0)
    ai_msg_id = generate_chronological_id(offset_ms=1000) # Offset of 1ms (1000us) to ensure assistant sorts second
    
    user_msg = ConversationMessage(
        id=user_msg_id, session_id=session.id, role="user", content=body.message,
        created_at=user_time
    )
    ai_msg = ConversationMessage(
        id=ai_msg_id, session_id=session.id, role="assistant",
        content=ai_response,
        retrieved_chunks=[{"text": c["text"][:200], "score": c["score"]} for c in chunks],
        graph_relations=graph_data,
        created_at=user_time + timedelta(seconds=1)
    )
    db.add(user_msg)
    db.add(ai_msg)

    await db.execute(update(ConversationSession).where(ConversationSession.id == session.id).values(
        context_store=json.dumps(new_context)
    ))
    await db.commit()

    return {
        "session_id": session.id,
        "response":   ai_response,
        "sources":    [{"title": c.get("title"), "score": c.get("score")} for c in chunks],
    }


@router.get("/sessions")
async def list_sessions(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    r = await db.execute(
        select(ConversationSession).where(ConversationSession.user_id == str(current_user.id))
        .order_by(ConversationSession.updated_at.desc())
    )
    sessions = r.scalars().all()
    return {"sessions": [{"id": s.id, "title": s.title, "updated_at": s.updated_at.isoformat() if s.updated_at else None} for s in sessions]}


@router.get("/sessions/{session_id}/messages")
async def session_messages(session_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    r = await db.execute(
        select(ConversationMessage).where(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
    )
    msgs = list(r.scalars().all())
    # Sort: chronologically first, then secondary sort on our chronological ID
    msgs.sort(key=lambda m: (m.created_at or datetime.min, m.id))
    return {"messages": [{"id": m.id, "role": m.role, "content": m.content,
                          "created_at": m.created_at.isoformat() if m.created_at else None} for m in msgs]}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    r = await db.execute(select(ConversationSession).where(ConversationSession.id == session_id))
    session = r.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized to delete this session")

    from sqlalchemy import delete as sql_delete
    await db.execute(sql_delete(ConversationMessage).where(ConversationMessage.session_id == session_id))
    await db.delete(session)
    await db.commit()

    return {"message": "Session deleted"}
