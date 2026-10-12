"""Tests for Role-Based Access Control (RBAC)."""

import pytest
from app.core.tenant import OrganizationRole


@pytest.fixture
def org_and_users(create_user, create_org, create_member):
    org = create_org(name="RBAC Store")
    owner = create_user(email="owner@store.in")
    admin = create_user(email="admin@store.in")
    operator = create_user(email="operator@store.in")
    auditor = create_user(email="auditor@store.in")

    create_member(org.id, owner.id, role=OrganizationRole.OWNER)
    create_member(org.id, admin.id, role=OrganizationRole.ADMIN)
    create_member(org.id, operator.id, role=OrganizationRole.OPERATOR)
    create_member(org.id, auditor.id, role=OrganizationRole.AUDITOR)

    return {
        "org": org,
        "owner": owner,
        "admin": admin,
        "operator": operator,
        "auditor": auditor,
    }


def test_owner_can_update_economics_and_roles(client, org_and_users, auth_headers):
    org = org_and_users["org"]
    owner = org_and_users["owner"]
    operator = org_and_users["operator"]
    headers = auth_headers(owner, org)

    # Update economics
    eco_resp = client.put(
        "/api/v1/economics",
        json={"forward_shipping_cost": 85.00, "packaging_cost": 25.00},
        headers=headers,
    )
    assert eco_resp.status_code == 200
    assert eco_resp.json()["forward_shipping_cost"] == "85.00"

    # Update operator role to admin
    role_resp = client.patch(
        f"/api/v1/orgs/{org.id}/members/{operator.id}/role",
        json={"role": "ADMIN"},
        headers=headers,
    )
    assert role_resp.status_code == 200


def test_admin_can_update_economics_but_cannot_change_roles(client, org_and_users, auth_headers):
    org = org_and_users["org"]
    admin = org_and_users["admin"]
    operator = org_and_users["operator"]
    headers = auth_headers(admin, org)

    # Admin can update economics
    eco_resp = client.put(
        "/api/v1/economics",
        json={"forward_shipping_cost": 90.00},
        headers=headers,
    )
    assert eco_resp.status_code == 200

    # Admin CANNOT update roles (only OWNER can)
    role_resp = client.patch(
        f"/api/v1/orgs/{org.id}/members/{operator.id}/role",
        json={"role": "ADMIN"},
        headers=headers,
    )
    assert role_resp.status_code == 403


def test_operator_cannot_update_economics(client, org_and_users, auth_headers):
    org = org_and_users["org"]
    operator = org_and_users["operator"]
    headers = auth_headers(operator, org)

    # Operator can read economics
    get_resp = client.get("/api/v1/economics", headers=headers)
    assert get_resp.status_code == 200

    # Operator cannot update economics
    put_resp = client.put(
        "/api/v1/economics",
        json={"forward_shipping_cost": 99.00},
        headers=headers,
    )
    assert put_resp.status_code == 403
    assert "permission denied" in put_resp.json()["detail"].lower()


def test_auditor_has_read_only_access(client, org_and_users, auth_headers):
    org = org_and_users["org"]
    auditor = org_and_users["auditor"]
    headers = auth_headers(auditor, org)

    # Auditor can read economics and audit logs
    eco_resp = client.get("/api/v1/economics", headers=headers)
    assert eco_resp.status_code == 200

    audit_resp = client.get("/api/v1/audit", headers=headers)
    assert audit_resp.status_code == 200

    # Auditor cannot update economics
    put_resp = client.put(
        "/api/v1/economics",
        json={"forward_shipping_cost": 100.00},
        headers=headers,
    )
    assert put_resp.status_code == 403
