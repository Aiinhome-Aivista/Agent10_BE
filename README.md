# Q2P — Quote-to-Policy Agentic AI Platform

Enterprise-grade AI-native insurance workflow automation platform built with FastAPI, React, LangGraph, Local Mistral LLM, ChromaDB (local), ArangoDB, and MySQL.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    React Frontend (Vite)                     │
│   Landing Page · 6 Persona Dashboards · RAG Chat · OTP      │
└─────────────────────────┬───────────────────────────────────┘
                          │ REST /api/v1/*
┌─────────────────────────▼───────────────────────────────────┐
│                   FastAPI Backend                            │
│  Auth · Cases · Quotes · OTP · RAG · Admin · UW · Compliance│
└──────┬──────────┬──────────┬──────────┬──────────┬──────────┘
       │          │          │          │          │
    MySQL     ChromaDB   ArangoDB   Mistral    SMTP
   (Main DB)  (Vectors)  (Graph)   (Local LLM) (Email)
```

### Multi-Agent System (LangGraph)

```
Orchestrator
  ├── Profile & Needs Agent
  ├── Suitability & Rules Agent
  ├── Quote Retrieval Agent  ──▶  HDFC | LIC | ICICI (mock)
  ├── Comparison & Explanation Agent
  ├── [HITL] Banker Approval
  ├── Exception & Compliance Agent
  └── Escalation Engine (APScheduler, every 10 min)
```

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- Node.js 20+
- MySQL 8.0
- [Ollama](https://ollama.com) with Mistral: `ollama pull mistral`
- ArangoDB 3.11 (optional — graph features)

### 2. Backend Setup

```bash
cd q2p-api

# Create virtualenv
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — set JWT_SECRET, MYSQL_PASSWORD, SMTP credentials

# Setup MySQL
mysql -u root -p < schema.sql

# Run Alembic migrations (optional — schema.sql already covers DDL)
cd backend
alembic upgrade head
cd ..

# Start server
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

API Docs: http://localhost:8000/docs

### 3. Frontend Setup

```bash
cd q2p-ui/frontend
npm install
npm run dev
```

App: http://localhost:3000

### 4. Local Mistral (via Ollama)

```bash
ollama serve          # starts on http://localhost:11434
ollama pull mistral   # downloads mistral model
```

The platform's LLM service POSTs to `http://localhost/api/generate` by default.
If you're using Ollama, update `LLM_BASE_URL` in `.env`:
```
LLM_BASE_URL=http://localhost:11434/api/generate
```

### 5. ChromaDB

No setup needed. ChromaDB runs **locally** using a persist directory:
```
CHROMA_PERSIST_DIR=./chroma_store
```
The directory is auto-created on first document upload.

### 6. ArangoDB (optional)

```bash
# macOS
brew install arangodb && arangodb

# Linux
# See: https://www.arangodb.com/download/
```

---

## Environment Variables

See `.env.example` for the full list. Critical ones:

| Variable | Description |
|---|---|
| `JWT_SECRET` | Secret key for JWT signing |
| `MYSQL_PASSWORD` | MySQL password |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | Email credentials |
| `LLM_BASE_URL` | Local Mistral endpoint |
| `CHROMA_PERSIST_DIR` | ChromaDB local storage path |

---

## API Routes

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/auth/login` | Login |
| POST | `/api/v1/auth/register` | Register |
| GET  | `/api/v1/cases/` | List cases |
| POST | `/api/v1/cases/` | Create case |
| POST | `/api/v1/cases/{id}/banker-approve` | Banker approval |
| POST | `/api/v1/quotes/case/{id}/fetch` | Fetch quotes from insurers |
| GET  | `/api/v1/quotes/case/{id}` | List quotes |
| POST | `/api/v1/otp/send` | Send OTP |
| POST | `/api/v1/otp/verify` | Verify OTP + record consent |
| POST | `/api/v1/rag/documents/upload` | Upload KB document |
| POST | `/api/v1/rag/chat` | RAG chat with memory |
| GET  | `/api/v1/underwriting/queue` | UW queue |
| POST | `/api/v1/underwriting/decision` | UW decision |
| GET  | `/api/v1/compliance/dashboard` | Compliance scores |
| GET  | `/api/v1/medical/queue` | Medical queue |
| GET  | `/api/v1/admin/stats` | Platform stats |
| POST | `/api/v1/workflow/case/{id}/run` | Trigger AI workflow |

---

## 15-Stage Workflow

1. Customer Intake → 2. Needs Analysis → 3. Suitability Validation →
4. Quote Retrieval → 5. Quote Comparison → 6. Recommendation →
7. **[HITL] Banker Approval** → 8. OTP Consent → 9. Proposal Generation →
10. Medical Coordination → 11. Underwriting → 12. Policy Issuance →
13. Exception Handling → 14. Escalation → 15. Completed

---

## Folder Structure

```
q2p-api/
├── .env.example
├── requirements.txt
├── schema.sql
├── configs/
│   └── base.py                  # Pydantic Settings
├── backend/
│   ├── main.py                  # FastAPI entrypoint
│   ├── alembic.ini
│   ├── alembic/env.py
│   └── app/
│       ├── core/
│       │   ├── database.py      # Async SQLAlchemy
│       │   └── security.py      # JWT + RBAC
│       ├── models/
│       │   └── all_models.py    # All SQLAlchemy models
│       ├── repositories/
│       │   └── user_repository.py
│       ├── middleware/
│       │   └── logging_middleware.py
│       └── api/v1/
│           ├── router.py
│           └── endpoints/
│               ├── auth.py
│               ├── cases.py
│               ├── quotes.py
│               ├── policies.py
│               ├── otp.py
│               ├── rag.py
│               ├── admin.py
│               ├── underwriting.py
│               ├── medical.py
│               ├── compliance.py
│               └── workflow.py
├── agents/
│   ├── orchestrator_agent.py    # LangGraph StateGraph
│   └── insurer_agents.py        # HDFC, LIC, ICICI mock APIs
├── llm/
│   ├── llm_service.py           # Local Mistral client
│   ├── prompt_manager.py        # All prompt templates
│   └── response_parser.py       # JSON extraction
├── rag/
│   ├── rag_pipeline.py          # Local ChromaDB ingestion + search
│   └── graph_retriever.py       # ArangoDB graph retrieval
├── smtp/
│   └── smtp_service.py          # Async SMTP
└── escalations/
    ├── escalation_engine.py     # Auto-escalation logic
    └── scheduler.py             # APScheduler

q2p-ui/frontend/
├── index.html
├── vite.config.js
├── tailwind.config.js
├── package.json
└── src/
    ├── App.jsx                  # All routes
    ├── main.jsx
    ├── index.css
    ├── services/api.js          # Axios + JWT interceptors
    ├── store/
    │   ├── index.js
    │   └── slices/
    │       ├── authSlice.js
    │       ├── casesSlice.js
    │       └── uiSlice.js
    ├── components/
    │   ├── common/index.jsx     # StatCard, Badge, DataTable, Btn…
    │   └── layout/DashboardShell.jsx
    └── pages/
        ├── LandingPage.jsx      # Full marketing landing page
        ├── auth/AuthPages.jsx   # Login + Register
        └── dashboard/
            ├── SuperAdminDashboard.jsx
            ├── BankerDashboard.jsx
            └── OtherDashboards.jsx  # Customer, UW, Compliance, Ops
```
