# Regal Fitness — Backend Core

This directory contains the core backend services, database configuration, and API application for **Regal Fitness**, a commercial gym management platform.

Developed by **Developer 2** on branch `developer-2-core`.

---

## Technical Stack

- **Language:** Python 3.11+
- **Web Framework:** FastAPI (v0.115+)
- **ASGI Server:** Uvicorn (v0.32+)
- **ORM:** SQLAlchemy 2.0
- **Validation & Serialization:** Pydantic v2 / Pydantic Settings
- **Database Driver:** PostgreSQL (psycopg2-binary)
- **Migrations:** Alembic
- **Testing:** Pytest & HTTPX

---

## Directory Structure

```
backend/
├── alembic/                 # Alembic migration scripts and environment
│   ├── versions/            # Migration version files
│   └── env.py               # Environment loader connecting Alembic to app settings
├── alembic.ini              # Alembic configuration
├── app/
│   ├── __init__.py          # App package version
│   ├── main.py              # FastAPI application entry point, CORS, root routes
│   ├── api/                 # API routing architecture
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── api.py       # API router aggregator
│   │       └── endpoints/   # Individual endpoint controllers
│   ├── core/                # Configuration and settings loader
│   │   ├── __init__.py
│   │   └── config.py        # Pydantic BaseSettings class reading from .env
│   ├── database/            # Database engine and connection lifecycle
│   │   ├── __init__.py
│   │   ├── base.py          # SQLAlchemy DeclarativeBase
│   │   └── session.py       # SessionLocal, Engine pooling, and get_db dependency
│   ├── models/              # SQLAlchemy database models (business models in Phase 2)
│   ├── schemas/             # Pydantic schemas for request/response validation
│   │   ├── __init__.py
│   │   └── health.py        # Root and health response schemas
│   ├── services/            # Business logic and domain service operations
│   └── utils/               # Common helper utilities and formatters
├── tests/                   # Pytest test suite
│   ├── __init__.py
│   ├── conftest.py          # Test client fixtures
│   └── test_health.py       # API and health check test cases
├── requirements.txt         # Pinned application dependencies
├── .env.example             # Environment variable blueprint
└── README.md                # Backend documentation
```

---

## Getting Started

### 1. Prerequisites

- Python 3.11 or higher
- PostgreSQL (for local development or production)
- Git

### 2. Create and Activate Virtual Environment

From the `backend` directory:

```bash
# Using standard venv
python -m venv .venv

# On Windows (PowerShell):
.venv\Scripts\Activate.ps1

# On macOS/Linux:
source .venv/bin/activate
```

Alternatively using `uv`:
```bash
uv venv
.venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy `.env.example` to create your local `.env`:

```bash
cp .env.example .env
```

Adjust the variables in `.env` as required for your local setup:
- `DATABASE_URL`: PostgreSQL connection string (`postgresql+psycopg2://user:password@localhost:5432/regal_fitness_db`)
- `ALLOWED_CORS_ORIGINS`: Allowed client domains (e.g., `["http://localhost:3000","http://localhost:5173"]`)
- `PORT`: HTTP port (default `8000`)
- `HOST`: Bind host (default `0.0.0.0`)

> **Security Note:** Never commit `.env` or credentials to version control.

---

## Running the Application

Start the development server with live reload:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The server will be available at:
- **API Base:** `http://localhost:8000/`
- **Health Check:** `http://localhost:8000/health`
- **Interactive Swagger Docs:** `http://localhost:8000/docs`
- **ReDoc Documentation:** `http://localhost:8000/redoc`
- **OpenAPI JSON Specification:** `http://localhost:8000/openapi.json`

---

## Running Tests

Execute the automated test suite using `pytest`:

```bash
pytest -v
```

---

## Database Migrations (Alembic)

Alembic is configured to read database connection details directly from `app.core.config.settings.DATABASE_URL` and target metadata from `Base.metadata`.

To generate a new migration revision (once models are defined):
```bash
alembic revision --autogenerate -m "description of migration"
```

To apply migrations:
```bash
alembic upgrade head
```
