# Regal Fitness — Public Frontend API Contracts

**Version:** 1.3.1
**Date:** 2026-11-19
**Authors:** Developer 2 (Backend Architecture & Core Management)
**Audience:** Developer 1 (Public Frontend, branch `developer-1-public`, React + Vite)
**Status:** DRAFT — Awaiting owner approval.

---

> [!IMPORTANT]
> **Architectural Status Legend:**
> - **[APPROVED EXISTING SCHEMA]**: Exists in current SQLAlchemy models and database migrations.
> - **[PROPOSED SCHEMA CHANGE]**: Recommended database migration presented for owner approval. Not yet applied.
> - **[PROPOSED API CONTRACT]**: Proposed endpoint interface specification for frontend integration. Not yet implemented.
> - **[ACTUAL IMPLEMENTED BEHAVIOR]**: Verified against actual backend source code (`handlers.py`, `config.py`, `rate_limit.py`, `endpoints/auth.py`, `endpoints/health.py`).
> - **[PROPOSED ARCHITECTURAL REFACTOR]**: Recommended backend component refactoring (e.g. moving utilities to shared core) before endpoint implementation.
> - **[PROPOSED IMPLEMENTATION REQUIREMENT]**: Mandatory concurrency, locking, or configuration validation protocol required during endpoint service implementation.

---

## Table of Contents

1. [Common Conventions & Actual Implementation](#1-common-conventions--actual-implementation)
2. [Proposed Schema Migrations for Owner Approval](#2-proposed-schema-migrations-for-owner-approval)
3. [Contract 1 — POST /api/v1/public/joining-applications](#3-contract-1--post-apiv1publicjoining-applications)
4. [Contract 2 — POST /api/v1/public/enquiries](#4-contract-2--post-apiv1publicenquiries)
5. [Contract 3 — POST /api/v1/public/visit-requests](#5-contract-3--post-apiv1publicvisit-requests)
6. [Contract 4 — GET /api/v1/public/membership-plans](#6-contract-4--get-apiv1publicmembership-plans)
7. [Contract 5 — GET /api/v1/public/gallery](#7-contract-5--get-apiv1publicgallery)
8. [Public API Rate Limiting Architecture](#8-public-api-rate-limiting-architecture)
9. [Request Examples](#9-request-examples)
10. [Response Examples](#10-response-examples)
11. [Schema Gaps & Pending Owner Decisions](#11-schema-gaps--pending-owner-decisions)
12. [Frontend Integration Notes (React + Vite)](#12-frontend-integration-notes-react--vite)

---

## 1. Common Conventions & Actual Implementation

### 1.1 Base URL & Path Conventions (React + Vite)

To avoid path duplication, the backend and frontend adhere to one consistent routing convention:

1. **Environment Variable**: `VITE_API_BASE_URL` contains the full origin and API version prefix (`/api/v1`):
   ```env
   # .env.development
   VITE_API_BASE_URL=http://localhost:8000/api/v1

   # .env.production
   VITE_API_BASE_URL=https://api.regalfitness.in/api/v1
   ```
2. **Frontend Request Paths**: Client-side API service calls append **relative endpoint paths** that do **not** repeat `/api/v1`:
   ```typescript
   // src/api/client.ts
   const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

   // Resulting URL: http://localhost:8000/api/v1/public/enquiries
   await fetch(`${API_BASE_URL}/public/enquiries`, { method: 'POST', ... });
   ```
3. **Backend Route Documentation**: Throughout this document, backend endpoints are referenced by their canonical full server route (e.g. `POST /api/v1/public/enquiries`), while frontend examples demonstrate the exact relative path (`/public/enquiries`).

### 1.2 HTTP Methods

Only two HTTP methods are used across all public endpoints:

| Method | Usage |
|--------|-------|
| `GET` | Retrieve publicly visible data (plans catalog, facility gallery) |
| `POST` | Submit public forms (joining application, general enquiry, visit request) |

All `POST` request bodies and responses use `Content-Type: application/json`.

### 1.3 Authentication

| Endpoint Group | Authentication Required | Notes |
|----------------|------------------------|-------|
| `/api/v1/public/*` | **None** | Unauthenticated, protected by rate limiting & validation |
| `/api/v1/auth/*` | **None / Bearer** | Phase 2 implementation (login, OTP, refresh) |
| `/api/v1/owner/*` | **Bearer JWT** | Protected owner management endpoints (Phase 3+) |

### 1.4 Error Response Verification [ACTUAL IMPLEMENTED BEHAVIOR]

Inspection of `backend/app/core/handlers.py`, `backend/app/core/exceptions.py`, and `backend/app/api/v1/endpoints/health.py` verifies the exact error response formats:

#### A. Application Exceptions (`AppException`)
```json
{
  "error": {
    "code": "BAD_REQUEST",
    "message": "Human-readable summary of the error.",
    "details": null
  }
}
```
- `error.code`: High-level error identifier (e.g. `BAD_REQUEST`, `RESOURCE_NOT_FOUND`, `RESOURCE_CONFLICT`, `RATE_LIMIT_EXCEEDED`).
- `error.message`: Clear description of the failure.
- `error.details`: Passed directly from `AppException.extra`. May be `null`, a dictionary (such as `{"retry_after_seconds": 3600}`), or a list of details.

#### B. Pydantic Request Validation Errors (`RequestValidationError` — HTTP 422)
FastAPI captures schema and type violations, invalid values, out-of-range numbers, and custom validator mismatches. In `handlers.py`, these are mapped into:
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request parameters or payload",
    "details": [
      {
        "field": "body -> phone_number",
        "message": "Phone number must be a valid 10-digit Indian or E.164 mobile number",
        "type": "value_error"
      }
    ]
  }
}
```
> [!NOTE]
> The `field` string in `RequestValidationError` follows FastAPI's location format joined with `" -> "` (e.g. `"body -> phone_number"` or `"body -> date_of_birth"`). The frontend should strip `"body -> "` prefix when mapping to form input field keys.

#### C. Generic Unexpected Exceptions (`Exception` — HTTP 500)
```json
{
  "error": {
    "code": "INTERNAL_SERVER_ERROR",
    "message": "An unexpected server error occurred",
    "details": null
  }
}
```
**Security Verification:** Unhandled server exceptions log the full traceback server-side via `logger.critical(..., exc_info=True)` but **never expose internal stack traces, SQL queries, or filesystem paths to the client**.

#### Standard Error Code Mapping

To maintain strict architectural consistency, **all request-schema, field-format, range, and field-consistency validation failures consistently return HTTP 422 `VALIDATION_ERROR`**. HTTP 400 is reserved for genuine business-rule rejections that are independent of request payload schema validity.

| HTTP Status | `error.code` | Cause & Actual Implementation Status |
|-------------|--------------|--------------------------------------|
| `400` | `BAD_REQUEST` | State-dependent business rule violation (e.g. gym operational constraint) |
| `404` | `RESOURCE_NOT_FOUND` | Referenced entity not found (e.g. selected plan ID does not exist or is inactive) |
| `409` | `RESOURCE_CONFLICT` | Duplicate active application in pipeline or applicant already has an active member profile |
| `422` | `VALIDATION_ERROR` | Schema type/format failure, future date of birth, age outside [1–120], age/DOB mismatch, past visit date, invalid time slot enum |
| `429` | `RATE_LIMIT_EXCEEDED` | Request threshold exceeded for client IP |
| `500` | `INTERNAL_SERVER_ERROR` | Unhandled generic server crash (traceback suppressed, verified in `handlers.py`) |
| `500` | `DATABASE_ERROR` | Uncaught SQLAlchemy database error during standard API operations (`handlers.py`) |
| `503` | `DATABASE_UNAVAILABLE` | **Readiness probe only**: Verified for `GET /health/ready` when PostgreSQL is unreachable (`endpoints/health.py`). Regular API endpoints do not return 503 unless an explicit readiness gateway is in place. |

### 1.5 Timestamps & Business Dates

- **Database Storage**: Timestamps are stored with timezone in UTC (`TIMESTAMPTZ` in PostgreSQL).
- **API Serialisation**: ISO 8601 UTC strings, e.g. `"2026-11-18T07:30:00Z"`.
- **Business Date Zone**: All business-day validations (e.g. "is date in the future?") evaluate against the gym's physical operational timezone: **`Asia/Kolkata` (UTC+5:30)**.
- **Frontend Display**: Developer 1 must convert UTC timestamps to `Asia/Kolkata` for display. Date-only fields (`YYYY-MM-DD`) require no timezone conversion.

### 1.6 Phone Number Normalization & Validation Standard

To prevent duplicate evasion, advisory lock mismatches, and database formatting drift:

1. **Canonical Parsing via Shared Utility**: All phone number inputs across public endpoints and owner workflows are parsed using a centralized backend phone utility powered by Google's `phonenumbers` library with default region `'IN'`.
2. **Public Form Validation Policy (Strict Mobile-Only Invariant)**:
   - All public customer-facing endpoints (`POST /public/joining-applications`, `POST /public/enquiries`, `POST /public/visit-requests`) strictly mandate **mobile handset numbers**:
     - **Indian Mobile Numbers**: Standard 10-digit mobile numbers starting with 6, 7, 8, or 9 (`^[6-9]\d{9}$`), normalized to canonical E.164 format: `+91XXXXXXXXXX`.
     - **International Numbers**: Must parse successfully to an E.164 mobile number (`^\+[1-9]\d{1,14}$`) where `phonenumbers.number_type(parsed)` resolves to `PhoneNumberType.MOBILE` (or `FIXED_LINE_OR_MOBILE` where regions do not distinguish).
     - **Rejection of Non-Mobile Numbers**: Landline / fixed-line numbers, toll-free numbers, and premium-rate numbers are **strictly rejected** with **HTTP 422 VALIDATION_ERROR**.
   - **Operational Rationale**: Gym onboarding, visit coordination, WhatsApp notifications, and SMS transaction alerts require a direct personal mobile handset. Fixed-line numbers cannot receive WhatsApp messages or SMS alerts.
3. **Broader Internal / Administrative Phone Policy**:
   - The database schema defines `phone_number` as `VARCHAR(20) NOT NULL` across `members`, `joining_applications`, and `owners`.
   - While internal administrative records and emergency contact secondary numbers may administratively record verified fixed-line numbers where explicitly approved by gym ownership, all public intake channels and member primary contact fields strictly enforce mobile numbers.
4. **Strict Normalization Rules**:
   - Formatting characters, whitespace, dashes, dots, and parentheses are stripped.
   - Ambiguous, unparseable, or out-of-range inputs are rejected immediately with **HTTP 422 VALIDATION_ERROR**.
5. **Universal Invariant**: **All database persistence, rate-limiting keys, duplicate application checks, active member profile checks, advisory locks, and SQL queries operate strictly on the canonical E.164 string.** No raw or partially formatted phone strings are stored or queried.

---

## 2. Proposed Schema Migrations for Owner Approval

### 2.1 Migration 2.1 — Membership Plan Public Visibility [PROPOSED SCHEMA CHANGE]

#### Problem
In the currently approved schema (`DATABASE_SCHEMA.md §5.3` and `app/models/plan.py`), `membership_plans` only has `is_active` (for billing/enrollment) and `is_archived` (soft delete). Creating an active plan currently forces it to be published, directly violating the business requirement that creating a plan must not automatically expose it on the public marketing site.

#### Proposed Solution
Add an explicit public publishing flag `is_publicly_visible` defaulting to `FALSE`:

```sql
-- Migration: add_membership_plan_public_visibility
ALTER TABLE membership_plans
ADD COLUMN is_publicly_visible BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX idx_plans_public_catalog
ON membership_plans (duration_days ASC)
WHERE is_active = TRUE AND is_archived = FALSE AND is_publicly_visible = TRUE;
```

#### Required ORM Model Update (`app/models/plan.py`)
```python
is_publicly_visible: Mapped[bool] = mapped_column(
    Boolean, nullable=False, default=False
)
```
> [!NOTE]
> `index=True` is omitted from the ORM attribute because the dedicated compound partial index `idx_plans_public_catalog` defined in the migration indexes `duration_days ASC` on the exact active/unarchived/public slice. A separate standalone B-tree index on the low-cardinality boolean column would be redundant and waste write I/O.

#### Existing Record Migration Behavior
- **Default Unpublished State**: When this migration executes, all pre-existing rows in `membership_plans` receive `is_publicly_visible = FALSE` via the column default.
- **Internal Enrollment Unaffected**: Existing plans remain fully available for internal billing, contract generation, and manual enrollment according to their existing `is_active` status.
- **Explicit Publishing Workflow**: Pre-existing plans are **not automatically published** during the migration. Gym owners must explicitly publish each plan they wish to surface on the marketing website via the owner dashboard (Phase 3+).

#### Public Catalog Query
With this migration applied, the public plan listing query becomes:
```sql
SELECT * FROM membership_plans
WHERE is_active = TRUE
  AND is_archived = FALSE
  AND is_publicly_visible = TRUE
ORDER BY duration_days ASC;
```

---

### 2.2 Migration 2.2 — Duplicate Application Concurrency Protection [PROPOSED SCHEMA CHANGE]

#### Problem
The `joining_applications` table lacks a database-level constraint preventing simultaneous duplicate submissions from the same applicant phone number.

#### Concurrency Analysis
In high-concurrency environments, ordinary application-level check-before-insert (e.g. `SELECT` followed by `INSERT`) is subject to race conditions:
- When a user submits two concurrent requests for a phone number that has not previously applied, **neither transaction finds an existing row during the check**.
- Row-level locking (`SELECT ... FOR UPDATE`) cannot lock a row that **does not exist yet**.
- Therefore, both transactions would proceed to insert, resulting in duplicate active applications for the same person.

#### Proposed Solution
A PostgreSQL partial unique index is the primary, concurrency-safe mechanism to guarantee mutual exclusion at the storage engine level for the active application pipeline:

```sql
-- Migration: uq_active_joining_application_phone
CREATE UNIQUE INDEX idx_uq_active_joining_app_phone
ON joining_applications (phone_number)
WHERE status IN ('submitted', 'reviewing', 'approved_pending_payment');
```

- **Guarantees**: Absolute database-level atomicity against concurrent race conditions for applications in the active pipeline (`submitted`, `reviewing`, `approved_pending_payment`).
- **Exception Mapping**: The backend catches the database `IntegrityError` (violating `idx_uq_active_joining_app_phone`) inside the transaction and translates it directly into `HTTP 409 RESOURCE_CONFLICT`.
- **Pre-check Defense**: A preliminary service-layer query check is performed before insert to deliver a clean application-level response early, but this check is an optimization and **not** the concurrency barrier.

#### Comprehensive 4-Stage Historical Data Remediation Process

Advisory locking (which hashes normalized E.164 phone strings) and cross-table member/application checks are reliable **only if existing database phone numbers conform to the exact same canonical E.164 representation** as incoming requests.

> [!CAUTION]
> **The Storage vs. Query Discrepancy Problem**: PostgreSQL partial unique indexes and exact SQL equality filters (`WHERE phone_number = :normalized_phone`) operate strictly on **raw stored strings**. In-memory normalization alone does **not** solve database-level checks. If historical records contain unnormalized strings (e.g. `'9876543210'`) while incoming submissions query for canonical E.164 (`'+919876543210'`), neither the partial unique index nor the pre-insert check will detect a match. Therefore, a complete data remediation process must precede the creation of Migration 2.2.

The data remediation protocol consists of four distinct, auditable stages:

```
[ Stage A: Read-Only Preflight ] ──(If Clean)──> [ Stage D: Migration 2.2 Application ]
               │
          (If Issues)
               ▼
[ Stage B: Administrative Review ]
               │ (Explicit Business Resolutions)
               ▼
[ Stage C: Controlled Remediation Migration ]
               │
               ▼
[ Stage D: Post-Remediation Verification ] ──(100% Verified)──> [ Migration 2.2 & Endpoints Enabled ]
```

##### Stage A — Read-Only Preflight Analysis
1. **Scope**: Comprehensive scan of every historical record across **both** `joining_applications` and `members`, encompassing all statuses (**active, inactive, and soft-archived records**).
2. **Invalid & Malformed Data Detection**:
   The preflight scans all stored strings and flags any row where `phone_number` is:
   - `NULL` or empty string (`''`)
   - Whitespace-only string (`'   '`)
   - Malformed value that fails canonical parsing via Google's `phonenumbers` library (with default region `'IN'`).
3. **In-Memory Canonical Normalization & Three-Category Collision Analysis**:
   Every valid phone number is parsed and canonicalized to E.164 in memory. The preflight groups all candidate records and systematically categorizes potential conflicts into **three distinct, non-overlapping categories**:

   - **Category A: Existing Database Constraint Violations (Immediate Migration Blockers)**:
     Collisions among **all unarchived members** covered by the existing PostgreSQL partial unique index:
     ```sql
     CREATE UNIQUE INDEX idx_uq_members_active_phone
     ON members (phone_number)
     WHERE is_archived = false;
     ```
     *Critical Detail*: This existing database constraint applies to **all unarchived members regardless of active status**, including inactive (`is_active = false`) but unarchived (`is_archived = false`) accounts. If two unarchived member records hold disparate raw strings (e.g. `'9876543210'` and `'+919876543210'`) that canonicalize to the identical E.164 string, updating the column in place in Stage C would immediately trigger a PostgreSQL `IntegrityError` and crash the migration. Category A collisions are **strict migration blockers** that must be resolved before Stage C can execute.

   - **Category B: Prospective Constraint Violations (Index Creation Blockers)**:
     Collisions within the active joining-application pipeline (`submitted`, `reviewing`, `approved_pending_payment`). If multiple active applications resolve to the same canonical E.164 number, applying Migration 2.2 (`idx_uq_active_joining_app_phone`) will fail with an index creation conflict. Category B collisions are **prospective index creation blockers** that must be deduplicated before Migration 2.2 is applied.

   - **Category C: Historical & Cross-Table Conflicts (Administrative Review & Reactivation Planning)**:
     *Important Distinction*: **Category C conflicts are NOT existing database constraint violations at migration time.**
     - **Archived Records Under Partial Indexing**: Because `idx_uq_members_active_phone` specifies `WHERE is_archived = false`, PostgreSQL legally permits multiple soft-archived rows (`is_archived = true`) to share the same canonical phone number without violating any database constraint.
     - **Historical Terminal Applications**: Applications in terminal states (`converted_to_member`, `rejected`, `withdrawn`) are outside the active pipeline partial index predicate.
     - **Operational Impact**: Although Category C conflicts do not violate database constraints or block the Stage C column update from completing, they represent future operational blockers (e.g. an archived member whose future reactivation would fail due to a phone collision with an active member, or cross-table confusion).
     - **Handling**: These conflicts are isolated for administrative review and classification in Stage B, capturing resolution metadata without blocking the database schema migration.

4. **Structured Diagnostic Output & Preflight Artifact Immutability Architecture**:
   The preflight produces a machine-readable JSON diagnostic report detailing every affected row (table, primary key UUID, raw string, canonical E.164 string, conflict category, and affected constraints).

   > [!IMPORTANT]
   > **Integrity vs. Immutability Architecture**:
   > Generating a SHA-256 checksum detects whether an artifact has been modified or corrupted; **a checksum alone does not make a file immutable**.
   > To guarantee that original historical raw phone values remain permanently recoverable and legally defensible:
   > 1. The preflight report (`phone_remediation_preflight_<timestamp>.json`) and its SHA-256 signature (`.sha256`) must be deposited into a **write-protected, version-locked, or tamper-resistant administrative backup location** (e.g. cloud object storage with Object Lock in Compliance/Governance mode, GCS bucket retention policies, or WORM storage).
   > 2. The original raw phone strings must remain permanently recoverable from both this secured preflight archive and the migration audit table.

5. **Zero-Write & Hard Halt Invariant**:
   Stage A is **strictly read-only**. If any malformed record or Category A/B conflict is detected, the script terminates immediately with exit code 1. It must **never automatically delete, merge, deactivate, or overwrite historical records**, change application statuses, or alter member accounts.

##### Stage B — Administrative Review & Resolution
1. **Gym Administration Ownership**: The diagnostic report and conflict classification logs are delivered to gym leadership for explicit review and manual resolution.
2. **Manual Business Resolution Guidelines**:
   - For duplicate active applications (Category B), administration verifies which application is legitimate, marking obsolete rows as `rejected` or `withdrawn`.
   - For cross-table overlaps (Category C), administration contacts the applicant to confirm whether they are an existing member seeking renewal (marking the application as `withdrawn`).
   - For member phone collisions on `is_archived = false` (Category A), administration reviews member identity, updating records to correct historical transcription errors.
   - For archived-record collisions (Category C), administration classifies whether the duplicate archived records represent duplicate accounts of the same person or different individuals, attaching resolution metadata without altering historical records.
   - For malformed numbers, administration consults physical intake forms to correct contact details.
3. **Strict Non-Destructive Policy**:
   Under **no circumstances** may automated scripts or administrative actions delete, merge, or overwrite historical records. All historical records (`joining_applications`, `members`, `payments`, `invoices`) must be permanently preserved for tax, accounting, and legal audit compliance.

##### Stage C — Controlled Remediation Migration & Dedicated Audit Table

> [!IMPORTANT]
> **Audit Table Status**: Inspection of the approved database schema (`DATABASE_SCHEMA.md`) and initial migration (`001_initial_schema.py`) verifies that **no dedicated pre-remediation phone audit table currently exists**. The existing `audit_logs` table (`app/models/audit.py`) is designed exclusively for application-level runtime entity events and lacks specific columns for tracking historical schema-level column migrations. The audit table proposed below is a new table to be created explicitly as the first step of the remediation migration.

To guarantee complete auditability, the historical phone remediation must establish a dedicated audit table:

1. **Proposed Migration-Created Audit Table (`phone_normalization_audit_log`)**:
   Created in PostgreSQL in the first step of the Alembic remediation migration:
   ```sql
   CREATE TABLE phone_normalization_audit_log (
       id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
       source_table VARCHAR(50) NOT NULL,
       original_record_id UUID NOT NULL,
       original_raw_phone VARCHAR(50) NOT NULL,
       canonical_e164_phone VARCHAR(20) NOT NULL,
       migration_identifier VARCHAR(100) NOT NULL,
       remediated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
       resolution_metadata JSONB NULL
   );

   CREATE INDEX idx_phone_audit_lookup
   ON phone_normalization_audit_log (source_table, original_record_id);
   ```
   - `source_table`: Name of the modified table (`'members'` or `'joining_applications'`).
   - `original_record_id`: Primary key UUID of the modified record.
   - `original_raw_phone`: Byte-for-byte exact unedited phone string prior to remediation.
   - `canonical_e164_phone`: Verified E.164 string written to the column.
   - `migration_identifier`: Specific Alembic migration version (e.g. `'alembic_remediation_phone_e164_v1'`).
   - `remediated_at`: Immutable UTC timestamp of the remediation, defaulting to `now()`.
   - `resolution_metadata`: JSONB containing administrative resolution notes, authorizing owner ID, and previous conflict context where applicable.
2. **Atomic Execution Protocol**:
   The Alembic data migration runs within an atomic database transaction:
   - Populates `phone_normalization_audit_log` with the original values.
   - Updates `phone_number` columns in-place to canonical E.164 across `members` and `joining_applications`.
   - If any unexpected value, unhandled parse error, or constraint violation occurs, the entire transaction rolls back completely.

##### Stage D — Post-Remediation Verification & Migration 2.2 Activation
1. **Re-Verification**: The automated Stage A preflight script is executed again in production.
2. **Acceptance Criteria**:
   - 100% of stored phone numbers in `joining_applications` match `^\+[1-9]\d{1,14}$`.
   - 100% of stored phone numbers in `members` match `^\+[1-9]\d{1,14}$`.
   - Exactly zero active pipeline duplicates.
   - Exactly zero unarchived member duplicates (`idx_uq_members_active_phone` fully satisfied).
   - Exactly zero active pipeline vs. active member overlaps.
3. **Index Application**: Only upon achieving 100% clean verification is Migration 2.2 (`idx_uq_active_joining_app_phone`) executed in PostgreSQL and public application submission endpoints enabled.

#### Scope Boundary & Cross-Table Concurrency
- `idx_uq_active_joining_app_phone` strictly covers phone numbers **within** the `joining_applications` table.
- When an application is approved and converted to an active gym member profile, its status changes to `converted_to_member`, releasing that application row from the partial index condition.
- A partial index on `joining_applications` **cannot enforce a foreign table constraint** against `members`.
- To prevent race conditions across all operations that create or reactivate active member profiles, a centralized transaction-scoped advisory lock is required (detailed in Section 3.4).

> [!WARNING]
> If Migration 2.2 is deferred by the owner, concurrency-safe duplicate prevention remains **unresolved** at the database level for the application pipeline. Migration 2.2 is strongly recommended for approval.

---

## 3. Contract 1 — POST /api/v1/public/joining-applications

**[PROPOSED API CONTRACT]**

### 3.1 Purpose

Submits a prospective member joining application. Creates a record in `joining_applications` with `status = "submitted"`.

**Business Rule**: Submission creates an application, **not** an active member. Approval does **not** activate a membership. Payment confirmation and member conversion are distinct, owner-executed operations in the owner dashboard.

**Visit Scheduling Scope & Storage Invariant [ACTUAL IMPLEMENTED BEHAVIOR]**:
- When `wants_visit_first = true`, the submitted `preferred_visit_date` and `preferred_visit_time_slot` are stored **directly within the `joining_applications` record itself** (`joining_applications.wants_visit_first`, `joining_applications.preferred_visit_date`, and `joining_applications.preferred_visit_time_slot` in `app/models/public.py`).
- **No Separate Record in `gym_visit_requests`**: Setting `wants_visit_first = true` on a joining application does **NOT** insert a row into the separate `gym_visit_requests` table.
- **Architectural Boundary**: The `gym_visit_requests` table (`Contract 3 — POST /api/v1/public/visit-requests`) is dedicated exclusively to standalone facility inspection tour requests by prospective visitors who are not submitting a formal joining application. Storing visit preferences inside `joining_applications` keeps the applicant's complete intake profile unified in one record for owner review.

### 3.2 Request

- **Canonical Route**: `POST /api/v1/public/joining-applications`
- **Frontend Path**: `POST ${VITE_API_BASE_URL}/public/joining-applications`
- **Content-Type**: `application/json`

#### Request Schema & Field Rules

| Field | Type | Required | Validation Rules |
|-------|------|----------|------------------|
| `applicant_name` | string | ✅ Yes | 2–150 characters, non-empty, trimmed |
| `phone_number` | string | ✅ Yes | Valid 10-digit Indian or E.164 mobile number; normalized to E.164 before processing |
| `gender` | string (enum) | ✅ Yes | Must be one of: `male`, `female`, `other`, `prefer_not_to_say` |
| `date_of_birth` | string (date) | ⚠️ Conditional | `YYYY-MM-DD`. Must not be in the future (relative to `Asia/Kolkata` business date). Calculated age must be between 1 and 120 inclusive. Required if `age` is absent |
| `age` | integer | ⚠️ Conditional | Integer $1 \le \text{age} \le 120$. Required if `date_of_birth` is absent |
| `address` | string | ❌ Optional | Max 500 characters, nullable |
| `selected_plan_id` | string (UUID) | ❌ Optional | If provided, must resolve to a plan with `is_active=TRUE AND is_archived=FALSE AND is_publicly_visible=TRUE`. Returns HTTP 404 if inactive or non-existent |
| `wants_visit_first` | boolean | ✅ Yes | `true` or `false` |
| `preferred_visit_date` | string (date) | ⚠️ Conditional | `YYYY-MM-DD`. Required if `wants_visit_first=true`. Must be $\ge$ current date in `Asia/Kolkata` |
| `preferred_visit_time_slot` | string (enum) | ⚠️ Conditional | Required if `wants_visit_first=true`. Must match one of the proposed candidate time slot constants |

### 3.3 Age vs. Date of Birth Consistency Policy

1. **At least one required**: Request must supply `date_of_birth`, `age`, or both.
2. **If only `date_of_birth` is supplied**:
   - Backend calculates: $\text{Calculated Age} = \text{Current Year} - \text{Birth Year} - (1 \text{ if birthday not yet reached this year else } 0)$ based on current date in `Asia/Kolkata`.
   - If `Calculated Age < 1` or `Calculated Age > 120`, request is rejected with **HTTP 422 VALIDATION_ERROR**.
   - Backend automatically sets `age = Calculated Age`.
3. **If only `age` is supplied**:
   - Backend validates $1 \le \text{age} \le 120$.
4. **If both `date_of_birth` and `age` are supplied**:
   - `date_of_birth` is treated as the primary source of truth.
   - Backend calculates `Calculated Age` based on `Asia/Kolkata` business date.
   - **Exact Equality Requirement**: The submitted `age` must **strictly equal** `Calculated Age`. **No tolerance (±1 year or otherwise) is permitted.**
   - If `submitted age != Calculated Age`, the request is rejected with **HTTP 422 VALIDATION_ERROR**:
     ```json
     {
       "error": {
         "code": "VALIDATION_ERROR",
         "message": "Invalid request parameters or payload",
         "details": [
           {
             "field": "body -> age",
             "message": "Submitted age (25) does not match calculated age (26) derived from date of birth (1999-11-15)",
             "type": "value_error"
           }
         ]
       }
     }
     ```

### 3.4 Duplicate Application & Active Member Lifecycle Policy

#### Terminology Clarification & Unarchived Member Database Predicate

To prevent business logic confusion and avoid database constraint violations across frontend and backend, three distinct concepts are explicitly distinguished based on the actual database schema:

- **Unarchived Member Record (`is_archived = false`) [ACTUAL DATABASE CONSTRAINT PREDICATE]**:
  In `app/models/member.py`, the unique index is defined as:
  ```sql
  CREATE UNIQUE INDEX idx_uq_members_active_phone
  ON members (phone_number)
  WHERE is_archived = false;
  ```
  > [!CRITICAL]
  > **Database Constraint Scope**: This PostgreSQL partial unique index indexes **every unarchived member row**, regardless of whether `is_active` is `TRUE` or `FALSE`. Consequently, the database strictly prohibits two rows with `is_archived = false` from holding the same phone number.
- **Active Member Profile**: A user account in `members` where `is_archived = false AND is_active = TRUE`. This signifies an enrolled individual with an active identity profile in the gym's management system.
- **Inactive, Unarchived Member Profile**: A user account in `members` where `is_archived = false AND is_active = FALSE` (e.g. an individual whose membership lapsed or was paused, but whose profile was never soft-archived).
- **Soft-Archived Member Record**: A row in `members` where `is_archived = TRUE`. These rows are exempt from `idx_uq_members_active_phone`. Multiple archived records may share a phone number.
- **Active Membership Contract**: A specific billing contract in `membership_records` where `system_status = 'active'` with current date within `[start_date, end_date]`. An active member profile may temporarily have an expired membership contract (awaiting renewal) while remaining an active member.

> [!IMPORTANT]
> **Owner-Controlled Handling of Inactive, Unarchived Member Profiles**:
> Because `idx_uq_members_active_phone` covers all unarchived records, any workflow creating a member profile (application conversion, direct manual creation, bulk import) must check `WHERE phone_number = :normalized_phone AND is_archived = false`. Checking only `is_active = TRUE` is strictly forbidden because inserting a new record when an inactive unarchived record exists will crash with a unique constraint violation.
> When an inactive unarchived profile is detected:
> 1. **Option 1 (Re-enroll / Reactivate Existing Profile — Recommended)**: Gym administration reactivates the existing profile (`UPDATE members SET is_active = TRUE WHERE id = :existing_member_id`) and attaches the new membership contract to this existing member ID, preserving customer lifetime value and sequence history without violating uniqueness.
> 2. **Option 2 (Soft-Archive Historical Profile)**: If gym administration determines that the new applicant is a completely distinct individual (e.g., a reassigned phone number from a mobile carrier), the owner must explicitly soft-archive the obsolete historical profile (`UPDATE members SET is_archived = TRUE WHERE id = :old_member_id`) before creating the new member profile. Archiving removes the old row from the unique index predicate, permitting the new profile to be inserted cleanly.

---

#### Centralized Phone Locking Architecture [PROPOSED IMPLEMENTATION REQUIREMENT]

Because prospective applicant submissions and multiple owner-side member management workflows operate across different database tables, an uncoordinated `SELECT` followed by `INSERT` is vulnerable to phantom concurrency collisions.

To guarantee complete cross-workflow serialization, a shared PostgreSQL **transaction-scoped advisory lock** keyed by the normalized E.164 phone number must be acquired across **all six** relevant workflows:

1. **Public Joining Application Submission** (`POST /api/v1/public/joining-applications`).
2. **Owner Application-to-Member Conversion** (Owner management endpoint).
3. **Owner Manual Member Creation** (Owner direct member enrollment).
4. **Owner Member Reactivation** (Reactivating an archived/inactive member profile).
5. **Bulk Member Import** (Migration scripts creating or reactivating active member profiles).
6. **Owner Member Phone Number Update** (Owner modifying an existing member's phone number).

#### Deterministic Advisory Lock Hashing Protocol
To eliminate cross-process hashing discrepancies, the locking algorithm must adhere to one strict, deterministic specification:
- **Hashing Function**: PostgreSQL 64-bit native extended text hash:
  ```sql
  SELECT pg_advisory_xact_lock(hashtextextended(:normalized_phone_number, 0));
  ```
- **64-bit Bigint Output**: `hashtextextended(text, bigint)` outputs a signed 64-bit integer (`BIGINT`), natively matching PostgreSQL's 64-bit advisory lock primitive `pg_advisory_xact_lock(bigint)`.
- **Python `hash()` Prohibition**: Python's built-in `hash()` is randomized with a process-unique salt on startup (`PYTHONHASHSEED`) and **must NEVER be used** for distributed database locking.
- **Collision Tolerance**: While 64-bit hash collisions are mathematically negligible, any collision merely serializes unrelated phone numbers momentarily without compromising data correctness or integrity.
- **Centralized Lock Service**: The backend must encapsulate this locking protocol in a dedicated shared utility (e.g. `app/core/phone_lock.py` providing `acquire_phone_advisory_lock(session, normalized_phone)`). No raw advisory lock queries should be duplicated across endpoint modules.

---

#### Deadlock Prevention in Bulk Member Imports [PROPOSED IMPLEMENTATION REQUIREMENT]

In bulk member import operations involving multiple phone numbers in a single transaction, concurrent imports could acquire locks in divergent orders, producing circular-wait database deadlocks:
- **Deadlock Scenario**: Batch A locks Phone 1 then attempts Phone 2; Batch B locks Phone 2 then attempts Phone 1 $\rightarrow$ Deadlock.
- **Mandatory Lexicographical Ordering**: Every bulk import workflow must execute the following deadlock prevention protocol:
  1. **Parse & Normalize**: Normalize all candidate phone numbers in the batch to canonical E.164.
  2. **Validate**: Reject malformed, invalid, or ambiguous phone numbers before requesting locks.
  3. **Batch Deduplication**: Eliminate duplicate phone numbers within the import batch.
  4. **Deterministic Lexicographical Sort**: Sort the unique normalized phone numbers lexicographically:
     ```python
     sorted_phones = sorted(list(set(normalized_batch_phones)))
     ```
  5. **Ordered Lock Acquisition**: Acquire the transaction-scoped advisory locks sequentially in that exact sorted order:
     ```sql
     -- Acquired sequentially for each phone in sorted_phones
     SELECT pg_advisory_xact_lock(hashtextextended(:phone, 0));
     ```
  6. **Process & Commit**: Perform active-member and active-application checks, execute inserts/reactivations, and commit the transaction, releasing all transaction-scoped locks atomically.
- **Scope Note**: Deterministic ordering prevents circular-wait deadlocks among concurrent phone-lock requests. It does not eliminate deadlocks caused by uncoordinated operations on unrelated tables.

---

#### Resolution of Payment Verification, Membership Record & Invoice Sequencing

#### 1. Architectural Investigation & Actual Schema Foreign-Key Invariants
Inspection of the approved database schema (`DATABASE_SCHEMA.md §5.2, §5.5, §5.6, §5.8`) and actual SQLAlchemy ORM models (`app/models/payment.py`, `app/models/invoice.py`, `app/models/membership.py`, `app/models/public.py`, `app/models/member.py`) establishes the following strict constraints:
- **Mandatory Member on Payment**: `payments.member_id` is defined as `Mapped[uuid.UUID] = mapped_column(ForeignKey("members.id", ondelete="RESTRICT"), nullable=False)`. A payment record **cannot exist** in `payments` without referencing an existing primary key in `members`.
- **Mandatory Foreign Keys on Invoice**: `invoices.member_id` is `nullable=False`, `invoices.payment_id` is unique and `nullable=False`, and `invoices.membership_record_id` is `nullable=False`. An invoice **cannot exist** without referencing both an existing payment and an existing membership record.
- **Handling of Nullable `payments.membership_record_id` vs. Non-Nullable `invoices.membership_record_id`**:
  - In `payments`, `membership_record_id` is defined as `UUID NULLABLE` (e.g. to accommodate raw preliminary drafts before contract linking).
  - However, in `invoices`, `membership_record_id` is strictly **`UUID NOT NULL`**.
  - **Explicit Confirmation & Association Workflow**:
    - **Case A (Already Populated)**: If `payments.membership_record_id` is already populated, the backend verifies that the referenced membership record exists and belongs to the exact same member (`membership_records.member_id == payments.member_id`). Confirmation continues only if this relationship is valid.
    - **Case B (NULL in Payment Record)**: If `payments.membership_record_id` is `NULL`, the confirmation request **must explicitly supply/select a valid `membership_record_id`**. The backend verifies that the supplied contract belongs to `payments.member_id`. Within the **exact same database transaction**, the backend persists this association by updating `payments.membership_record_id` before inserting the invoice.
    - **Case C (Relationship Cannot Be Established)**: If `payments.membership_record_id` is missing, unresolvable, or references a contract belonging to a different member, the confirmation request **must be rejected immediately** with **HTTP 422 VALIDATION_ERROR** or **HTTP 409 RESOURCE_CONFLICT**. No invoice is created, and the payment is not marked confirmed.
    - **Atomicity & Schema Invariant**: Updating `payments.membership_record_id`, marking `payments.status = 'confirmed'`, and inserting into `invoices` are executed atomically within one transaction. The backend must **never generate an invoice with an incorrect, mismatched, or missing membership relationship**.
- **Atomic Invoice Generation on Payment Confirmation**: The business and compliance rule dictates that confirming a payment must generate an immutable tax invoice in the **exact same database transaction**. Duplicate invoices must be prevented via the unique constraint on `invoices.payment_id`.
- **No Application Payment Foreign Keys**: `joining_applications` contains only `converted_member_id` referencing `members.id`. There are **no columns, foreign keys, or relationships** linking `joining_applications` to `payments` or `invoices`.
- **Membership Record Lifecycle Discovery (`app/models/membership.py`)**:
  Inspection reveals that `membership_records.system_status` defines the following valid states:
  `'pending_activation'`, `'active'`, `'expired'`, `'cancelled'`.
  Critically, its column default is **`'pending_activation'`**, and the activation audit columns (`activated_by_owner_id` and `activated_at`) are explicitly **nullable**:
  ```python
  system_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_activation")
  activated_by_owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("owners.id", ondelete="SET NULL"), nullable=True)
  activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
  ```
  **Crucial Architectural Discovery**: A membership contract does **not** require an active payment to be instantiated. It can be created in a non-operational, non-activated state (`system_status = 'pending_activation'`) immediately upon member conversion, establishing the required `membership_record_id` *before* payment recording and confirmation.

#### 2. Evaluation of Architectural Options

- **Option A (Recommended & 100% Schema-Compliant): Pre-Payment Pending Membership Contract & Atomic Invoice Generation**
  1. Owner formally approves the joining application $\rightarrow$ `status = 'approved_pending_payment'`.
  2. Owner initiates member conversion.
  3. Conversion creates the `members` record (`is_active = TRUE`, generating `member_code` e.g. `RF001`), transitions the application to `converted_to_member` (storing `converted_member_id`), and creates the `membership_records` contract in **`system_status = 'pending_activation'`** referencing `member_id` and confirmed `plan_id`.
  4. With both `member_id` and `membership_record_id` established, the owner records the pending payment in `payments` linking both entities.
  5. Upon verifying funds (cash or UPI), the owner confirms the payment. In the **exact same database transaction**, the system generates the permanent `invoices` receipt row (linking `payment_id`, `membership_record_id`, and `member_id`). If invoice generation fails, payment confirmation rolls back atomically.
  6. With payment confirmed and invoiced, the owner explicitly activates the membership contract (`system_status = 'active'`, stamping `activated_by_owner_id` and `activated_at`).
  - *Trade-offs*: Fully compliant with the existing approved schema. Requires **zero schema modifications**. Perfectly satisfies all foreign key non-null constraints across `members`, `payments`, `invoices`, and `membership_records`.
- **Option B: Application-Linked Pre-Enrollment Payments (Requires Schema Migration)**
  - Requires altering `payments` to make `member_id` nullable, adding `joining_application_id`, altering `invoices` to make `membership_record_id` nullable, and creating custom reconciliation workflows.
  - *Trade-offs*: Violates financial accounting invariants that every payment belongs to a legal member profile and every invoice covers an identified membership contract. Heavy schema bloat. Strongly rejected.

> [!IMPORTANT]
> **Owner Decision Recommendation**: Formally recommend **Option A**. It resolves the circular dependency naturally, satisfies all foreign key invariants without database schema changes, and maintains strict owner control over payment confirmation and physical facility activation.

---

#### Workflow 1: Public Joining Application Submission (Transaction Sequence)

1. **Normalize**: Normalize input phone number to E.164 (`+91XXXXXXXXXX`).
2. **Acquire Phone Lock**:
   ```sql
   SELECT pg_advisory_xact_lock(hashtextextended(:normalized_phone_number, 0));
   ```
   *(Held until the transaction commits or rolls back).*
3. **Check Active Member Profile**:
   ```sql
   SELECT id FROM members
   WHERE phone_number = :normalized_phone_number
     AND is_archived = FALSE
     AND is_active = TRUE;
   ```
   If found, abort transaction and return **HTTP 409 RESOURCE_CONFLICT**:
   ```json
   {
     "error": {
       "code": "RESOURCE_CONFLICT",
       "message": "An active member profile is already registered with this phone number. Please contact gym administration for renewals or account assistance.",
       "details": null
     }
   }
   ```
4. **Check Active Application Pipeline**:
   ```sql
   SELECT id FROM joining_applications
   WHERE phone_number = :normalized_phone_number
     AND status IN ('submitted', 'reviewing', 'approved_pending_payment');
   ```
   If found, abort transaction and return **HTTP 409 RESOURCE_CONFLICT**:
   ```json
   {
     "error": {
       "code": "RESOURCE_CONFLICT",
       "message": "An active joining application is already being processed for this phone number. Please contact gym administration if you need to make changes.",
       "details": null
     }
   }
   ```
5. **Insert Record**: `INSERT INTO joining_applications (...) VALUES (...)` with status `'submitted'`. (Backed by Migration 2.2 unique index).
6. **Commit**: Committing the transaction commits the data and automatically releases the advisory lock.

---

#### Workflow 2: Owner Application-to-Member Conversion (Transaction Sequence — Option A)

To prevent race conditions, avoid self-conflict, and resolve the payment circular dependency:

1. **Normalize**: Obtain and normalize the phone number from the application to be converted (`:normalized_phone_number`).
2. **Acquire Phone Lock**:
   ```sql
   SELECT pg_advisory_xact_lock(hashtextextended(:normalized_phone_number, 0));
   ```
   *(Held until the transaction commits or rolls back).*
3. **Lock Source Application Row (`FOR UPDATE`)**:
   Explicitly acquire an exclusive row-level lock on the source application:
   ```sql
   SELECT * FROM joining_applications
   WHERE id = :application_id_being_converted
   FOR UPDATE;
   ```
4. **Validate Conversion Eligibility & Identity**:
   Verify that:
   - The application exists.
   - Its stored phone number matches `:normalized_phone_number`.
   - Its current status is strictly **`approved_pending_payment`**.
   > [!IMPORTANT]
   > Applications in `submitted`, `reviewing`, `rejected`, `withdrawn`, or `converted_to_member` are **strictly ineligible** for member conversion. Conversion is permitted only after an owner has formally approved the application into `approved_pending_payment`.
5. **Check Unarchived Member Predicate (`idx_uq_members_active_phone`)**:
   Query all unarchived records matching the phone number to respect the database uniqueness constraint:
   ```sql
   SELECT id, is_active FROM members
   WHERE phone_number = :normalized_phone_number
     AND is_archived = FALSE;
   ```
   - **If an Active Member Profile is found (`is_active = TRUE`)**: Abort transaction and return **HTTP 409 RESOURCE_CONFLICT** (an active member profile is already registered with this phone number).
   - **If an Inactive Unarchived Profile is found (`is_active = FALSE`)**: An unarchived historical profile exists. To prevent violating `idx_uq_members_active_phone`, a duplicate member row cannot be inserted. The owner must choose:
     1. *Re-enroll Existing Profile (Recommended)*: Reactivate existing profile (`UPDATE members SET is_active = TRUE WHERE id = :existing_member_id`) and attach the new contract to this existing member ID.
     2. *Soft-Archive Historical Profile*: If verified as a distinct person (e.g. recycled mobile number), owner explicitly archives the old record (`UPDATE members SET is_archived = TRUE WHERE id = :old_member_id`) before proceeding to create a new member profile.
6. **Check for OTHER Active Applications (Self-Exclusion)**:
   Explicitly exclude the application currently being converted using `id != :application_id_being_converted`:
   ```sql
   SELECT id FROM joining_applications
   WHERE phone_number = :normalized_phone_number
     AND status IN ('submitted', 'reviewing', 'approved_pending_payment')
     AND id != :application_id_being_converted;
   ```
   If any *other* active application is found, abort transaction and return **HTTP 409 RESOURCE_CONFLICT** (conflicting duplicate application in pipeline requiring administrative cleanup).
7. **Plan Selection & Snapshot Confirmation**:
   The public joining application permits `selected_plan_id` to be omitted (`nullable=True`). The conversion workflow handles both cases explicitly:
   - **Case A (Valid Plan Selected by Applicant)**: If `selected_plan_id` was provided and that plan remains currently eligible (`is_active = TRUE AND is_archived = FALSE`), the owner may adopt it as the proposed plan. The owner reviews and confirms the snapshot duration, base price, applicable discount, and final net fee.
   - **Case B (No Plan Selected by Applicant)**: If `selected_plan_id IS NULL`, the owner **must explicitly select an eligible plan** (`is_active = TRUE AND is_archived = FALSE`) from the catalog.
   - **Case C (Selected Plan Ineligible)**: If the originally selected plan has since been deactivated (`is_active = FALSE`) or archived (`is_archived = TRUE`), the system flags the plan as unavailable and requires the owner to explicitly select another currently eligible plan.
   - **Strict Prohibition**: The system must **never automatically assign a default plan** (e.g. defaulting arbitrarily to a 1-month plan).
   - **Schema Compatibility**: Because `membership_records.plan_id` is non-null (`ForeignKey("membership_plans.id", ondelete="RESTRICT")`), the owner's explicit confirmation provides the mandatory `plan_id` and plan snapshot fields, perfectly fulfilling all database constraints.

8. **Atomic Member Profile Creation, Pending Contract Instantiation & Application Transition**:
   In the same atomic database transaction:
   - `INSERT INTO members (...) VALUES (...)` creating the new active member profile (`is_active = TRUE`, generating `member_code` e.g. `RF001`).
   - `UPDATE joining_applications SET status = 'converted_to_member', converted_member_id = :new_member_id WHERE id = :application_id_being_converted`.
   - `INSERT INTO membership_records (...) VALUES (...)` generating the initial contract in **`system_status = 'pending_activation'`**:
     - `member_id = :new_member_id`
     - `plan_id = :confirmed_plan_id`
     - `plan_snapshot_name = :confirmed_plan.name`
     - `plan_snapshot_duration_days = :confirmed_plan.duration_days`
     - `plan_snapshot_base_price = :confirmed_plan.base_price`
     - `plan_snapshot_is_pt = :confirmed_plan.is_pt`
     - `discount_amount = :confirmed_discount_amount`
     - `total_fee = :confirmed_plan.base_price - :confirmed_discount_amount`
     - `start_date = :proposed_start_date`
     - `expiry_date = :proposed_start_date + :confirmed_plan.duration_days - 1`
     - `created_by_owner_id = :owner_id`
     - `activated_by_owner_id = NULL`
     - `activated_at = NULL`

9. **Commit Conversion Transaction**:
   Committing the transaction persists all three entities atomically and releases the source row lock and phone advisory lock. The member profile is active, and the membership contract is instantiated in pending activation state.

10. **Payment Recording Workflow**:
    With stable `member_id` and `membership_record_id` established:
    - The owner records the received payment into `payments` linking `member_id` and `membership_record_id` with `status = 'pending'`.
    - **Flexible Payment Types Supported**:
      - Full settlement (`payment_type = 'full'`).
      - Partial down-payment (`payment_type = 'partial'`).
      - Installment payment against scheduled balance dues (`payment_type = 'installment'`).
      - Advance payment (`payment_type = 'advance'`).
    - **1 : N Relationship**: Multiple payment records can belong to the same `membership_record_id`.

11. **Synchronous Payment Confirmation & Invoice Generation (Strengthened Concurrency, Refund-Aware Financials & Idempotency Guarantees)**:
    When an owner confirms a received payment (full settlement, partial down-payment, installment, or advance):

    ##### A. Hierarchical Membership-Level Locking Sequence & Mandatory Association Revalidation
    To prevent two concurrent installment confirmations or a concurrent refund and payment confirmation for the same membership contract from calculating stale cumulative balances or racing on remaining fee amounts, all payment confirmation operations adhere to a strict two-tier hierarchical lock ordering:

    1. **Identify & Validate Relationship Pre-Check**:
       - Retrieve the target payment record (`:payment_id`).
       - Determine the candidate contract ID:
         - If `payments.membership_record_id` is already populated on the payment record, set `:candidate_membership_record_id = payments.membership_record_id`.
         - If `payments.membership_record_id` is `NULL`, the confirmation request **must explicitly supply a valid `:membership_record_id` in the request payload** (`:payload.membership_record_id`). Set `:candidate_membership_record_id = :payload.membership_record_id`.
       - If no contract is associated or supplied, abort immediately with **HTTP 422 VALIDATION_ERROR**.
    2. **Lock `membership_records` Row First**:
       Acquire an exclusive row-level lock on the contract using `:candidate_membership_record_id` to serialize all financial calculations for this membership:
       ```sql
       SELECT * FROM membership_records
       WHERE id = :candidate_membership_record_id
       FOR UPDATE;
       ```
    3. **Lock `payments` Row Second**:
       Acquire an exclusive row-level lock on the individual payment to serialize its status transition:
       ```sql
       SELECT * FROM payments
       WHERE id = :payment_id
       FOR UPDATE;
       ```
    4. **Post-Lock Re-Read & Mandatory Membership Association Revalidation**:
       Under the acquired row locks, re-read the fresh, committed `payments` row from the database:
       - **Detecting Stale Pre-Lock Association**:
         Inspect the locked `payments.membership_record_id`:
         - If `payments.membership_record_id` is already populated on the locked payment record:
           - Verify that `payments.membership_record_id == :candidate_membership_record_id`.
           - If `payments.membership_record_id` does NOT match `:candidate_membership_record_id` (indicating another concurrent transaction associated this payment with a different membership record while this transaction was waiting for the lock), **abort safely with HTTP 409 RESOURCE_CONFLICT** ("Payment was concurrently associated with a different membership contract").
           - **Do not proceed using a stale pre-lock association.**
         - If `payments.membership_record_id` is `NULL` on the locked payment record:
           - Verify that `:payload.membership_record_id` was provided and matches `:candidate_membership_record_id`.
           - Verify that `membership_records.member_id == payments.member_id`. If the contract belongs to a different member, abort immediately with **HTTP 409 RESOURCE_CONFLICT** or **HTTP 422 VALIDATION_ERROR** ("Membership record belongs to a different member").
           - The resolved association `:candidate_membership_record_id` will be persisted onto the payment record during confirmation (Step 9).

    ##### B. Idempotency State Handling & Concurrency Evaluation
    5. **Evaluate Idempotency & Committed Payment State**:
       - **Idempotency Key Assignment Timing**:
         In the approved schema, `payments.idempotency_key` is assigned primarily during **payment creation** (`payments.idempotency_key` on the payment record).
         If confirmation-time assignment is supported, the incoming key must be explicitly persisted to `payments.idempotency_key` under the acquired payment-row lock (`FOR UPDATE`), where PostgreSQL enforces uniqueness via `uq_payments_idempotency_key`.
       - **Confirmation Request Payload**:
         The payment confirmation request payload consists of:
         - `payment_id`: UUID
         - `membership_record_id`: UUID (required if `payments.membership_record_id` is initially NULL)
         - `confirmed_amount`: Decimal / Numeric string matching `payments.amount`
         - `payment_method`: String matching `payments.payment_method`
         - `idempotency_key`: Optional String(128)
       - **Explicit Architectural Schema Limitation**:
         The approved schema stores `idempotency_key: String(128)` on `payments`, but **does not possess a request body hash column** (e.g. `request_payload_hash VARCHAR(64)`). Therefore, idempotency verification is performed strictly by comparing persisted core business entity fields rather than an automated cryptographic request fingerprint. Generic full-request payload fingerprinting is not claimed without a dedicated, persisted request hash column.
       - **Concurrency & Idempotency State Machine**:
         When concurrent confirmation requests arrive for the same payment, the first transaction acquires the required row locks (`membership_records` then `payments` `FOR UPDATE`). Any concurrent request blocks waiting on the payment lock. Once unblocked, the waiting request re-reads the payment row and evaluates its actual committed state:
         - **Case 1: Pending Payment with Matching Key (`payments.status == 'pending'`)**:
           - If `payments.idempotency_key` was already populated during payment creation and `payload.idempotency_key == payments.idempotency_key`:
             Continue confirmation processing after acquiring the required locks.
           - If `payments.idempotency_key` is populated but `payload.idempotency_key` does not match:
             Reject with **HTTP 409 RESOURCE_CONFLICT** ("Idempotency key mismatch for pending payment").
           - If `payments.idempotency_key` is `NULL` and `payload.idempotency_key` is supplied:
             Persist `idempotency_key = payload.idempotency_key` onto the payment record under the payment row lock during confirmation.
           - Proceed to balance calculations and invoice generation.
         - **Case 2: Concurrent Request (Waiting on Payment Lock)**:
           The concurrent request waits on `SELECT ... FROM payments WHERE id = :payment_id FOR UPDATE`. Upon acquiring the lock, it re-reads the fresh payment row and evaluates whether the payment has transitioned to `'confirmed'` or remains `'pending'`.
         - **Case 3: Already-Confirmed Payment with Matching Key & Matching Stored Business Fields**:
           If `payments.status == 'confirmed'`, and `payload.idempotency_key` is provided and matches `payments.idempotency_key`:
           - Compare incoming request parameters against locked, persisted database fields:
             - `payload.confirmed_amount == payments.amount`
             - `payload.payment_method == payments.payment_method`
             - `:candidate_membership_record_id == payments.membership_record_id`
             - `payments.member_id == membership_records.member_id`
           - If all stored business fields match: Safely return the existing original invoice (`SELECT * FROM invoices WHERE payment_id = :payment_id`).
         - **Case 4: Already-Confirmed Payment with Conflicting Fields**:
           If `payments.status == 'confirmed'`, and `payload.idempotency_key` matches `payments.idempotency_key`, but any stored business field differs (differing amount, payment method, or membership record association):
           Reject immediately with **HTTP 409 RESOURCE_CONFLICT** ("Payment has already been confirmed with conflicting parameters").
         - **Case 5: Already-Confirmed Payment Without a Matching Idempotency Key**:
           If `payments.status == 'confirmed'`, and `payload.idempotency_key` is omitted, or does NOT match `payments.idempotency_key`:
           Reject immediately with **HTTP 409 RESOURCE_CONFLICT** ("Payment has already been confirmed and invoiced").
         - **Case 6: Key Reused for a Different Payment**:
           If `payload.idempotency_key` is already assigned to a different payment row (`payments.id != :payment_id`), PostgreSQL raises an `IntegrityError` on `uq_payments_idempotency_key`, mapping directly to **HTTP 409 RESOURCE_CONFLICT** ("Idempotency key already assigned to a different payment").
       - **Storage Engine Guarantee**: `payments.idempotency_key UNIQUE` and `invoices.payment_id UNIQUE` guarantee that concurrent threads cannot create duplicate confirmations or duplicate invoices.

    ##### C. Refund-Aware Financial Ledger Calculations & Overpayment Policy
    6. **Calculate Prior Confirmed Payments and Processed Refunds Under Contract Lock**:
       Because `membership_records` is locked `FOR UPDATE`, no concurrent transaction can confirm another installment, process refunds, or calculate balances for this contract simultaneously.
       The calculation strictly factors in all prior confirmed payments and all processed refunds for this membership contract:
       ```sql
       -- Prior gross confirmed payments
       SELECT COALESCE(SUM(amount), 0.00)
       FROM payments
       WHERE membership_record_id = :candidate_membership_record_id
         AND status = 'confirmed';

       -- Prior processed refunds for this contract's payments
       SELECT COALESCE(SUM(pr.amount), 0.00)
       FROM payment_refunds pr
       JOIN payments p ON pr.original_payment_id = p.id
       WHERE p.membership_record_id = :candidate_membership_record_id
         AND pr.status = 'processed';
       ```
    7. **Calculate Net Cumulative Paid Amount & Remaining Balance**:
       $$\text{prior\_net\_confirmed\_paid} = \text{prior\_gross\_confirmed\_paid} - \text{prior\_processed\_refunds}$$
       $$\text{cumulative\_paid\_to\_date} = \text{prior\_net\_confirmed\_paid} + \text{payments.amount}$$
       $$\text{contract\_total\_fee} = \text{membership\_records.total\_fee}$$
       $$\text{remaining\_balance\_after\_payment} = \text{contract\_total\_fee} - \text{cumulative\_paid\_to\_date}$$
    8. **Strict Overpayment Policy & Balance Invariants**:
       - The system must **never silently produce a negative remaining balance**.
       - The database enforces CheckConstraint `ck_invoices_balances_valid`:
         `contract_total_fee >= 0.00 AND payment_amount > 0.00 AND remaining_balance_after_payment >= 0.00`.
       - If `payments.amount` exceeds the remaining contract balance (producing `remaining_balance_after_payment < 0.00`), the payment amount exceeds the outstanding contract liability.
       - Unless a separately approved advance-payment credit rule explicitly permits customer credit-ledger balances, the confirmation transaction **must be rejected immediately** with **HTTP 422 VALIDATION_ERROR** or **HTTP 409 RESOURCE_CONFLICT** ("Payment amount exceeds remaining contract balance").
       - **Historical Invoice Immutability**:
         Past invoices are immutable, frozen financial receipts reflecting the contract balance state *at the moment of their respective confirmation*. A subsequent refund modifies the net ledger position going forward (`prior_net_confirmed_paid`), allowing subsequent installment confirmations or replacement payments to reflect the updated net balance. Past invoice rows are never updated or recalculated.
       - Existing database invoice constraints are preserved without modification.

    ##### D. Atomic Persistence & Invoice Generation
    9. **Confirm Payment & Persist Membership Association**:
       Within the same transaction, update `payments` (persisting `membership_record_id` if it was previously `NULL`, and persisting `idempotency_key` if supplied during confirmation):
       ```sql
       UPDATE payments
       SET membership_record_id = :candidate_membership_record_id,
           idempotency_key = COALESCE(:idempotency_key, idempotency_key),
           status = 'confirmed',
           confirmed_by_owner_id = :confirming_owner_id,
           confirmed_at = NOW()
       WHERE id = :payment_id;
       ```
    10. **Generate Immutable Invoice in Same Transaction**:
        ```sql
        INSERT INTO invoices (
          id,
          invoice_number,
          payment_id,
          membership_record_id,
          member_id,
          contract_total_fee,
          payment_amount,
          cumulative_paid_to_date,
          remaining_balance_after_payment,
          payment_date,
          created_by_owner_id,
          created_at
        ) VALUES (
          gen_random_uuid(),
          :generated_invoice_number,
          :payment_id,
          :candidate_membership_record_id,
          :member_id,
          :contract_total_fee,
          :payments_amount,
          :cumulative_paid_to_date,
          :remaining_balance_after_payment,
          :payments_date,
          :confirming_owner_id,
          NOW()
        );
        ```
    11. **Rollback Guarantee**:
        If invoice generation fails for any reason (sequence collision, disk failure, validation error), the entire transaction rolls back immediately. `payments.status` remains `'pending'`, `payments.membership_record_id` reverts if it was updated, and no invoice is created.
    12. **Commit Transaction**:
        Committing the transaction persists the payment confirmation, contract association, and invoice creation atomically, releasing both the `membership_records` lock and `payments` lock simultaneously.

    ##### E. Consistent Lock Acquisition Order Across Confirmation and Refund Processing
    To prevent transaction deadlocks and race conditions between concurrent installment payment confirmations and refund processing for the same membership contract, **both payment confirmation and refund processing acquire locks in the exact same hierarchical order**:
    1. Lock `membership_records` row `FOR UPDATE`.
    2. Lock `payments` row `FOR UPDATE`.
    Because both workflows serialize at the contract level first, concurrent execution cannot compute inconsistent financial balances, and database deadlocks between the two operations are eliminated.

12. **Separation of Payment Confirmation from Membership Activation**:
    > [!IMPORTANT]
    > **Core Business Invariant**: **Payment confirmation never automatically activates a membership.**
    - Confirmation of a full payment, partial payment, multiple installments, or advance payment leaves the contract in **`system_status = 'pending_activation'`**.
    - Membership activation is strictly an **independent, owner-authorized operational action**.
    - When the owner explicitly triggers activation in the dashboard, the system updates the record using verified existing model fields:
      ```sql
      UPDATE membership_records
      SET system_status = 'active',
           activated_by_owner_id = :activating_owner_id,
           activated_at = NOW(),
           start_date = :actual_start_date,
           expiry_date = :actual_expiry_date
      WHERE id = :membership_record_id;
      ```
    - **Approved Date & Renewal Rules (`DATABASE_SCHEMA.md §12.2`)**:
      - **New Membership**: `start_date` is the agreed facility access date; `expiry_date = start_date + plan_snapshot_duration_days - 1 day`.
      - **Renewal Before Expiry**: `new_start_date = current_expiry_date + 1 day`; `new_expiry_date = new_start_date + plan_snapshot_duration_days - 1 day`; links `previous_membership_id`.
      - **Renewal After Expiry (Lapsed Member)**: `new_start_date = payment_confirmation_date + 1 day` (or owner-authorized start date); `new_expiry_date = new_start_date + plan_snapshot_duration_days - 1 day`.
    - No new columns, fake statuses, or automatic triggers are introduced.

---

#### Workflow 2B: Owner Refund Processing & Financial Ledger Locking Protocol [APPROVED EXISTING SCHEMA]

When an owner processes an explicit refund or correction for a previously confirmed payment, concurrent installment confirmations on the same contract could read stale net balances. To prevent inconsistent financial balance calculations and ensure deadlock-free concurrency, refund processing executes under an identical hierarchical lock acquisition order:

1. **Target Identification & Pre-Check**:
   - The owner selects a confirmed payment record to refund (`:original_payment_id`).
   - Query payment to resolve the contract association:
     ```sql
     SELECT id, member_id, membership_record_id, amount, status
     FROM payments
     WHERE id = :original_payment_id;
     ```
   - Verify `payments.status == 'confirmed'`. (Only confirmed payments may be refunded).
   - Resolve contract ID: `:membership_record_id = payments.membership_record_id`.
   - If `:membership_record_id` is `NULL`, abort with **HTTP 422 VALIDATION_ERROR** (confirmed payments must reference a valid membership record).

2. **Strict Consistent Lock Acquisition Order (Identical to Payment Confirmation)**:
   - **Step 1: Lock `membership_records` Row First**:
     Acquire an exclusive row-level lock on the contract to serialize all contract-level balance calculations:
     ```sql
     SELECT * FROM membership_records
     WHERE id = :membership_record_id
     FOR UPDATE;
     ```
   - **Step 2: Lock `payments` Row Second**:
     Acquire an exclusive row-level lock on the original payment being refunded:
     ```sql
     SELECT * FROM payments
     WHERE id = :original_payment_id
     FOR UPDATE;
     ```

3. **Revalidation Under Locks**:
   - Verify under the acquired row locks that `payments.status == 'confirmed'`.
   - Verify `payments.membership_record_id == :membership_record_id`.
   - Verify `payments.member_id == membership_records.member_id`.

4. **Payment-Level & Contract-Level Refund Validation**:
   - **Positive Refund Amount**:
     Enforce `amount > 0.00` (conforming to CheckConstraint `ck_refunds_amount_positive`).
   - **Payment-Level Refund Ceiling**:
     Calculate prior processed refunds for this specific payment under lock:
     ```sql
     SELECT COALESCE(SUM(amount), 0.00)
     FROM payment_refunds
     WHERE original_payment_id = :original_payment_id
       AND status = 'processed';
     ```
     Enforce: `prior_payment_refunds + :refund_amount <= payments.amount`. (Total refunded cannot exceed the original confirmed payment amount). If exceeded, reject with **HTTP 422 VALIDATION_ERROR** ("Refund amount exceeds original payment balance").
   - **Contract-Level Net Balance Update**:
     Calculate contract gross confirmed payments and total processed refunds under the contract lock:
     ```sql
     -- Contract gross confirmed payments
     SELECT COALESCE(SUM(amount), 0.00) FROM payments
     WHERE membership_record_id = :membership_record_id AND status = 'confirmed';

     -- Contract total processed refunds
     SELECT COALESCE(SUM(pr.amount), 0.00)
     FROM payment_refunds pr
     JOIN payments p ON pr.original_payment_id = p.id
     WHERE p.membership_record_id = :membership_record_id
       AND pr.status = 'processed';
     ```
     The net confirmed paid position updates dynamically:
     $$\text{net\_confirmed\_paid} = \text{gross\_confirmed} - (\text{prior\_contract\_refunds} + \text{refund\_amount})$$

5. **Insert Record into `payment_refunds` Table**:
   Persist the refund record using verified existing model columns and default status (`status = 'processed'`):
   ```sql
   INSERT INTO payment_refunds (
     id,
     refund_number,
     original_payment_id,
     member_id,
     amount,
     refund_reason,
     refund_method,
     transaction_reference,
     status,
     processed_by_owner_id,
     created_at
   ) VALUES (
     gen_random_uuid(),
     :generated_refund_number,
     :original_payment_id,
     :member_id,
     :refund_amount,
     :refund_reason,
     :refund_method,
     :transaction_reference,
     'processed',
     :processing_owner_id,
     NOW()
   );
   ```

6. **Historical Invoices Left Intact**:
   Historical invoice records (`invoices`) are **never modified or deleted**. The refund is recorded as an independent correction in `payment_refunds`, dynamically adjusting the contract's net balance. Any subsequent installment payments confirmed for this contract will calculate balances against the revised net position.

7. **Commit Transaction**:
   Committing the transaction persists the refund record atomically and releases both the `membership_records` lock and `payments` lock simultaneously.

---

#### Workflows 3, 4 & 5: Manual Member Creation, Reactivation & Bulk Import

For any manual owner creation of a member, reactivation of an inactive member (`is_active` set to `TRUE`), or bulk data import:
1. Normalize phone to E.164. (For bulk import, sort batch phones lexicographically and lock in sorted order to prevent deadlocks).
2. Acquire `pg_advisory_xact_lock(hashtextextended(:normalized_phone_number, 0))`.
3. Check for existing unarchived member profiles:
   ```sql
   SELECT id, is_active FROM members
   WHERE phone_number = :normalized_phone_number
     AND is_archived = FALSE;
   ```
   - If an **active unarchived member** (`is_active = TRUE`) is found, abort immediately with **HTTP 409 RESOURCE_CONFLICT** ("Member with this phone number already exists").
   - If an **inactive unarchived member** (`is_active = FALSE`) is found, do not attempt to insert a duplicate member row (which would violate database unique index `idx_uq_members_active_phone`). Present the owner with two administrative options:
     - **Option 1 (Re-enrollment / Reactivation)**: Reactivate the existing member profile (`UPDATE members SET is_active = TRUE, updated_at = NOW() WHERE id = :existing_member_id`) and create a new membership contract under their existing profile.
     - **Option 2 (Reassigned Phone / Soft-Archive)**: If the owner confirms that the new applicant is a distinct individual who acquired a reassigned phone number, the owner must explicitly soft-archive the old inactive profile first (`UPDATE members SET is_archived = TRUE, updated_at = NOW() WHERE id = :old_member_id`). This releases the phone number under `idx_uq_members_active_phone`, allowing the new member profile to be created cleanly.
4. Check for active joining applications (`joining_applications.status IN ('submitted', 'reviewing', 'approved_pending_payment')`). If found, reject with **HTTP 409 RESOURCE_CONFLICT**.
5. Execute insert or reactivation update.
6. Commit transaction, releasing the advisory lock atomically.

---

#### Workflow 6: Owner Member Phone Number Update (Two-Phase Sorted Advisory Locks)

When an owner updates an existing member's phone number in the management dashboard, a concurrent phone swap or update can race against incoming joining applications or concurrent member updates. To eliminate deadlocks and ensure complete isolation across both old and new numbers, the transaction employs a deterministic two-key advisory locking protocol:

1. **Normalize Both Phone Numbers**:
   - Normalize the member's current phone number to canonical E.164: `:normalized_old_phone`.
   - Normalize the proposed new phone number to canonical E.164: `:normalized_new_phone`.

2. **Handle Identity / No-Op Update**:
   - If `:normalized_old_phone == :normalized_new_phone`:
     - Acquire a single transaction-scoped advisory lock:
       ```sql
       SELECT pg_advisory_xact_lock(hashtextextended(:normalized_new_phone, 0));
       ```
     - Lock the member row `FOR UPDATE`:
       ```sql
       SELECT * FROM members WHERE id = :member_id FOR UPDATE;
       ```
     - Verify and commit without acquiring redundant locks.

3. **Deterministic Lexicographical Lock Acquisition**:
   - If `:normalized_old_phone != :normalized_new_phone`:
     - Sort both phone strings in strict lexicographical order:
       `sorted_phones = sorted([:normalized_old_phone, :normalized_new_phone])`
     - Acquire both transaction-scoped advisory locks sequentially in that sorted order:
       ```sql
       SELECT pg_advisory_xact_lock(hashtextextended(:sorted_phones[0], 0));
       SELECT pg_advisory_xact_lock(hashtextextended(:sorted_phones[1], 0));
       ```
     - This guarantees that two concurrent operations updating between the same two numbers in opposite directions will acquire locks in the exact same sequence, eliminating PostgreSQL transaction deadlocks.

4. **Lock and Verify Current Member Row**:
   - Acquire exclusive row-level lock on the target member:
     ```sql
     SELECT * FROM members WHERE id = :member_id FOR UPDATE;
     ```
   - Verify that the member's stored phone number still equals `:normalized_old_phone`. If a concurrent transaction already altered the member's phone number, abort immediately with **HTTP 409 RESOURCE_CONFLICT** ("Member phone number was modified concurrently").

5. **Check for Collisions Under Dual Locks**:
   - **Check Unarchived Member Collision (Excluding Current Member)**:
     ```sql
     SELECT id FROM members
     WHERE phone_number = :normalized_new_phone
       AND is_archived = FALSE
       AND id != :member_id;
     ```
     If found, abort transaction and return **HTTP 409 RESOURCE_CONFLICT** ("Another gym member profile is already registered with this phone number").
   - **Check Active Joining Application Collision**:
     ```sql
     SELECT id FROM joining_applications
     WHERE phone_number = :normalized_new_phone
       AND status IN ('submitted', 'reviewing', 'approved_pending_payment');
     ```
     If found, abort transaction and return **HTTP 409 RESOURCE_CONFLICT** ("An active joining application is currently being processed for this phone number").

6. **Execute Update**:
   ```sql
   UPDATE members
   SET phone_number = :normalized_new_phone,
       updated_at = NOW()
   WHERE id = :member_id;
   ```

7. **Commit Transaction**:
   Committing the transaction persists the phone update and automatically releases the member row lock and both advisory locks simultaneously.

---

#### Permitted Reapplication Lifecycle
- `rejected` and `withdrawn` applications release the phone number: prospective applicants whose previous applications were rejected or withdrawn (and who do not possess an unarchived member profile) may submit a fresh joining application.
- `converted_to_member` does **not** release the phone number: reapplication remains blocked as long as the member profile remains unarchived (`members.is_archived = FALSE`). If a lapsed member profile is subsequently soft-archived (`members.is_archived = TRUE`), the phone number is released for new registrations.
- **Historical Integrity**: Historical applications and member records are preserved permanently for accounting, tax, and audit compliance. No records are deleted or overwritten.

### 3.5 Successful Response

**HTTP 201 Created**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "submitted",
  "created_at": "2026-11-18T07:30:00Z"
}
```

> [!NOTE]
> Owner-only internal fields (`handling_owner_id`, `notes`, `converted_member_id`) are never exposed in the public submission response.

### 3.6 Application Status Progression [APPROVED EXISTING SCHEMA]

| Status | Set By | Description |
|--------|--------|-------------|
| `submitted` | Public API | Default initial state upon public submission |
| `reviewing` | Owner | Owner is reviewing details or speaking with applicant (ineligible for conversion) |
| `approved_pending_payment` | Owner | Application approved; waiting for joining fee / membership payment (**only status eligible for conversion**) |
| `converted_to_member` | Owner | Converted to active member profile (subsequently eligible for payment entry) |
| `rejected` | Owner | Application rejected by gym administration (releases phone number) |
| `withdrawn` | Owner | Applicant withdrew application before payment (releases phone number) |

---

## 4. Contract 2 — POST /api/v1/public/enquiries

**[PROPOSED API CONTRACT]**

### 4.1 Purpose

Accepts general questions, equipment inquiries, or feedback from prospective visitors.

### 4.2 Request

- **Canonical Route**: `POST /api/v1/public/enquiries`
- **Frontend Path**: `POST ${VITE_API_BASE_URL}/public/enquiries`
- **Content-Type**: `application/json`

#### Request Schema

| Field | Type | Required | Validation Rules |
|-------|------|----------|------------------|
| `name` | string | ✅ Yes | 2–150 characters, non-empty, trimmed |
| `phone_number` | string | ✅ Yes | Valid Indian or international mobile number; normalized to E.164 |
| `message` | string | ✅ Yes | 5–2000 characters, non-empty |

### 4.3 Successful Response

**HTTP 201 Created**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "status": "pending",
  "created_at": "2026-11-18T07:31:00Z"
}
```

### 4.4 Enquiry Status Values [APPROVED EXISTING SCHEMA]

| Status | Set By | Description |
|--------|--------|-------------|
| `pending` | Public API | Newly submitted inquiry awaiting owner review |
| `contacted` | Owner | Owner reached out to visitor |
| `resolved` | Owner | Inquiry answered and completed |
| `spam` | Owner | Flagged as junk; hidden from active dashboard |

---

## 5. Contract 3 — POST /api/v1/public/visit-requests

**[PROPOSED API CONTRACT]**

### 5.1 Purpose

Allows a prospective member to schedule an in-person facility tour or trial workout.

### 5.2 Visit Request Time Slot Constants [PROPOSED CONSTANTS AWAITING OWNER APPROVAL]

The following three candidate time slot strings are proposed:

1. `"Morning (9am–12pm)"` — Operational interval: [09:00, 12:00) (09:00 inclusive to 12:00 exclusive).
2. `"Afternoon (12pm–4pm)"` — Operational interval: [12:00, 16:00) (12:00 inclusive to 16:00 exclusive).
3. `"Evening (4pm–8pm)"` — Operational interval: [16:00, 20:00) (16:00 inclusive to 20:00 exclusive).

> [!IMPORTANT]
> **Pending Owner Confirmation**: These three slots are candidate constants proposed for architectural alignment. They have **not been finalized or approved** by the gym owners. The stated intervals describe operational hours and do not imply automated real-time booking logic. Upon formal owner confirmation, backend Pydantic schemas and frontend dropdown menus will strictly bind to the confirmed strings. Non-matching strings will fail with **HTTP 422 VALIDATION_ERROR**.

### 5.3 Request

- **Canonical Route**: `POST /api/v1/public/visit-requests`
- **Frontend Path**: `POST ${VITE_API_BASE_URL}/public/visit-requests`
- **Content-Type**: `application/json`

#### Request Schema

| Field | Type | Required | Validation Rules |
|-------|------|----------|------------------|
| `visitor_name` | string | ✅ Yes | 2–150 characters, non-empty, trimmed |
| `phone_number` | string | ✅ Yes | Valid Indian or international mobile number; normalized to E.164 |
| `preferred_date` | string (date) | ✅ Yes | `YYYY-MM-DD`. Must be $\ge$ current date in `Asia/Kolkata` (fails with HTTP 422 if in the past) |
| `preferred_time_slot` | string (enum) | ✅ Yes | Must match one of the proposed candidate time slot constants |

### 5.4 Successful Response

**HTTP 201 Created**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440002",
  "status": "pending",
  "preferred_date": "2026-11-22",
  "preferred_time_slot": "Morning (9am–12pm)",
  "created_at": "2026-11-18T07:32:00Z"
}
```

### 5.5 Visit Request Status Progression [APPROVED EXISTING SCHEMA]

| Status | Set By | Description |
|--------|--------|-------------|
| `pending` | Public API | Request received; awaiting owner confirmation |
| `approved` | Owner | Visit confirmed for requested date/slot |
| `alternative_suggested` | Owner | Requested slot unavailable; owner suggested alternative date/slot |
| `completed` | Owner | Visitor completed their facility tour |
| `missed` | Owner | Visitor did not arrive |
| `rejected` | Owner | Request declined |
| `cancelled` | Owner | Request cancelled |

---

## 6. Contract 4 — GET /api/v1/public/membership-plans

**[PROPOSED API CONTRACT]**

### 6.1 Purpose

Returns the active, publicly visible membership plans for the marketing and pricing pages.

### 6.2 Request

- **Canonical Route**: `GET /api/v1/public/membership-plans`
- **Frontend Path**: `GET ${VITE_API_BASE_URL}/public/membership-plans`

No parameters, headers, or authentication required.

### 6.3 Backend Query

```sql
SELECT
    id, name, category, duration_days, duration_months,
    base_price, description, is_personal_training, is_custom_offer
FROM membership_plans
WHERE is_active = TRUE
  AND is_archived = FALSE
  AND is_publicly_visible = TRUE
ORDER BY duration_days ASC;
```

### 6.4 Successful Response

**HTTP 200 OK**
```json
{
  "plans": [
    {
      "id": "d6a4fb53-ce70-7102-e845-4567890abcde",
      "name": "Monthly Basic",
      "category": "general_fitness",
      "duration_days": 30,
      "duration_months": 1,
      "base_price": "1500.00",
      "description": "Full access to general fitness equipment and locker facilities.",
      "is_personal_training": false,
      "is_custom_offer": false
    }
  ]
}
```

- Returns `{"plans": []}` if no plans are published (never 404).
- `base_price`: Decimal formatted as string (e.g. `"1500.00"`).
- Internal columns omitted: `created_by_owner_id`, `is_archived`, `is_active`, `is_publicly_visible`, `created_at`, `updated_at`.

---

## 7. Contract 5 — GET /api/v1/public/gallery

**[PROPOSED API CONTRACT]**

### 7.1 Purpose

Provides images of gym facilities, equipment, and training zones for the public landing page gallery.

### 7.2 Gallery Image URL Resolution & Security Architecture

In `app/models/gallery.py` [APPROVED EXISTING SCHEMA], the column `storage_path` stores a relative storage key or filename (e.g. `gallery/facilities/weights-area.webp`) or an absolute URL.

#### Proposed Configuration Settings
To deliver gallery assets securely without hardcoding or leaking infrastructure, two separate configuration parameters are proposed (e.g. in `app/core/config.py`):

1. **`settings.CDN_BASE_URL`**: Proposed base origin used to prefix relative storage keys (e.g. `https://cdn.regalfitness.in`).
2. **`settings.APPROVED_ASSET_DOMAINS`**: Proposed allowlist of approved hostnames permitted for absolute asset URLs (e.g. `["cdn.regalfitness.in", "assets.regalfitness.in"]`).
   - **Exact Hostname Matching Invariant**: Hostname matching is strictly evaluated via **exact, case-insensitive string equality** (`url_host.lower() == allowed_domain.lower()`).
   - **No Wildcard or Suffix Matching**: Wildcard matching (`*.regalfitness.in`) and partial suffix matching (`url_host.endswith("regalfitness.in")`) are **strictly prohibited** to prevent domain spoofing (such as `attackerregalfitness.in` or unauthorized staging subdomains). Subdomains are only accepted when **explicitly and independently enumerated** in `settings.APPROVED_ASSET_DOMAINS`.

> [!IMPORTANT]
> Both `CDN_BASE_URL` and `APPROVED_ASSET_DOMAINS` are **proposed configuration settings**. Neither setting currently exists in `app/core/config.py`. They must be added prior to implementing public gallery URL resolution.

#### CDN_BASE_URL Validation Requirements [PROPOSED IMPLEMENTATION REQUIREMENT]
To guarantee operational security, `CDN_BASE_URL` must undergo strict startup validation (e.g. via Pydantic validator in `app/core/config.py`):
1. **HTTPS Enforcement**: Must strictly start with `https://`. Insecure `http://` is rejected.
2. **Valid Hostname**: Must parse to a valid, fully qualified domain name without user credentials.
3. **No Embedded Credentials**: URLs containing user-info components (`https://user:password@host`) are strictly forbidden and must fail validation.
4. **Domain Membership via Exact Match**: The hostname of `CDN_BASE_URL` must match an entry in `APPROVED_ASSET_DOMAINS` exactly.
5. **Normalization**: The base URL must be normalized (stripping trailing slashes, lowercasing scheme and hostname) before any asset path is appended.
6. **Startup Halt**: If `CDN_BASE_URL` fails validation in production, application startup must halt immediately.

#### Strict URL Generation & Path Sanitization Rules [PROPOSED IMPLEMENTATION REQUIREMENT]
1. **Public Asset Delivery**: Public gallery assets are intended to use **permanent public CDN / static cache URLs**, not expiring signed URLs, ensuring optimal browser caching and CDN edge delivery.
2. **Absolute HTTPS URL Validation**:
   - Must parse successfully as an RFC 3986 URI with scheme `https://`.
   - **User-info Rejection**: Absolute URLs containing embedded username/password components are strictly rejected.
   - **Hostname Validation**: Must contain a non-empty, valid hostname.
   - **Exact Approved Domain Check**: The hostname of the absolute URL must match an entry in `settings.APPROVED_ASSET_DOMAINS` exactly. Unlisted subdomains or external domains (e.g. `https://untrusted-site.com/...`) are rejected.
3. **Relative Storage Path Sanitization**:
   Before concatenating any relative path to `CDN_BASE_URL`, the path must undergo strict canonical decoding and validation:
   - **Directory Traversal Rejection**: Reject paths containing `../` or `..\\`.
   - **Encoded Traversal Rejection**: Reject URL-encoded traversal sequences (such as `%2e%2e%2f`, `%2e%2e/`, `%2e%2e%5c`) and double-encoded sequences where multi-pass decoding resolves to directory traversal.
   - **Filesystem Path Rejection**: Reject absolute Unix paths (`/var/...`, `/etc/...`) and Windows drive paths (`C:\...`, `D:\...`).
   - **Backslash Rejection**: Reject backslash path separators (`\`) to enforce POSIX-compliant URI syntax.
   - **Null Byte Rejection**: Reject any path containing null bytes (`\0`, `%00`) or control characters.
4. **Information Leakage Prevention**:
   - Private storage bucket names, internal object storage keys, AWS/cloud credentials, and local server filesystem paths must **never** be exposed in API responses.
   - Public URLs must never be synthesized directly from unvalidated client input.
5. **Resolution Failure Handling**:
   - If `CDN_BASE_URL` is unconfigured, or if an image row contains an unresolvable or invalid storage path, the backend must return a controlled server-side error or safely omit that image record from the public list. It must **never** leak raw filesystem paths or backend error traces.

### 7.3 Cover Image Invariant

Per `idx_uq_gallery_single_cover` in `app/models/gallery.py` [APPROVED EXISTING SCHEMA]:
```sql
CREATE UNIQUE INDEX idx_uq_gallery_single_cover
ON gallery_images (is_cover_image)
WHERE is_cover_image = true AND is_active = true;
```

> [!IMPORTANT]
> Because this is a partial unique index, there is **zero or one active cover image** at any given moment:
> - Exactly **one** image has `is_cover_image = true` if a cover image has been designated.
> - **Zero** images have `is_cover_image = true` if no active image has been set as cover.
>
> The frontend must handle the `0` cover image state gracefully by falling back to the first available image or a default hero placeholder.

### 7.4 Request

- **Canonical Route**: `GET /api/v1/public/gallery`
- **Frontend Path**: `GET ${VITE_API_BASE_URL}/public/gallery`

### 7.5 Backend Query

```sql
SELECT id, storage_path, title, display_order, is_cover_image
FROM gallery_images
WHERE is_active = TRUE
ORDER BY display_order ASC;
```

### 7.6 Successful Response

**HTTP 200 OK**
```json
{
  "images": [
    {
      "id": "g9d7ie86-fh03-0435-h178-7890abcdef01",
      "image_url": "https://cdn.regalfitness.in/gallery/gym-exterior.webp",
      "title": "Regal Fitness Main Entrance",
      "display_order": 0,
      "is_cover_image": true
    },
    {
      "id": "h0e8jf97-gi14-1546-i289-890abcdef012",
      "image_url": "https://cdn.regalfitness.in/gallery/weights-area.webp",
      "title": "Free Weights & Dumbbells Zone",
      "display_order": 1,
      "is_cover_image": false
    }
  ]
}
```

- `image_url`: Sanitized, public CDN URL.
- `title`: Nullable; serves as the HTML `alt` attribute and caption.
- Internal columns omitted: `storage_path`, `file_name`, `file_size_bytes`, `uploaded_by_owner_id`, `is_active`, timestamps.

---

## 8. Public API Rate Limiting Architecture

### 8.1 Single-Process Development vs. Production Multi-Worker Architecture

To safeguard API stability while accommodating local development and high-availability production, rate limiting is structured into two distinct operational modes:

1. **Development & Single-Process Mode (`InMemoryRateLimiter`) [ACTUAL IMPLEMENTED BEHAVIOR]**:
   - `backend/app/core/rate_limit.py` provides an in-memory sliding-window limiter using thread-safe process memory (Python dict of timestamp deques).
   - Suitable strictly for local developer environments, automated test execution, and single-worker Uvicorn configurations.
   - **Limitations**: Memory is process-local and non-persistent; state resets upon server restart and is not shared across OS processes.
   - Currently, rate limiting is active only on Phase 2 auth endpoints (`/auth/login`, `/auth/forgot-password`, `/auth/verify-reset-otp`). Public endpoints do not currently possess active rate limiting because they are not yet implemented.
2. **Production Multi-Worker Architecture (Redis-Backed Distributed Limiter) [PROPOSED IMPLEMENTATION REQUIREMENT]**:
   - In production deployments running multiple Uvicorn worker processes (e.g. `gunicorn -w 4 -k uvicorn.workers.UvicornWorker`) or distributed multi-container replicas behind a load balancer, each process operates in its own isolated memory space.
   - **Multi-Worker Vulnerability**: If in-memory rate limiting were used in a 4-worker cluster, an attacker could issue up to $4 \times \text{limit}$ requests before being throttled.
   - **Production Requirement**: Production mandates adapting the `RateLimiter` interface in `app/core/rate_limit.py` to use a **centralized Redis cluster** using atomic Redis sorted-set sliding windows (`ZADD`, `ZREMRANGEBYSCORE`, `ZCARD`, `EXPIRE`), preserving the exact same `check_or_raise()` interface and application exception mapping across all workers.

### 8.2 Client IP Utility Ownership & Proposed Refactoring [PROPOSED ARCHITECTURAL REFACTOR]

- **Existing State**: Currently, client IP extraction (`get_client_ip(request)`) is implemented in `backend/app/api/v1/endpoints/auth.py`.
- **Architectural Gap**: Having public endpoints import an IP utility from an authentication route module creates an undesirable cross-domain dependency.
- **Proposed Refactoring**:
  1. The client IP resolution logic must be relocated to a shared core utility (e.g. `backend/app/core/network.py` or `backend/app/core/request.py`).
  2. Both `auth.py` and upcoming public endpoint modules will import `get_client_ip` from this shared core location.
  3. The existing trusted-proxy security behavior—validating `X-Forwarded-For` strictly against `settings.trusted_proxy_ip_set`—must be fully preserved.
  4. IP extraction logic will not be duplicated.

### 8.3 Proposed Rate Limits for Public Endpoints

To prevent spam submissions, denial-of-service, and SMS notification exhaustion, the following rate limits are proposed for implementation:

| Endpoint | Target Action | Proposed Limit | Window | Strategy & Scope |
|----------|---------------|----------------|--------|------------------|
| `POST /public/joining-applications` | Application Form | **5 requests** | 1 hour (3600s) | Client IP + Action key: `rate:post_joining:<ip>` |
| `POST /public/enquiries` | General Enquiry Form | **5 requests** | 1 hour (3600s) | Client IP + Action key: `rate:post_enquiry:<ip>` |
| `POST /public/visit-requests` | Visit Request Form | **5 requests** | 1 hour (3600s) | Client IP + Action key: `rate:post_visit:<ip>` |
| `GET /public/membership-plans` | Plans Catalog Read | **60 requests** | 1 minute (60s) | **Per endpoint**: Client IP + Action key: `rate:get_plans:<ip>` |
| `GET /public/gallery` | Facility Gallery Read | **60 requests** | 1 minute (60s) | **Per endpoint**: Client IP + Action key: `rate:get_gallery:<ip>` |

> [!NOTE]
> Public GET rate limiting is enforced **per endpoint per client IP**, not as a shared collective pool. A visitor browsing the gallery is evaluated independently against `rate:get_gallery:<ip>` and will not exhaust their rate allocation for viewing the plan catalog.

### 8.4 Production Multi-Worker Redis Implementation Specification

- In production environments, the backend runs under Gunicorn with multiple Uvicorn workers (or multiple distributed container replicas behind a load balancer).
- **Redis Implementation Architecture**:
  - The shared rate limiter connects to Redis via `settings.REDIS_URL` (e.g. `redis://redis:6379/0`).
  - **Atomicity Requirement**: The entire sliding-window evaluation and recording must execute **strictly within a single atomic Redis Lua script** (`EVAL` / `EVALSHA`). This eliminates race conditions between separate read (`ZCARD`) and write (`ZADD`) commands across concurrent Uvicorn worker threads.
  - **Unique Sorted-Set Member Guarantee**:
    To prevent duplicate timestamp collisions when two concurrent requests arrive at the exact same millisecond, each request member inserted into the sorted set is uniquely keyed:
    $$\text{member} = \langle\text{timestamp\_ms}\rangle : \langle\text{request\_id}\rangle$$
    (e.g. `1763550000123:a5b4c3d2-e1f0-4a8b-9c7d-6e5f4a3b2c1d`).
    The sorted-set **score** is strictly the numeric epoch millisecond timestamp (`timestamp_ms`), ensuring precise time-based pruning.

  - **Atomic Lua Script Specification**:
    ```lua
    -- KEYS[1]: rate limit key, e.g. "rate:post_joining:203.0.113.195"
    -- ARGV[1]: current timestamp in milliseconds (now_ms)
    -- ARGV[2]: window size in milliseconds (window_ms)
    -- ARGV[3]: max requests allowed in window (limit)
    -- ARGV[4]: unique member identifier (now_ms .. ":" .. request_id)
    -- ARGV[5]: key TTL in seconds (ceil(window_ms / 1000))

    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local limit = tonumber(ARGV[3])
    local member = ARGV[4]
    local ttl = tonumber(ARGV[5])

    local clear_before = now - window

    -- 1. Prune expired entries outside current rolling window
    redis.call('ZREMRANGEBYSCORE', key, 0, clear_before)

    -- 2. Count requests remaining in rolling window
    local current_count = redis.call('ZCARD', key)

    if current_count < limit then
        -- 3. Under limit: record current request with unique member and set TTL
        redis.call('ZADD', key, now, member)
        redis.call('EXPIRE', key, ttl)
        local remaining = limit - current_count - 1
        return { 1, remaining, 0 } -- { allowed (1=true), remaining, retry_after_seconds }
    else
        -- 4. Over limit: calculate exact retry_after from oldest timestamp in window
        local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
        local retry_after = 1
        if oldest and #oldest >= 2 then
            local oldest_time = tonumber(oldest[2])
            local diff_ms = (oldest_time + window) - now
            if diff_ms > 0 then
                retry_after = math.ceil(diff_ms / 1000)
            end
        end
        return { 0, 0, retry_after } -- { allowed (0=false), remaining, retry_after_seconds }
    end
    ```

  - **Key Format**: `rate:{action}:{client_ip}` (e.g. `rate:post_joining:203.0.113.195`).
  - **Per-Endpoint Limits & Action Mapping**: Preserves the exact table specifications from Section 8.3.
  - **HTTP 429 Response & Header Mapping**:
    When `allowed == 0`, the backend raises `RateLimitExceededException`, returning **HTTP 429 TOO_MANY_REQUESTS** with the mandatory `Retry-After` header and structured error payload:
    ```http
    HTTP/1.1 429 Too Many Requests
    Content-Type: application/json
    Retry-After: 1420
    X-RateLimit-Limit: 5
    X-RateLimit-Remaining: 0
    X-RateLimit-Reset: 1420

    {
      "error_code": "RATE_LIMIT_EXCEEDED",
      "message": "Too many requests. Please try again later.",
      "details": {
        "limit": 5,
        "window_seconds": 3600,
        "retry_after_seconds": 1420
      }
    }
    ```
  - This guarantees identical, race-condition-free, cluster-wide rate limiting across all Uvicorn processes and Kubernetes worker pods.

---

## 9. Request Examples

### 9.1 Joining Application — Full (with Facility Tour)

```http
POST /api/v1/public/joining-applications
Content-Type: application/json

{
  "applicant_name": "Priya Sharma",
  "phone_number": "+919876543210",
  "gender": "female",
  "date_of_birth": "1998-04-15",
  "address": "12, MG Road, Bengaluru, Karnataka 560001",
  "selected_plan_id": "d6a4fb53-ce70-7102-e845-4567890abcde",
  "wants_visit_first": true,
  "preferred_visit_date": "2026-11-25",
  "preferred_visit_time_slot": "Evening (4pm–8pm)"
}
```

### 9.2 Joining Application — Minimal (Age only, No Tour, No Plan)

```http
POST /api/v1/public/joining-applications
Content-Type: application/json

{
  "applicant_name": "Rahul Verma",
  "phone_number": "9123456789",
  "gender": "male",
  "age": 28,
  "wants_visit_first": false
}
```

### 9.3 General Enquiry

```http
POST /api/v1/public/enquiries
Content-Type: application/json

{
  "name": "Ananya Krishnan",
  "phone_number": "+918765432109",
  "message": "Do you offer early morning CrossFit or functional training batches between 6:00 AM and 7:30 AM?"
}
```

### 9.4 Visit Request

```http
POST /api/v1/public/visit-requests
Content-Type: application/json

{
  "visitor_name": "Suresh Patel",
  "phone_number": "+917654321098",
  "preferred_date": "2026-11-22",
  "preferred_time_slot": "Morning (9am–12pm)"
}
```

---

## 10. Response Examples

### 10.1 Successful Submissions (HTTP 201 Created)

#### Joining Application
```json
{
  "id": "a3f1c820-9b4d-4e7f-b512-1234567890ab",
  "status": "submitted",
  "created_at": "2026-11-18T07:30:00Z"
}
```

#### General Enquiry
```json
{
  "id": "b4e2d931-ac5e-5f80-c623-234567890abc",
  "status": "pending",
  "created_at": "2026-11-18T07:31:00Z"
}
```

#### Visit Request
```json
{
  "id": "c5f3ea42-bd6f-6091-d734-34567890abcd",
  "status": "pending",
  "preferred_date": "2026-11-22",
  "preferred_time_slot": "Morning (9am–12pm)",
  "created_at": "2026-11-18T07:32:00Z"
}
```

### 10.2 Error Responses

#### A. Pydantic Validation Failure — Slot Enum (HTTP 422 VALIDATION_ERROR)
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request parameters or payload",
    "details": [
      {
        "field": "body -> preferred_time_slot",
        "message": "Input should be 'Morning (9am–12pm)', 'Afternoon (12pm–4pm)' or 'Evening (4pm–8pm)'",
        "type": "enum"
      }
    ]
  }
}
```

#### B. Validation Failure — Past Visit Date (HTTP 422 VALIDATION_ERROR)
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request parameters or payload",
    "details": [
      {
        "field": "body -> preferred_visit_date",
        "message": "preferred_visit_date cannot be in the past relative to Asia/Kolkata business date.",
        "type": "value_error"
      }
    ]
  }
}
```

#### C. Validation Failure — Age and DOB Inconsistency (HTTP 422 VALIDATION_ERROR)
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request parameters or payload",
    "details": [
      {
        "field": "body -> age",
        "message": "Submitted age (25) does not match calculated age (26) derived from date of birth (1999-11-15)",
        "type": "value_error"
      }
    ]
  }
}
```

#### D. Business Rule Conflict — Duplicate Active Application in Pipeline (HTTP 409 RESOURCE_CONFLICT)
```json
{
  "error": {
    "code": "RESOURCE_CONFLICT",
    "message": "An active joining application is already being processed for this phone number. Please contact gym administration if you need to make changes.",
    "details": null
  }
}
```

#### E. Business Rule Conflict — Existing Active Member Profile (HTTP 409 RESOURCE_CONFLICT)
```json
{
  "error": {
    "code": "RESOURCE_CONFLICT",
    "message": "An active member profile is already registered with this phone number. Please contact gym administration for renewals or account assistance.",
    "details": null
  }
}
```

#### F. Selected Plan Inactive / Unpublished (HTTP 404 RESOURCE_NOT_FOUND)
```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "The selected membership plan does not exist or is not currently available for public enrollment.",
    "details": null
  }
}
```

#### G. Rate Limit Exceeded (HTTP 429 RATE_LIMIT_EXCEEDED)
```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Too many requests. Please try again in 3420 seconds.",
    "details": {
      "retry_after_seconds": 3420
    }
  }
}
```

---

## 11. Schema Gaps & Pending Owner Decisions

| # | Item | Architectural Recommendation | Status | Owner Action Required |
|---|------|------------------------------|--------|-----------------------|
| **1** | **Migration 2.1: Public Plan Visibility** | **APPROVE** | Proposed Schema Change | Approve adding `is_publicly_visible BOOLEAN NOT NULL DEFAULT FALSE` to `membership_plans`. Pre-existing plans default to unpublished and remain internally enrollable until explicitly published. |
| **2** | **Migration 2.2: Duplicate Application Concurrency Protection & 4-Stage Remediation** | **APPROVE with Dedicated Audit Table & 4-Stage Remediation** | Proposed Schema Change | Approve partial unique index `idx_uq_active_joining_app_phone` on `joining_applications(phone_number)` for active pipeline statuses. Preceded by 4-Stage Remediation (A: Read-Only Preflight covering active, inactive, and archived records to catch `idx_uq_members_active_phone` collisions; B: Administrative Review; C: Controlled Alembic Migration creating `phone_normalization_audit_log` and updating columns in-place; D: 100% Verification). |
| **3** | **Centralized Phone Advisory Locking & Bulk Deadlock Prevention** | **APPROVE Architecture (6 Workflows)** | Proposed Implementation Requirement | Approve shared transaction-scoped `pg_advisory_xact_lock(hashtextextended(:phone, 0))` centralized in core service across public submission, owner conversion, manual creation, reactivation, bulk import (with deterministic lexicographical sorting), and owner-side phone number updates (using two-phase sorted advisory locks). |
| **4** | **Optional Plan Selection & Conversion Workflow** | **APPROVE Workflow 2 Architecture** | Proposed Implementation Architecture | Approve Option A conversion: Applicant may omit plan; owner explicitly chooses and confirms eligible plan, snapshot pricing, and duration; system never auto-assigns default plan. Creates pending membership contract (`pending_activation`) fulfilling non-null `plan_id`. |
| **5** | **Hierarchical Payment Confirmation, Invoicing, Refund Concurrency & Idempotency Guarantees** | **APPROVE Workflow Architecture** | Proposed Implementation Architecture | Approve payment confirmation and refund processing workflows: Two-tier hierarchical lock ordering (`membership_records` row first `FOR UPDATE`, then `payments` row second `FOR UPDATE`) shared consistently across both confirmation and refund processing; post-lock revalidation of candidate vs persisted `membership_record_id` to detect concurrent association changes; evaluated idempotency state machine handling pending retries under lock, committed already-confirmed payment replay via stored-field comparison, and conflicting key/payload rejection with HTTP 409 (preserving explicit documentation of schema limitation regarding request body hash); refund-aware ledger calculations factoring processed refunds; strict overpayment rejection under `ck_invoices_balances_valid`; and atomic invoice generation using verified existing fields (`confirmed_by_owner_id`, `confirmed_at`, `created_by_owner_id`). |
| **6** | **Independent Membership Activation Lifecycle** | **APPROVE Invariant Architecture** | Existing Schema Preserved | Approve invariant that payment confirmation (full, partial, installment, or advance) never auto-activates membership. Activation remains an explicit, owner-authorized dashboard action stamping `activated_by_owner_id` and `activated_at`, with term dates adhering to approved renewal rules (`DATABASE_SCHEMA.md §12.2`). |
| **7** | **Visitor Message Field** | **EXCLUDE from Initial Release** | Existing Schema Preserved | Do not add a visitor message column for the initial release. The existing `notes` column remains exclusively for owner-internal notes. No migration required. |
| **8** | **Visit Time Slot Constants** | **Proposed Constants Awaiting Approval** | Proposed API Contract | Proposed candidate constants with operational intervals: `Morning (9am–12pm)` [09:00, 12:00), `Afternoon (12pm–4pm)` [12:00, 16:00), `Evening (4pm–8pm)` [16:00, 20:00). Owner confirmation pending. Both frontend and backend will strictly bind to confirmed labels. |
| **9** | **Gallery Exact Hostname Matching & Redis Rate Limiting** | **APPROVE Security Specifications** | Proposed Configuration & Infrastructure | Approve exact case-insensitive hostname allowlisting (no wildcard/suffix subdomains) and production Redis-backed sliding-window rate limiting executed via atomic Lua script with unique member `<timestamp_ms>:<request_id>` identifiers for multi-worker deployments. |

---

## 12. Frontend Integration Notes (React + Vite)

### 12.1 Environment Variable Configuration

```typescript
// src/api/client.ts
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

if (!API_BASE_URL) {
  throw new Error("Missing VITE_API_BASE_URL environment variable.");
}

// Correct usage: append relative path without repeating /api/v1
export async function submitEnquiry(payload: EnquiryRequest) {
  const response = await fetch(`${API_BASE_URL}/public/enquiries`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return response.json();
}
```

### 12.2 Form Validation Field Mapping

When receiving a `422 VALIDATION_ERROR`, map the `field` string to your form state keys:

```typescript
// Helper to extract input field key from FastAPI error loc
function getFormFieldName(loc: string): string {
  // Strips "body -> " prefix from "body -> phone_number"
  return loc.replace(/^body\s*->\s*/, '');
}
```

### 12.3 Plan Price Display Formatting

`base_price` is returned as a fixed-decimal string (e.g. `"1500.00"`):

```typescript
export function formatPlanPrice(priceString: string): string {
  const numericPrice = Number.parseFloat(priceString);
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(numericPrice);
}
// Returns: "₹1,500"
```

### 12.4 Cover Image Fallback Strategy

Because there can be **zero or one** active cover image:

```typescript
const coverImage = galleryImages.find((img) => img.is_cover_image)
  || galleryImages[0]
  || { image_url: '/assets/default-gym-hero.webp', title: 'Regal Fitness' };
```

---

*Contract revision v1.3.1 authored by Developer 2. Awaiting final user and owner approval before implementing endpoints or generating database migrations.*
