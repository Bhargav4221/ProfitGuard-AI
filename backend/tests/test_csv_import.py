"""Tests for Two-Stage CSV Import Pipeline: Validation, Staging, Idempotent Commit, and History."""

import io
from decimal import Decimal
import pytest
from app.core.tenant import OrganizationRole
from app.models.audit_log import AuditLog
from app.models.import_job import ImportJob
from app.models.order import Order


def test_download_csv_template(client):
    res = client.get("/api/v1/csv-import/template")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "external_order_id" in res.text
    assert "order_value" in res.text
    assert "payment_method" in res.text


def test_csv_preview_valid_file_does_not_persist_orders(client, create_user, create_org, create_member, auth_headers, db_session):
    user = create_user(email="csv@example.com")
    org = create_org(name="Acme Fashion")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    # Valid CSV with UTF-8 BOM
    csv_content = (
        "\ufeffexternal_order_id,order_value,payment_method,customer_name,customer_phone,shipping_pincode\n"
        "ORD-2001,1200.00,COD,Vikram Malhotra,9876543210,560001\n"
        "ORD-2002,850.50,PREPAID,Meera Iyer,9812345678,400001\n"
    )

    files = {"file": ("orders.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    res = client.post("/api/v1/csv-import/preview", files=files, headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["total_rows"] == 2
    assert data["valid_rows"] == 2
    assert data["invalid_rows"] == 0
    assert data["duplicate_rows"] == 0
    assert len(data["errors"]) == 0
    assert len(data["sample_valid_rows"]) == 2

    # Verification: Stage A must NOT write to orders table
    order_count = db_session.query(Order).filter_by(org_id=org.id).count()
    assert order_count == 0


def test_csv_preview_validation_errors(client, create_user, create_org, create_member, auth_headers):
    user = create_user(email="csv@example.com")
    org = create_org(name="Acme Fashion")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    csv_content = (
        "external_order_id,order_value,payment_method,customer_phone,shipping_pincode\n"
        ",500.00,COD,9876543210,560001\n"                       # Missing order id
        "ORD-ERR-1,-100.00,COD,9876543210,560001\n"            # Negative order value
        "ORD-ERR-2,500.00,CRYPTO,9876543210,560001\n"          # Invalid payment method
        "ORD-ERR-3,500.00,COD,12345,560001\n"                  # Invalid phone format
        "ORD-ERR-4,500.00,COD,9876543210,012345\n"             # Invalid pincode format (starts with 0)
    )

    files = {"file": ("orders_err.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    res = client.post("/api/v1/csv-import/preview", files=files, headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["total_rows"] == 5
    assert data["valid_rows"] == 0
    assert data["invalid_rows"] == 5
    assert len(data["errors"]) == 5

    columns_with_errors = {err["column_name"] for err in data["errors"]}
    assert "external_order_id" in columns_with_errors
    assert "order_value" in columns_with_errors
    assert "payment_method" in columns_with_errors
    assert "customer_phone" in columns_with_errors
    assert "shipping_pincode" in columns_with_errors


def test_csv_preview_catches_intra_file_duplicates(client, create_user, create_org, create_member, auth_headers):
    user = create_user(email="csv@example.com")
    org = create_org(name="Acme Fashion")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    # In CSV, duplicate order ID with conflicting details
    csv_content = (
        "external_order_id,order_value,payment_method\n"
        "ORD-DUP-1,500.00,COD\n"
        "ORD-DUP-1,700.00,PREPAID\n"
    )

    files = {"file": ("duplicates.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    res = client.post("/api/v1/csv-import/preview", files=files, headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["total_rows"] == 2
    assert data["duplicate_rows"] == 1


def test_csv_preview_catches_existing_order_in_db(client, create_user, create_org, create_member, auth_headers):
    user = create_user(email="csv@example.com")
    org = create_org(name="Acme Fashion")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    # 1. Manually create an order first
    client.post("/api/v1/orders", json={
        "external_order_id": "ORD-EXISTING-99",
        "order_value": "500.00",
        "payment_method": "COD",
    }, headers=headers)

    # 2. Try to preview CSV containing that same external order ID
    csv_content = (
        "external_order_id,order_value,payment_method\n"
        "ORD-EXISTING-99,500.00,COD\n"
        "ORD-NEW-100,600.00,COD\n"
    )
    files = {"file": ("check_db_dup.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    res = client.post("/api/v1/csv-import/preview", files=files, headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["valid_rows"] == 1
    assert data["duplicate_rows"] == 1
    dup_error = [e for e in data["errors"] if e["external_order_id"] == "ORD-EXISTING-99"][0]
    assert "already exists in your account" in dup_error["error_message"]


def test_csv_commit_success_and_audit(client, create_user, create_org, create_member, auth_headers, db_session):
    user = create_user(email="csv@example.com")
    org = create_org(name="Acme Fashion")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    # Stage A: Preview
    csv_content = (
        "external_order_id,order_value,payment_method,customer_name,customer_phone,product_name,quantity,unit_price\n"
        "ORD-COMMIT-1,999.00,COD,Kavita Sen,9876543210,Handbag,1,999.00\n"
        "ORD-COMMIT-2,1499.00,PREPAID,Rajesh K,9898989898,Watch,1,1499.00\n"
    )
    files = {"file": ("batch1.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    preview_res = client.post("/api/v1/csv-import/preview", files=files, headers=headers)
    assert preview_res.status_code == 200
    preview_id = preview_res.json()["preview_id"]

    # Stage B: Commit
    commit_res = client.post("/api/v1/csv-import/commit", json={"preview_id": preview_id}, headers=headers)
    assert commit_res.status_code == 200
    commit_data = commit_res.json()
    assert commit_data["inserted_count"] == 2
    assert commit_data["skipped_count"] == 0
    assert commit_data["status"] == "COMMITTED"

    # Verify orders are in DB
    orders = db_session.query(Order).filter_by(org_id=org.id).all()
    assert len(orders) == 2
    assert {o.external_order_id for o in orders} == {"ORD-COMMIT-1", "ORD-COMMIT-2"}

    # Verify Audit Log
    audit = db_session.query(AuditLog).filter_by(
        org_id=org.id,
        action="CSV_IMPORT_COMMITTED",
        resource_id=preview_id,
    ).first()
    assert audit is not None
    assert audit.payload["inserted_count"] == 2


def test_csv_commit_idempotent_double_commit_rejected(client, create_user, create_org, create_member, auth_headers):
    user = create_user(email="csv@example.com")
    org = create_org(name="Acme Fashion")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    csv_content = "external_order_id,order_value,payment_method\nORD-IDEMP-1,500.00,COD\n"
    files = {"file": ("idemp.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    preview_res = client.post("/api/v1/csv-import/preview", files=files, headers=headers)
    preview_id = preview_res.json()["preview_id"]

    # Commit 1 -> Success
    res1 = client.post("/api/v1/csv-import/commit", json={"preview_id": preview_id}, headers=headers)
    assert res1.status_code == 200

    # Commit 2 -> Rejected with 400
    res2 = client.post("/api/v1/csv-import/commit", json={"preview_id": preview_id}, headers=headers)
    assert res2.status_code == 400
    assert "already been committed" in res2.json()["detail"]


def test_csv_preview_quoted_fields_with_commas(client, create_user, create_org, create_member, auth_headers):
    user = create_user(email="csv@example.com")
    org = create_org(name="Acme Fashion")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    # Address contains comma inside quotes
    csv_content = (
        'external_order_id,order_value,payment_method,shipping_address1\n'
        'ORD-COMMA-1,750.00,COD,"Flat 402, Lakeview Apartments, MG Road"\n'
    )
    files = {"file": ("quotes.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    res = client.post("/api/v1/csv-import/preview", files=files, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["valid_rows"] == 1
    assert data["sample_valid_rows"][0]["shipping_address1"] == "Flat 402, Lakeview Apartments, MG Road"


def test_csv_preview_missing_mandatory_headers_fails(client, create_user, create_org, create_member, auth_headers):
    user = create_user(email="csv@example.com")
    org = create_org(name="Acme Fashion")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    # Missing payment_method header
    csv_content = "external_order_id,order_value\nORD-1,100.00\n"
    files = {"file": ("bad_headers.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    res = client.post("/api/v1/csv-import/preview", files=files, headers=headers)
    assert res.status_code == 400
    assert "missing mandatory headers" in res.json()["detail"]


def test_csv_import_history_and_details(client, create_user, create_org, create_member, auth_headers):
    user = create_user(email="csv@example.com")
    org = create_org(name="Acme Fashion")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    # Create preview with 1 valid and 1 invalid
    csv_content = (
        "external_order_id,order_value,payment_method\n"
        "ORD-HIST-1,400.00,COD\n"
        "ORD-HIST-2,BAD_VAL,COD\n"
    )
    files = {"file": ("hist.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    preview_res = client.post("/api/v1/csv-import/preview", files=files, headers=headers)
    job_id = preview_res.json()["preview_id"]

    # History list
    history_res = client.get("/api/v1/csv-import/history", headers=headers)
    assert history_res.status_code == 200
    hist_data = history_res.json()
    assert hist_data["total"] >= 1
    assert any(j["id"] == job_id for j in hist_data["jobs"])

    # Detail view
    detail_res = client.get(f"/api/v1/csv-import/history/{job_id}", headers=headers)
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert detail_data["id"] == job_id
    assert len(detail_data["errors"]) == 1
    assert detail_data["errors"][0]["external_order_id"] == "ORD-HIST-2"


def test_csv_import_rbac(client, create_user, create_org, create_member, auth_headers):
    user_auditor = create_user(email="auditor_csv@example.com")
    org = create_org(name="Acme Fashion")
    create_member(org.id, user_auditor.id, role=OrganizationRole.AUDITOR)
    auditor_headers = auth_headers(user_auditor, org)

    csv_content = "external_order_id,order_value,payment_method\nORD-AUD-1,500.00,COD\n"
    files = {"file": ("aud.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}

    # Auditor cannot preview
    res_prev = client.post("/api/v1/csv-import/preview", files=files, headers=auditor_headers)
    assert res_prev.status_code == 403

    # Auditor can view history list
    res_hist = client.get("/api/v1/csv-import/history", headers=auditor_headers)
    assert res_hist.status_code == 200
