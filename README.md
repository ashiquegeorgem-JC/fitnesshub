# Regal Fitness — Gym Management Platform

Regal Fitness is a commercial-grade gym management application designed for streamlined fitness club operations, member onboarding, automated subscription and renewal management, financial reporting, billing, and communication workflows.

The project is developed concurrently by two dedicated developers sharing this repository:
- **Developer 1 (Public & Frontend):** Public customer website, landing pages, pricing displays, inquiry forms, and member visit scheduling.
- **Developer 2 (Core & Backend):** Backend API, database architecture, authentication, member lifecycle, payments, dues, invoicing, owner dashboards, reporting, notifications, WhatsApp integration, Drive integration, and security backups.

---

## Technology Stack

### Backend (Developer 2)
- **Language:** Python (3.11+)
- **API Framework:** FastAPI
- **Database:** PostgreSQL
- **ORM:** SQLAlchemy 2.0
- **Data Validation & Settings:** Pydantic v2 & Pydantic Settings
- **Database Migrations:** Alembic
- **ASGI Server:** Uvicorn
- **Testing:** Pytest & HTTPX

### Frontend (Developer 1)
- Managed on dedicated branch `developer-1-public`.

---

## Repository Structure

```
fitnesshub/
│
├── backend/
│   ├── alembic/             # Database schema migrations
│   ├── alembic.ini          # Alembic configuration
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py          # FastAPI application initialization & routes
│   │   ├── core/            # Global configuration & environment settings
│   │   │   ├── __init__.py
│   │   │   └── config.py
│   │   ├── database/        # Engine, connection pooling, session lifecycle
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   └── session.py
│   │   ├── models/          # SQLAlchemy database entities (business tables added in Phase 2)
│   │   │   └── __init__.py
│   │   ├── schemas/         # Pydantic validation schemas
│   │   │   ├── __init__.py
│   │   │   └── health.py
│   │   ├── api/             # API routing
│   │   │   ├── __init__.py
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── api.py
│   │   │       └── endpoints/
│   │   │           └── health.py
│   │   ├── services/        # Domain business logic
│   │   │   └── __init__.py
│   │   └── utils/           # Utility functions & helpers
│   │       └── __init__.py
│   │
│   ├── tests/               # Automated test suite
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   └── test_health.py
│   ├── requirements.txt     # Pinned Python package dependencies
│   ├── .env.example         # Template for environment configuration
│   └── README.md            # Backend-specific documentation
│
├── docs/                    # Architecture and project documentation
│   └── architecture.md
│
├── .gitignore               # Root git ignore specification
└── README.md                # Project documentation (this file)
```

---

## Git Branch Workflow

We follow an isolated branch strategy to ensure stable feature delivery and parallel collaboration without merge conflicts:

| Branch | Purpose | Owner |
|---|---|---|
| `main` | Production-ready stable integrated releases | Both (Integration) |
| `developer-1-public` | Public website and customer frontend | Developer 1 |
| `developer-2-core` | Core backend, database, and APIs | Developer 2 |
| `integration` | Staging, cross-tier integration and end-to-end testing | Shared |

### Branching & Contribution Rules
1. Never commit or push directly to `main`.
2. All backend development must occur on branch `developer-2-core`.
3. Never modify Developer 1's frontend files from backend branch.
4. Commit changes with clear, descriptive commit messages.
5. Never commit `.env`, secrets, credentials, or API keys. Always use `.env.example` as a template.

---

## Backend Setup Instructions

### 1. Python Virtual Environment Creation

Navigate to the `backend` directory and create an isolated virtual environment:

```bash
cd backend
python -m venv .venv
```

Activate the virtual environment:

- **Windows (PowerShell):**
  ```powershell
  .venv\Scripts\Activate.ps1
  ```
- **Windows (Command Prompt):**
  ```cmd
  .venv\Scripts\activate.bat
  ```
- **macOS / Linux:**
  ```bash
  source .venv/bin/activate
  ```

### 2. Dependency Installation

Install all required production and testing dependencies:

```bash
pip install -r requirements.txt
```

### 3. Environment Configuration

Copy the example template to create your local `.env`:

```bash
cp .env.example .env
```

Configure your environment variables:

```ini
APP_NAME="Regal Fitness API"
APP_ENV=development
APP_DEBUG=true
API_V1_STR=/api/v1
HOST=0.0.0.0
PORT=8000

# Allowed CORS Origins (JSON array or comma-separated strings)
ALLOWED_CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]

# PostgreSQL Database URL
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/regal_fitness_db
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30
```

> **Warning:** Do not commit the `.env` file to Git.

### 4. Running the Backend Server

Start the FastAPI application using Uvicorn with auto-reload enabled:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The server binds to `http://localhost:8000`.

### 5. API Endpoints and Documentation

Once the server is running, access the endpoints and interactive docs:

- **Root API Status:** `GET http://localhost:8000/`
- **Application Health Check:** `GET http://localhost:8000/health`
- **Interactive Swagger Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation:** [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **OpenAPI JSON Schema:** [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

### 6. Running Tests

Run the backend test suite:

```bash
pytest -v
```
