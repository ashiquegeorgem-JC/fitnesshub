# Regal Fitness — Dashboard & Analytics API Specification

**Module:** Phase 3 — Owner Dashboard & Analytics
**Version:** 1.0.0
**Status:** Approved Implementation
**Audience:** Backend Developers, Frontend Developers, Mobile App Team, QA
**Base Path:** `/api/v1/dashboard`

---

## 1. Architectural Overview & Security

The Regal Fitness Dashboard & Analytics module delivers high-performance, real-time business intelligence for gym owners. It aggregates membership lifecycles, renewal risks, financial transactions, and operational activity logs into structured, strongly-typed RESTful endpoints.

### 1.1 Authentication & Authorization
- **Bearer Token Authentication:** All dashboard endpoints require a valid JWT access token passed via the HTTP header:
  `Authorization: Bearer <access_token>`
- **Dual-Owner Parity:** In accordance with Phase 2 core security requirements, both gym owners have identical permissions and equal access to all metrics and audit logs.
- **Unauthorized Requests:** Requests missing valid credentials return HTTP `401 Unauthorized`.

### 1.2 Timezone & Business Date Standard
- **Official Timezone:** `Asia/Kolkata` (UTC+5:30).
- All date boundaries for "today", "this_week", "this_month", "this_year", admission dates, and expiration alerts are resolved against the business date in `Asia/Kolkata`.
- Stored database timestamps in UTC are converted to `Asia/Kolkata` date boundaries when filtering transactional records.

### 1.3 Financial Integrity Invariants
1. **Confirmed Collections Only:** Only payments with `payment_status = 'confirmed'` are counted towards revenue and collections. Pending, failed, or abandoned payments are strictly excluded.
2. **Net Collections Formula:**
   $$\text{Net Collections} = \sum \text{Gross Confirmed Payments} - \sum \text{Processed Refunds}$$
3. **Outstanding Dues Formula:** Evaluated dynamically at the contract level in accordance with `DATABASE_SCHEMA.md §4`:
   $$\text{Net Paid} = \sum \text{Confirmed Payments} - \sum \text{Processed Refunds}$$
   $$\text{Contract Outstanding} = \max\left(0.00, \text{total\_fee} - \text{Net Paid} - \sum \text{Waived Dues}\right)$$
   Scalar subqueries are enforced across payments, refunds, and due schedules to eliminate Cartesian explosion risk.

---

## 2. Endpoints Reference

### 2.1 Overview Dashboard
`GET /api/v1/dashboard/overview`

High-level operational snapshot summarizing active memberships, expiration alerts, daily/monthly business velocity, financial totals, and recent activity.

- **Method:** `GET`
- **Query Parameters:** None
- **Response Model:** `DashboardOverviewResponse`
- **Sample Request:**
  ```http
  GET /api/v1/dashboard/overview HTTP/1.1
  Host: api.regalfitness.com
  Authorization: Bearer <token>
  ```
- **Sample Response (HTTP 200):**
  ```json
  {
    "as_of_date": "2026-11-23",
    "member_counts": {
      "total_members": 150,
      "active_members": 128,
      "expired_members": 18,
      "pending_activation_members": 4,
      "archived_members": 12
    },
    "alerts": {
      "expiring_within_7_days": 12,
      "expiring_within_3_days": 4,
      "renewal_pending_activation": 3
    },
    "today_metrics": {
      "new_admissions": 2,
      "renewals": 3,
      "collections": "7500.00"
    },
    "month_metrics": {
      "new_admissions": 24,
      "renewals": 41,
      "gross_collections": "162000.00",
      "processed_refunds": "2500.00",
      "net_collections": "159500.00"
    },
    "financial_summary": {
      "total_outstanding_dues": "18500.00",
      "today_collections": "7500.00",
      "month_collections": "159500.00"
    },
    "recent_activity": [
      {
        "id": "e8a91090-8457-418b-986c-48b0c41ec351",
        "timestamp": "2026-11-23T14:30:00Z",
        "actor": "Owner A",
        "action": "PAYMENT_CONFIRMED",
        "entity_type": "payment",
        "entity_id": "90e25bbf-b40b-426c-859a-df3603407db3",
        "description": "Payment confirmed by Owner A",
        "status_code": 200
      }
    ]
  }
  ```

---

### 2.2 Membership Analytics
`GET /api/v1/dashboard/membership-analytics`

Detailed member distribution across plans, acquisition rates, churn/expiry statistics, and new vs. renewal contract breakdowns.

- **Method:** `GET`
- **Query Parameters:**
  | Parameter | Type | Required | Description |
  |---|---|---|---|
  | `start_date` | `date` (YYYY-MM-DD) | No | Optional start date filter for admissions, renewals, and contracts |
  | `end_date` | `date` (YYYY-MM-DD) | No | Optional end date filter |
- **Validation:** If `start_date > end_date`, returns HTTP `400 Bad Request`.
- **Response Model:** `MembershipAnalyticsResponse`
- **Sample Request:**
  ```http
  GET /api/v1/dashboard/membership-analytics?start_date=2026-11-01&end_date=2026-11-30 HTTP/1.1
  Host: api.regalfitness.com
  Authorization: Bearer <token>
  ```
- **Sample Response (HTTP 200):**
  ```json
  {
    "period": {
      "start_date": "2026-11-01",
      "end_date": "2026-11-30",
      "preset": "custom"
    },
    "summary": {
      "new_admissions": 24,
      "renewals": 41,
      "total_active_members": 128,
      "total_expired_members": 18,
      "expiring_within_7_days": 12,
      "expiring_within_3_days": 4
    },
    "plan_distribution": [
      {
        "plan_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "plan_name": "Monthly General",
        "duration_days": 30,
        "base_price": "1500.00",
        "active_members_count": 84,
        "total_contracts_count": 312
      },
      {
        "plan_id": "7ca85f64-5717-4562-b3fc-2c963f66afa7",
        "plan_name": "Annual VIP",
        "duration_days": 365,
        "base_price": "12000.00",
        "active_members_count": 44,
        "total_contracts_count": 89
      }
    ],
    "membership_type_breakdown": {
      "new_count": 24,
      "renewal_count": 41,
      "upgrade_count": 0
    }
  }
  ```

---

### 2.3 Financial Analytics
`GET /api/v1/dashboard/financial-analytics`

In-depth financial metrics covering gross collections, refunds, net income, payment classifications (full, partial, advance), revenue streams (new vs. renewal memberships), and payment method utilization.

- **Method:** `GET`
- **Query Parameters:**
  | Parameter | Type | Required | Description |
  |---|---|---|---|
  | `preset` | `string` | No | Preset range: `today`, `this_week`, `this_month`, `this_year`, `custom` (Default: `this_month`) |
  | `start_date` | `date` (YYYY-MM-DD) | No | Required if `preset=custom` |
  | `end_date` | `date` (YYYY-MM-DD) | No | Required if `preset=custom` |
- **Validation:**
  - `preset='custom'` without `start_date` or `end_date` returns HTTP `400 Bad Request`.
  - `start_date > end_date` returns HTTP `400 Bad Request`.
- **Response Model:** `FinancialAnalyticsResponse`
- **Sample Request:**
  ```http
  GET /api/v1/dashboard/financial-analytics?preset=this_month HTTP/1.1
  Host: api.regalfitness.com
  Authorization: Bearer <token>
  ```
- **Sample Response (HTTP 200):**
  ```json
  {
    "period": {
      "start_date": "2026-11-01",
      "end_date": "2026-11-23",
      "preset": "this_month"
    },
    "totals": {
      "gross_confirmed_collections": "162000.00",
      "processed_refunds": "2500.00",
      "net_collections": "159500.00",
      "outstanding_dues": "18500.00"
    },
    "payment_type_breakdown": {
      "full_payments": {
        "amount": "120000.00",
        "count": 60
      },
      "partial_payments": {
        "amount": "32000.00",
        "count": 18
      },
      "advance_payments": {
        "amount": "10000.00",
        "count": 5
      }
    },
    "membership_type_revenue": {
      "new_membership_revenue": "48000.00",
      "renewal_revenue": "114000.00",
      "upgrade_revenue": "0.00"
    },
    "payment_method_breakdown": [
      {
        "payment_method": "upi",
        "amount": "98000.00",
        "count": 52,
        "percentage": "60.49"
      },
      {
        "payment_method": "cash",
        "amount": "44000.00",
        "count": 22,
        "percentage": "27.16"
      },
      {
        "payment_method": "card",
        "amount": "20000.00",
        "count": 9,
        "percentage": "12.35"
      }
    ]
  }
  ```

---

### 2.4 Renewal Pipeline
`GET /api/v1/dashboard/renewal-pipeline`

Actionable retention pipeline organizing gym members by renewal urgency and risk state. Enables owners to proactively retain expiring members and collect unpaid balances.

- **Method:** `GET`
- **Query Parameters:**
  | Parameter | Type | Required | Default | Description |
  |---|---|---|---|---|
  | `category` | `string` | No | `all` | Filter by category: `all`, `urgent_expiry` (or `expiring_3_days`), `expiring_soon`, `expiring_7_days`, `already_expired`, `renewal_pending`, `recently_renewed` |
  | `page` | `integer` | No | `1` | Page number (>= 1) |
  | `page_size` | `integer` | No | `20` | Page size (1 to 100) |
- **Classification Rules:**
  - `urgent_expiry`: Active contract expiring in $\le 3$ days ($0 \le \text{expiry} - \text{today} \le 3$).
  - `expiring_soon`: Active contract expiring in 4 to 7 days ($4 \le \text{expiry} - \text{today} \le 7$).
  - `renewal_pending`: Expired contract with newer contract in `pending_activation`.
  - `already_expired`: Expired contract with no active or pending contract.
  - `recently_renewed`: Renewed within the past 30 days.
- **Response Model:** `RenewalPipelineResponse`
- **Sample Request:**
  ```http
  GET /api/v1/dashboard/renewal-pipeline?category=urgent_expiry&page=1&page_size=20 HTTP/1.1
  Host: api.regalfitness.com
  Authorization: Bearer <token>
  ```
- **Sample Response (HTTP 200):**
  ```json
  {
    "summary": {
      "expiring_3_days_count": 4,
      "expiring_7_days_count": 12,
      "already_expired_count": 18,
      "renewal_pending_count": 3,
      "recently_renewed_count": 14
    },
    "items": [
      {
        "member_id": "b3e51d92-23c2-48a5-b1a7-17243c21a418",
        "member_code": "RF014",
        "member_name": "Rohan Mehra",
        "phone_number": "+919876543210",
        "membership_id": "4fe27ab1-86d7-4c31-897b-8b9a1175de02",
        "plan_name": "Monthly General",
        "expiry_date": "2026-11-25",
        "outstanding_dues": "500.00",
        "renewal_status": "urgent_expiry",
        "days_until_expiry": 2,
        "days_since_expiry": 0,
        "has_pending_renewal": false
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total_items": 4,
      "total_pages": 1,
      "has_next": false,
      "has_prev": false
    }
  }
  ```

---

### 2.5 Recent Activity
`GET /api/v1/dashboard/recent-activity`

Chronological audit log stream detailing administrative and operational events performed across the gym system.

- **Method:** `GET`
- **Query Parameters:**
  | Parameter | Type | Required | Default | Description |
  |---|---|---|---|---|
  | `action` | `string` | No | `None` | Filter by action type (e.g., `MEMBER_CREATED`, `PAYMENT_CONFIRMED`, `REFUND_PROCESSED`, `MEMBER_ARCHIVED`) |
  | `limit` | `integer` | No | `20` | Max records to retrieve (1 to 100) |
  | `offset` | `integer` | No | `0` | Offset pagination (>= 0) |
- **Response Model:** `RecentActivityResponse`
- **Sample Request:**
  ```http
  GET /api/v1/dashboard/recent-activity?limit=10&offset=0 HTTP/1.1
  Host: api.regalfitness.com
  Authorization: Bearer <token>
  ```
- **Sample Response (HTTP 200):**
  ```json
  {
    "items": [
      {
        "id": "7a3562a9-7c42-4919-b59f-d00eaeb8d003",
        "timestamp": "2026-11-23T14:45:10Z",
        "actor": "Owner A",
        "action": "PAYMENT_CONFIRMED",
        "entity_type": "payment",
        "entity_id": "2b9e6f47-8a12-4d2c-9a28-0912cb85fe33",
        "description": "Payment confirmed by Owner A",
        "status_code": 200
      },
      {
        "id": "18c2b742-5f11-470a-9d0f-4882746da011",
        "timestamp": "2026-11-23T12:30:00Z",
        "actor": "Owner B",
        "action": "MEMBER_CREATED",
        "entity_type": "member",
        "entity_id": "90e25bbf-b40b-426c-859a-df3603407db3",
        "description": "Member created by Owner B",
        "status_code": 201
      }
    ],
    "limit": 10,
    "offset": 0,
    "total_count": 348
  }
  ```

---

## 3. Database & Query Performance Notes

1. **Cartesian Product Elimination:** To prevent performance degradation when calculating outstanding dues across members with multiple payments, refunds, and due schedules, scalar subqueries (`_contract_outstanding_subqueries`) are used instead of multiple full table joins.
2. **Archived Member Exclusion:** All member queries verify `Member.is_archived.is_(False)` unless specifically querying archived counts.
3. **Manual Overrides Compliance:** Membership queries properly evaluate `is_manual_override = True AND override_status = 'active'` as actively admitted members, even when system dates or statuses differ.
4. **Zero Safe Defaults:** When querying an empty database or periods with zero activity, all endpoints return safe zero counts and `0.00` decimal strings without raising null pointer or division-by-zero exceptions.
