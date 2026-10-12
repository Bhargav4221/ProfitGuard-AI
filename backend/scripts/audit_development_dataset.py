"""
audit_development_dataset.py
Validates the downloaded RTO development dataset against quality, schema,
integrity, and leakage requirements.
"""

import json
from pathlib import Path
import pandas as pd
import numpy as np

def run_dataset_audit():
    dataset_path = Path("data/development/rto_feature_table_sample.csv")
    dictionary_path = Path("data/development/rto_feature_dictionary.csv")
    
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found at {dataset_path}")
        
    df = pd.read_csv(dataset_path)
    
    # 1. Dimensions & Schema
    row_count, col_count = df.shape
    columns = df.columns.tolist()
    
    # 2. Duplicate checks
    duplicate_rows = int(df.duplicated().sum())
    duplicate_order_ids = int(df["order_id"].duplicated().sum())
    
    # 3. Missing values
    missing_series = df.isnull().sum()
    columns_with_nulls = {
        col: {"count": int(count), "pct": round(float(count / row_count) * 100, 2)}
        for col, count in missing_series.items()
        if count > 0
    }
    
    # 4. Target variable & class balance
    target_counts = df["target_rto"].value_counts().to_dict()
    target_0 = int(target_counts.get(0, 0)) # Delivered
    target_1 = int(target_counts.get(1, 0)) # RTO
    rto_rate = float(target_1 / row_count)
    
    # Check for invalid target states
    valid_targets = set([0, 1])
    actual_targets = set(df["target_rto"].unique())
    has_valid_terminal_targets_only = actual_targets.issubset(valid_targets)
    
    # 5. Date ranges
    df["order_timestamp_dt"] = pd.to_datetime(df["order_timestamp"])
    min_order_date = str(df["order_timestamp_dt"].min())
    max_order_date = str(df["order_timestamp_dt"].max())
    
    # 6. Payment breakdown
    payment_counts = df["payment_type"].value_counts().to_dict()
    cod_flag_counts = df["is_cod"].value_counts().to_dict()
    cod_rto_rate = float(df[df["is_cod"] == 1]["target_rto"].mean())
    prepaid_rto_rate = float(df[df["is_cod"] == 0]["target_rto"].mean())
    
    # 7. Order Value Summary
    val_stats = {
        "min": float(df["order_value"].min()),
        "max": float(df["order_value"].max()),
        "mean": round(float(df["order_value"].mean()), 2),
        "median": round(float(df["order_value"].median()), 2),
        "std": round(float(df["order_value"].std()), 2)
    }
    
    # 8. Customer & Pincode Cardinality
    unique_customers = int(df["customer_id"].nunique())
    unique_pincodes = int(df["customer_pincode"].nunique())
    unique_sellers = int(df["primary_seller_id"].nunique())
    first_orders_count = int(df["is_first_order"].sum())
    
    # 9. Leakage Check
    # Post-order features that MUST NOT exist in model inputs
    leakage_fields = [
        "ndr_count", "delivery_attempts", "carrier_status", "delivery_timestamp",
        "rto_initiated_timestamp", "delivery_agent_id", "final_delivery_status"
    ]
    detected_leakage = [col for col in leakage_fields if col in df.columns]
    
    # 10. Audit result assembly
    audit_report = {
        "dataset_file": str(dataset_path),
        "row_count": row_count,
        "column_count": col_count,
        "duplicate_rows": duplicate_rows,
        "duplicate_order_ids": duplicate_order_ids,
        "date_range": {
            "start": min_order_date,
            "end": max_order_date
        },
        "target_variable": {
            "name": "target_rto",
            "delivered_count_0": target_0,
            "rto_count_1": target_1,
            "rto_prevalence_pct": round(rto_rate * 100, 2),
            "terminal_outcomes_only": has_valid_terminal_targets_only
        },
        "payment_segmentation": {
            "payment_types": payment_counts,
            "cod_count": int(cod_flag_counts.get(1, 0)),
            "prepaid_count": int(cod_flag_counts.get(0, 0)),
            "cod_rto_rate_pct": round(cod_rto_rate * 100, 2),
            "prepaid_rto_rate_pct": round(prepaid_rto_rate * 100, 2)
        },
        "order_value_stats": val_stats,
        "entity_cardinality": {
            "unique_customers": unique_customers,
            "unique_pincodes": unique_pincodes,
            "unique_sellers": unique_sellers,
            "first_time_orders": first_orders_count
        },
        "missing_columns": columns_with_nulls,
        "leakage_audit": {
            "prohibited_fields_detected": detected_leakage,
            "leakage_safe": len(detected_leakage) == 0
        }
    }
    
    output_path = Path("data/development/DATA_AUDIT_REPORT.json")
    with open(output_path, "w") as f:
        json.dump(audit_report, f, indent=2)
        
    print(f"Audit completed successfully. Results written to {output_path}")
    print(f"- Rows: {row_count}")
    print(f"- Columns: {col_count}")
    print(f"- Duplicate rows: {duplicate_rows}")
    print(f"- Terminal outcomes: Delivered={target_0}, RTO={target_1} (RTO Rate: {round(rto_rate * 100, 2)}%)")
    print(f"- COD RTO Rate: {round(cod_rto_rate * 100, 2)}% vs Prepaid RTO Rate: {round(prepaid_rto_rate * 100, 2)}%")
    print(f"- Leakage Safe: {len(detected_leakage) == 0}")
    print(f"- Missing Value Columns: {len(columns_with_nulls)}")

if __name__ == "__main__":
    run_dataset_audit()
