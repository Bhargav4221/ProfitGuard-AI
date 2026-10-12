"""Tests for Order Management: CRUD, Decimal Precision, Immutability, Audit Logs, and RBAC."""

from decimal import Decimal
from uuid import uuid4
import pytest
from app.core.tenant import OrganizationRole
from app.models.audit_log import AuditLog
from app.models.order import Order


def test_create_order_success(client, create_user, create_org, create_member, auth_headers):
    user = create_user(email="merchant@example.com")
    org = create_org(name="Acme Fashion")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    payload = {
        "external_order_id": "ORD-1001",
        "currency": "INR",
        "order_value": "1499.50",
        "payment_method": "COD",
        "customer_name": "Rohan Sharma",
        "customer_phone": "9876543210",
        "customer_email": "rohan@example.com",
        "shipping_address1": "House 12, Indiranagar",
        "shipping_city": "Bengaluru",
        "shipping_state": "Karnataka",
        "shipping_pincode": "560038",
        "shipping_country": "IN",
        "courier_name": "Delhivery",
        "items": [
            {
                "product_name": "Linen Shirt",
                "sku": "LIN-BLU-M",
                "quantity": 2,
                "unit_price": "749.75",
                "unit_cost": "250.00",
            }
        ],
    }

    res = client.post("/api/v1/orders", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["external_order_id"] == "ORD-1001"
    assert Decimal(str(data["order_value"])) == Decimal("1499.50")
    assert data["payment_method"] == "COD"
    assert data["status"] == "PENDING"
    assert len(data["items"]) == 1
    assert data["items"][0]["product_name"] == "Linen Shirt"
    assert data["items"][0]["quantity"] == 2
    assert Decimal(str(data["items"][0]["total_price"])) == Decimal("1499.50")


def test_create_order_duplicate_external_id_fails(client, create_user, create_org, create_member, auth_headers):
    user = create_user(email="merchant@example.com")
    org = create_org(name="Acme Fashion")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    payload = {
        "external_order_id": "ORD-DUPLICATE",
        "order_value": "999.00",
        "payment_method": "COD",
    }

    res1 = client.post("/api/v1/orders", json=payload, headers=headers)
    assert res1.status_code == 201

    res2 = client.post("/api/v1/orders", json=payload, headers=headers)
    assert res2.status_code == 409
    assert "already exists in your organization" in res2.json()["detail"]


def test_different_orgs_can_have_same_external_order_id(client, create_user, create_org, create_member, auth_headers):
    user = create_user(email="merchant@example.com")
    org1 = create_org(name="Org 1")
    org2 = create_org(name="Org 2")
    create_member(org1.id, user.id, role=OrganizationRole.OPERATOR)
    create_member(org2.id, user.id, role=OrganizationRole.OPERATOR)

    payload = {
        "external_order_id": "ORD-COMMON-100",
        "order_value": "500.00",
        "payment_method": "PREPAID",
    }

    res1 = client.post("/api/v1/orders", json=payload, headers=auth_headers(user, org1))
    assert res1.status_code == 201

    res2 = client.post("/api/v1/orders", json=payload, headers=auth_headers(user, org2))
    assert res2.status_code == 201
    assert res1.json()["id"] != res2.json()["id"]


def test_create_order_validation_failures(client, create_user, create_org, create_member, auth_headers):
    user = create_user(email="merchant@example.com")
    org = create_org(name="Acme Fashion")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    # 1. Invalid phone (9 digits)
    res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-V1",
        "order_value": "100.00",
        "payment_method": "COD",
        "customer_phone": "987654321",
    }, headers=headers)
    assert res.status_code == 422

    # 2. Invalid pincode (starts with 0)
    res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-V2",
        "order_value": "100.00",
        "payment_method": "COD",
        "shipping_pincode": "012345",
    }, headers=headers)
    assert res.status_code == 422

    # 3. Invalid payment method
    res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-V3",
        "order_value": "100.00",
        "payment_method": "CRYPTO",
    }, headers=headers)
    assert res.status_code == 422

    # 4. Zero order value
    res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-V4",
        "order_value": "0.00",
        "payment_method": "COD",
    }, headers=headers)
    assert res.status_code == 422


def test_order_value_immutability(client, create_user, create_org, create_member, auth_headers):
    user = create_user(email="merchant@example.com")
    org = create_org(name="Acme Fashion")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    # Create order
    create_res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-IMMUTABLE",
        "order_value": "2499.00",
        "payment_method": "COD",
        "customer_name": "Original Name",
    }, headers=headers)
    assert create_res.status_code == 201
    order_id = create_res.json()["id"]

    # Attempt to tamper order_value, external_order_id, and id alongside customer_name
    patch_res = client.patch(f"/api/v1/orders/{order_id}", json={
        "customer_name": "Updated Customer Name",
        "order_value": "100.00",
        "external_order_id": "TAMPERED_ID",
    }, headers=headers)
    assert patch_res.status_code == 200
    updated_data = patch_res.json()

    # Original value and external ID must remain strictly unchanged
    assert updated_data["customer_name"] == "Updated Customer Name"
    assert Decimal(str(updated_data["order_value"])) == Decimal("2499.00")
    assert updated_data["external_order_id"] == "ORD-IMMUTABLE"


def test_order_audit_trail(client, create_user, create_org, create_member, auth_headers, db_session):
    user = create_user(email="merchant@example.com")
    org = create_org(name="Acme Fashion")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    # 1. Create order
    create_res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-AUDIT",
        "order_value": "899.00",
        "payment_method": "COD",
    }, headers=headers)
    assert create_res.status_code == 201
    order_id = create_res.json()["id"]

    # Check audit log contains ORDER_CREATED
    audit_create = db_session.query(AuditLog).filter_by(
        org_id=org.id,
        action="ORDER_CREATED",
        resource_id=order_id,
    ).first()
    assert audit_create is not None
    assert audit_create.payload["external_order_id"] == "ORD-AUDIT"

    # 2. Update order
    patch_res = client.patch(f"/api/v1/orders/{order_id}", json={
        "status": "CONFIRMED",
    }, headers=headers)
    assert patch_res.status_code == 200

    # Check audit log contains ORDER_UPDATED
    audit_update = db_session.query(AuditLog).filter_by(
        org_id=org.id,
        action="ORDER_UPDATED",
        resource_id=order_id,
    ).first()
    assert audit_update is not None
    assert "status" in audit_update.payload["changes"]
    assert audit_update.payload["changes"]["status"]["new"] == "CONFIRMED"


def test_orders_rbac(client, create_user, create_org, create_member, auth_headers):
    user_op = create_user(email="operator@example.com")
    user_auditor = create_user(email="auditor@example.com")
    org = create_org(name="Acme Fashion")
    create_member(org.id, user_op.id, role=OrganizationRole.OPERATOR)
    create_member(org.id, user_auditor.id, role=OrganizationRole.AUDITOR)

    op_headers = auth_headers(user_op, org)
    auditor_headers = auth_headers(user_auditor, org)

    # 1. Operator creates order -> Allowed
    res_op = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-RBAC-1",
        "order_value": "599.00",
        "payment_method": "PREPAID",
    }, headers=op_headers)
    assert res_op.status_code == 201
    order_id = res_op.json()["id"]

    # 2. Auditor tries to create order -> Forbidden (403)
    res_aud_create = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-RBAC-2",
        "order_value": "599.00",
        "payment_method": "PREPAID",
    }, headers=auditor_headers)
    assert res_aud_create.status_code == 403

    # 3. Auditor tries to update order -> Forbidden (403)
    res_aud_patch = client.patch(f"/api/v1/orders/{order_id}", json={
        "status": "HOLD",
    }, headers=auditor_headers)
    assert res_aud_patch.status_code == 403

    # 4. Auditor reads order and list -> Allowed (200)
    res_aud_get = client.get(f"/api/v1/orders/{order_id}", headers=auditor_headers)
    assert res_aud_get.status_code == 200
    assert res_aud_get.json()["id"] == order_id

    res_aud_list = client.get("/api/v1/orders", headers=auditor_headers)
    assert res_aud_list.status_code == 200
    assert res_aud_list.json()["total"] >= 1


def test_orders_filtering_and_pagination(client, create_user, create_org, create_member, auth_headers):
    user = create_user(email="filter@example.com")
    org = create_org(name="Acme Fashion")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    # Create 3 distinct orders
    client.post("/api/v1/orders", json={
        "external_order_id": "ORD-FILTER-1",
        "order_value": "1000.00",
        "payment_method": "COD",
        "status": "PENDING",
        "customer_name": "Priya Nair",
    }, headers=headers)

    client.post("/api/v1/orders", json={
        "external_order_id": "ORD-FILTER-2",
        "order_value": "2000.00",
        "payment_method": "PREPAID",
        "status": "DELIVERED",
        "customer_name": "Ananya Sharma",
    }, headers=headers)

    client.post("/api/v1/orders", json={
        "external_order_id": "ORD-FILTER-3",
        "order_value": "3000.00",
        "payment_method": "COD",
        "status": "RTO",
        "customer_name": "Priya Nair",
    }, headers=headers)

    # Filter by status DELIVERED
    res_status = client.get("/api/v1/orders?status=DELIVERED", headers=headers)
    assert res_status.status_code == 200
    data_status = res_status.json()
    assert data_status["total"] == 1
    assert data_status["orders"][0]["external_order_id"] == "ORD-FILTER-2"

    # Filter by payment_method COD
    res_pm = client.get("/api/v1/orders?payment_method=COD", headers=headers)
    assert res_pm.status_code == 200
    assert res_pm.json()["total"] == 2

    # Search by customer name
    res_search = client.get("/api/v1/orders?search=Priya", headers=headers)
    assert res_search.status_code == 200
    assert res_search.json()["total"] == 2

    # Pagination: limit=1, offset=1
    res_page = client.get("/api/v1/orders?limit=1&offset=1", headers=headers)
    assert res_page.status_code == 200
    assert len(res_page.json()["orders"]) == 1
    assert res_page.json()["total"] == 3


def test_get_order_items(client, create_user, create_org, create_member, auth_headers):
    user = create_user(email="items@example.com")
    org = create_org(name="Acme Fashion")
    create_member(org.id, user.id, role=OrganizationRole.OPERATOR)
    headers = auth_headers(user, org)

    create_res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-ITEMS-1",
        "order_value": "1500.00",
        "payment_method": "COD",
        "items": [
            {"product_name": "Item A", "quantity": 1, "unit_price": "500.00"},
            {"product_name": "Item B", "quantity": 2, "unit_price": "500.00"},
        ],
    }, headers=headers)
    assert create_res.status_code == 201
    order_id = create_res.json()["id"]

    items_res = client.get(f"/api/v1/orders/{order_id}/items", headers=headers)
    assert items_res.status_code == 200
    items = items_res.json()
    assert len(items) == 2
    names = {it["product_name"] for it in items}
    assert names == {"Item A", "Item B"}
