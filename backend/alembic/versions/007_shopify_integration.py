"""Shopify Integration Tables with PostgreSQL RLS.

Revision ID: 007_shopify_integration
Revises: 006_real_order_outcomes
Create Date: 2026-10-12 17:05:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '007_shopify_integration'
down_revision: Union[str, None] = '006_real_order_outcomes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    json_col = postgresql.JSONB if is_postgres else sa.JSON

    # 1. shopify_stores
    op.create_table(
        'shopify_stores',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('org_id', sa.CHAR(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('shop_domain', sa.String(255), unique=True, nullable=False),
        sa.Column('access_token_encrypted', sa.Text(), nullable=True),
        sa.Column('webhook_secret_encrypted', sa.Text(), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='not_configured'),
        sa.Column('installed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('uninstalled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('scopes', sa.String(500), nullable=True, server_default='read_orders,write_orders'),
        sa.Column('api_version', sa.String(20), nullable=False, server_default='2024-01'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_shopify_stores_org_id', 'shopify_stores', ['org_id'])
    op.create_index('ix_shopify_stores_shop_domain', 'shopify_stores', ['shop_domain'])
    op.create_index('idx_shopify_stores_org_status', 'shopify_stores', ['org_id', 'status'])

    # 2. shopify_webhook_deliveries
    op.create_table(
        'shopify_webhook_deliveries',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('org_id', sa.CHAR(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True),
        sa.Column('shopify_store_id', sa.CHAR(36), sa.ForeignKey('shopify_stores.id', ondelete='SET NULL'), nullable=True),
        sa.Column('shopify_delivery_id', sa.String(100), unique=True, nullable=False),
        sa.Column('topic', sa.String(100), nullable=False),
        sa.Column('shop_domain', sa.String(255), nullable=False),
        sa.Column('shopify_order_id', sa.String(100), nullable=True),
        sa.Column('order_id', sa.CHAR(36), sa.ForeignKey('orders.id', ondelete='SET NULL'), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='RECEIVED'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('payload_summary', json_col, nullable=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_shopify_deliveries_org_id', 'shopify_webhook_deliveries', ['org_id'])
    op.create_index('ix_shopify_deliveries_store_id', 'shopify_webhook_deliveries', ['shopify_store_id'])
    op.create_index('ix_shopify_deliveries_delivery_id', 'shopify_webhook_deliveries', ['shopify_delivery_id'])
    op.create_index('ix_shopify_deliveries_topic', 'shopify_webhook_deliveries', ['topic'])
    op.create_index('ix_shopify_deliveries_shop_domain', 'shopify_webhook_deliveries', ['shop_domain'])
    op.create_index('ix_shopify_deliveries_order_id', 'shopify_webhook_deliveries', ['order_id'])
    op.create_index('idx_shopify_deliveries_org_topic', 'shopify_webhook_deliveries', ['org_id', 'topic'])
    op.create_index('idx_shopify_deliveries_org_status', 'shopify_webhook_deliveries', ['org_id', 'status'])

    # PostgreSQL Row-Level Security
    if is_postgres:
        op.execute("ALTER TABLE shopify_stores ENABLE ROW LEVEL SECURITY;")
        op.execute("""
            CREATE POLICY tenant_isolation_shopify_stores ON shopify_stores
            FOR ALL
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
            WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
        """)

        op.execute("ALTER TABLE shopify_webhook_deliveries ENABLE ROW LEVEL SECURITY;")
        op.execute("""
            CREATE POLICY tenant_isolation_shopify_deliveries ON shopify_webhook_deliveries
            FOR ALL
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
            WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
        """)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP POLICY IF EXISTS tenant_isolation_shopify_deliveries ON shopify_webhook_deliveries;")
        op.execute("DROP POLICY IF EXISTS tenant_isolation_shopify_stores ON shopify_stores;")

    op.drop_table('shopify_webhook_deliveries')
    op.drop_table('shopify_stores')
