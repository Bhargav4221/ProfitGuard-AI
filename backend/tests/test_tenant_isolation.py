"""Tests for Cross-Tenant Data Isolation and Access Denial."""

from uuid import uuid4
import pytest
from app.core.tenant import OrganizationRole


@pytest.fixture
def two_tenants(create_user, create_org, create_member):
    # Tenant A
    org_a = create_org(name="Merchant Alpha")
    user_a = create_user(email="alpha@store.in")
    create_member(org_a.id, user_a.id, role=OrganizationRole.OWNER)

    # Tenant B
    org_b = create_org(name="Merchant Beta")
    user_b = create_user(email="beta@store.in")
    create_member(org_b.id, user_b.id, role=OrganizationRole.OWNER)

    return {
        "org_a": org_a,
        "user_a": user_a,
        "org_b": org_b,
        "user_b": user_b,
    }


def test_cross_tenant_access_denied_via_header_manipulation(client, two_tenants, auth_headers):
    user_a = two_tenants["user_a"]
    org_b = two_tenants["org_b"]

    # User A tries to spoof X-Org-Id header with Org B's ID
    headers = auth_headers(user_a)
    headers["X-Org-Id"] = str(org_b.id)

    response = client.get("/api/v1/economics", headers=headers)
    assert response.status_code == 403
    assert "not a member" in response.json()["detail"].lower()


def test_cross_tenant_organization_details_access_denied(client, two_tenants, auth_headers):
    user_a = two_tenants["user_a"]
    org_b = two_tenants["org_b"]
    headers = auth_headers(user_a)

    # User A tries to access Org B's detail endpoint
    response = client.get(f"/api/v1/orgs/{org_b.id}", headers=headers)
    assert response.status_code == 403
    assert "access forbidden" in response.json()["detail"].lower()


def test_cross_tenant_invite_member_denied(client, two_tenants, auth_headers, create_user):
    user_a = two_tenants["user_a"]
    org_b = two_tenants["org_b"]
    intruder = create_user(email="intruder@store.in")
    headers = auth_headers(user_a)

    response = client.post(
        f"/api/v1/orgs/{org_b.id}/members/invite",
        json={"email": intruder.email, "role": "ADMIN"},
        headers=headers,
    )
    assert response.status_code == 403


def test_missing_tenant_context_header_denied(client, two_tenants, auth_headers):
    user_a = two_tenants["user_a"]
    # Provide auth header but omit X-Org-Id header
    headers = auth_headers(user_a)

    response = client.get("/api/v1/economics", headers=headers)
    assert response.status_code == 400
    assert "missing required 'x-org-id' header" in response.json()["detail"].lower()


def test_malformed_tenant_context_header_denied(client, two_tenants, auth_headers):
    user_a = two_tenants["user_a"]
    headers = auth_headers(user_a)
    headers["X-Org-Id"] = "not-a-valid-uuid"

    response = client.get("/api/v1/economics", headers=headers)
    assert response.status_code == 400
    assert "invalid format" in response.json()["detail"].lower()


def test_guessing_unrelated_org_id_denied(client, two_tenants, auth_headers):
    user_a = two_tenants["user_a"]
    headers = auth_headers(user_a)
    random_org_id = str(uuid4())
    headers["X-Org-Id"] = random_org_id

    response = client.get("/api/v1/economics", headers=headers)
    assert response.status_code == 403
