# Regal Fitness — Member Management API

**Module:** Phase 4 — Member Management
**Version:** 1.0.0
**Status:** Approved Implementation
**Base Path:** `/api/v1/members`
**Authentication:** All endpoints require a valid JWT Bearer token from Phase 2 authentication.

---

## Overview

The Member Management API provides complete lifecycle management for gym members:
creating, listing, viewing, updating, archiving, reactivating members, and retrieving
their historical membership contracts and payment records.

**Key invariants:**
- Creating or updating a member **never** creates a membership, payment, or invoice.
- Archiving **never** deletes any database record or modifies financial balances.
- Reactivating **never** activates any existing membership.
- Both gym owners have identical, unrestricted access to all endpoints.

---

## Authentication

All endpoints require:
```
Authorization: Bearer <access_token>
```
Requests without a valid token return **HTTP 401**.

---

## Phone Number Handling

### Normalization Rules

| Input Format | Stored As |
|---|---|
| `9876543210` (10-digit) | `+919876543210` |
| `09876543210` (11-digit, leading 0) | `+919876543210` |
| `919876543210` (12-digit, 91-prefix) | `+919876543210` |
| `+919876543210` (E.164) | `+919876543210` (unchanged) |
| `+447911123456` (international E.164) | `+447911123456` (unchanged) |
| Spaces, dashes, parentheses | Stripped before normalization |

### Uniqueness Rule

A phone number must be unique among **non-archived** members.

- Archived members' phone numbers are released from the uniqueness constraint (via `idx_uq_members_active_phone` partial index).
- Reactivating an archived member re-checks uniqueness before reactivation.

> [!NOTE]
> Phone uniqueness under concurrent requests is enforced by the PostgreSQL partial unique index
> `idx_uq_members_active_phone` (WHERE `is_archived = false`) backed by advisory locks in the
> service layer. Advisory locks are no-ops on SQLite test databases.

---

## Member Codes

Every new member receives an auto-generated sequential RF code: `RF001`, `RF002`, etc.

- Generated using the atomic `member_code_seq` PostgreSQL sequence.
- Codes are unique and globally immutable after creation.
- Cannot be modified through any API endpoint.

> [!IMPORTANT]
> RF code uniqueness under concurrent requests is guaranteed by the PostgreSQL sequence on production.
> SQLite tests verify monotonic increments sequentially only.

---

## Endpoints

---

### POST `/api/v1/members/`
**Create Member**

Registers a new gym member. Auto-generates the RF member code. Does NOT create memberships or payments.

**Request Body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `full_name` | string | ✅ | 2–100 characters |
| `phone_number` | string | ✅ | Normalized to E.164 |
| `gender` | string | ✅ | `male`, `female`, `other`, `prefer_not_to_say` |
| `date_of_birth` | date | ❌ | ISO 8601, cannot be in the future |
| `age` | integer | ❌ | 1–120 |
| `address` | string | ❌ | Up to 1000 characters |
| `joining_date` | date | ❌ | Defaults to current IST business date |
| `emergency_contact_name` | string | ❌ | Up to 100 characters |
| `emergency_contact_phone` | string | ❌ | Normalized to E.164 |
| `profile_photo_url` | string | ❌ | Up to 500 characters |

**Response:** `201 Created` — `MemberResponse`

**Error Responses:**
| Status | Condition |
|---|---|
| `401` | Missing or invalid token |
| `409` | Phone number already in use by a non-archived member |
| `422` | Validation error (missing fields, invalid gender, future DOB, extra fields) |

**Example:**
```json
POST /api/v1/members/
{
  "full_name": "Alice Kumar",
  "phone_number": "9811111111",
  "gender": "female",
  "date_of_birth": "1995-06-15",
  "address": "123 MG Road, Bangalore"
}
```

---

### GET `/api/v1/members/`
**List Members**

Returns a paginated, filterable, and sortable list of members.

**Query Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `search` | string | — | Search by RF code, full name, or phone number |
| `gender` | string | — | Filter: `male`, `female`, `other`, `prefer_not_to_say` |
| `is_archived` | boolean | `false` | `false` = active members; `true` = archived members |
| `sort_by` | string | `created_at` | `created_at`, `joining_date`, `full_name`, `member_code` |
| `sort_order` | string | `desc` | `asc` or `desc` |
| `page` | integer | `1` | Page number (≥ 1) |
| `page_size` | integer | `20` | Items per page (1–100) |

**Default behavior:** Returns only non-archived members unless `is_archived=true` is specified.

**Response:** `200 OK` — `MemberListResponse`
```json
{
  "items": [ ... ],
  "total": 42,
  "page": 1,
  "page_size": 20,
  "total_pages": 3
}
```

**Error Responses:**
| Status | Condition |
|---|---|
| `401` | Missing or invalid token |
| `422` | Invalid query parameter (e.g., `page=0`, `page_size=200`) |

---

### GET `/api/v1/members/{member_id}`
**Get Member Details**

Returns the full profile for a specific member identified by UUID. Archived members are accessible.

**Path Parameter:** `member_id` — UUID of the member.

**Response:** `200 OK` — `MemberResponse`

**Error Responses:**
| Status | Condition |
|---|---|
| `401` | Missing or invalid token |
| `404` | Member not found |

---

### PATCH `/api/v1/members/{member_id}`
**Update Member**

Partially updates permitted member profile fields. Protected fields are rejected.

**Protected fields (always rejected with `422`):**
`member_code`, `id`, `is_archived`, `archived_at`, `archive_reason`, `created_by_owner_id`, `created_at`, `updated_at`

**Request Body (all fields optional):**

| Field | Type | Description |
|---|---|---|
| `full_name` | string | 2–100 characters |
| `phone_number` | string | Normalized, uniqueness re-checked |
| `gender` | string | `male`, `female`, `other`, `prefer_not_to_say` |
| `date_of_birth` | date | Cannot be in the future |
| `age` | integer | 1–120 |
| `address` | string | Up to 1000 characters |
| `joining_date` | date | — |
| `emergency_contact_name` | string | Up to 100 characters |
| `emergency_contact_phone` | string | Normalized to E.164 |
| `profile_photo_url` | string | Up to 500 characters |

**Phone Update Concurrency (PostgreSQL):**
1. Normalize both old and new phone numbers.
2. Acquire advisory locks in lexicographical order on both numbers.
3. Lock the member row `FOR UPDATE`.
4. Verify the member's stored phone has not changed concurrently.
5. Check uniqueness (excluding current member) before updating.

**Response:** `200 OK` — `MemberResponse`

**Error Responses:**
| Status | Condition |
|---|---|
| `400` | No valid fields provided |
| `401` | Missing or invalid token |
| `404` | Member not found |
| `409` | Phone number conflict or concurrent phone modification |
| `422` | Validation error or protected field |

**Audit event:** `member.updated`

---

### POST `/api/v1/members/{member_id}/archive`
**Archive Member**

Soft-archives a member. All membership contracts, payments, invoices, and refunds are preserved unchanged.

**Request Body (optional):**
```json
{ "reason": "Relocated abroad" }
```

**Guarantees:**
- Member row is never deleted.
- `is_archived` → `true`; `archived_at` → current UTC timestamp.
- Financial records are untouched.
- Membership `system_status` values are untouched.

**Response:** `200 OK` — `MemberResponse`

**Error Responses:**
| Status | Condition |
|---|---|
| `401` | Missing or invalid token |
| `404` | Member not found |
| `409` | Member is already archived |

**Audit event:** `member.archived`

---

### POST `/api/v1/members/{member_id}/reactivate`
**Reactivate Member**

Reactivates an archived member. The original RF member code and all historical records are preserved. Does NOT activate any membership.

**Workflow:**
1. Verify the member is currently archived.
2. Acquire PostgreSQL advisory lock on the member's phone number.
3. Lock the member row `FOR UPDATE`.
4. Check phone uniqueness (excluding this member) among non-archived members.
5. Clear `is_archived`, `archived_at`, `archive_reason`.
6. Record audit event.

**Response:** `200 OK` — `MemberResponse`

**Error Responses:**
| Status | Condition |
|---|---|
| `401` | Missing or invalid token |
| `404` | Member not found |
| `409` | Member is already active, or phone conflict with another non-archived member |

**Audit event:** `member.reactivated`

---

### GET `/api/v1/members/{member_id}/memberships`
**Member Membership History**

Returns a paginated list of all historical membership contracts for a member, ordered newest first.

**Query Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `page` | integer | `1` | Page number (≥ 1) |
| `page_size` | integer | `20` | Items per page (1–100) |

**Response:** `200 OK` — `MemberMembershipHistoryResponse`
```json
{
  "member_id": "...",
  "member_code": "RF001",
  "items": [
    {
      "id": "...",
      "plan_id": "...",
      "plan_snapshot_name": "Basic Plan",
      "plan_snapshot_duration_days": 30,
      "plan_snapshot_base_price": "5000.00",
      "plan_snapshot_is_pt": false,
      "discount_amount": "0.00",
      "total_fee": "5000.00",
      "start_date": "2026-01-01",
      "expiry_date": "2026-01-31",
      "system_status": "active",
      "override_status": null,
      "is_manual_override": false,
      "override_reason": null,
      "membership_type": "new",
      "previous_membership_id": null,
      "created_at": "2026-01-01T10:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

**This endpoint never modifies membership records.**

**Error Responses:**
| Status | Condition |
|---|---|
| `401` | Missing or invalid token |
| `404` | Member not found |

---

### GET `/api/v1/members/{member_id}/payments`
**Member Payment History**

Returns a paginated list of all payment records for a member, ordered newest first. Includes aggregated processed refund totals per payment.

**Query Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `page` | integer | `1` | Page number (≥ 1) |
| `page_size` | integer | `20` | Items per page (1–100) |

**Response:** `200 OK` — `MemberPaymentHistoryResponse`
```json
{
  "member_id": "...",
  "member_code": "RF001",
  "items": [
    {
      "id": "...",
      "payment_number": "PAY0001",
      "membership_record_id": "...",
      "amount": "5000.00",
      "payment_type": "full",
      "payment_method": "cash",
      "transaction_reference": null,
      "payment_date": "2026-01-01",
      "status": "confirmed",
      "notes": null,
      "refunded_amount": "0.00",
      "has_refunds": false,
      "created_at": "2026-01-01T10:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

**Notes:**
- `refunded_amount` is the sum of `PaymentRefund.amount` where `status = 'processed'`.
- `has_refunds` is `true` when `refunded_amount > 0`.
- Pending and rejected refunds are excluded from `refunded_amount`.
- Payment status values: `pending`, `confirmed`, `failed`.
- **This endpoint never modifies payment or refund records.**

**Error Responses:**
| Status | Condition |
|---|---|
| `401` | Missing or invalid token |
| `404` | Member not found |

---

## Response Schema: MemberResponse

```json
{
  "id": "uuid",
  "member_code": "RF001",
  "full_name": "Alice Kumar",
  "phone_number": "+919811111111",
  "date_of_birth": "1995-06-15",
  "age": null,
  "gender": "female",
  "address": "123 MG Road, Bangalore",
  "joining_date": "2026-01-01",
  "emergency_contact_name": null,
  "emergency_contact_phone": null,
  "profile_photo_url": null,
  "is_archived": false,
  "archived_at": null,
  "archive_reason": null,
  "created_by_owner_id": "uuid",
  "created_at": "2026-01-01T04:30:00Z",
  "updated_at": "2026-01-01T04:30:00Z"
}
```

---

## Audit Events

| Event | Trigger |
|---|---|
| `member.created` | `POST /api/v1/members/` |
| `member.updated` | `PATCH /api/v1/members/{member_id}` |
| `member.archived` | `POST /api/v1/members/{member_id}/archive` |
| `member.reactivated` | `POST /api/v1/members/{member_id}/reactivate` |

Audit logs capture owner ID, entity ID, previous and new field values (sensitive fields redacted), IP address, and user agent.

---

## Out of Scope (Phase 4)

The following operations are NOT implemented in this module:

- Membership plan creation or management
- Membership activation or renewals
- Payment processing, invoices, or refunds
- Joining application conversion
- WhatsApp or push notifications
- Attendance tracking
- Bulk member import

---

## Concurrency and PostgreSQL Notes

> [!WARNING]
> SQLite test databases do not prove PostgreSQL row-locking or advisory lock behavior.

| Feature | Mechanism | Verified On |
|---|---|---|
| RF code uniqueness | PostgreSQL `member_code_seq` sequence (atomic) | PostgreSQL staging required |
| Active phone uniqueness | `idx_uq_members_active_phone` partial unique index | SQLite partial index (service-level in tests) |
| Phone update races | `pg_advisory_xact_lock` on old + new phones | PostgreSQL staging required |
| Member creation races | `pg_advisory_xact_lock` on new phone | PostgreSQL staging required |
| Reactivation races | `pg_advisory_xact_lock` on phone + row `FOR UPDATE` | PostgreSQL staging required |
