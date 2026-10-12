# Dataset Metadata & Provenance: RTO Prediction Analytics (Development)

## 1. Provenance Information
- **Source Repository URL:** [https://github.com/Bir-exp/rto-prediction-analytics](https://github.com/Bir-exp/rto-prediction-analytics)
- **Repository Author:** Birkishor Sahu (`veerexp23@gmail.com`)
- **Retrieval Date:** 2026-10-12
- **License:** **Unlicensed** (No explicit `LICENSE` or `COPYING` file is committed to the repository; standard public GitHub terms apply).
- **Dataset Nature:** **SYNTHETIC** (Industry-inspired synthetic marketplace data modeled after Indian horizontal e-commerce operations, e.g., Meesho/Flipkart).
- **Real Merchant Data Present:** **NO**. All records are synthetically generated using causal random draws and parameterized statistical profiles.

---

## 2. Dataset Description & Upstream Repository Structure
The upstream repository designs an end-to-end Return-to-Origin (RTO) analytics and machine learning pipeline predicting order-time RTO risk.

### Upstream Storage Disclosure
- **Full Database / Parquet Exclusions:** The upstream repository explicitly states in `data/raw/README.md` and `data/processed/README.md` that full raw tables (300,000 orders) and the full feature Parquet file (`rto_feature_table.parquet`, 296,588 resolved rows) are **excluded from GitHub due to file size constraints**.
- **Available Committed Data:** The repository provides:
  1. `data/processed/rto_feature_table_sample.csv` (1,000 rows × 53 columns) containing the first 1,000 resolved orders with all engineered order, customer, seller, geographical, and temporal features alongside the ground-truth terminal target `target_rto`.
  2. `data/processed/rto_feature_dictionary.csv` (53 feature definitions, data types, null profiles, and leakage audit statuses).
  3. `data/processed/rto_feature_groups.csv` (Taxonomy mapping features to domain groups).
  4. `artifacts/modeling/` and `artifacts/business/` (Precomputed experiment results, selected feature lists, model comparison metrics, and risk concentration tables).
  5. `src/data_generation/` (10 self-contained Python generation scripts to reproduce the full synthetic dataset from random seed 42).

---

## 3. Legal and Safety Reproducibility Assessment
- **Safety:** The data generation scripts use standard scientific Python libraries (`numpy`, `pandas`, `scipy`). No external network requests, proprietary API keys, or web scrapers are invoked.
- **Legal Compliance:** The generation scripts do not contain real PII (personally identifiable information), real phone numbers, real credit card details, or proprietary merchant data. All customer names, addresses, and transaction amounts are synthetic.
- **Licensing Constraint:** Because the upstream repo has no open-source license grant (e.g. MIT, Apache 2.0), this dataset and its artifacts must strictly remain in `data/development/` for offline research, testing, and algorithmic benchmarking. It must **never** be packaged or redistributed as proprietary production intellectual property.

---

## 4. Strict Isolation and Non-Contamination Policy
- **No Database Ingestion:** These synthetic records must NEVER be inserted into `profitguard_dev.db` or production PostgreSQL databases.
- **No Decision Engine Overwrite:** ProfitGuard AI's production order decision engine (`backend/app/services/decision_engine.py`) uses operational financial rules, threshold bounds, and Bayesian shrinkage priors with tenant isolation. It must NOT serve predictions derived from synthetic ML weights.
- **Labeling Standard:** All models, test logs, plots, and metric summaries generated from this dataset must bear the label:
  `SYNTHETIC DEVELOPMENT RESULTS - NOT EVALUATED ON REAL PRODUCTION DATA`.
