"""Order Evaluations and Decisions Table with PostgreSQL RLS.

Revision ID: 003_order_evaluations
Revises: 002_orders_and_imports
Create Date: 2026-10-11 23:40:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '003_order_evaluations'
down_revision: Union[str, None] = '002_orders_and_imports'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.create_table(
        'order_evaluations',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('org_id', sa.CHAR(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('order_id', sa.CHAR(36), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('evaluated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('evaluated_by_user_id', sa.CHAR(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('recommended_action', sa.String(50), nullable=False),
        sa.Column('recommended_lift', sa.Numeric(12, 2), nullable=False, server_default='0.00'),
        sa.Column('ship_as_is_ec', sa.Numeric(12, 2), nullable=False),
        sa.Column('best_ec', sa.Numeric(12, 2), nullable=False),
        sa.Column('profit_at_risk', sa.Numeric(12, 2), nullable=False),
        sa.Column('baseline_p_rto', sa.Numeric(5, 4), nullable=False),
        sa.Column('uncertainty_score', sa.Numeric(5, 4), nullable=False),
        sa.Column('risk_tier', sa.String(20), nullable=False),
        sa.Column('comparison_data', postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.Text(), nullable=False, server_default='[]'),
        sa.Column('explanation_data', postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.Text(), nullable=False, server_default='{}'),
        sa.Column('decision_status', sa.String(50), nullable=False, server_default='EVALUATED'),
        sa.Column('selected_action', sa.String(50), nullable=True),
        sa.Column('override_reason', sa.Text(), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decided_by_user_id', sa.CHAR(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('intervention_status', sa.String(50), nullable=False, server_default='NONE'),
        sa.Column('intervention_notes', sa.Text(), nullable=True),
        sa.Column('intervention_resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_order_evaluations_org_id', 'order_evaluations', ['org_id'])
    op.create_index('ix_order_evaluations_order_id', 'order_evaluations', ['order_id'])
    op.create_index('idx_order_eval_org_created', 'order_evaluations', ['org_id', 'created_at'])
    op.create_index('idx_order_eval_org_order', 'order_evaluations', ['org_id', 'order_id'])
    op.create_index('idx_order_eval_org_status', 'order_evaluations', ['org_id', 'decision_status'])

    # PostgreSQL Row-Level Security
    if is_postgres:
        op.execute("ALTER TABLE order_evaluations ENABLE ROW LEVEL SECURITY;")
        op.execute("""
            CREATE POLICY tenant_isolation_order_evaluations ON order_evaluations
            FOR ALL
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
            WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
        """)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP POLICY IF EXISTS tenant_isolation_order_evaluations ON order_evaluations;")

    op.drop_table('order_evaluations')
