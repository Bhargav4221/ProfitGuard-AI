"""Pytest Fixtures: Test Database, FastAPI TestClient, and Multi-Tenant Auth Fixtures."""

import os
import sys
import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Add backend to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.core.tenant import OrganizationRole
from app.main import app
from app.models import MerchantEconomics, OrgMembership, Organization, User

# In-memory SQLite for high-speed, isolated unit and integration testing
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def setup_test_database():
    """Recreates database tables cleanly before every test function."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session():
    """Provides a dedicated SQLAlchemy session for test fixtures."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session):
    """FastAPI TestClient with overridden get_db dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def create_user(db_session):
    """Factory fixture to create test users."""
    def _create_user(email="test@example.com", password="Password123!", is_active=True, is_superadmin=False):
        user = User(
            id=uuid4(),
            email=email.lower(),
            hashed_password=hash_password(password),
            full_name="Test User",
            is_active=is_active,
            is_superadmin=is_superadmin,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return _create_user


@pytest.fixture
def create_org(db_session):
    """Factory fixture to create test organizations with default economics."""
    def _create_org(name="Acme D2C Store"):
        org = Organization(
            id=uuid4(),
            name=name,
            slug=f"acme-{uuid4().hex[:6]}",
            status="active",
        )
        db_session.add(org)
        db_session.flush()

        economics = MerchantEconomics(org_id=org.id)
        db_session.add(economics)
        db_session.commit()
        db_session.refresh(org)
        return org

    return _create_org


@pytest.fixture
def create_member(db_session):
    """Factory fixture to assign roles to users within organizations."""
    def _create_member(org_id, user_id, role=OrganizationRole.OPERATOR):
        membership = OrgMembership(
            id=uuid4(),
            org_id=org_id,
            user_id=user_id,
            role=role,
        )
        db_session.add(membership)
        db_session.commit()
        db_session.refresh(membership)
        return membership

    return _create_member


@pytest.fixture
def auth_headers():
    """Generates Authorization and X-Org-Id headers for a given user and org."""
    def _auth_headers(user, org=None):
        token = create_access_token(subject=str(user.id), claims={"email": user.email})
        headers = {"Authorization": f"Bearer {token}"}
        if org:
            headers["X-Org-Id"] = str(org.id)
        return headers

    return _auth_headers
