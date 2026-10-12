# ProfitGuard AI — Production Integration Safety & Security Specification

## 1. Executive Summary & Environment Security Notice

ProfitGuard AI is designed as a secure, multi-tenant SaaS platform for Indian D2C merchants managing high-volume Cash on Delivery (COD) and prepaid fulfillment. This document defines the production integration architecture, courier webhook security, external commerce adapters, and the database Row-Level Security (RLS) enforcement model.

> [!CAUTION]
> **Real PostgreSQL RLS Verification Status: NOT VERIFIED (Real PostgreSQL not connected)**
> In the local test and development environment, neither a local PostgreSQL server on port 5432 nor Docker daemon is active. All automated application tests run against an in-memory SQLite database simulating RLS session scopes and tenant filter clauses. While all Alembic migrations (001 through 005) include syntactically valid PostgreSQL RLS policies (`CREATE POLICY ... ON ... USING (org_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)`), live verification against a native PostgreSQL kernel with restricted database roles must be completed during staging deployment prior to processing live production traffic.

---

## 2. Inbound Courier Webhook & Adapter Specifications

ProfitGuard AI supports unified delivery tracking event ingestion from major Indian logistics aggregators and direct courier partners. All incoming tracking webhooks are processed through idempotent endpoints with cryptographic signature verification.

### 2.1 Supported Logistics Carriers & Inbound Adapters

| Courier / Channel | Authentication Scheme | Required Secret / Credential | Supported Events | Idempotency Key Scheme |
| :--- | :--- | :--- | :--- | :--- |
| **Delhivery** | HMAC-SHA256 signature in `X-Delhivery-Signature` or API token | `DELHIVERY_WEBHOOK_SECRET` | `MANIFESTED`, `DISPATCHED`, `IN_TRANSIT`, `OUT_FOR_DELIVERY`, `DELIVERED`, `UNDELIVERED_ATTEMPT`, `RTO_INITIATED`, `RTO_DELIVERED` | Courier Waybill + Attempt Number (`waybill:attempt`) |
| **Shiprocket** | HMAC-SHA256 header `X-Shiprocket-Signature` | `SHIPROCKET_WEBHOOK_TOKEN` | `PICKED_UP`, `IN_TRANSIT`, `OUT_FOR_DELIVERY`, `DELIVERED`, `NDR`, `RTO_INITIATED`, `RTO_DELIVERED` | AWB + Status Code + Timestamp |
| **Blue Dart** | Basic Auth / Mutual TLS with Bearer Token | `BLUEDART_CUSTOMER_CODE`, `BLUEDART_LICENSE_KEY` | `STATUS_UPDATE`, `DELIVERY_FAILED`, `SHIPMENT_DELIVERED`, `RETURNED` | Scan Key + Token ID |
| **Shopify / D2C Webhooks** | HMAC-SHA256 in `X-Shopify-Hmac-SHA256` | `SHOPIFY_API_SECRET` | `orders/create`, `orders/updated`, `orders/cancelled`, `fulfillments/create` | Shopify Order ID + Fulfillment ID |

---

## 3. Webhook Security & Idempotency Protocol

### 3.1 Cryptographic Signature Verification
All external webhook ingress routes (`/api/v1/delivery/webhooks/{carrier}`) enforce signature verification prior to payload parsing:

```python
computed_hmac = hmac.new(
    webhook_secret.encode("utf-8"),
    raw_payload_bytes,
    hashlib.sha256
).hexdigest()

if not hmac.compare_digest(incoming_signature, computed_hmac):
    raise HTTPException(status_code=401, detail="Invalid webhook signature")
```

### 3.2 Idempotency & Deduplication Guarantees
1. **Unique Event Keying**: Every tracking event requires a unique `event_id`. The database schema enforces a composite unique constraint:
   $$\text{UNIQUE}(\text{org\_id}, \text{event\_id})$$
2. **Replay Invariance**: When a carrier sends duplicate webhooks (e.g., retries due to network jitter), the event engine detects the existing `event_id`, bypasses state re-evaluation, returns `HTTP 201 Created` with the existing event record, and does NOT re-trigger NDR cases or re-calculate economics.
3. **Timestamp Tolerance**: Inbound webhooks with event timestamps diverging by more than $\pm 15\text{ minutes}$ from host NTP clock are flagged for clock-skew inspection.

### 3.3 Terminal State Protection Guard
Once an order reaches a terminal state (`DELIVERED`, `RTO`, `CANCELLED`):
- Any subsequent late delivery events (e.g., duplicate `OUT_FOR_DELIVERY` scans or late carrier pings) are appended to the delivery audit log for traceability.
- The order status and financial ledger are strictly immutable and will **never** revert back to in-transit or active status.

---

## 4. Authoritative Financial Accounting Convention

To prevent discrepancies and double-counting across the order lifecycle, ProfitGuard AI enforces a single, mathematically verified unit economics accounting ledger:

$$\text{Realized Contribution (RC)} = \text{Collected Revenue} - \text{COGS} - S_f - S_r - F_p - C_{\text{pkg}} - D_{\text{rto}} - C_{\text{pre-dispatch}} - C_{\text{ndr}}$$

### 4.1 Cost Accrual Rules
1. **Gross Merchandise Value (GMV)**:
   - Recorded at initial checkout ingestion (`order_value`).
   - Immutable across all subsequent states.
2. **Collected Revenue**:
   - For **Delivered COD**: Equals collected cash value upon physical delivery.
   - For **Delivered Prepaid**: Equals captured checkout payment.
   - For **RTO / Cancelled**: Evaluates to ₹0.00 (any customer refund for prepaid is netted out).
3. **Forward Shipping ($S_f$)**:
   - Sunk immediately upon carrier manifest / dispatch (`READY_TO_SHIP` / `SHIPPED`).
   - Incurred on both delivered and RTO shipments.
4. **Reverse Shipping ($S_r$)**:
   - Accrues **only** upon physical carrier handover for return transit (`RTO`).
   - On successful first-time delivery or successful NDR reattempt delivery, $S_r = ₹0.00$ (avoided loss).
5. **Payment Collection Fees ($F_p$)**:
   - COD Collection Fee: Accrued per merchant policy (`ON_DELIVERY_COLLECTION` vs `ON_MANIFEST_DISPATCH`).
   - Prepaid Gateway Fee (MDR): Accrued at checkout authorization.
6. **Pre-Dispatch Intervention Cost ($C_{\text{pre-dispatch}}$)**:
   - Incurred once when an automated OTP verification SMS, WhatsApp message, or manual review occurs (typically ₹0.50–₹1.50).
7. **NDR Recovery Intervention Cost ($C_{\text{ndr}}$)**:
   - Sum of customer contact outreach costs and carrier reattempt fees (e.g. ₹3.00 for WhatsApp + reattempt booking).
   - Accrues only when recovery actions are executed.
8. **Inventory Damage / Impairment ($D_{\text{rto}}$)**:
   - Incurred only upon verified RTO return inspection based on configured damage impairment rate.
   - Evaluates to ₹0.00 on delivered orders.

---

## 5. PostgreSQL Row-Level Security (RLS) Specification

For multi-tenant SaaS isolation, ProfitGuard AI defines database-enforced RLS policies across all tenant-scoped tables:

### 5.1 Tables with RLS Enforced
- `orders`
- `order_items`
- `merchant_economics`
- `order_evaluations`
- `delivery_events`
- `ndr_cases`
- `ndr_action_logs`
- `order_financial_reconciliations`
- `audit_logs`

### 5.2 Session Tenant Context Injection
For every request transaction, the application sets the session tenant variable:
```sql
SET LOCAL app.current_tenant_id = '<authenticated-org-uuid>';
```

### 5.3 Formal PostgreSQL RLS Policy Definition
```sql
ALTER TABLE order_financial_reconciliations ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_financial_reconciliations FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_financial_reconciliations
ON order_financial_reconciliations
FOR ALL
USING (org_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
WITH CHECK (org_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);
```

### 5.4 Pre-Production Verification Checklist for Real PostgreSQL
Before promoting to staging or production:
1. Connect via `psql` using a non-superuser application role (`profitguard_app_user`).
2. Verify table permissions: Ensure `BYPASSRLS` is NOT granted to the application user.
3. Execute tenant isolation queries:
   ```sql
   SET LOCAL app.current_tenant_id = '00000000-0000-0000-0000-000000000001';
   SELECT count(*) FROM orders; -- Must return only Tenant 1 records
   SET LOCAL app.current_tenant_id = '00000000-0000-0000-0000-000000000002';
   SELECT count(*) FROM orders; -- Must return only Tenant 2 records
   RESET app.current_tenant_id;
   SELECT count(*) FROM orders; -- Must return 0 rows (fail-closed)
   ```
4. Verify that cross-tenant inserts fail with an RLS check violation.

---

## 6. Simulated Demonstration Dataset Harness

To enable deterministic demonstrations and regression testing without corrupting live merchant data:
1. All demo orders are assigned external order IDs matching `DEMO-*`.
2. All demo events are flagged with `is_simulated = true`.
3. The demo reset endpoint executes:
   ```sql
   DELETE FROM orders WHERE org_id = :org_id AND external_order_id LIKE 'DEMO-%';
   ```
   This guarantees that non-demo merchant orders are never deleted or affected.
