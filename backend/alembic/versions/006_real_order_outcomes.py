"""Real-Order Outcome Tracking Table with PostgreSQL RLS.

Revision ID: 006_real_order_outcomes
Revises: 005_financial_reconciliation
Create Date: 2026-10-12 16:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '006_real_order_outcomes'
down_revision: Union[str, None] = '005_financial_reconciliation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    json_col = postgresql.JSONB if is_postgres else sa.JSON

    op.create_table(
        'order_outcomes',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('org_id', sa.CHAR(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('order_id', sa.CHAR(36), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('external_order_id', sa.String(255), nullable=False),
        sa.Column('evaluation_id', sa.CHAR(36), sa.ForeignKey('order_evaluations.id', ondelete='SET NULL'), nullable=True),
        sa.Column('reconciliation_id', sa.CHAR(36), sa.ForeignKey('financial_reconciliations.id', ondelete='SET NULL'), nullable=True),
        sa.Column('model_version', sa.String(100), nullable=True),
        sa.Column('feature_contract_version', sa.String(50), nullable=True),
        sa.Column('prediction_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('prediction_feature_ref', sa.String(255), nullable=True),
        sa.Column('prediction_features_snapshot', json_col, nullable=True),
        sa.Column('predicted_p_rto', sa.Numeric(5, 4), nullable=True),
        sa.Column('predicted_risk_tier', sa.String(20), nullable=True),
        sa.Column('deterministic_recommendation', sa.String(50), nullable=False),
        sa.Column('merchant_approved_action', sa.String(50), nullable=True),
        sa.Column('intervention_status', sa.String(50), nullable=False, server_default='NONE'),
        sa.Column('intervention_cost', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('final_delivery_outcome', sa.String(50), nullable=False),
        sa.Column('carrier_name', sa.String(100), nullable=True),
        sa.Column('tracking_number', sa.String(100), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rto_reason_code', sa.String(100), nullable=True),
        sa.Column('rto_reason_description', sa.Text(), nullable=True),
        sa.Column('realized_order_value', sa.Numeric(12, 2), nullable=False),
        sa.Column('realized_collected_revenue', sa.Numeric(12, 2), nullable=False, server_default='0.00'),
        sa.Column('realized_cogs', sa.Numeric(12, 2), nullable=False, server_default='0.00'),
        sa.Column('realized_shipping_cost', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('realized_damage_cost', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('realized_rto_loss', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('realized_contribution', sa.Numeric(12, 2), nullable=False),
        sa.Column('expected_contribution', sa.Numeric(12, 2), nullable=True),
        sa.Column('variance_ec_vs_rc', sa.Numeric(12, 2), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('recorded_by_user_id', sa.CHAR(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('org_id', 'order_id', name='uq_order_outcomes_org_order'),
    )
    op.create_index('ix_order_outcomes_org_id', 'order_outcomes', ['org_id'])
    op.create_index('ix_order_outcomes_order_id', 'order_outcomes', ['order_id'])
    op.create_index('idx_order_outcomes_org_terminal', 'order_outcomes', ['org_id', 'final_delivery_outcome'])
    op.create_index('idx_order_outcomes_org_recorded', 'order_outcomes', ['org_id', 'recorded_at'])
    op.create_index('idx_order_outcomes_org_model', 'order_outcomes', ['org_id', 'model_version'])

    # PostgreSQL Row-Level Security
    if is_postgres:
        op.execute("ALTER TABLE order_outcomes ENABLE ROW LEVEL SECURITY;")
        op.execute("""
            CREATE POLICY tenant_isolation_order_outcomes ON order_outcomes
            FOR ALL
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
            WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
        """)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP POLICY IF EXISTS tenant_isolation_order_outcomes ON order_outcomes;")

    op.drop_table('order_outcomes')
