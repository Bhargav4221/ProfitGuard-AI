"""Tests for Deterministic Serialization, Cryptographic Hash Chaining, and Tamper Detection."""

from uuid import uuid4
import pytest
from app.models.audit_log import canonicalize_payload, compute_audit_hash, AuditLog
from app.services.audit_service import AuditService


def test_deterministic_payload_canonicalization():
    dict1 = {"b": 2, "a": 1, "c": {"y": 20, "x": 10}}
    dict2 = {"a": 1, "c": {"x": 10, "y": 20}, "b": 2}

    canon1 = canonicalize_payload(dict1)
    canon2 = canonicalize_payload(dict2)

    assert canon1 == canon2
    assert canon1 == '{"a":1,"b":2,"c":{"x":10,"y":20}}'


def test_audit_hash_chain_verification_intact(db_session, create_org, create_user):
    org = create_org(name="Audit Test Brand")
    user = create_user(email="auditor@brand.in")

    # Record 4 sequential events
    AuditService.record_event(
        session=db_session,
        org_id=org.id,
        actor_user_id=user.id,
        action="LOGIN_SUCCESS",
        resource_type="User",
        resource_id=str(user.id),
        payload={"ip": "127.0.0.1"},
    )
    AuditService.record_event(
        session=db_session,
        org_id=org.id,
        actor_user_id=user.id,
        action="UPDATE_SETTING",
        resource_type="MerchantEconomics",
        resource_id=str(org.id),
        payload={"forward_shipping_cost": 75.00},
    )
    AuditService.record_event(
        session=db_session,
        org_id=org.id,
        actor_user_id=user.id,
        action="INVITE_MEMBER",
        resource_type="OrgMembership",
        resource_id="mem_123",
        payload={"email": "operator@brand.in", "role": "OPERATOR"},
    )
    db_session.commit()

    is_valid, broken_seq, detail = AuditService.verify_chain(db_session, org.id)
    assert is_valid is True
    assert broken_seq is None
    assert "verified successfully" in detail.lower()


def test_audit_hash_chain_detects_payload_tampering(db_session, create_org, create_user):
    org = create_org(name="Tamper Test Brand")
    user = create_user(email="admin@tamper.in")

    for i in range(1, 4):
        AuditService.record_event(
            session=db_session,
            org_id=org.id,
            actor_user_id=user.id,
            action=f"ACTION_{i}",
            resource_type="Resource",
            resource_id=f"res_{i}",
            payload={"step": i, "amount": i * 100},
        )
    db_session.commit()

    # Tamper with record #2 directly in database
    rec2 = db_session.query(AuditLog).filter_by(org_id=org.id, sequence_number=2).one()
    rec2.payload = {"step": 2, "amount": 999999}  # Altered payload!
    db_session.commit()

    is_valid, broken_seq, detail = AuditService.verify_chain(db_session, org.id)
    assert is_valid is False
    assert broken_seq == 2
    assert "tampered entry" in detail.lower() or "hash mismatch" in detail.lower()


def test_audit_hash_chain_detects_broken_link(db_session, create_org, create_user):
    org = create_org(name="Link Test Brand")
    user = create_user(email="admin@link.in")

    for i in range(1, 4):
        AuditService.record_event(
            session=db_session,
            org_id=org.id,
            actor_user_id=user.id,
            action=f"ACTION_{i}",
            resource_type="Resource",
            resource_id=f"res_{i}",
            payload={"step": i},
        )
    db_session.commit()

    # Corrupt previous_hash of record #3
    rec3 = db_session.query(AuditLog).filter_by(org_id=org.id, sequence_number=3).one()
    rec3.previous_hash = "deadbeef" * 8
    db_session.commit()

    is_valid, broken_seq, detail = AuditService.verify_chain(db_session, org.id)
    assert is_valid is False
    assert broken_seq == 3
    assert "broken link" in detail.lower()


def test_isolated_tenants_have_independent_hash_chains(db_session, create_org, create_user):
    org_a = create_org(name="Org A")
    org_b = create_org(name="Org B")
    user = create_user(email="user@multitenant.in")

    log_a1 = AuditService.record_event(
        session=db_session,
        org_id=org_a.id,
        actor_user_id=user.id,
        action="ORG_A_INIT",
        resource_type="Org",
    )
    log_b1 = AuditService.record_event(
        session=db_session,
        org_id=org_b.id,
        actor_user_id=user.id,
        action="ORG_B_INIT",
        resource_type="Org",
    )
    db_session.commit()

    # Both genesis blocks start with 64 zeroes
    assert log_a1.previous_hash == "0" * 64
    assert log_b1.previous_hash == "0" * 64
    assert log_a1.sequence_number == 1
    assert log_b1.sequence_number == 1

    # Their current hashes differ because org_id is mixed into the hash
    assert log_a1.current_hash != log_b1.current_hash

    # Both chains verify independently
    assert AuditService.verify_chain(db_session, org_a.id)[0] is True
    assert AuditService.verify_chain(db_session, org_b.id)[0] is True
