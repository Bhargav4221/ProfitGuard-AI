# ProfitGuard AI — Milestone 3: Order Decision Engine Specification & Documentation

## 1. Executive Summary

Milestone 3 implements the **Profit-Aware Order Decision Engine** for ProfitGuard AI. Rather than treating Return to Origin (RTO) simply as a classification risk score (0-1), the decision engine optimizes merchant **Contribution Profit** across 5 candidate fulfillment actions.

For every evaluated order, the engine evaluates the expected contribution ($EC$) of each candidate action, deducts intervention expenses exactly once, computes the incremental lift ($\Delta EC$) against the default baseline (`SHIP_AS_IS`), verifies strict policy guards, selects the profit-maximizing eligible action, and records the evaluation with complete transparency and human-override capability.

---

## 2. Decision Engine Architecture

```
                                    +-----------------------+
                                    |     Incoming Order    |
                                    +-----------+-----------+
                                                |
                                                v
               +-----------------------------------------------------------------+
               |              Tier 1: Base Terminal Outcome Payoffs              |
               |                                                                 |
               |  BaseContrib(Delivered) = R_col - COGS - S_f - F_p - C_inv     |
               |  BaseContrib(RTO)       = - (S_f + S_r + F_p + D_rto + C_inv)   |
               |  BaseContrib(Cancelled) = 0 (Inventory restored, no shipping)   |
               +--------------------------------+--------------------------------+
                                                |
                                                v
               +-----------------------------------------------------------------+
               |       Risk Estimation & Heuristic Pincode Uncertainty           |
               |                                                                 |
               |  U = sqrt(M_0 / (M_0 + N)),  M_0 = 25                           |
               |  Anti-Cancellation Gate: If U > 0.50 or N < 15, HOLD_CANCEL     |
               |  is disallowed regardless of negative expected value.           |
               +--------------------------------+--------------------------------+
                                                |
                                                v
               +-----------------------------------------------------------------+
               |             Tier 2: Five Candidate Actions Evaluation           |
               |                                                                 |
               |  1. SHIP_AS_IS: Baseline dispatch (C_int = 0)                   |
               |  2. VERIFY_OTP: WhatsApp/SMS OTP (C_int = ₹1.50)                |
               |  3. INCENTIVIZE_PREPAID: Discount + PG Fee (Disqualified if COD)|
               |  4. MANUAL_REVIEW: Call Center Audit (C_int = ₹15.00)           |
               |  5. HOLD_CANCEL: Automated cancellation (Policy gated)          |
               +--------------------------------+--------------------------------+
                                                |
                                                v
               +-----------------------------------------------------------------+
               |           Tier 3: Policy Guards & Optimal Selection             |
               |                                                                 |
               |  - Safety Value Cap (Default: ₹10,000 max order value for auto) |
               |  - Merchant auto-cancel permission (allow_auto_cancel)          |
               |  - Maximum Expected Contribution Selection:                     |
               |    a* = argmax_{a in Eligible} [ EC(a) ]                         |
               |    Lift Delta EC = EC(a*) - EC(SHIP_AS_IS)                      |
               +--------------------------------+--------------------------------+
                                                |
                                                v
                               +---------------------------------+
                               | Persistence & Audit Ledger      |
                               | (order_evaluations table, RLS)  |
                               +---------------------------------+
```

---

## 3. Financial Accounting Specifications

All monetary calculations use Python `Decimal` fixed-point arithmetic (`ROUND_HALF_UP`) to 2 decimal places. Floating-point arithmetic is strictly prohibited across all services.

### 3.1 Strict Separation of Concepts
1. **Gross Merchandise Value ($V$):** Original customer invoice value. Strictly immutable once created.
2. **Collected Revenue ($R_{col}$):** Actual cash collected. On RTO, $R_{col} = 0$. On delivered COD, $R_{col} = V$. On delivered prepaid, $R_{col} = V - \text{prepaid\_discount}$.
3. **Expected Contribution ($EC$):** Probability-weighted future outcome minus action intervention cost.
4. **Realized Contribution ($RC$):** Ex-post actual contribution after physical fulfillment and verified accounting events.

### 3.2 Terminal Outcome Payoffs (Tier 1)
For an order with order value $V$, COGS $C$, forward shipping $S_f$, reverse shipping $S_r$, inventory impairment $D_{rto}$, inventory holding/packaging cost $C_{inv}$, payment gateway rate $r_{pg}$, and COD fee policy:

* **Delivered COD:**
  $$\text{BaseContrib}_{\text{Delivered}} = V - C - S_f - F_{\text{cod}} - C_{inv}$$
  *(Where $F_{\text{cod}}$ is incurred based on merchant policy: `UPON_DELIVERY_ONLY` vs `UPON_MANIFEST`)*
* **Delivered Prepaid:**
  $$\text{BaseContrib}_{\text{Delivered}} = V - C - S_f - (V \times r_{pg}) - C_{inv}$$
* **RTO COD:**
  $$\text{BaseContrib}_{\text{RTO}} = - (S_f + S_r + F_{\text{cod-manifest}} + D_{rto} + C_{inv})$$
  *(Note: Revenue collected is ₹0; COD collection fee is ₹0 under `UPON_DELIVERY_ONLY`)*
* **RTO Prepaid (Refunded):**
  $$\text{BaseContrib}_{\text{RTO}} = - (S_f + S_r + (V \times r_{pg}) + D_{rto} + C_{inv})$$
  *(Customer is refunded $V$; gateway processing fee on the original transaction is non-refundable)*
* **Cancelled Order:**
  $$\text{BaseContrib}_{\text{Cancelled}} = 0$$
  *(Order is stopped before warehouse manifest; goods remain in inventory; no shipping or carrier fees are incurred)*

### 3.3 Action-Adjusted Expected Contribution ($EC$) (Tier 2)
For any candidate action $a \in \{\text{SHIP\_AS\_IS}, \text{VERIFY\_OTP}, \text{INCENTIVIZE\_PREPAID}, \text{MANUAL\_REVIEW}, \text{HOLD\_CANCEL}\}$:

$$EC(a) = \sum_{o \in \{\text{Delivered}, \text{RTO}, \text{Cancelled}\}} P(o \mid a) \times \text{BaseContrib}(o \mid a) - C_{\text{int}}(a)$$

* **Intervention Cost Incurred Exactly Once:**
  - $C_{\text{int}}(\text{SHIP\_AS\_IS}) = ₹0$
  - $C_{\text{int}}(\text{VERIFY\_OTP}) = ₹1.50$ (SMS/WhatsApp provider charge)
  - $C_{\text{int}}(\text{INCENTIVIZE\_PREPAID}) = \text{Discount} + (V_{\text{disc}} \times r_{pg})$
  - $C_{\text{int}}(\text{MANUAL\_REVIEW}) = ₹15.00$ (Agent dialer and review allocation)
  - $C_{\text{int}}(\text{HOLD\_CANCEL}) = ₹0$

---

## 4. Transparent Risk Estimation & Heuristic Uncertainty

### 4.1 Input Classification
To ensure auditability, all numbers entering the decision engine carry explicit taxonomy labels:
- `[SPECIFIED / FIXTURE]`: Benchmark test fixtures (Fixtures 1–9) used for verification.
- `[CONFIGURED]`: Merchant-specific financial policies retrieved from organization settings.
- `[ESTIMATED]`: Model-derived risk and transition probabilities.
- `[MEASURED]`: Verifiable historical performance data.

### 4.2 Heuristic Pincode Uncertainty Formula
Because delivery performance varies widely across Indian postal codes, the engine assesses statistical confidence based on historical sample size $N$ in the order's destination pincode:

$$U = \sqrt{\frac{M_0}{M_0 + N}}, \quad M_0 = 25$$

| Sample Size ($N$) | Uncertainty ($U$) | Reliability Interpretation |
|:---|:---|:---|
| $N = 0$ | $1.000$ (100%) | Complete lack of evidence |
| $N = 10$ | $0.845$ (84.5%) | Sparse data; high variance |
| $N = 25$ | $0.707$ (70.7%) | Moderate variance |
| $N = 75$ | $0.500$ (50.0%) | Anti-cancellation gate boundary |
| $N = 100$ | $0.447$ (44.7%) | Preliminary reliability threshold |
| $N = 500$ | $0.218$ (21.8%) | High statistical confidence |

### 4.3 Anti-Cancellation Gate
To protect merchant sales volume and avoid customer alienation from false positives:
- Automated cancellation (`HOLD_CANCEL`) is **strictly prohibited** if $U > 0.50$ (or $N < 15$), even if $EC(\text{SHIP\_AS\_IS}) < 0$ and `allow_auto_cancel` is enabled.
- Orders in high-uncertainty areas with elevated risk are routed to `MANUAL_REVIEW` or `VERIFY_OTP` instead.

---

## 5. Policy Guards

The engine enforces three deterministic policy guards before recommending an action:
1. **Safety Order Value Cap (`safety_value_cap`):**
   - High-value orders exceeding the merchant's configured threshold (default: ₹10,000) are protected from automated cancellation.
   - If an order's value exceeds the cap, `HOLD_CANCEL` is blocked and `MANUAL_REVIEW` is substituted.
2. **Auto-Cancel Permission (`allow_auto_cancel`):**
   - Unless the merchant explicitly opts in to automated order cancellation, `HOLD_CANCEL` is disabled and flagged with a policy override.
3. **Prepaid Disqualification:**
   - Orders already paid via online payment gateways (`payment_method == 'PREPAID'`) are immediately disqualified from `INCENTIVIZE_PREPAID`, preventing illogical discount offers.

---

## 6. API Specifications

### 6.1 `POST /api/v1/orders/{order_id}/evaluate`
Runs the 5-action decision comparison engine for an order and persists an `order_evaluations` record.

**Response Schema (`OrderEvaluationOut`):**
```json
{
  "id": "e4b1a1c2-3d4e-5f6a-7b8c-9d0e1f2a3b4c",
  "order_id": "f5c2b3a4-4e5f-6a7b-8c9d-0e1f2a3b4c5d",
  "org_id": "9f8a7b6c-5d4e-3f2a-1b0c-9e8d7c6b5a4f",
  "status": "EVALUATED",
  "recommended_action": "VERIFY_OTP",
  "recommended_ec": "358.50",
  "baseline_ec": "300.00",
  "expected_lift": "58.50",
  "evaluation_mode": "PROFIT_AWARE_V1",
  "action_comparisons": [
    {
      "action": "SHIP_AS_IS",
      "p_delivered": "0.7000",
      "p_rto": "0.3000",
      "p_cancelled": "0.0000",
      "base_payoff_delivered": "500.00",
      "base_payoff_rto": "-200.00",
      "intervention_cost": "0.00",
      "expected_contribution": "300.00",
      "incremental_lift": "0.00",
      "is_policy_eligible": true,
      "disqualification_reason": null
    },
    {
      "action": "VERIFY_OTP",
      "p_delivered": "0.8500",
      "p_rto": "0.1000",
      "p_cancelled": "0.0500",
      "base_payoff_delivered": "500.00",
      "base_payoff_rto": "-200.00",
      "intervention_cost": "1.50",
      "expected_contribution": "358.50",
      "incremental_lift": "58.50",
      "is_policy_eligible": true,
      "disqualification_reason": null
    }
  ],
  "explanation": {
    "summary": "VERIFY_OTP yields highest expected contribution (₹358.50 vs baseline ₹300.00, lift: +₹58.50).",
    "base_rto_prob": "0.3000",
    "pincode_uncertainty": "0.3536",
    "pincode_sample_size": 175,
    "triggered_rules": [],
    "policy_guards": []
  },
  "created_at": "2026-10-11T18:15:00Z"
}
```

### 6.2 `GET /api/v1/orders/{order_id}/decision`
Retrieves the latest evaluation for the specified order.

### 6.3 `POST /api/v1/orders/{order_id}/decision`
Accepts or overrides the engine's recommendation.

**Request Payload:**
```json
{
  "selected_action": "SHIP_AS_IS",
  "is_override": true,
  "override_reason": "Merchant confirmed repeat customer identity via phone"
}
```

### 6.4 `POST /api/v1/orders/{order_id}/intervention-outcome`
Records ex-post execution results (e.g. OTP verification success, prepaid incentive conversion, call center review note).

---

## 7. PostgreSQL Row-Level Security (RLS)

The `order_evaluations` table implements tenant isolation via PostgreSQL Row-Level Security:

```sql
CREATE POLICY tenant_isolation_order_evaluations ON order_evaluations
    AS RESTRICTIVE
    USING (org_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);
```

All queries set the tenant session parameter via `app.dependencies.get_tenant_db`, guaranteeing strict cross-tenant isolation at the database layer.

---

## 8. Frontend User Experience

The Next.js 14 frontend provides merchant operators with actionable risk insights and controls:
- **Order Table Integration:** Single-click "Decide" button next to each order.
- **Top Recommendation Banner:** Highlighted recommendation with Expected Lift ($\Delta EC$).
- **5-Action Comparison Table:** Detailed view of Expected Contribution ($EC$), Delivered/RTO probabilities, Intervention Costs, and Eligibility.
- **Rule Explanations & Uncertainty Disclosures:** Transparent display of triggered heuristics, pincode historical sample size ($N$), and statistical uncertainty ($U$).
- **Operator Override Workflow:** Dropdown to select alternative actions with mandatory override rationale logging.
- **Intervention Lifecycle Tracking:** Direct interface to record OTP delivery status and customer responses.
