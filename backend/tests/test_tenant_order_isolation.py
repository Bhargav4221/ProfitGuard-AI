"""Tests for Tenant Isolation in Order Management and CSV Ingestion."""

import io
from app.core.tenant import OrganizationRole


def test_cross_tenant_order_read_denied(client, create_user, create_org, create_member, auth_headers):
    # Setup Tenant 1
    user1 = create_user(email="user1@tenant1.com")
    org1 = create_org(name="Tenant 1 Store")
    create_member(org1.id, user1.id, role=OrganizationRole.OPERATOR)
    headers1 = auth_headers(user1, org1)

    # Setup Tenant 2
    user2 = create_user(email="user2@tenant2.com")
    org2 = create_org(name="Tenant 2 Store")
    create_member(org2.id, user2.id, role=OrganizationRole.OPERATOR)
    headers2 = auth_headers(user2, org2)

    # Tenant 1 creates an order
    order_res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-T1-001",
        "order_value": "999.00",
        "payment_method": "COD",
    }, headers=headers1)
    assert order_res.status_code == 201
    order1_id = order_res.json()["id"]

    # Tenant 2 attempts to read Tenant 1's order -> 404 Not Found (strict isolation, no info leak)
    res = client.get(f"/api/v1/orders/{order1_id}", headers=headers2)
    assert res.status_code == 404
    assert "Order not found or unauthorized" in res.json()["detail"]


def test_cross_tenant_order_list_isolation(client, create_user, create_org, create_member, auth_headers):
    user1 = create_user(email="user1@tenant1.com")
    org1 = create_org(name="Tenant 1 Store")
    create_member(org1.id, user1.id, role=OrganizationRole.OPERATOR)
    headers1 = auth_headers(user1, org1)

    user2 = create_user(email="user2@tenant2.com")
    org2 = create_org(name="Tenant 2 Store")
    create_member(org2.id, user2.id, role=OrganizationRole.OPERATOR)
    headers2 = auth_headers(user2, org2)

    # Org 1 creates order
    client.post("/api/v1/orders", json={
        "external_order_id": "ORD-T1-SECRET",
        "order_value": "1500.00",
        "payment_method": "COD",
    }, headers=headers1)

    # Org 2 lists orders -> Should be completely empty
    list_res = client.get("/api/v1/orders", headers=headers2)
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 0
    assert len(list_res.json()["orders"]) == 0


def test_cross_tenant_order_patch_denied(client, create_user, create_org, create_member, auth_headers):
    user1 = create_user(email="user1@tenant1.com")
    org1 = create_org(name="Tenant 1 Store")
    create_member(org1.id, user1.id, role=OrganizationRole.OPERATOR)
    headers1 = auth_headers(user1, org1)

    user2 = create_user(email="user2@tenant2.com")
    org2 = create_org(name="Tenant 2 Store")
    create_member(org2.id, user2.id, role=OrganizationRole.OPERATOR)
    headers2 = auth_headers(user2, org2)

    order_res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-T1-002",
        "order_value": "1200.00",
        "payment_method": "COD",
    }, headers=headers1)
    order1_id = order_res.json()["id"]

    # Tenant 2 attempts to patch Tenant 1's order -> 404
    patch_res = client.patch(f"/api/v1/orders/{order1_id}", json={
        "status": "CANCELLED",
    }, headers=headers2)
    assert patch_res.status_code == 404


def test_cross_tenant_order_items_denied(client, create_user, create_org, create_member, auth_headers):
    user1 = create_user(email="user1@tenant1.com")
    org1 = create_org(name="Tenant 1 Store")
    create_member(org1.id, user1.id, role=OrganizationRole.OPERATOR)
    headers1 = auth_headers(user1, org1)

    user2 = create_user(email="user2@tenant2.com")
    org2 = create_org(name="Tenant 2 Store")
    create_member(org2.id, user2.id, role=OrganizationRole.OPERATOR)
    headers2 = auth_headers(user2, org2)

    order_res = client.post("/api/v1/orders", json={
        "external_order_id": "ORD-T1-ITEMS",
        "order_value": "500.00",
        "payment_method": "COD",
        "items": [{"product_name": "Classified Item", "quantity": 1, "unit_price": "500.00"}],
    }, headers=headers1)
    order1_id = order_res.json()["id"]

    # Tenant 2 tries to list items -> 404
    items_res = client.get(f"/api/v1/orders/{order1_id}/items", headers=headers2)
    assert items_res.status_code == 404


def test_cross_tenant_csv_commit_denied(client, create_user, create_org, create_member, auth_headers):
    user1 = create_user(email="user1@tenant1.com")
    org1 = create_org(name="Tenant 1 Store")
    create_member(org1.id, user1.id, role=OrganizationRole.OPERATOR)
    headers1 = auth_headers(user1, org1)

    user2 = create_user(email="user2@tenant2.com")
    org2 = create_org(name="Tenant 2 Store")
    create_member(org2.id, user2.id, role=OrganizationRole.OPERATOR)
    headers2 = auth_headers(user2, org2)

    # Tenant 1 previews CSV
    csv_content = "external_order_id,order_value,payment_method\nORD-T1-CSV,500.00,COD\n"
    files = {"file": ("t1.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    prev_res = client.post("/api/v1/csv-import/preview", files=files, headers=headers1)
    preview_id = prev_res.json()["preview_id"]

    # Tenant 2 tries to commit Tenant 1's preview -> 404
    commit_res = client.post("/api/v1/csv-import/commit", json={"preview_id": preview_id}, headers=headers2)
    assert commit_res.status_code == 404
    assert "Import preview not found or unauthorized" in commit_res.json()["detail"]


def test_cross_tenant_csv_history_detail_denied(client, create_user, create_org, create_member, auth_headers):
    user1 = create_user(email="user1@tenant1.com")
    org1 = create_org(name="Tenant 1 Store")
    create_member(org1.id, user1.id, role=OrganizationRole.OPERATOR)
    headers1 = auth_headers(user1, org1)

    user2 = create_user(email="user2@tenant2.com")
    org2 = create_org(name="Tenant 2 Store")
    create_member(org2.id, user2.id, role=OrganizationRole.OPERATOR)
    headers2 = auth_headers(user2, org2)

    csv_content = "external_order_id,order_value,payment_method\nORD-T1-HIST,500.00,COD\n"
    files = {"file": ("t1.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    prev_res = client.post("/api/v1/csv-import/preview", files=files, headers=headers1)
    job_id = prev_res.json()["preview_id"]

    # Tenant 2 cannot get Tenant 1's import job
    res = client.get(f"/api/v1/csv-import/history/{job_id}", headers=headers2)
    assert res.status_code == 404
