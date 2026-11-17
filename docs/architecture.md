# Regal Fitness — Architecture Overview

## 1. System Context

Regal Fitness is a commercial gym management platform built with high performance, security, and scalability in mind.

- **Frontend & Public Website**: Developed independently by Developer 1 on branch `developer-1-public`. Covers landing pages, membership browsing, inquiry workflows, and visit requests.
- **Backend & Core Engine**: Architected and developed by Developer 2 on branch `developer-2-core`. Covers core business logic, database models, payment processing, membership lifecycle, invoicing, owner dashboards, reporting, and external integrations (WhatsApp, Google Drive, Excel exports).

## 2. Backend Modular Layout

The backend follows clean architecture principles, separating concerns across distinct layers:

```
backend/
├── app/
│   ├── api/            # API routing, request validation, and HTTP serialization
│   ├── core/           # Global configuration, settings loader, security primitives
│   ├── database/       # SQLAlchemy engine, connection pooling, session lifecycle
│   ├── models/         # Declarative database entities (business tables added in Phase 2)
│   ├── schemas/        # Pydantic schemas for data transfer and validation
│   ├── services/       # Core business logic and transactional operations
│   └── utils/          # Cross-cutting helper functions and formatting
├── alembic/            # Database schema migrations
├── tests/              # Pytest test suite
├── .env.example        # Environment variable blueprint
└── requirements.txt    # Locked production and testing dependencies
```

## 3. Database Layer

- **Database Engine**: PostgreSQL
- **ORM**: SQLAlchemy 2.0 (Declarative Base, Type annotations)
- **Migrations**: Alembic with environment-aware dynamic URL configuration
- **Connection Pooling**: Configured with `pool_pre_ping=True`, customizable pool size and overflow to support concurrent dashboard and member traffic.

## 4. API & Documentation

- **Framework**: FastAPI (asynchronous, OpenAPI 3.1 & Swagger compliant)
- **Validation**: Pydantic v2
- **CORS**: Configurable via `ALLOWED_CORS_ORIGINS` environment variable
- **Documentation**: Interactive Swagger UI at `/docs` and ReDoc at `/redoc`
