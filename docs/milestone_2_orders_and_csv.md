# ProfitGuard AI — Milestone 2: Order Management & Two-Stage CSV Ingestion

## 1. Architectural Overview

Milestone 2 establishes high-performance, strictly isolated order lifecycle management and an enterprise-grade Two-Stage CSV Ingestion Engine designed for Indian D2C merchants handling up to thousands of orders daily.

```
Merchant CSV Upload / Shopify Webhooks
               │
               ▼
┌──────────────────────────────────────────────┐
│ Stage A: Preview & Validation (In-Memory)   │
│ - UTF-8 / UTF-8 with BOM parsing             │
│ - Strict RFC 4180 delimiter handling         │
│ - Decimal monetary arithmetic verification    │
│ - Indian phone (10-digit) & pincode (6-digit)│
│ - Multi-item order reconciliation            │
│ - Intra-file and DB duplicate identification │
│ - Writes to `import_jobs` (status: PREVIEW)  │
│   and `import_job_errors`                    │
└──────────────────────┬───────────────────────┘
                       │ Valid Rows Staged (Zero Orders Table Writes)
                       ▼
┌──────────────────────────────────────────────┐
│ Stage B: Transactional Commit                │
│ - Atomic DB transaction                      │
│ - Idempotent execution (single-commit guard) │
│ - Double-check duplicate prevention          │
│ - Writes to `orders` and `order_items`       │
│ - Hash-chained audit event recorded          │
│ - Status updated to COMMITTED                │
└──────────────────────────────────────────────┘
```

---

## 2. Immutability & Financial Accounting Protection

1. **Original Order Value Immutability**:
   - `orders.order_value` represents the Gross Merchandise Value (GMV in ₹) agreed upon at checkout.
   - It is strictly immutable and cannot be updated via `PATCH /orders/{id}` or any subsequent status change (e.g., RTO, cancellation, or partial refund).
   - In accordance with our financial accounting specification, subsequent adjustments, delivery losses, reverse courier fees, and damage accruals are recorded in distinct, downstream ledger models without mutating the original order value.

2. **Decimal Financial Arithmetic**:
   - Every monetary field (`order_value`, `unit_price`, `unit_cost`, `total_price`) uses PostgreSQL `Numeric(12, 2)` / Python `Decimal`.
   - Floating-point representations (`float` / `double`) are strictly prohibited across backend models, schemas, and services to prevent binary rounding inaccuracies.

3. **Indian Validation Standards**:
   - **Phone**: Normalizes standard Indian mobile numbers to 10 digits (`^[6-9]\d{9}$`), stripping `+91`, `91`, leading `0`, dashes, spaces, and parentheses.
   - **Pincode**: Validates 6-digit Indian postal codes starting with digits 1-9 (`^[1-9][0-9]{5}$`).

---

## 3. Database Schema & Multi-Tenant PostgreSQL RLS

Alembic migration `002_orders_and_imports.py` provisions four tables with strict tenant isolation and PostgreSQL Row-Level Security:

1. `orders`:
   - UniqueConstraint: `uq_order_org_external_id (org_id, external_order_id)`. Prevents ID collisions within a merchant tenant while enabling distinct tenants to process identical external IDs safely.
   - Indexes: `org_id`, `created_at`, `status`, `customer_phone`, `external_order_id`.
   - RLS Policy: `tenant_isolation_orders` enforcing `org_id = current_setting('app.current_org_id', true)::uuid`.

2. `order_items`:
   - Line items linked to orders with `CASCADE` delete.
   - Database Check Constraints:
     - `quantity >= 1`
     - `unit_price >= 0`
     - `total_price >= 0`
   - RLS Policy: `tenant_isolation_order_items`.

3. `import_jobs`:
   - Tracks Stage A staging and Stage B commit lifecycle (`PREVIEW` -> `COMMITTED`).
   - Stores parsed valid rows in `staged_data` (JSONB) with operational limits (max 10 MB, 5,000 rows).
   - RLS Policy: `tenant_isolation_import_jobs`.

4. `import_job_errors`:
   - Detailed row-by-row error logs recording row index, external order ID, column name, and specific validation message.
   - RLS Policy: `tenant_isolation_import_job_errors`.

---

## 4. Two-Stage CSV Pipeline Endpoints

| Method | Endpoint | Allowed Roles | Description |
|---|---|---|---|
| `GET` | `/api/v1/csv-import/template` | Public / All | Downloads standard RFC 4180 CSV template |
| `POST` | `/api/v1/csv-import/preview` | `OWNER`, `ADMIN`, `OPERATOR` | Stage A: Parses, validates, and stages rows |
| `POST` | `/api/v1/csv-import/commit` | `OWNER`, `ADMIN`, `OPERATOR` | Stage B: Transactionally commits staged orders |
| `GET` | `/api/v1/csv-import/history` | All Roles | Lists import jobs and status metrics |
| `GET` | `/api/v1/csv-import/history/{id}` | All Roles | Retrieves detailed job status and row-level errors |

---

## 5. Next.js Frontend Dashboard & Wizard

Implemented in Next.js 14 (App Router) with TypeScript, Tailwind CSS, and Lucide icons:
- **Order Management Table**: Real-time filtering by status (`PENDING`, `CONFIRMED`, `HOLD`, `DELIVERED`, `RTO`, `CANCELLED`), payment method (`COD`, `PREPAID`), search query, and server-side pagination.
- **Two-Stage Ingestion Wizard**:
  - Sample template download shortcut.
  - Drag-and-drop file upload with format and size checking.
  - Stage A preview dashboard with summary metric badges (Total, Valid, Duplicates, Invalid), valid row data preview table, and row error alert log.
  - Stage B confirmation button with idempotency guard.
  - Post-commit success dialog and import history auditor.

---

## 6. Verification & Test Suite Results

Full automated testing was executed against the backend suite:
- **Total Tests**: 74 tests
- **Passed**: 74 tests (100% pass rate)
- **Failed**: 0
- **Execution Time**: ~43 seconds

### Key Test Coverage Modules
1. `backend/tests/test_orders.py`:
   - Manual order creation with line items and Decimal arithmetic.
   - Tenant-scoped uniqueness and cross-tenant duplicate safety.
   - Phone, pincode, payment method, and monetary value validation.
   - Immutability of order value and key identifiers during update operations.
   - Complete append-only audit trail logging for `ORDER_CREATED` and `ORDER_UPDATED`.
   - RBAC enforcement (`OPERATOR` vs `AUDITOR`).
2. `backend/tests/test_csv_import.py`:
   - Template download header validation.
   - UTF-8 with BOM (`utf-8-sig`) decoding and quoted field parsing.
   - Verification that Stage A preview never writes to `orders`.
   - Intra-file duplicate detection and DB collision handling.
   - Transactional commit and idempotency (double commit rejected with 400).
   - Audit trail verification (`CSV_IMPORT_COMMITTED`).
3. `backend/tests/test_tenant_order_isolation.py`:
   - Cross-tenant order read denial (HTTP 404).
   - Cross-tenant order list denial.
   - Cross-tenant order patch denial.
   - Cross-tenant line items read denial.
   - Cross-tenant CSV commit and history detail denial.
