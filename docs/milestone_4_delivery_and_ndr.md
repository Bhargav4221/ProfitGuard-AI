# ProfitGuard AI — Milestone 4: Delivery Lifecycle & NDR Recovery Hub

## 1. Executive Summary

Milestone 4 implements the **End-to-End Delivery Lifecycle & Non-Delivery Report (NDR) Recovery Hub** for ProfitGuard AI. For Indian Direct-to-Consumer (D2C) e-commerce merchants, 60–75% of Return to Origin (RTO) losses occur after an initial failed doorstep delivery attempt.

The NDR Recovery Hub catches failed delivery scans in real time, quantifies the **Net Recovery Lift** ($\Delta \text{Lift}$) of rescuing the parcel versus abandoning it to RTO, enforces permitted multi-channel recovery actions (`CONTACT_CUSTOMER`, `VERIFY_ADDRESS`, `SCHEDULE_REATTEMPT`, `ESCALATE_TO_MANUAL_REVIEW`, `REQUEST_RTO`, `CLOSE_CASE`), updates customer delivery addresses in-flight, and automatically resolves cases when reattempt delivery succeeds.

---

## 2. Delivery State Machine & Lifecycle Graph

```
  +---------+
  | PENDING |
  +----+----+
       |
       v
  +-----------+               +------+
  | CONFIRMED +-------------->| HOLD |
  +----+------+               +---+--+
       |                          |
       v                          v
+--------------+           +--------------+
| READY_TO_SHIP+---------->| CANCELLED    |  (Terminal)
+------+-------+           +--------------+
       |                          ^
       v                          |
  +---------+                     |
  | SHIPPED +---------------------+
  +----+----+                     |
       |                          |
       v                          |
+------------------+              |
| OUT_FOR_DELIVERY +--------------+
+----+-------+-----+              |
     |       |                    |
     |       v                    |
     |   +-------+                |
     |   |  NDR  +----------------+
     |   +---+---+
     |       | (Reattempt)
     v       v
 +---------------+         +---------------+
 |   DELIVERED   |         |      RTO      |  (Terminal)
 +---------------+         +---------------+
    (Terminal)
```

### Permitted Transitions Matrix

| From State | Allowed Next States | Description |
|:---|:---|:---|
| `PENDING` | `CONFIRMED`, `HOLD`, `CANCELLED` | Initial order intake state |
| `CONFIRMED` | `READY_TO_SHIP`, `HOLD`, `CANCELLED` | Order validated and accepted |
| `HOLD` | `CONFIRMED`, `READY_TO_SHIP`, `CANCELLED` | Risk pause or customer hold |
| `READY_TO_SHIP` | `SHIPPED`, `HOLD`, `CANCELLED` | Warehouse packing & carrier manifest |
| `SHIPPED` | `OUT_FOR_DELIVERY`, `DELIVERED`, `NDR`, `RTO` | In transit with logistics partner |
| `OUT_FOR_DELIVERY` | `DELIVERED`, `NDR`, `RTO` | Courier rider out on delivery run |
| `NDR` | `OUT_FOR_DELIVERY`, `DELIVERED`, `RTO`, `CANCELLED` | Delivery attempt failed; in rescue workflow |
| `DELIVERED` | *(None — Terminal)* | Cash/online payment collected; terminal |
| `RTO` | *(None — Terminal)* | Returned to warehouse inventory; terminal |
| `CANCELLED` | *(None — Terminal)* | Cancelled prior to manifest; terminal |

### Out-of-Order & Terminal Protection
1. **Terminal Immutability**: If an order has reached `DELIVERED`, `RTO`, or `CANCELLED`, receiving delayed or out-of-order scans (e.g. an earlier delayed `OUT_FOR_DELIVERY` or `NDR` event) records the tracking event in the chronological audit table `delivery_events`, but **strictly does not revert** the terminal order state.
2. **Order Value Immutability**: The original checkout GMV (`order_value`) remains 100% immutable across all delivery events, reattempts, or return scans.

---

## 3. Idempotency & Webhook HMAC Security

### Event Idempotency
- Unique constraint `uq_delivery_events_org_event_id` on `(org_id, event_id)` prevents double-counting or double-processing.
- If a carrier webhooks the same scan multiple times, the engine returns the existing event record with HTTP 200 without creating duplicate events or repeating state mutations.

### Webhook Signature Verification
- Inbound courier webhooks (`POST /api/v1/delivery/webhook`) require an HMAC-SHA256 signature in the `X-Courier-Signature` header:
  $$\text{HMAC}_{\text{SHA256}}(\text{raw\_body}, \text{secret})$$
- Verified using timing-safe `hmac.compare_digest`. Invalid or missing signatures are rejected with HTTP 401 Unauthorized.

### Explicit Simulation Labeling
- Every simulated tracking event is strictly marked with `is_simulated = True` and `event_source = 'COURIER_WEBHOOK_SIMULATED'`.
- Simulated data is never fabricated or presented as verified live carrier scans in either backend models or frontend UI.

---

## 4. NDR Recovery Decision Support: Zero Double-Counting Accounting

### Base Terminal Payoffs in NDR
When an order enters NDR, the goods have already left the warehouse and forward delivery was attempted:
1. **Forward Shipping Cost ($S_f$):** Already committed and sunk. Counted in both delivered and RTO base payoffs.
2. **Reverse Shipping Cost ($S_r$):** Charged by the carrier **only if** the package terminates in RTO. If delivery is rescued, $S_r$ is **avoided**.
3. **Inventory Impairment ($D_{\text{rto}}$):** Lost value due to transit damage, packaging wear, or batch expiry:
   $$D_{\text{rto}} = \text{COGS} \times \text{inventory\_damage\_rate}$$
4. **COD Manifest vs Delivery Policy:**
   - If `UPON_DELIVERY_ONLY`, carrier COD collection fee $F_{\text{cod}}$ is incurred only upon successful delivery.
   - If `UPON_MANIFEST`, $F_{\text{cod}}$ is charged upon warehouse handover.

### Payoffs Specification
$$\text{Payoff}(\text{Delivered}) = R_{\text{col}} - \text{COGS} - S_f - F_p - C_{\text{inv}}$$
$$\text{Payoff}(\text{RTO}) = - (S_f + S_r + F_{\text{cod-manifest}} + D_{\text{rto}} + C_{\text{inv}})$$

### Profit at Risk (PaR)
The gross financial upside of successfully delivering the order rather than letting it RTO:
$$\text{PaR} = \text{Payoff}(\text{Delivered}) - \text{Payoff}(\text{RTO})$$
$$\text{PaR} = R_{\text{col}} - \text{COGS} + S_r + D_{\text{rto}} + (F_{\text{cod-manifest}} - F_p)$$

### Net Recovery Lift Formula
For a chosen recovery action $a$ with rescue delivery probability $P_{\text{deliv}}(a)$ and incremental intervention cost $C_{\text{int}}(a)$:
$$EC(a) = P_{\text{deliv}}(a) \times \text{Payoff}(\text{Delivered}) + (1 - P_{\text{deliv}}(a)) \times \text{Payoff}(\text{RTO}) - C_{\text{int}}(a)$$
$$\Delta \text{Recovery Lift} = EC(a) - \text{Payoff}(\text{RTO}) = P_{\text{deliv}}(a) \times \text{PaR} - C_{\text{int}}(a)$$

**Double-Counting Safeguards Verified:**
- Sunk forward shipping $S_f$ is present in both base outcomes and cancels out in lift $\Delta \text{Lift}$.
- Avoided reverse shipping $S_r$ is credited exactly once in PaR.
- Action intervention cost $C_{\text{int}}(a)$ is subtracted exactly once.
- Recovered revenue is counted exactly once if delivered.

---

## 5. Permitted NDR Recovery Actions

1. **`CONTACT_CUSTOMER`**:
   - Outreach via WhatsApp, SMS, or Call Center dialer.
   - Captures customer reason, preferred delivery time window, or gate instructions.
   - Updates case status to `IN_PROGRESS`.
2. **`VERIFY_ADDRESS`**:
   - Captures corrected house/flat number, landmark, city, postal pincode, or alternate mobile number.
   - Propagates amended shipping details directly onto the core `orders` table.
3. **`SCHEDULE_REATTEMPT`**:
   - Transmits requested redelivery slot and special instructions to logistics partner.
   - Updates case status to `REATTEMPT_SCHEDULED`.
4. **`ESCALATE_TO_MANUAL_REVIEW`**:
   - Escalates high-value cases or orders with customer refusal to senior tele-callers.
   - Sets case priority to `HIGH`.
5. **`REQUEST_RTO`**:
   - Terminates rescue attempts when customer confirms cancellation or refuses delivery.
   - Transitions case to `RESOLVED_RTO` and initiates carrier RTO scan on the order.
6. **`CLOSE_CASE`**:
   - Manually closes case with logged audit rationale.

---

## 6. PostgreSQL Row-Level Security (RLS)

Migration `004_delivery_lifecycle_and_ndr.py` enables RLS on all three delivery tables:
```sql
ALTER TABLE delivery_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_delivery_events ON delivery_events
    FOR ALL
    USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
    WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);

ALTER TABLE ndr_cases ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_ndr_cases ON ndr_cases
    FOR ALL
    USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
    WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);

ALTER TABLE ndr_action_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_ndr_action_logs ON ndr_action_logs
    FOR ALL
    USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
    WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
```

---

## 7. REST API Endpoints

| Method | Path | Auth / Role | Description |
|:---|:---|:---|:---|
| `POST` | `/api/v1/delivery/events` | `OPERATOR`, `ADMIN`, `OWNER` | Ingests delivery scan, validates state machine, triggers NDR |
| `POST` | `/api/v1/delivery/simulate` | `OPERATOR`, `ADMIN`, `OWNER` | Simulates delivery event with `is_simulated=True` |
| `POST` | `/api/v1/delivery/webhook` | Webhook HMAC Signature | Courier tracking webhook receiver |
| `GET` | `/api/v1/delivery/events/{order_id}` | All tenant roles | Chronological delivery history for order |
| `GET` | `/api/v1/delivery/ndr` | All tenant roles | Lists NDR cases with multi-criteria filtering |
| `GET` | `/api/v1/delivery/ndr/{case_id}` | All tenant roles | Retrieves NDR case details and audit history |
| `POST` | `/api/v1/delivery/ndr/{case_id}/actions` | `OPERATOR`, `ADMIN`, `OWNER` | Executes permitted recovery action |
| `GET` | `/api/v1/delivery/ndr/{case_id}/recommendation` | All tenant roles | Decision support lift & PaR calculation |
