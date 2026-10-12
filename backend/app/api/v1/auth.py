"""Authentication API Endpoints: Register, Login, Refresh, Logout, Me."""

import re
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, security_bearer
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.tenant import OrganizationRole
from app.models.membership import OrgMembership
from app.models.merchant_economics import MerchantEconomics
from app.models.organization import Organization
from app.models.revoked_token import RevokedToken
from app.models.user import User
from app.schemas.auth import TokenRefresh, TokenResponse, UserLogin, UserOut, UserRegister
from app.services.audit_service import AuditService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, session: Session = Depends(get_db)):
    """Registers a new user, creates their initial organization, and assigns OWNER role."""
    # Check if email is already registered
    existing_user = session.scalar(select(User).where(User.email == payload.email.lower()))
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists.",
        )

    # Create User
    new_user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        is_active=True,
    )
    session.add(new_user)
    session.flush()

    # Generate slug for initial organization
    base_slug = re.sub(r"[^a-z0-9]+", "-", payload.organization_name.lower()).strip("-")
    slug = f"{base_slug}-{str(uuid4())[:8]}"

    # Create Organization
    org = Organization(
        name=payload.organization_name,
        slug=slug,
        status="active",
    )
    session.add(org)
    session.flush()

    # Create OrgMembership with OWNER role
    membership = OrgMembership(
        org_id=org.id,
        user_id=new_user.id,
        role=OrganizationRole.OWNER,
    )
    session.add(membership)

    # Initialize default MerchantEconomics for this organization
    economics = MerchantEconomics(org_id=org.id)
    session.add(economics)
    session.flush()

    # Record genesis audit log
    AuditService.record_event(
        session=session,
        org_id=org.id,
        actor_user_id=new_user.id,
        action="ORGANIZATION_INITIALIZED",
        resource_type="Organization",
        resource_id=str(org.id),
        payload={"organization_name": org.name, "owner_email": new_user.email},
    )

    session.commit()

    # Issue JWT tokens
    access_token = create_access_token(
        subject=str(new_user.id),
        claims={"email": new_user.email, "org_id": str(org.id)}
    )
    refresh_token = create_refresh_token(subject=str(new_user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, session: Session = Depends(get_db)):
    """Authenticates credentials and returns access and refresh tokens."""
    user = session.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Please contact support.",
        )

    access_token = create_access_token(
        subject=str(user.id),
        claims={"email": user.email}
    )
    refresh_token = create_refresh_token(subject=str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(payload: TokenRefresh, session: Session = Depends(get_db)):
    """Rotates refresh token and issues a new access token."""
    try:
        decoded = decode_token(payload.refresh_token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid refresh token: {str(e)}",
        )

    if decoded.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token provided is not a refresh token.",
        )

    jti = decoded.get("jti")
    if jti:
        is_revoked = session.scalar(select(RevokedToken).where(RevokedToken.jti == jti))
        if is_revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has been revoked.",
            )

    user_id = decoded.get("sub")
    user = session.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer active.",
        )

    # Invalidate previous refresh token (single-use rotation)
    if jti:
        exp_timestamp = decoded.get("exp", int(datetime.now(timezone.utc).timestamp()))
        revoked_record = RevokedToken(
            jti=jti,
            expires_at=datetime.fromtimestamp(exp_timestamp, tz=timezone.utc),
        )
        session.add(revoked_record)
        session.commit()

    # Issue fresh token pair
    new_access_token = create_access_token(subject=str(user.id), claims={"email": user.email})
    new_refresh_token = create_refresh_token(subject=str(user.id))

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(
    credentials=Depends(security_bearer),
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revokes the current access token and prevents its reuse."""
    try:
        decoded = decode_token(credentials.credentials)
        jti = decoded.get("jti")
        if jti:
            exp_timestamp = decoded.get("exp", int(datetime.now(timezone.utc).timestamp()))
            revoked_record = RevokedToken(
                jti=jti,
                expires_at=datetime.fromtimestamp(exp_timestamp, tz=timezone.utc),
            )
            session.add(revoked_record)
            session.commit()
    except Exception:
        pass

    return {"message": "Successfully logged out."}


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    """Returns profile information for the authenticated user."""
    return current_user
