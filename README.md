# AUREN — Premium Personal AI Assistant Platform

AUREN is an independent, premium personal AI assistant platform designed for structured long-term memory, personal task planning, private journaling, goals tracking, and proactive daily briefings with strict user data isolation.

---

## 🏛️ Architectural Overview

- **Frontend:** React 19 + TypeScript + Vite + Tailwind CSS
- **Backend:** Python FastAPI + Pydantic v2 + Uvicorn
- **Database & Auth (Target):** Supabase PostgreSQL + Supabase Auth
- **Semantic Memory (Target):** PostgreSQL with `pgvector`
- **AI & Embedding:** Pluggable provider interface (agnostic to LLM backend: Gemini, OpenAI, Claude, or local)

```
AUREN/
├── backend/                       # Python FastAPI Backend
│   ├── .env.example               # Backend environment template
│   ├── pyproject.toml             # Python package configuration (Python >=3.12)
│   ├── requirements.txt           # Production dependencies
│   ├── requirements-dev.txt       # Development dependencies (pytest, etc.)
│   ├── app/
│   │   ├── main.py                # Application entrypoint & CORS middleware
│   │   ├── core/
│   │   │   ├── config.py          # Pydantic Settings configuration
│   │   │   └── security.py        # Supabase JWT verification & auth middleware
│   │   ├── api/v1/                # Modular API endpoints
│   │   │   ├── router.py          # Unified router
│   │   │   └── health.py          # Health check endpoint (/api/v1/health)
│   │   ├── models/                # Pydantic data schemas
│   │   │   ├── health.py          # Health response schema
│   │   │   └── user.py            # Authenticated user context schema
│   │   └── services/              # Pluggable service layers
│   │       ├── llm/base.py        # Replaceable LLM provider interface
│   │       └── embeddings/base.py # Replaceable embedding provider interface
│   └── tests/                     # Pytest suite
│       └── test_health.py         # Health check & root API tests
│
├── frontend/                      # React + TypeScript + Vite Frontend
│   ├── .env.example               # Frontend environment template
│   ├── package.json               # Node.js dependencies & scripts
│   ├── tsconfig.json              # TypeScript configuration
│   ├── vite.config.ts             # Vite build & proxy configuration
│   ├── tailwind.config.js         # Tailwind CSS styling configuration
│   └── src/
│       ├── main.tsx               # React root mounting
│       ├── App.tsx                # Responsive landing & system status view
│       ├── index.css              # Tailwind styles & theme variables
│       ├── api/
│       │   ├── client.ts          # Typed API client with Supabase JWT integration
│       │   ├── health.ts          # Health API service
│       │   └── types.ts           # API contract types
│       └── lib/
│           └── supabase.ts        # Client-safe Supabase Auth client initialization
│
├── .gitignore                     # Git exclusion rules (secrets, venv, node_modules)
└── README.md                      # Project documentation and setup guide
```

---

## 🚀 Quick Start Guide

### Prerequisites
- **Python:** 3.12 or newer
- **Node.js:** v18.0.0 or newer (v22+ recommended)
- **Git**

---

### 1. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements-dev.txt

# Copy environment template
cp .env.example .env

# Run automated tests
pytest -v

# Start the development server
uvicorn app.main:app --reload --port 8000
```

The backend will be available at:
- **API Root:** [http://localhost:8000/](http://localhost:8000/)
- **Health Check:** [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)
- **Interactive OpenAPI Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

### 2. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Copy environment template
cp .env.example .env

# Verify TypeScript compilation and production build
npm run build

# Start the Vite development server
npm run dev
```

The frontend will be available at:
- **Web App:** [http://localhost:5173/](http://localhost:5173/)

---

## 🔒 Security & Data Isolation Architecture

1. **User Isolation by Design:**
   - Every user-owned domain entity is anchored to an authenticated user ID (`sub` claim in Supabase JWT).
2. **Zero Client-Side Secrets:**
   - The frontend only holds `VITE_SUPABASE_ANON_KEY` (public anon key).
   - AI provider keys (`LLM_API_KEY`), database credentials, and service tokens exist exclusively on the server backend.
3. **Robust JWT Validation:**
   - The backend validates Supabase Auth tokens using asymmetric JWKS (`.well-known/jwks.json`) and/or secret signing keys before any protected route is executed.
4. **No Service-Role Key for User Operations:**
   - User actions never bypass Supabase Row Level Security (RLS).

---

## 🗺️ Implementation Roadmap

- [x] **Phase 1: Project Scaffolding & Configuration** *(Completed)*
  - Monorepo folder structure
  - Backend FastAPI scaffolding with `/api/v1/health` and automated pytest suite
  - Frontend React + TypeScript + Vite + Tailwind CSS setup
  - Pluggable abstract interfaces for LLM and Embedding providers
  - Typed frontend API client foundation
  - `.gitignore` and `.env.example` configurations
- [x] **Phase 2: Database Schema & Supabase Auth Integration** *(Completed)*
  - Core database migrations (10 tables: profiles, projects, tasks, conversations, messages, memories, journal_entries, goals, milestones, briefings)
  - Row Level Security (RLS) policies enforcing strict `auth.uid() = user_id` isolation
  - Automated `updated_at` and `auth.users` profile creation triggers
  - FastAPI JWT verification with JWKS/secret signing key and `/api/v1/auth/me` endpoint
  - Comprehensive 17-test automated auth and isolation test suite
  - React `AuthContext`, `useAuth`, `AuthModal`, and session restoration
- [ ] **Phase 3: Core AI & Semantic Memory Engine (pgvector)**
- [ ] **Phase 4: Personal Productivity Modules (Tasks, Journal, Goals)**
- [ ] **Phase 5: Daily Briefings & Intelligence Synthesis**
- [ ] **Phase 6: Hardening, Polish & Comprehensive Testing**

---

## 📄 License

*Licensing choice to be determined prior to open-source or commercial release.*

