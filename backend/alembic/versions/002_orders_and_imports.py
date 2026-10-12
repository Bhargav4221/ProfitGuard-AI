"""Orders and Two-Stage CSV Import Pipeline Tables with PostgreSQL RLS.

Revision ID: 002_orders_and_imports
Revises: 001_initial_foundation
Create Date: 2026-10-11 23:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '002_orders_and_imports'
down_revision: Union[str, None] = '001_initial_foundation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Import Jobs Table (Stage A & B tracking)
    op.create_table(
        'import_jobs',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('org_id', sa.CHAR(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_by_user_id', sa.CHAR(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='PREVIEW'),
        sa.Column('total_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('valid_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('invalid_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('duplicate_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('staged_data', postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.Text(), nullable=False, server_default='[]'),
        sa.Column('committed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_import_jobs_org_id', 'import_jobs', ['org_id'])
    op.create_index('idx_import_jobs_org_created', 'import_jobs', ['org_id', 'created_at'])

    # 2. Import Job Errors Table
    op.create_table(
        'import_job_errors',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('org_id', sa.CHAR(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('import_job_id', sa.CHAR(36), sa.ForeignKey('import_jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('row_index', sa.Integer(), nullable=False),
        sa.Column('external_order_id', sa.String(255), nullable=True),
        sa.Column('column_name', sa.String(100), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_import_job_errors_org_id', 'import_job_errors', ['org_id'])
    op.create_index('ix_import_job_errors_import_job_id', 'import_job_errors', ['import_job_id'])
    op.create_index('idx_import_errors_org_job', 'import_job_errors', ['org_id', 'import_job_id'])

    # 3. Orders Table
    op.create_table(
        'orders',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('org_id', sa.CHAR(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('external_order_id', sa.String(255), nullable=False),
        sa.Column('order_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, server_default='INR'),
        sa.Column('order_value', sa.Numeric(12, 2), nullable=False),
        sa.Column('payment_method', sa.String(50), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='PENDING'),
        sa.Column('fulfillment_status', sa.String(50), nullable=False, server_default='UNFULFILLED'),
        sa.Column('customer_name', sa.String(255), nullable=True),
        sa.Column('customer_phone', sa.String(50), nullable=True),
        sa.Column('customer_email', sa.String(255), nullable=True),
        sa.Column('shipping_address1', sa.Text(), nullable=True),
        sa.Column('shipping_address2', sa.Text(), nullable=True),
        sa.Column('shipping_city', sa.String(100), nullable=True),
        sa.Column('shipping_state', sa.String(100), nullable=True),
        sa.Column('shipping_pincode', sa.String(20), nullable=True),
        sa.Column('shipping_country', sa.String(10), nullable=False, server_default='IN'),
        sa.Column('courier_name', sa.String(100), nullable=True),
        sa.Column('tracking_number', sa.String(100), nullable=True),
        sa.Column('source_channel', sa.String(100), nullable=False, server_default='MANUAL'),
        sa.Column('import_job_id', sa.CHAR(36), sa.ForeignKey('import_jobs.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('org_id', 'external_order_id', name='uq_order_org_external_id'),
    )
    op.create_index('ix_orders_org_id', 'orders', ['org_id'])
    op.create_index('ix_orders_external_order_id', 'orders', ['external_order_id'])
    op.create_index('ix_orders_customer_phone', 'orders', ['customer_phone'])
    op.create_index('ix_orders_customer_email', 'orders', ['customer_email'])
    op.create_index('ix_orders_shipping_pincode', 'orders', ['shipping_pincode'])
    op.create_index('ix_orders_import_job_id', 'orders', ['import_job_id'])
    op.create_index('idx_orders_org_created', 'orders', ['org_id', 'created_at'])
    op.create_index('idx_orders_org_status', 'orders', ['org_id', 'status'])
    op.create_index('idx_orders_org_phone', 'orders', ['org_id', 'customer_phone'])

    # 4. Order Items Table
    op.create_table(
        'order_items',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('org_id', sa.CHAR(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('order_id', sa.CHAR(36), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sku', sa.String(100), nullable=True),
        sa.Column('external_product_id', sa.String(255), nullable=True),
        sa.Column('product_name', sa.String(255), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('unit_price', sa.Numeric(12, 2), nullable=False),
        sa.Column('unit_cost', sa.Numeric(12, 2), nullable=True),
        sa.Column('total_price', sa.Numeric(12, 2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('quantity >= 1', name='ck_order_item_quantity_positive'),
        sa.CheckConstraint('unit_price >= 0', name='ck_order_item_unit_price_non_neg'),
        sa.CheckConstraint('total_price >= 0', name='ck_order_item_total_price_non_neg'),
    )
    op.create_index('ix_order_items_org_id', 'order_items', ['org_id'])
    op.create_index('ix_order_items_order_id', 'order_items', ['order_id'])

    # 5. PostgreSQL Row-Level Security Policies
    if is_postgres:
        for table in ['import_jobs', 'import_job_errors', 'orders', 'order_items']:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            op.execute(f"""
                CREATE POLICY tenant_isolation_{table} ON {table}
                FOR ALL
                USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
                WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
            """)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        for table in ['order_items', 'orders', 'import_job_errors', 'import_jobs']:
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table};")

    op.drop_table('order_items')
    op.drop_table('orders')
    op.drop_table('import_job_errors')
    op.drop_table('import_jobs')
