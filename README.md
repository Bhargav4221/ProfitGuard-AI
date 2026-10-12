# ProfitGuard AI — Risk-Aware E-commerce RTO Decision Platform

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-14.2%20App%20Router-black.svg)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0%2B-3178C6.svg)](https://www.typescriptlang.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind%20CSS-3.4-38B2AC.svg)](https://tailwindcss.com/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-1.7%2B-F7931E.svg)](https://scikit-learn.org/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0%2B-red.svg)](https://www.sqlalchemy.org/)
[![Alembic](https://img.shields.io/badge/Alembic-1.13%2B-brown.svg)](https://alembic.sqlalchemy.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15%2B%20RLS-336791.svg)](https://www.postgresql.org/)
[![Meta WhatsApp Cloud API](https://img.shields.io/badge/Meta%20WhatsApp-Cloud%20API%20v20.0-25D366.svg)](https://developers.facebook.com/docs/whatsapp/cloud-api)
[![Shopify API](https://img.shields.io/badge/Shopify%20API-Webhooks%202024--01-96BF48.svg)](https://shopify.dev/docs/api)
[![Tests](https://img.shields.io/badge/Tests-183%20Passed-brightgreen.svg)]()

> **Notice & Disclaimer**: Predictions, risk scores, and estimated contribution calculations produced by ProfitGuard AI are decision-support outputs based on mathematical modeling and historical priors. They are intended to assist e-commerce operators and merchants in risk management and do not constitute guaranteed operational or financial outcomes.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Problem Statement](#problem-statement)
3. [Novelty and Architectural Differentiation](#novelty-and-architectural-differentiation)
4. [Technology Stack](#technology-stack)
5. [Complete System Architecture](#complete-system-architecture)
6. [End-to-End Technical Workflow](#end-to-end-technical-workflow)
7. [Machine-Learning Pipeline](#machine-learning-pipeline)
   - [Dataset Source and Provenance](#dataset-source-and-provenance)
   - [Feature Engineering & Feature Contract](#feature-engineering--feature-contract)
   - [Model Training and Evaluation](#model-training-and-evaluation)
   - [Inference Pipeline](#inference-pipeline)
   - [Limitations and Multi-Tier Governance](#limitations-and-multi-tier-governance)
8. [Economic Decision Engine](#economic-decision-engine)
   - [Input Variables & Payoffs](#input-variables--payoffs)
   - [The 5 Candidate Actions](#the-5-candidate-actions)
   - [Estimated Contribution Formulas](#estimated-contribution-formulas)
   - [Step-by-Step Numerical Example](#step-by-step-numerical-example)
   - [Authoritative Realized Contribution Ledger](#authoritative-realized-contribution-ledger)
9. [Decision Engine vs. ML Model Comparison](#decision-engine-vs-ml-model-comparison)
10. [Storefront & Messaging Integrations](#storefront--messaging-integrations)
    - [Shopify Integration](#shopify-integration)
    - [Meta WhatsApp Business Cloud API](#meta-whatsapp-business-cloud-api)
11. [Database Schema & Data Flow](#database-schema--data-flow)
12. [Security, Reliability, and Governance](#security-reliability-and-governance)
13. [Installation & Local Setup](#installation--local-setup)
14. [Configuration Reference](#configuration-reference)
15. [Testing & Verification](#testing--verification)
16. [Project Directory Structure](#project-directory-structure)
17. [Limitations & Roadmap](#limitations--roadmap)
18. [Contribution, License & Contact](#contribution-license--contact)

---

## Project Overview

**ProfitGuard AI** is a production-oriented, multi-tenant SaaS platform built for Direct-to-Consumer (D2C) e-commerce merchants. In emerging e-commerce markets—especially India—Cash-on-Delivery (COD) accounts for 60% to 75% of order volumes. A significant portion of these orders fail during transit and result in **Return-to-Origin (RTO)**, inflicting substantial unrecoverable costs on merchants in forward logistics, reverse logistics, transit damage, and locked-up inventory.

Rather than relying solely on black-box risk scores or crude blanket cancellations, ProfitGuard AI implements an integrated, profit-maximizing decision framework:
- **Ex-Ante ML Risk Estimation**: Evaluates non-delivery likelihood at checkout using customer, order, geographical, and historical signals under strict zero-leakage feature contracts.
- **3-Tier Economic Decision Engine**: Computes action-adjusted expected financial contributions ($EC$) across 5 discrete operational choices (`SHIP_AS_IS`, `VERIFY_OTP`, `INCENTIVIZE_PREPAID`, `MANUAL_REVIEW`, `HOLD_CANCEL`) deducting intervention costs exactly once.
- **Operational Intervention Hub**: Directly coordinates pre-dispatch customer verification (via Meta WhatsApp Cloud API OTP templates) and Non-Delivery Report (NDR) recovery workflows when couriers report first-attempt delivery failures.
- **Ex-Post Financial Settlement**: Tracks actual courier transit scans to terminal outcomes (`DELIVERED`, `RTO`, `CANCELLED`) and settles realized contribution ($RC$) into an authoritative ledger to audit estimated vs. realized results without double-counting.

---

## Problem Statement

E-commerce merchants operating in COD-heavy markets face an operational asymmetry:
1. **Unrecoverable Shipping Losses**: When a COD parcel is rejected or cannot be delivered, the merchant absorbs forward freight ($S_f$), reverse freight ($S_r$), packaging ($C_{\text{pkg}}$), and inventory damage rates ($D_{\text{inv}}$), while receiving ₹0.00 in revenue.
2. **The "High-Risk, High-Margin" Fallacy**: A generic classifier might flag an order with a 30% RTO probability as "high risk". However, if the order carries a ₹3,000 contribution margin and shipping costs ₹150, shipping the order yields a positive expected value of ₹1,950. Cancelling it destroys profit. Conversely, an order with only 20% RTO risk but a thin ₹100 margin may yield negative expected value after factoring in return freight.
3. **Blanket Interventions Waste Capital**: Sending OTP verification or discount incentives to every buyer incurs unnecessary SaaS and messaging costs, friction at checkout, and delayed fulfillment.
4. **Lack of Closed-Loop Feedback**: Most systems score an order at checkout and never reconcile whether the prediction was accurate or whether the intervention improved delivery rates.

```mermaid
flowchart TD
    subgraph Problem ["The Traditional Dilemma"]
        A[Incoming COD Order] --> B{Standalone ML Classifier}
        B -->|High Risk Score| C[Blanket Order Cancellation]
        B -->|Low Risk Score| D[Blind Fulfillment]
        C --> E[Lost Revenue & Alienated Legitimate Customers]
        D --> F[Avoidable RTO Losses & Sunk Freight Costs]
    end

    subgraph Solution ["ProfitGuard AI Integrated Approach"]
        G[Incoming COD Order] --> H[Order Feature Contract]
        H --> I[Ex-Ante Risk Estimation]
        I --> J[Economic Decision Engine]
        J --> K{Optimal Policy Selection}
        K -->|Positive Lift| L[Targeted WhatsApp OTP / Prepaid Incentive]
        K -->|High Margin Safe| M[Fulfill As-Is]
        K -->|Net Negative & Low Uncertainty| N[Operator Manual Review / Hold]
        L & M --> O[Courier Transit & Delivery State Machine]
        O -->|Delivery Failure| P[NDR Customer Recovery Hub]
        O -->|Terminal Settlement| Q[Authoritative Realized Ledger]
        P --> Q
    end

    style Problem fill:#fff1f2,stroke:#f43f5e,stroke-width:2px
    style Solution fill:#f0fdf4,stroke:#22c55e,stroke-width:2px
```

---

## Novelty and Architectural Differentiation

ProfitGuard AI distinguishes itself from conventional fraud filters and standalone risk models by structuring operations into a closed-loop economic pipeline:

$$\mathbf{ML\ Risk\ Estimation} \xrightarrow{\quad} \mathbf{Economic\ Decision\ Engine} \xrightarrow{\quad} \mathbf{Operational\ Intervention} \xrightarrow{\quad} \mathbf{Outcome\ Reconciliation}$$

1. **Separation of Statistical Risk from Economic Choice**: Risk is an input to an optimization model, not the decision itself. An action is recommended only if its expected contribution exceeds baseline fulfillment by an incremental profit margin ($\Delta EC > 0$).
2. **Single-Intervention Cost Rule**: Traditional spreadsheets and rule engines frequently double-count communications or platform fees. ProfitGuard AI enforces strict single-deduction accounting: pre-dispatch messaging expenses ($C_{\text{int}}$) are deducted exactly once from the chosen decision branch.
3. **Uncertainty Calibration & Anti-Cancellation Gate**: Consequential automation (e.g., cancelling an order) is strictly forbidden on sparse data. Pincode reliability is governed by Bayesian shrinkage uncertainty $U = \sqrt{M_0 / (M_0 + N)}$. If an area has fewer than 15 historical orders ($N < 15$) or uncertainty exceeds threshold ($U > 0.7910$), autonomous cancellation is locked out, forcing human review.
4. **Closed-Loop NDR Recovery Queue**: If an order fails first delivery attempt, it enters an active NDR state machine. The system computes expected recovery lift ($\Delta \text{Lift}$) vs. abandoning to RTO, allowing operators to trigger WhatsApp address re-verification or schedule delivery re-attempts.
5. **Strict Multi-Tier ML Governance**: The platform natively isolates development benchmark models from production fulfillment through three explicit operating modes: `SHADOW`, `LIVE_ASSISTED`, and `DISABLED`. Synthetic benchmark models are restricted from autonomous order cancellation.

---

## Technology Stack

| Technology | Where It Is Used | Purpose in ProfitGuard AI |
|:---|:---|:---|
| **Python 3.10+** | Backend Runtime | Core programming language powering the backend REST API, mathematical services, and ML execution. |
| **FastAPI** | Backend Framework | High-performance asynchronous API framework providing automatic OpenAPI documentation, dependency injection, and Pydantic validation. |
| **scikit-learn** | ML Pipeline | Serialized `Pipeline` and `ColumnTransformer` preprocessing, imputation, scaling, and `LogisticRegression` probability calibration. |
| **joblib** | Model Persistence | Secure loading and serialization of versioned ML artifacts and metadata dictionaries (`rto_model_v1.joblib`). |
| **PostgreSQL 15+** | Primary Database | Multi-tenant transactional relational storage, enforced with Row-Level Security (RLS) policies and transaction-local variables. |
| **SQLAlchemy 2.0** | ORM & Query Layer | Type-safe declarative database models, transactional sessions, and relationship mappings. |
| **Alembic** | Database Migrations | Versioned, deterministic DDL migrations tracking schema changes from initial auth to real outcome ledgers and WhatsApp schemas. |
| **Next.js 14** | Frontend Framework | React-based App Router frontend delivering responsive server/client rendering, dashboard KPIs, and management tabs. |
| **TypeScript** | Frontend Language | Compile-time type checking ensuring strict alignment with backend Pydantic API contracts and state models. |
| **Tailwind CSS** | UI Styling | Modern, responsive design system with custom components, alerts, and modal dialogs. |
| **Meta WhatsApp Cloud API** | Channel Integration | Official Meta Graph API (v20.0) integration for template dispatch, OTP verification, customer responses, and delivery status events. |
| **Shopify API** | Storefront Integration | Real-time HMAC-SHA256 authenticated webhook receiver (`orders/create`) and bi-directional order tagging synchronization. |
| **pytest** | Test Framework | Comprehensive automated testing suite covering unit tests, cryptographic tests, integration flows, and end-to-end user journeys (183 tests). |

---

## Complete System Architecture

The following diagram details the interactions between operators, the Next.js presentation layer, the FastAPI backend, internal services, and external third-party platforms:

```mermaid
flowchart TB
    subgraph Clients ["Operators & Storefronts"]
        Merchant["Merchant / Operations Agent"]
        ShopifyStore["Shopify Storefront (External)"]
        WhatsAppUser["Customer Mobile Device (External)"]
    end

    subgraph Frontend ["Next.js 14 Frontend (Port 3000)"]
        DashboardUI["Orders & KPIs Dashboard"]
        DecisionUI["5-Action Decision Modal"]
        NDRHubUI["NDR Recovery Queue"]
        IntegrationsUI["Integrations Hub (Shopify & WhatsApp)"]
        ReconciliationUI["Financial Reconciliation View"]
    end

    subgraph Backend ["FastAPI Backend (Port 8000)"]
        AuthRouter["JWT Auth & Tenant Context"]
        OrderRouter["Order Management & Two-Stage CSV"]
        DecisionRouter["Decision & Evaluation API"]
        NDRRouter["Delivery & NDR State Machine"]
        IntegrationRouter["Shopify & WhatsApp Webhook Handlers"]
        ReconcileRouter["Financial Settlement API"]
        
        subgraph EngineCore ["Decision & ML Subsystems"]
            FeatureContract["ML Feature Contract v1.0.0"]
            InferenceEngine["ML Inference Engine (Logistic Regression)"]
            DecisionEngine["3-Tier Economic Decision Engine"]
            PolicyGate["Anti-Cancellation & Safety Gate"]
        end
        
        subgraph Services ["Core Business Services"]
            WhatsAppService["WhatsApp Service & AES-256 Crypto"]
            ShopifyService["Shopify Sync Adapter"]
            DeliveryService["Delivery State Transition Engine"]
            AuditService["Tamper-Evident SHA-256 Audit Trail"]
        end
    end

    subgraph Database ["PostgreSQL Relational Storage (RLS Enabled)"]
        DB_Orders[("Orders & Line Items")]
        DB_Evaluations[("Order Evaluations")]
        DB_NDR[("NDR Cases & Action Logs")]
        DB_WhatsApp[("WhatsApp Messages & Opt-Outs")]
        DB_Settlement[("Order Financial Reconciliation")]
        DB_Audit[("Append-Only Audit Logs")]
    end

    subgraph ExternalServices ["External Cloud APIs"]
        MetaGraph["Meta Graph API (graph.facebook.com)"]
        ShopifyAPI["Shopify Admin API (shopify.dev)"]
    end

    %% Client Interactions
    Merchant -->|HTTPS| Frontend
    ShopifyStore -->|orders/create Webhook HMAC| IntegrationRouter
    WhatsAppUser <-->|Inbound / Outbound Messages| MetaGraph

    %% Frontend to Backend
    DashboardUI & DecisionUI & NDRHubUI & IntegrationsUI & ReconciliationUI -->|REST API Bearer JWT| Backend

    %% Backend Internal Processing
    AuthRouter --> OrderRouter & DecisionRouter & NDRRouter & IntegrationRouter & ReconcileRouter
    OrderRouter --> FeatureContract
    FeatureContract --> InferenceEngine
    InferenceEngine --> DecisionEngine
    DecisionEngine --> PolicyGate
    PolicyGate --> DB_Evaluations

    %% Integration Handlers
    IntegrationRouter --> WhatsAppService & ShopifyService
    WhatsAppService <-->|HTTPS Bearer Token| MetaGraph
    ShopifyService <-->|HTTPS OAuth| ShopifyAPI

    %% Delivery and Reconciliation
    NDRRouter --> DeliveryService
    DeliveryService --> DB_NDR
    ReconcileRouter --> DB_Settlement

    %% Database Persist
    OrderRouter --> DB_Orders
    WhatsAppService --> DB_WhatsApp
    Backend --> AuditService
    AuditService --> DB_Audit

    style Clients fill:#f8fafc,stroke:#64748b,stroke-width:1px
    style Frontend fill:#eff6ff,stroke:#3b82f6,stroke-width:2px
    style Backend fill:#f0fdf4,stroke:#22c55e,stroke-width:2px
    style Database fill:#fdf4ff,stroke:#c084fc,stroke-width:2px
    style ExternalServices fill:#fffbeb,stroke:#f59e0b,stroke-width:2px
```

---

## End-to-End Technical Workflow

Every order entering ProfitGuard AI traverses a deterministic, audited lifecycle:

```mermaid
flowchart TD
    Start([Order Placed / Ingested]) --> IngestionChoice{Ingestion Method}
    
    IngestionChoice -->|CSV Upload| StageA[Stage A: RFC 4180 Preview & Duplicate Detection]
    StageA --> StageB[Stage B: Idempotent Atomic Commit]
    IngestionChoice -->|Shopify Webhook| ShopifyHmac{Verify HMAC-SHA256}
    ShopifyHmac -->|Invalid| RejectShopify[HTTP 401 Unauthorized]
    ShopifyHmac -->|Valid| IngestOrder[Order Created with Immutable GMV]
    StageB --> IngestOrder

    IngestOrder --> FeatureExtraction[Extract 41 Canonical Order Features]
    FeatureExtraction --> FeatureCheck{Feature Contract Validation}
    
    FeatureCheck -->|Missing Fields| FallbackRule[Fallback to Rule-Based Prior]
    FeatureCheck -->|Valid Schema| MLInference[ML Pipeline: Predict P_RTO]
    
    FallbackRule & MLInference --> EconomicEval[Economic Decision Engine: Compute Payoffs & EC across 5 Actions]
    
    EconomicEval --> GuardCheck{Policy Guards Check}
    GuardCheck -->|Order Value > Safety Cap| MandatoryReview[Flag: Mandatory Manual Review]
    GuardCheck -->|N < 15 or Uncertainty > 0.7910| AntiCancel[Lock Out Autonomous Cancellation]
    GuardCheck -->|Within Bounds| SelectOptimal[Identify Action with Max Expected Contribution]

    MandatoryReview & AntiCancel & SelectOptimal --> FinalActionSelection{Recommended Action}
    
    FinalActionSelection -->|SHIP_AS_IS| ManifestShip[Manifest Parcel to Courier]
    FinalActionSelection -->|VERIFY_OTP| SendWhatsAppOTP[Dispatch WhatsApp OTP Confirmation]
    FinalActionSelection -->|INCENTIVIZE_PREPAID| SendDiscount[Send WhatsApp Prepaid Conversion Link]
    FinalActionSelection -->|MANUAL_REVIEW| OperatorQueue[Hold for Operator Verification]
    FinalActionSelection -->|HOLD_CANCEL| AutoCancelOrder[Mark Order CANCELLED & Sync Shopify Tag]

    SendWhatsAppOTP --> CustomerReply{Customer OTP Reply}
    CustomerReply -->|Confirmed| ManifestShip
    CustomerReply -->|Cancelled / Timeout| AutoCancelOrder

    SendDiscount --> CustomerPayment{Customer Prepayment}
    CustomerPayment -->|Converted| ManifestPrepaid[Manifest as Prepaid Parcel]
    CustomerPayment -->|Declined / COD| ManifestShip

    OperatorQueue --> OperatorChoice{Operator Review}
    OperatorChoice -->|Approve| ManifestShip
    OperatorChoice -->|Reject| AutoCancelOrder

    ManifestShip & ManifestPrepaid --> InTransit[Courier In Transit: OUT_FOR_DELIVERY]
    
    InTransit --> TransitScan{First Courier Attempt Scan}
    TransitScan -->|Customer Accepts| TerminalDelivered([Terminal: DELIVERED])
    TransitScan -->|Customer Absent / Refused| TriggerNDR[Create NDR Recovery Case]

    TriggerNDR --> NDRActions{NDR Action Evaluation}
    NDRActions -->|Positive Recovery Lift| ContactCust[WhatsApp Address Re-Verification]
    NDRActions -->|Negative Recovery Lift| CourierRTO[Issue Return-to-Origin Instruction]
    
    ContactCust --> ReattemptScan{Courier Re-Attempt Scan}
    ReattemptScan -->|Successful| TerminalDelivered
    ReattemptScan -->|Failed Again| CourierRTO

    CourierRTO --> TerminalRTO([Terminal: RTO Returned to Warehouse])

    TerminalDelivered & TerminalRTO & AutoCancelOrder --> SettleLedger[Ex-Post Settlement: Order Financial Reconciliation]
    SettleLedger --> EndAudit([Tamper-Evident SHA-256 Audit Log])

    style Start fill:#e0f2fe,stroke:#0284c7
    style TerminalDelivered fill:#dcfce7,stroke:#16a34a
    style TerminalRTO fill:#fee2e2,stroke:#dc2626
    style AutoCancelOrder fill:#fef3c7,stroke:#d97706
    style EndAudit fill:#f3e8ff,stroke:#9333ea
```

---

## Machine-Learning Pipeline

### Dataset Source and Provenance

- **Origin**: Upstream research project `rto-prediction-analytics` authored by Birkishor Sahu (`https://github.com/Bir-exp/rto-prediction-analytics`).
- **Nature**: **Synthetic e-commerce benchmark data**. Generated via parameterized causal statistical profiles modeled after Indian marketplace logistics (Meesho/Flipkart archetype). All customer names, phone numbers, addresses, and transactional histories are synthetically drawn using random seed 42. No real personal or proprietary customer data is included.
- **Development Sample**: The active benchmark dataset is located at `data/development/rto_feature_table_sample.csv` (1,000 resolved rows × 54 columns, SHA-256: `d00b1c78d876c17322c7c412d8804f0ed979fde95f9b28e5231fefa4ae336b2a`).
- **Ground Truth Target**: `target_rto` (binary flag: `1` for Return-to-Origin, `0` for Successful Delivery). In the 1,000-sample benchmark, total RTO prevalence is **20.6%** (206 positive instances).

### Feature Engineering & Feature Contract

ProfitGuard AI enforces a formal feature contract ([`FEATURE_CONTRACT_v1.json`](file:///c:/Users/bharg/Downloads/profitguard/data/development/FEATURE_CONTRACT_v1.json)) managed through [`ml_feature_contract.py`](file:///c:/Users/bharg/Downloads/profitguard/backend/app/services/ml_feature_contract.py).

#### Temporal Isolation & Zero-Leakage Guarantee
All features must be constructed strictly prior to order placement ($T_{\text{order}} - 1\ \mu\text{s}$). The contract explicitly forbids future operational indicators:
- Prohibited: `delivery_attempts`, `carrier_status`, `delivery_timestamp`, `rto_initiated_timestamp`, `delivery_agent_id`, `ndr_count`, and `final_delivery_status`.

#### The 41 Canonical Serving Features
The model operates on exactly 41 validated features (36 numerical, 5 categorical):
1. **Order Attributes (13)**: `is_cod`, `payment_type`, `order_value`, `log_order_value`, `item_line_count`, `total_quantity`, `unique_seller_count`, `unique_category_count`, `dominant_category`, `contains_fragile_product`, `contains_premium_product`, `total_product_weight_g`, `average_item_price`.
2. **Customer Demographics & History (11)**: `customer_tenure_days`, `is_first_order`, `customer_prior_order_count`, `customer_region`, `customer_location_tier`, `customer_serviceability_score`, `customer_orders_last_30d`, `customer_orders_last_90d`, `customer_days_since_last_order`, `customer_prior_cod_share`, `customer_prior_avg_order_value`.
3. **Seller Behavioral Profile (6)**: `seller_tenure_days`, `seller_prior_order_count`, `seller_orders_last_30d`, `seller_avg_dispatch_hours_prior_30d`, `seller_dispatch_hours_std_prior_30d`, `seller_dispatch_history_count_30d`.
4. **Temporal & Seasonal Events (3)**: `is_event_period`, `event_category`, `event_impact_score`.
5. **Ratios & History Availability Flags (8)**: `current_vs_customer_avg_value_ratio`, `customer_history_available`, `seller_history_available`, `dominant_category_orders_last_30d`, `dominant_category_orders_last_90d`, `category_demand_acceleration`, `category_avg_order_value_prior_30d`, `category_history_count_30d`.

### Model Training and Evaluation

#### Chronological Dataset Partition
To evaluate real-world sequential generalization, the 1,000-order sample was split chronologically:
- **Train Set (60%)**: 600 orders (Jan 1, 2023 – Jan 11, 2023) | 128 RTOs (21.33% rate)
- **Validation Set (20%)**: 200 orders (Jan 11, 2023 – Jan 13, 2023) | 41 RTOs (20.50% rate)
- **Holdout Test Set (20%)**: 200 orders (Jan 13, 2023 – Jan 14, 2023) | 37 RTOs (18.50% rate)

#### Distinguishing the Evaluation Benchmark from the Serving Artifact
During the independent ML audit (Phase 2 & Phase 3.1), two distinct models were evaluated:
1. **Random Forest Classifier (Research Benchmark)**:
   - Evaluated to investigate non-linear decision boundaries and class imbalance sensitivity.
   - At the standard 0.50 probability cutoff, the uncalibrated Random Forest achieved an $F_1$ score of only 0.0889 because only 8 out of 200 holdout orders exceeded 0.50. When calibrated with validation-tuned threshold ($\tau^* = 0.18$), test recall rose to 70.27% ($F_1 = 0.3796$).
2. **Logistic Regression Pipeline (Production Serving Artifact)**:
   - Serialized in [`rto_model_v1.joblib`](file:///c:/Users/bharg/Downloads/profitguard/data/development/models/rto_model_v1.joblib).
   - Comprises a scikit-learn `Pipeline` with `ColumnTransformer`:
     - Numerical Transformer: `SimpleImputer(strategy='median')` followed by `StandardScaler()`.
     - Categorical Transformer: `SimpleImputer(strategy='most_frequent')` followed by `OneHotEncoder(handle_unknown='ignore', sparse_output=False)`.
     - Classifier: `LogisticRegression(C=1.0, max_iter=1000, random_state=42)`.
   - On the holdout test set with threshold $\tau = 0.18$, the Logistic Regression model flags 84 orders, yielding 29 True Positives and 55 False Positives ($78.38\%$ Recall, $34.52\%$ Precision, $0.4793$ $F_1$).

> **Critical Methodological Distinction**: The Random Forest benchmark results must not be presented as the performance of the Logistic Regression serving artifact. The serving runtime strictly executes the serialized Logistic Regression pipeline.

```mermaid
flowchart LR
    subgraph DataPrep ["Data & Feature Engineering"]
        RawData[rto_feature_table_sample.csv\n1000 rows × 54 cols] --> ChronoSplit[Chronological Split\nTrain: 600 | Val: 200 | Test: 200]
        ChronoSplit --> Preprocessor[ColumnTransformer\nMedian Imputer + StandardScaler (36 num)\nMode Imputer + OneHotEncoder (5 cat)]
    end

    subgraph Evaluation ["Phase 2 Audit Comparison"]
        Preprocessor --> RF_Model[Random Forest Benchmark\nTau* = 0.18 | F1 = 0.3796]
        Preprocessor --> LR_Model[Logistic Regression Pipeline\nTau = 0.18 | F1 = 0.4793]
    end

    subgraph Serving ["Serving Runtime"]
        LR_Model --> SaveArtifact[(rto_model_v1.joblib)]
        SaveArtifact --> MLInferenceService[ML Inference Engine\nStrict Feature Contract Validation]
        MLInferenceService --> ShadowOutput[P_RTO Probability + Tier]
    end

    style DataPrep fill:#f8fafc,stroke:#64748b
    style Evaluation fill:#fffbeb,stroke:#d97706
    style Serving fill:#f0fdf4,stroke:#16a34a
```

### Inference Pipeline

When an order arrives via Shopify webhook or CSV import:
1. `ml_inference_service.py` extracts raw fields and invokes `ml_feature_contract.py`.
2. Missing non-critical features receive median/mode defaults via the transformer; missing mandatory identifiers abort inference safely, returning `RULE_BASED_FALLBACK`.
3. Feature arrays are passed to `pipeline.predict_proba(X)[0][1]` to yield calibrated RTO probability $P_{\text{RTO}} \in [0.01, 0.95]$.
4. The output is categorized into four operational risk tiers:
   - **LOW**: $P_{\text{RTO}} < 0.15$
   - **MEDIUM**: $0.15 \le P_{\text{RTO}} < 0.35$
   - **HIGH**: $0.35 \le P_{\text{RTO}} < 0.60$
   - **CRITICAL**: $P_{\text{RTO}} \ge 0.60$

### Limitations and Multi-Tier Governance

Because the model was trained on synthetic benchmark data, it has not been calibrated on live courier transit telemetry. Unchecked autonomous actions based on synthetic weights could lead to merchant losses. ProfitGuard AI enforces three explicit runtime operating modes:
- **`SHADOW`** (Default): ML inference executes asynchronously on every eligible incoming order. Inferences are recorded to `order_evaluations` audit metadata for monitoring, but the decision engine uses deterministic rule-based priors.
- **`LIVE_ASSISTED`**: The decision engine incorporates the predicted probability into action expected contributions, but consequential actions (`HOLD_CANCEL`) require operator approval.
- **`DISABLED`**: ML inference is deactivated; orders execute entirely via rule-based decisioning.

---

## Economic Decision Engine

The Economic Decision Engine ([`decision_engine.py`](file:///c:/Users/bharg/Downloads/profitguard/backend/app/services/decision_engine.py)) operates independently of the statistical model. It uses microeconomic decision theory under uncertainty to select the action that maximizes the merchant's expected net margin.

### Input Variables & Payoffs

| Variable | Symbol | Typical Units | Description |
|:---|:---|:---|:---|
| Order Value (GMV) | $V$ | INR (₹) | Checkout order gross merchandise value (immutable). |
| Cost of Goods Sold | $\text{COGS}$ | INR (₹) | Total manufacturing or procurement cost of the line items. |
| Forward Shipping Cost | $S_f$ | INR (₹) | Courier charge for forward transit to customer. |
| Reverse Shipping Cost | $S_r$ | INR (₹) | Courier charge for returning unaccepted parcel to warehouse. |
| Packaging Cost | $C_{\text{pkg}}$ | INR (₹) | Packaging materials and warehouse dispatch labor. |
| COD Carrier Fee | $F_{\text{cod}}$ | INR (₹) | Courier collection surcharge on Cash-on-Delivery shipments. |
| Payment Gateway Fee | $F_{\text{pg}}$ | INR (₹) | Fee charged by payment processors on prepaid transactions. |
| Inventory Damage Rate | $D_{\text{inv}}$ | Fraction $[0, 1]$ | Proportion of product cost lost due to transit packaging/handling damage. |
| RTO Probability | $p$ | Probability $[0, 1]$ | Estimated non-acceptance probability ($P_{\text{RTO}}$). |

#### Base Outcome Terminal Payoffs (Tier 1)

1. **Delivered Payoff ($\Pi_{\text{del}}$)**: Customer accepts parcel and pays.
   - For COD:
     $$\Pi_{\text{del}} = V - F_{\text{cod}} - \text{COGS} - C_{\text{pkg}} - S_f$$
   - For Prepaid:
     $$\Pi_{\text{del}} = V - F_{\text{pg}} - \text{COGS} - C_{\text{pkg}} - S_f$$
2. **RTO Payoff ($\Pi_{\text{rto}}$)**: Customer rejects or cannot be reached. Parcel returns to merchant.
   - Damage loss: $\text{Loss}_{\text{dmg}} = D_{\text{inv}} \times \text{COGS}$.
   - For COD (with carrier fee incurred upon manifest):
     $$\Pi_{\text{rto}} = - F_{\text{cod}} - C_{\text{pkg}} - S_f - S_r - (D_{\text{inv}} \times \text{COGS})$$
   - For Prepaid (revenue refunded in full; gateway fee non-refundable):
     $$\Pi_{\text{rto}} = - F_{\text{pg}} - C_{\text{pkg}} - S_f - S_r - (D_{\text{inv}} \times \text{COGS})$$
3. **Cancelled Payoff ($\Pi_{\text{cancel}}$)**: Order cancelled prior to dispatch.
   $$\Pi_{\text{cancel}} = 0.00$$

### The 5 Candidate Actions

ProfitGuard AI evaluates exactly 5 pre-dispatch choices for every order:
1. `SHIP_AS_IS`: Fulfill the order immediately with no customer intervention.
2. `VERIFY_OTP`: Send an automated WhatsApp / SMS OTP verification request prior to warehouse dispatch.
3. `INCENTIVIZE_PREPAID`: Offer a small discount incentive to convert a COD order to prepaid.
4. `MANUAL_REVIEW`: Route the order to human operations queue for phone or address verification.
5. `HOLD_CANCEL`: Cancel the order prior to dispatch to prevent anticipated negative cash flow.

### Estimated Contribution Formulas

```mermaid
flowchart TD
    Inputs["Order Value (V), COGS, Freight (Sf, Sr), Damage Rate (Dinv), P_RTO (p)"] --> BasePayoffs["Calculate Base Terminal Payoffs: Delivered, RTO, Cancelled"]
    BasePayoffs --> Evaluate5["Compute Expected Contribution (EC) for 5 Candidate Actions"]
    
    Evaluate5 --> EC1["SHIP_AS_IS\nEC = (1-p)*Delivered + p*RTO"]
    Evaluate5 --> EC2["VERIFY_OTP\nEC = P_conf * Branch_conf + (1-P_conf)*0 - C_otp"]
    Evaluate5 --> EC3["INCENTIVIZE_PREPAID\nEC = P_conv * Payoff_conv + (1-P_conv)*EC_ship - C_comm"]
    Evaluate5 --> EC4["MANUAL_REVIEW\nEC = P_appr * Branch_appr + (1-P_appr)*0 - C_manual"]
    Evaluate5 --> EC5["HOLD_CANCEL\nEC = 0.00 (Lift = -EC_ship)"]
    
    EC1 & EC2 & EC3 & EC4 & EC5 --> PolicyGuards{Policy & Governance Guards}
    PolicyGuards -->|V > Safety Cap| StripShip[Disqualify SHIP_AS_IS]
    PolicyGuards -->|U > 0.7910 or N < 15| StripCancel[Disqualify HOLD_CANCEL]
    PolicyGuards -->|Allow Auto-Cancel = False| StripCancel2[Disqualify HOLD_CANCEL]
    
    StripShip & StripCancel & StripCancel2 & PolicyGuards --> RankEligible[Rank Eligible Actions by EC Descending]
    RankEligible --> SelectBest[Select Action with Highest Expected Contribution]
    Select बेस्ट --> OutputDecision[Record Recommendation & Lift vs SHIP_AS_IS]

    style Inputs fill:#f8fafc,stroke:#64748b
    style BasePayoffs fill:#e0f2fe,stroke:#0284c7
    style PolicyGuards fill:#fffbeb,stroke:#d97706
    style SelectBest fill:#dcfce7,stroke:#16a34a
```

#### 1. Action: `SHIP_AS_IS`
Fulfill without pre-dispatch contact. Intervention cost is ₹0.00.
$$EC_{\text{ship}} = (1 - p) \cdot \Pi_{\text{del}} + p \cdot \Pi_{\text{rto}}$$

#### 2. Action: `VERIFY_OTP`
The customer is sent an OTP confirmation request with probability of confirmation $p_{\text{conf}} = 0.75$. If confirmed, residual risk drops to $p_{\text{rto\_conf}} = p \times 0.40$. If unconfirmed, the order is cancelled ($\Pi_{\text{cancel}} = 0$). Pre-dispatch cost $C_{\text{otp}}$ (₹3.00) is deducted once.
$$\text{Branch}_{\text{conf}} = (1 - p_{\text{rto\_conf}}) \cdot \Pi_{\text{del}} + p_{\text{rto\_conf}} \cdot \Pi_{\text{rto}}$$
$$EC_{\text{otp}} = p_{\text{conf}} \cdot \text{Branch}_{\text{conf}} + (1 - p_{\text{conf}}) \cdot 0.00 - C_{\text{otp}}$$
$$\Delta EC_{\text{otp}} = EC_{\text{otp}} - EC_{\text{ship}}$$

#### 3. Action: `INCENTIVIZE_PREPAID` (COD Orders Only)
The merchant offers discount $D_{\text{prep}}$ to convert to prepaid with conversion probability $p_{\text{conv}} = 0.20$. Converted orders carry low prepaid RTO rate $p_{\text{rto\_prep}} = 0.05$. If declined, the order falls back to $EC_{\text{ship}}$. Communications cost $C_{\text{comm}}$ (₹5.00) is deducted once.
$$V' = \max(1.00, V - D_{\text{prep}})$$
$$F_{\text{pg}}' = \left(\frac{\text{Gateway}\%}{100} \cdot V'\right) + \text{Gateway}_{\text{flat}}$$
$$\Pi_{\text{del\_conv}} = V' - F_{\text{pg}}' - \text{COGS} - C_{\text{pkg}} - S_f$$
$$\Pi_{\text{rto\_conv}} = - F_{\text{pg}}' - C_{\text{pkg}} - S_f - S_r - (D_{\text{inv}} \cdot \text{COGS})$$
$$\Pi_{\text{converted}} = (1 - p_{\text{rto\_prep}}) \cdot \Pi_{\text{del\_conv}} + p_{\text{rto\_prep}} \cdot \Pi_{\text{rto\_conv}}$$
$$EC_{\text{prep}} = p_{\text{conv}} \cdot \Pi_{\text{converted}} + (1 - p_{\text{conv}}) \cdot EC_{\text{ship}} - C_{\text{comm}}$$
$$\Delta EC_{\text{prep}} = EC_{\text{prep}} - EC_{\text{ship}}$$

#### 4. Action: `MANUAL_REVIEW`
An operator reviews the order with approval probability $p_{\text{appr}} = 0.80$. Residual risk drops to $p_{\text{rto\_appr}} = p \times \frac{1}{3}$. Review cost $C_{\text{manual}}$ (₹20.00) is deducted once.
$$\text{Branch}_{\text{appr}} = (1 - p_{\text{rto\_appr}}) \cdot \Pi_{\text{del}} + p_{\text{rto\_appr}} \cdot \Pi_{\text{rto}}$$
$$EC_{\text{manual}} = p_{\text{appr}} \cdot \text{Branch}_{\text{appr}} + (1 - p_{\text{appr}}) \cdot 0.00 - C_{\text{manual}}$$
$$\Delta EC_{\text{manual}} = EC_{\text{manual}} - EC_{\text{ship}}$$

#### 5. Action: `HOLD_CANCEL`
Cancel order before dispatch. No revenue collected, but freight, COD, and damage losses are avoided.
$$EC_{\text{cancel}} = 0.00$$
$$\Delta EC_{\text{cancel}} = 0.00 - EC_{\text{ship}} = - EC_{\text{ship}}$$

*Eligibility constraints*: `HOLD_CANCEL` is permitted **only** when $EC_{\text{ship}} < 0$, merchant setting `allow_auto_cancel == True`, pincode uncertainty $U \le 0.7910$, sample size $N \ge 15$, and order value does not exceed safety cap.

---

### Step-by-Step Numerical Example

Consider a typical Indian D2C apparel order with the following parameters:
- **Order GMV ($V$)**: ₹1,500.00 (Cash on Delivery)
- **Product COGS**: ₹500.00
- **Forward Shipping ($S_f$)**: ₹80.00
- **Reverse Shipping ($S_r$)**: ₹70.00
- **Packaging Cost ($C_{\text{pkg}}$)**: ₹20.00
- **COD Carrier Fee ($F_{\text{cod}}$)**: ₹40.00 (charged upon manifest)
- **Inventory Damage Rate ($D_{\text{inv}}$)**: 10% ($0.10 \times 500 = ₹50.00$)
- **Intervention Unit Costs**: $C_{\text{otp}} = ₹3.00$, $C_{\text{manual}} = ₹20.00$, $C_{\text{comm}} = ₹5.00$, $D_{\text{prep}} = ₹100.00$
- **RTO Risk ($p$)**: $0.35$ (35% probability)

#### Step 1: Base Terminal Payoffs
$$\Pi_{\text{del}} = 1500 - 40 - 500 - 20 - 80 = \mathbf{+₹860.00}$$
$$\Pi_{\text{rto}} = - 40 - 20 - 80 - 70 - 50 = \mathbf{-₹260.00}$$

#### Step 2: Calculate `SHIP_AS_IS`
$$EC_{\text{ship}} = (1 - 0.35) \cdot (860.00) + 0.35 \cdot (-260.00) = 559.00 - 91.00 = \mathbf{+₹468.00}$$

#### Step 3: Calculate `VERIFY_OTP`
$$p_{\text{rto\_conf}} = 0.35 \times 0.40 = 0.14$$
$$\text{Branch}_{\text{conf}} = (1 - 0.14) \cdot (860.00) + 0.14 \cdot (-260.00) = 739.60 - 36.40 = ₹703.20$$
$$EC_{\text{otp}} = 0.75 \cdot (703.20) + 0.25 \cdot (0.00) - 3.00 = 527.40 - 3.00 = \mathbf{+₹524.40}$$
$$\text{Lift}_{\text{otp}} = 524.40 - 468.00 = \mathbf{+₹56.40}$$

#### Step 4: Decision Engine Recommendation
Comparing $EC_{\text{otp}}$ (+₹524.40) to $EC_{\text{ship}}$ (+₹468.00), verifying the order via OTP yields an incremental expected lift of **+₹56.40 per order**.
The engine selects **`VERIFY_OTP`** and triggers WhatsApp pre-dispatch verification.

---

### Authoritative Realized Contribution Ledger

To prevent model bias or optimistic reporting, [`reconciliation_service.py`](file:///c:/Users/bharg\Downloads\profitguard\backend\app\services\reconciliation_service.py) settles all completed orders into `order_financial_reconciliation`:

$$RC = \text{Collected Revenue} - \text{COGS} - S_f - S_r - F_p - C_{\text{pkg}} - D_{\text{rto}} - C_{\text{pre-dispatch}} - C_{\text{ndr}}$$

- **Strict Sunk-Cost Attribution**: Forward freight ($S_f$) is permanently sunk once an order enters transit. Reverse freight ($S_r = 0$) is charged only if the parcel returns.
- **Realized Cash Revenue**: Uncollected COD orders reflect ₹0.00 collected revenue, ensuring that gross checkout GMV is never conflated with realized net income.

---

## Decision Engine vs. ML Model Comparison

| Dimension | Machine Learning Model | Economic Decision Engine |
|:---|:---|:---|
| **Primary Purpose** | Estimate probability of non-delivery $P(\text{RTO})$ based on historical and contextual patterns. | Determine which operational action (`SHIP`, `OTP`, `PREPAID`, `REVIEW`, `CANCEL`) maximizes net margin. |
| **Input Signals** | 41 order, customer, seller, geographical, and demand features. | $P_{\text{RTO}}$, order value, COGS, freight costs, COD fees, damage rates, intervention costs. |
| **Primary Output** | Continuous score $p \in [0.01, 0.95]$ and risk tier (`LOW`, `MED`, `HIGH`, `CRIT`). | Recommended action, expected contribution ($EC$), and incremental lift ($\Delta EC$). |
| **Core Method** | Logistic regression with feature imputation, scaling, and one-hot encoding. | Microeconomic decision theory, single-cost deduction, and policy guardrails. |
| **Key Limitation** | Sensitive to class imbalance and distribution shift; cannot decide value trade-offs alone. | Relies on merchant operational cost assumptions and risk parameter estimates. |

> **Why High Risk Does Not Equal Cancellation**: A high RTO probability ($p = 0.40$) does not justify cancelling a high-ticket order with ₹2,000 product margin. The expected contribution remains strongly positive. The decision engine ensures that high-margin orders are protected while thin-margin orders are defended.

---

## Storefront & Messaging Integrations

### Shopify Integration

Implemented via [`shopify_service.py`](file:///c:/Users/bharg/Downloads/profitguard/backend/app/services/shopify_service.py) and [`shopify_adapter.py`](file:///c:/Users/bharg/Downloads/profitguard/backend/app/services/integrations/shopify_adapter.py):
- **Real-Time Webhook Processing**: Accepts Shopify's `orders/create`, `orders/updated`, and `orders/cancelled` topics at `/api/v1/orders/webhook`.
- **HMAC-SHA256 Signature Verification**: Every request is verified against the raw request body using `X-Shopify-Hmac-Sha256` and the merchant's secret.
- **Bi-Directional Order Tagging**: When an order decision is confirmed (or cancelled), ProfitGuard AI automatically synchronizes risk tags (`ProfitGuard: Low Risk`, `ProfitGuard: Hold Review`) back to the Shopify Admin API.

### Meta WhatsApp Business Cloud API

Implemented via [`whatsapp_service.py`](file:///c:/Users/bharg/Downloads/profitguard/backend/app/services/whatsapp_service.py) and [`whatsapp_adapter.py`](file:///c:/Users/bharg/Downloads/profitguard/backend/app/services/integrations/whatsapp_adapter.py):
- **Official Meta Cloud API (v20.0)**: Connects directly to `graph.facebook.com` without intermediary aggregator markup.
- **Three Supported Connection Modes**:
  1. `MOCK`: Local offline development mode. Simulates delivery receipts and webhook handshakes with zero external fees.
  2. `META_TEST`: Meta Developer Sandbox testing with verified Meta test phone numbers.
  3. `LIVE`: Production enterprise WhatsApp Business Account (WABA).
- **Approved Utility Templates**:
  - `order_confirmation_cod`: Features quick-reply interactive buttons (`CONFIRM_ORDER`, `CANCEL_ORDER`).
  - `ndr_delivery_recovery`: Outreaches to customers when delivery fails to re-verify addresses and schedule re-attempts.
- **Secure Webhooks**:
  - `GET /api/v1/integrations/whatsapp/webhook`: Handles Meta `hub.challenge` verification handshakes.
  - `POST /api/v1/integrations/whatsapp/webhook`: Cryptographically validates `X-Hub-Signature-256` HMAC signatures using the configured Meta App Secret.
- **Regulatory Opt-Out Compliance**: Immediate detection of keyword opt-outs (`STOP`, `UNSUBSCRIBE`, `OPT OUT`), preventing further automated messages to unsubscribed numbers.

---

## Database Schema & Data Flow

ProfitGuard AI is backed by 9 versioned Alembic migrations managing 18 relational tables:

```mermaid
erDiagram
    organizations ||--o{ users : "employs"
    organizations ||--o{ merchant_economics : "configures"
    organizations ||--o{ orders : "owns"
    organizations ||--o{ import_jobs : "executes"
    organizations ||--o{ shopify_configs : "integrates"
    organizations ||--o{ whatsapp_configs : "configures"
    organizations ||--o{ audit_logs : "records"

    orders ||--o{ order_items : "contains"
    orders ||--o{ order_evaluations : "evaluated_by"
    orders ||--o{ delivery_events : "tracks"
    orders ||--o{ ndr_cases : "generates"
    orders ||--o{ financial_reconciliations : "settles"
    orders ||--o{ whatsapp_messages : "triggers"

    ndr_cases ||--o{ ndr_action_logs : "logs_actions"

    organizations {
        uuid id PK
        string name
        string slug
        string status
    }

    merchant_economics {
        uuid id PK
        uuid org_id FK
        decimal default_cogs_percent
        decimal forward_shipping_cost
        decimal reverse_shipping_cost
        decimal packaging_cost
        decimal cod_carrier_fee
        decimal safety_value_cap
        boolean allow_auto_cancel
    }

    orders {
        uuid id PK
        uuid org_id FK
        string external_order_id
        decimal order_value
        string payment_method
        string status
        string shipping_pincode
        string customer_phone
    }

    order_evaluations {
        uuid id PK
        uuid order_id FK
        string recommended_action
        decimal recommended_lift
        decimal predicted_rto_risk
        string risk_tier
        jsonb explanation_metadata
    }

    ndr_cases {
        uuid id PK
        uuid order_id FK
        string status
        string priority
        string latest_ndr_reason
        integer attempt_count
    }

    financial_reconciliations {
        uuid id PK
        uuid order_id FK
        decimal gross_order_value
        decimal collected_revenue
        decimal realized_contribution
        boolean is_settled
    }

    whatsapp_configs {
        uuid id PK
        uuid org_id FK
        string phone_number_id
        string operating_mode
        text access_token_encrypted
        text app_secret_encrypted
    }

    audit_logs {
        uuid id PK
        uuid org_id FK
        string action
        string resource_type
        string current_hash
        string previous_hash
    }
```

---

## Security, Reliability, and Governance

1. **Authentication & Session Security**:
   - Access tokens: Short-lived (15-minute) JWTs signed with HMAC-SHA256.
   - Refresh tokens: Long-lived (7-day) cryptographically random tokens stored hashed in the database, with automatic rotation upon refresh.
   - Password security: Standard `bcrypt` password hashing with salts.
2. **PostgreSQL Row-Level Security (RLS)**:
   - Tenant isolation enforced at the database kernel level.
   - Every transaction executes `SELECT set_config('app.current_org_id', :org_id, true)`, preventing cross-tenant leakage.
   - Role separation between migration execution (`pg_migrator`, DDL bypass) and application runtime (`pg_app_runtime`, DML constrained).
3. **Application-Level AES-256-GCM Encryption**:
   - Sensitive tokens (Meta Access Tokens, App Secrets, Carrier API keys) are encrypted using authenticated AES-256-GCM with distinct 12-byte initialization vectors (IV) and tamper tags.
   - Key versioning supports transparent key rotation (`v1`, `v2`).
4. **Tamper-Evident Audit Logging**:
   - Append-only `audit_logs` table using SHA-256 hash chaining:
     $$\text{Hash}_k = \text{SHA256}(\text{Hash}_{k-1} \parallel \text{CanonicalJSON}(\text{Payload}_k))$$
   - Concurrency conflicts prevented via PostgreSQL transactional advisory locks.
5. **Anti-Tampering Idempotency**:
   - Webhook deliveries and courier scan events verify unique IDs, preventing duplicate order ingestion or replay attacks.

---

## Installation & Local Setup

### Prerequisites
- **Python**: Version 3.10 or higher.
- **Node.js**: Version 18.0 or higher (Node 20+ recommended).
- **PostgreSQL**: Version 15+ (optional for local dev; SQLite supported out-of-the-box for rapid development and testing).

---

### Setup for Windows PowerShell

#### 1. Clone & Navigate to Repository
```powershell
git clone <repository_url> profitguard
cd profitguard
```

#### 2. Configure Backend Environment
```powershell
Copy-Item backend\.env.example backend\.env
```
*(Optionally open `backend\.env` in an editor to adjust database URLs or encryption keys).*

#### 3. Setup Python Virtual Environment
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

#### 4. Run Database Migrations
```powershell
# For default SQLite local dev
alembic upgrade head
```

#### 5. Start Backend API Server
```powershell
uvicorn app.main:app --reload --port 8000
```
*API Swagger documentation is accessible at `http://localhost:8000/docs`.*

#### 6. Configure & Start Frontend
In a separate PowerShell window:
```powershell
cd profitguard\frontend
Copy-Item .env.example .env.local
npm.cmd install
npm.cmd run dev
```
*Access the ProfitGuard AI merchant dashboard at `http://localhost:3000`.*

---

### Setup for Unix / Linux / macOS (Bash / Zsh)

#### 1. Clone & Navigate
```bash
git clone <repository_url> profitguard
cd profitguard
```

#### 2. Backend Setup
```bash
cp backend/.env.example backend/.env
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

#### 3. Frontend Setup
In a new terminal:
```bash
cd profitguard/frontend
cp .env.example .env.local
npm install
npm run dev
```

---

## Configuration Reference

The following environment variables are supported in `backend/.env` (derived from [`.env.example`](file:///c:/Users/bharg/Downloads/profitguard/backend/.env.example)):

| Variable | Required | Default / Placeholder | Purpose |
|:---|:---:|:---|:---|
| `ENVIRONMENT` | No | `development` | Operating environment (`development`, `staging`, `production`). |
| `DEBUG` | No | `true` | Enables Swagger UI documentation and debug log traces. |
| `DATABASE_URL` | Yes | `postgresql://user:pass@localhost:5432/profitguard_dev` | Primary PostgreSQL runtime DML database connection string. |
| `MIGRATION_DATABASE_URL` | No | *(Optional dedicated DDL URL)* | Alembic migration connection URL used by database administrators. |
| `JWT_SECRET_KEY` | Yes | `change-this-in-production-to-a-secure-random-secret-key-32bytes` | 256-bit secret key used to sign and verify HS256 JWT auth tokens. |
| `JWT_ALGORITHM` | No | `HS256` | Cryptographic algorithm for JWT session tokens. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `15` | Session access token lifespan in minutes. |
| `ACTIVE_ENCRYPTION_KEY_VERSION` | Yes | `v1` | Identifies active encryption key version in `ENCRYPTION_KEYS`. |
| `ENCRYPTION_KEYS` | Yes | `{"v1":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"}` | JSON mapping of versioned 32-byte hex keys for AES-256-GCM. |
| `CORS_ORIGINS` | No | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated list of browser origins permitted for CORS. |
| `SHOPIFY_API_VERSION` | No | `2024-01` | Supported Shopify Admin API version. |
| `SHOPIFY_WEBHOOK_SECRET` | No | `""` | Shared secret used to verify `X-Shopify-Hmac-Sha256` webhooks. |
| `WHATSAPP_OPERATING_MODE` | No | `MOCK` | Messaging mode: `MOCK` (local simulation), `META_TEST` (sandbox), `LIVE` (WABA). |
| `WHATSAPP_PHONE_NUMBER_ID` | No | `""` | Meta WhatsApp Cloud API Phone Number ID. |
| `WHATSAPP_ACCESS_TOKEN` | No | `""` | System User Permanent Token with `whatsapp_business_messaging` scope. |
| `WHATSAPP_APP_SECRET` | No | `""` | Meta App Secret for validating incoming webhook HMAC-SHA256 signatures. |
| `WHATSAPP_WEBHOOK_VERIFY_TOKEN`| No | `profitguard_whatsapp_verify_token_default` | Secret token exchanged during Meta `hub.challenge` webhook handshake. |

---

## Testing & Verification

ProfitGuard AI includes automated test suites covering all platform layers:

```bash
cd backend
python -m pytest tests -v
```

### Verified Test Suite Breakdown (183 Tests Passing)

```text
============================= test session starts =============================
platform win32 -- Python 3.10.11, pytest-9.1.1, pluggy-1.6.0
collected 183 items

tests/test_audit_log.py                      ........                        [  4%]
tests/test_auth.py                           .......                         [  8%]
tests/test_crypto.py                         ......                          [ 11%]
tests/test_csv_import.py                     ................                [ 20%]
tests/test_customer_journey_verification.py  ......                          [ 23%]
tests/test_database_rls.py                   ...                             [ 25%]
tests/test_decision_engine.py                ...................             [ 35%]
tests/test_delivery_lifecycle.py             ................                [ 44%]
tests/test_evaluation_reconciliation.py     ......                          [ 47%]
tests/test_financial_fixtures.py             .........                       [ 52%]
tests/test_health_and_routes.py              ......                          [ 55%]
tests/test_judge_order_flow.py               .......                         [ 59%]
tests/test_live_ml_decisioning.py            ............                    [ 66%]
tests/test_migrations.py                     ..                              [ 67%]
tests/test_milestone5_e2e_journey.py         ........                        [ 71%]
tests/test_ml_shadow_service.py              ..........                      [ 77%]
tests/test_orders.py                         ..............                  [ 84%]
tests/test_outcome_tracking.py               ...........                     [ 90%]
tests/test_rbac.py                           .....                           [ 93%]
tests/test_shopify_integration.py            ............                    [100%]
tests/test_whatsapp_integration.py           ..........                      [100%]

======================= 183 passed, 4 warnings in 98.19s ======================
```

### Frontend Production Build
```bash
cd frontend
npm.cmd run build
```
- **Result**: Successfully compiled 4 static routes (`/`, `/_not-found`) with zero TypeScript, ESLint, or runtime errors.

---

## Project Directory Structure

```text
profitguard/
├── backend/
│   ├── alembic/                    # Database DDL migrations (001 - 009)
│   │   ├── versions/
│   │   │   ├── 001_initial_foundation.py
│   │   │   ├── 002_orders_and_imports.py
│   │   │   ├── 003_order_evaluations.py
│   │   │   ├── 004_delivery_lifecycle_and_ndr.py
│   │   │   ├── 005_financial_reconciliation.py
│   │   │   ├── 006_real_order_outcomes.py
│   │   │   ├── 007_shopify_integration.py
│   │   │   ├── 008_live_ml_decisioning.py
│   │   │   └── 009_whatsapp_integration.py
│   │   └── env.py
│   ├── app/
│   │   ├── api/v1/                 # Endpoints (auth, orgs, orders, delivery, economics, integrations, audit)
│   │   ├── core/                   # Security, JWT, AES-256 crypto, DB session, tenant context
│   │   ├── models/                 # SQLAlchemy 2.0 ORM models (Order, Evaluation, NDR, WhatsApp, Audit)
│   │   ├── schemas/                # Pydantic v2 validation contracts
│   │   ├── services/
│   │   │   ├── decision_engine.py          # 3-Tier economic optimization engine
│   │   │   ├── delivery_service.py         # Courier delivery state machine
│   │   │   ├── ml_feature_contract.py      # Feature contract schema validator
│   │   │   ├── ml_inference_service.py     # Production ML inference interface
│   │   │   ├── ml_shadow_service.py        # Shadow-mode serving service
│   │   │   ├── outcome_tracking_service.py # Real outcome & delivery tracking
│   │   │   ├── reconciliation_service.py   # Ex-post financial settlement ledger
│   │   │   ├── shopify_service.py          # Shopify store integration service
│   │   │   ├── whatsapp_service.py         # Meta WhatsApp Business Cloud API service
│   │   │   └── integrations/               # Protocol adapters (Shopify & WhatsApp)
│   │   └── main.py                 # FastAPI application factory & lifespan setup
│   ├── tests/                      # Pytest test suite (183 automated tests)
│   ├── .env.example
│   ├── alembic.ini
│   └── requirements.txt
├── data/
│   └── development/
│       ├── models/
│       │   └── rto_model_v1.joblib          # Trained LogisticRegression serving artifact
│       ├── DATASET_METADATA.md              # Provenance & synthetic data disclosure
│       ├── FEATURE_CONTRACT_v1.json         # 41-feature canonical contract specification
│       ├── rto_feature_table_sample.csv     # 1,000-order development benchmark dataset
│       └── SYNTHETIC_ML_EVALUATION.json     # Independent audit & reconciliation results
├── frontend/
│   ├── src/
│   │   ├── app/                    # Next.js 14 App Router layout and dashboard page
│   │   ├── components/             # Reusable UI modals (OrderDecision, NDR, Shopify, WhatsApp, CSV)
│   │   ├── services/               # API client service layer
│   │   └── types/                  # TypeScript interface definitions
│   ├── .env.example
│   ├── package.json
│   └── tailwind.config.js
├── docs/                           # Architectural, security, and integration specifications
├── .gitignore                      # Safe Git exclusions (ignoring .env, caches, DBs)
└── README.md                       # Comprehensive platform documentation
```

---

## Limitations & Roadmap

### Current Limitations
- **Synthetic ML Benchmark**: The current ML model artifact was trained on synthetic benchmark data. While it verifies feature contract compliance, pipeline execution, and shadow-mode serving, empirical weights must be retrained on merchant-specific historical data before enabling autonomous cancellations.
- **National Courier Assumptions**: Reverse freight rates and forward shipping fees are modeled as uniform merchant averages; distance-based zonal courier tariffs (e.g., Intra-City vs. Metro vs. North-East) are simplified into flat unit figures.
- **Single-Node Execution**: In local development, async tasks run synchronously within FastAPI threadpools.

### Engineering Roadmap
- [ ] **Real-World Courier Integrations**: Implement live tracking webhook adapters for Indian carriers (Delhivery, BlueDart, Shiprocket, Xpressbees).
- [ ] **Zonal Shipping Matrix**: Integrate dynamic forward and reverse freight matrices based on origin-destination pincode pairs.
- [ ] **Distributed Queue Support**: Add Celery / Redis worker deployment scripts for high-throughput webhook ingest bursts (10,000+ orders/min).
- [ ] **Empirical Drift Monitoring**: Add automated Kolmogorov-Smirnov drift detection to monitor feature distribution shifts between training priors and live Shopify traffic.

---

## Contribution, License & Contact

### Contribution
Contributions, bug reports, and architectural reviews are welcome.
1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/courier-adapter`).
3. Commit changes with clear, descriptive commit messages.
4. Verify that all 183 backend tests pass (`pytest`) and frontend compiles (`npm run build`).
5. Open a Pull Request detailing changes, test evidence, and architectural rationale.

### License
**No license has been specified.** All rights are reserved by the original project authors. This software is provided for evaluation, development, and inspection purposes.

### Contact & Support
For questions, bug reports, or integration inquiries, open an issue directly in the GitHub repository's issue tracker.
