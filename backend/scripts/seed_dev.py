"""Development Database Seeder for ProfitGuard AI.

Creates:
1. Default Organization: 'Acme D2C Store'
2. Owner User: 'demo@profitguard.ai' / 'DemoPassword123!'
3. MerchantEconomics configuration
4. Initial Demonstration Orders (via DemoService)
"""

import sys
from pathlib import Path
from uuid import uuid4

# Ensure backend root is on sys.path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from sqlalchemy import select
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.core.tenant import OrganizationRole
from app.models.membership import OrgMembership
from app.models.merchant_economics import MerchantEconomics
from app.models.organization import Organization
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.demo_service import DemoService


def seed_development_data():
    session = SessionLocal()
    try:
        print("[1/4] Checking existing demo merchant organization...")
        org = session.scalar(select(Organization).where(Organization.name == "Acme D2C Store"))
        if not org:
            org = Organization(
                id=uuid4(),
                name="Acme D2C Store",
                slug="acme-d2c-store",
                status="active",
            )
            session.add(org)
            session.flush()
            print(f"      Created organization: {org.name} ({org.id})")
        else:
            print(f"      Found existing organization: {org.name} ({org.id})")

        print("[2/4] Checking demo merchant user...")
        demo_email = "demo@profitguard.ai"
        user = session.scalar(select(User).where(User.email == demo_email))
        if not user:
            user = User(
                id=uuid4(),
                email=demo_email,
                hashed_password=hash_password("DemoPassword123!"),
                full_name="Acme Store Manager",
                is_active=True,
            )
            session.add(user)
            session.flush()
            print(f"      Created user: {user.email} ({user.id})")
        else:
            print(f"      Found existing user: {user.email} ({user.id})")

        # Ensure OrgMembership
        membership = session.scalar(
            select(OrgMembership).where(
                OrgMembership.org_id == org.id,
                OrgMembership.user_id == user.id,
            )
        )
        if not membership:
            membership = OrgMembership(
                org_id=org.id,
                user_id=user.id,
                role=OrganizationRole.OWNER,
            )
            session.add(membership)
            session.flush()
            print(f"      Created OWNER membership for {user.email} in {org.name}")

        print("[3/4] Checking merchant economics...")
        econ = session.scalar(select(MerchantEconomics).where(MerchantEconomics.org_id == org.id))
        if not econ:
            econ = MerchantEconomics(org_id=org.id)
            session.add(econ)
            session.flush()
            print("      Initialized default MerchantEconomics (COD fee: Rs.35, S_f: Rs.70, S_r: Rs.65, OTP: Rs.0.50)")
        else:
            print("      MerchantEconomics already configured.")

        # Record audit log
        AuditService.record_event(
            session=session,
            org_id=org.id,
            actor_user_id=user.id,
            action="DEV_SEED_INITIALIZED",
            resource_type="Organization",
            resource_id=str(org.id),
            payload={"org_name": org.name, "user_email": user.email},
        )
        session.commit()

        print("[4/4] Seeding initial demonstration orders...")
        demo_res = DemoService.seed_demo_data(org_id=org.id, session=session, user_id=user.id)
        print(f"      {demo_res['message']}")
        print(f"      Seeded orders: {', '.join(demo_res['seeded_orders'])}")

        print("\nSUCCESS: Development database seeded successfully!")
        print(f"Login Email:    {demo_email}")
        print("Password:       DemoPassword123!")
        print(f"Tenant Org ID:  {org.id}")

    except Exception as e:
        session.rollback()
        print(f"ERROR: Seeding failed: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed_development_data()
