"""Order Financial Reconciliation Table with PostgreSQL RLS.

Revision ID: 005_financial_reconciliation
Revises: 004_delivery_lifecycle_and_ndr
Create Date: 2026-10-12 00:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '005_financial_reconciliation'
down_revision: Union[str, None] = '004_delivery_lifecycle_and_ndr'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.create_table(
        'financial_reconciliations',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('org_id', sa.CHAR(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('order_id', sa.CHAR(36), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('external_order_id', sa.String(255), nullable=False),
        sa.Column('terminal_status', sa.String(50), nullable=False),
        sa.Column('order_value', sa.Numeric(12, 2), nullable=False),
        sa.Column('collected_revenue', sa.Numeric(12, 2), nullable=False, server_default='0.00'),
        sa.Column('cogs', sa.Numeric(12, 2), nullable=False, server_default='0.00'),
        sa.Column('forward_shipping_cost', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('reverse_shipping_cost', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('payment_fee', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('packaging_cost', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('inventory_damage_cost', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('pre_dispatch_intervention_cost', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('ndr_recovery_intervention_cost', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('realized_contribution', sa.Numeric(12, 2), nullable=False),
        sa.Column('expected_contribution', sa.Numeric(12, 2), nullable=True),
        sa.Column('variance_ec_vs_rc', sa.Numeric(12, 2), nullable=True),
        sa.Column('reconciliation_status', sa.String(50), nullable=False, server_default='SETTLED'),
        sa.Column('accounting_notes', sa.Text(), nullable=True),
        sa.Column('reconciled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('org_id', 'order_id', name='uq_reconciliation_org_order'),
    )
    op.create_index('ix_financial_reconciliations_org_id', 'financial_reconciliations', ['org_id'])
    op.create_index('ix_financial_reconciliations_order_id', 'financial_reconciliations', ['order_id'])
    op.create_index('idx_reconciliation_org_status', 'financial_reconciliations', ['org_id', 'terminal_status'])
    op.create_index('idx_reconciliation_org_created', 'financial_reconciliations', ['org_id', 'created_at'])

    # PostgreSQL Row-Level Security
    if is_postgres:
        op.execute("ALTER TABLE financial_reconciliations ENABLE ROW LEVEL SECURITY;")
        op.execute("""
            CREATE POLICY tenant_isolation_financial_reconciliations ON financial_reconciliations
            FOR ALL
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
            WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
        """)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP POLICY IF EXISTS tenant_isolation_financial_reconciliations ON financial_reconciliations;")

    op.drop_table('financial_reconciliations')
