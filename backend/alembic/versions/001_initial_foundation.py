"""Initial Foundation: Users, Organizations, Memberships, Economics, Tokens, AuditLogs, and PostgreSQL RLS.

Revision ID: 001_initial_foundation
Revises: 
Create Date: 2026-10-11 22:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001_initial_foundation'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Detect dialect
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Users Table
    op.create_table(
        'users',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1' if not is_postgres else 'true')),
        sa.Column('is_superadmin', sa.Boolean(), nullable=False, server_default=sa.text('0' if not is_postgres else 'false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_users_email', 'users', ['email'])

    # 2. Organizations Table
    op.create_table(
        'organizations',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False, unique=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_organizations_slug', 'organizations', ['slug'])

    # 3. Organization Memberships Table
    role_enum = sa.Enum('OWNER', 'ADMIN', 'OPERATOR', 'AUDITOR', name='org_role_enum')
    op.create_table(
        'org_memberships',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('org_id', sa.CHAR(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.CHAR(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', role_enum, nullable=False, server_default='OPERATOR'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('org_id', 'user_id', name='uq_org_membership_user'),
    )
    op.create_index('ix_org_memberships_org_id', 'org_memberships', ['org_id'])
    op.create_index('ix_org_memberships_user_id', 'org_memberships', ['user_id'])

    # 4. Merchant Economics Table
    op.create_table(
        'merchant_economics',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('org_id', sa.CHAR(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('default_cogs_percent', sa.Numeric(5, 2), nullable=False, server_default='30.00'),
        sa.Column('forward_shipping_cost', sa.Numeric(10, 2), nullable=False, server_default='70.00'),
        sa.Column('reverse_shipping_cost', sa.Numeric(10, 2), nullable=False, server_default='65.00'),
        sa.Column('packaging_cost', sa.Numeric(10, 2), nullable=False, server_default='20.00'),
        sa.Column('cod_carrier_fee', sa.Numeric(10, 2), nullable=False, server_default='35.00'),
        sa.Column('cod_fee_incurred_on', sa.String(50), nullable=False, server_default='UPON_DELIVERY_ONLY'),
        sa.Column('payment_gateway_percent', sa.Numeric(5, 2), nullable=False, server_default='2.00'),
        sa.Column('payment_gateway_flat', sa.Numeric(10, 2), nullable=False, server_default='3.00'),
        sa.Column('inventory_damage_rate', sa.Numeric(5, 4), nullable=False, server_default='0.0500'),
        sa.Column('otp_verification_cost', sa.Numeric(10, 2), nullable=False, server_default='0.50'),
        sa.Column('manual_review_cost', sa.Numeric(10, 2), nullable=False, server_default='18.00'),
        sa.Column('prepaid_incentive_discount', sa.Numeric(10, 2), nullable=False, server_default='50.00'),
        sa.Column('prepaid_comms_cost', sa.Numeric(10, 2), nullable=False, server_default='0.50'),
        sa.Column('tax_accounting_mode', sa.String(50), nullable=False, server_default='TAX_EXCLUSIVE_NET'),
        sa.Column('allow_auto_cancel', sa.Boolean(), nullable=False, server_default=sa.text('0' if not is_postgres else 'false')),
        sa.Column('enable_holdout_experiment', sa.Boolean(), nullable=False, server_default=sa.text('0' if not is_postgres else 'false')),
        sa.Column('holdout_percentage', sa.Numeric(5, 2), nullable=False, server_default='5.00'),
        sa.Column('safety_value_cap', sa.Numeric(10, 2), nullable=False, server_default='3500.00'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_merchant_economics_org_id', 'merchant_economics', ['org_id'])

    # 5. Revoked Tokens Table
    op.create_table(
        'revoked_tokens',
        sa.Column('jti', sa.String(36), primary_key=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_revoked_tokens_jti', 'revoked_tokens', ['jti'])
    op.create_index('ix_revoked_tokens_expires_at', 'revoked_tokens', ['expires_at'])

    # 6. Audit Logs Table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('org_id', sa.CHAR(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sequence_number', sa.BigInteger(), nullable=False),
        sa.Column('actor_user_id', sa.CHAR(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('resource_type', sa.String(100), nullable=False),
        sa.Column('resource_id', sa.String(255), nullable=True),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.Text(), nullable=False),
        sa.Column('previous_hash', sa.String(64), nullable=False),
        sa.Column('current_hash', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('idx_audit_org_seq', 'audit_logs', ['org_id', 'sequence_number'], unique=True)
    op.create_index('idx_audit_org_created', 'audit_logs', ['org_id', 'created_at'])

    # 7. PostgreSQL Row-Level Security (RLS) Policies
    if is_postgres:
        # Enable RLS on tenant-owned tables
        op.execute("ALTER TABLE merchant_economics ENABLE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;")

        # Create policies enforcing app.current_org_id setting
        op.execute("""
            CREATE POLICY tenant_isolation_economics ON merchant_economics
            FOR ALL
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
            WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
        """)
        op.execute("""
            CREATE POLICY tenant_isolation_audit ON audit_logs
            FOR ALL
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
            WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
        """)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP POLICY IF EXISTS tenant_isolation_audit ON audit_logs;")
        op.execute("DROP POLICY IF EXISTS tenant_isolation_economics ON merchant_economics;")

    op.drop_table('audit_logs')
    op.drop_table('revoked_tokens')
    op.drop_table('merchant_economics')
    op.drop_table('org_memberships')
    op.drop_table('organizations')
    op.drop_table('users')

    if is_postgres:
        sa.Enum(name='org_role_enum').drop(bind, checkfirst=True)
