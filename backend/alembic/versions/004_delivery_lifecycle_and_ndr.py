"""Delivery Lifecycle Events and NDR Recovery Tables with PostgreSQL RLS.

Revision ID: 004_delivery_lifecycle_and_ndr
Revises: 003_order_evaluations
Create Date: 2026-10-12 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '004_delivery_lifecycle_and_ndr'
down_revision: Union[str, None] = '003_order_evaluations'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Delivery Events Table
    op.create_table(
        'delivery_events',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('org_id', sa.CHAR(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('order_id', sa.CHAR(36), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_id', sa.String(255), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('previous_status', sa.String(50), nullable=True),
        sa.Column('new_status', sa.String(50), nullable=False),
        sa.Column('event_source', sa.String(50), nullable=False, server_default='SYSTEM'),
        sa.Column('is_simulated', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('carrier_name', sa.String(100), nullable=True),
        sa.Column('tracking_number', sa.String(100), nullable=True),
        sa.Column('carrier_status_code', sa.String(50), nullable=True),
        sa.Column('reason_code', sa.String(100), nullable=True),
        sa.Column('reason_description', sa.Text(), nullable=True),
        sa.Column('location', sa.String(255), nullable=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('org_id', 'event_id', name='uq_delivery_events_org_event_id'),
    )
    op.create_index('ix_delivery_events_org_id', 'delivery_events', ['org_id'])
    op.create_index('ix_delivery_events_order_id', 'delivery_events', ['order_id'])
    op.create_index('idx_delivery_events_org_order', 'delivery_events', ['org_id', 'order_id'])
    op.create_index('idx_delivery_events_org_occurred', 'delivery_events', ['org_id', 'occurred_at'])

    # 2. NDR Cases Table
    op.create_table(
        'ndr_cases',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('org_id', sa.CHAR(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('order_id', sa.CHAR(36), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('case_number', sa.String(50), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='OPEN'),
        sa.Column('priority', sa.String(20), nullable=False, server_default='MEDIUM'),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('last_attempt_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reason_code', sa.String(100), nullable=False),
        sa.Column('carrier_reason_raw', sa.Text(), nullable=True),
        sa.Column('assigned_operator_id', sa.CHAR(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('assigned_operator_name', sa.String(255), nullable=True),
        sa.Column('customer_contacted', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('contact_method', sa.String(50), nullable=True),
        sa.Column('customer_response', sa.Text(), nullable=True),
        sa.Column('updated_address1', sa.Text(), nullable=True),
        sa.Column('updated_address2', sa.Text(), nullable=True),
        sa.Column('updated_city', sa.String(100), nullable=True),
        sa.Column('updated_state', sa.String(100), nullable=True),
        sa.Column('updated_pincode', sa.String(20), nullable=True),
        sa.Column('updated_phone', sa.String(50), nullable=True),
        sa.Column('reattempt_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_action', sa.String(100), nullable=True),
        sa.Column('next_action_due', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_simulated', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('expected_recovery_lift', sa.Numeric(12, 2), nullable=True),
        sa.Column('estimated_recovery_ec', sa.Numeric(12, 2), nullable=True),
        sa.Column('recommended_recovery_action', sa.String(50), nullable=True),
        sa.Column('recommendation_rationale', sa.Text(), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closed_by_user_id', sa.CHAR(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('closure_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('org_id', 'case_number', name='uq_ndr_cases_org_case_num'),
    )
    op.create_index('ix_ndr_cases_org_id', 'ndr_cases', ['org_id'])
    op.create_index('ix_ndr_cases_order_id', 'ndr_cases', ['order_id'])
    op.create_index('idx_ndr_cases_org_status', 'ndr_cases', ['org_id', 'status'])
    op.create_index('idx_ndr_cases_org_order', 'ndr_cases', ['org_id', 'order_id'])
    op.create_index('idx_ndr_cases_org_priority', 'ndr_cases', ['org_id', 'priority'])

    # 3. NDR Action Logs Table
    op.create_table(
        'ndr_action_logs',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('org_id', sa.CHAR(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ndr_case_id', sa.CHAR(36), sa.ForeignKey('ndr_cases.id', ondelete='CASCADE'), nullable=False),
        sa.Column('order_id', sa.CHAR(36), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('actor_user_id', sa.CHAR(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action_type', sa.String(50), nullable=False),
        sa.Column('action_details', postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.Text(), nullable=False, server_default='{}'),
        sa.Column('intervention_cost', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_ndr_action_logs_org_id', 'ndr_action_logs', ['org_id'])
    op.create_index('ix_ndr_action_logs_case_id', 'ndr_action_logs', ['ndr_case_id'])
    op.create_index('idx_ndr_actions_org_case', 'ndr_action_logs', ['org_id', 'ndr_case_id'])
    op.create_index('idx_ndr_actions_org_created', 'ndr_action_logs', ['org_id', 'created_at'])

    # PostgreSQL Row-Level Security
    if is_postgres:
        op.execute("ALTER TABLE delivery_events ENABLE ROW LEVEL SECURITY;")
        op.execute("""
            CREATE POLICY tenant_isolation_delivery_events ON delivery_events
            FOR ALL
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
            WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
        """)

        op.execute("ALTER TABLE ndr_cases ENABLE ROW LEVEL SECURITY;")
        op.execute("""
            CREATE POLICY tenant_isolation_ndr_cases ON ndr_cases
            FOR ALL
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
            WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
        """)

        op.execute("ALTER TABLE ndr_action_logs ENABLE ROW LEVEL SECURITY;")
        op.execute("""
            CREATE POLICY tenant_isolation_ndr_action_logs ON ndr_action_logs
            FOR ALL
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
            WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
        """)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP POLICY IF EXISTS tenant_isolation_ndr_action_logs ON ndr_action_logs;")
        op.execute("DROP POLICY IF EXISTS tenant_isolation_ndr_cases ON ndr_cases;")
        op.execute("DROP POLICY IF EXISTS tenant_isolation_delivery_events ON delivery_events;")

    op.drop_table('ndr_action_logs')
    op.drop_table('ndr_cases')
    op.drop_table('delivery_events')
