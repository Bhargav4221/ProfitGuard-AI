"""Meta WhatsApp Business Cloud API Integration Schema.

Revision ID: 009_whatsapp_integration
Revises: 008_live_ml_decisioning
Create Date: 2026-10-12 19:48:00.000000

Creates:
- whatsapp_configs: Per-tenant Meta WABA credentials and operating mode.
- whatsapp_messages: Outbound and inbound WhatsApp messages, statuses, costs, and timestamps.
- whatsapp_opt_outs: Customer STOP/opt-out registry.
- whatsapp_webhook_events: Idempotent webhook event receipt log.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '009_whatsapp_integration'
down_revision: Union[str, None] = '008_live_ml_decisioning'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    json_col = postgresql.JSONB if is_postgres else sa.JSON

    # 1. whatsapp_configs
    op.create_table(
        'whatsapp_configs',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('org_id', sa.CHAR(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('phone_number_id', sa.String(100), nullable=True),
        sa.Column('business_account_id', sa.String(100), nullable=True),
        sa.Column('access_token_encrypted', sa.Text(), nullable=True),
        sa.Column('app_secret_encrypted', sa.Text(), nullable=True),
        sa.Column('webhook_verify_token', sa.String(255), nullable=True, server_default='profitguard_whatsapp_verify_token_default'),
        sa.Column('operating_mode', sa.String(50), nullable=False, server_default='MOCK'),
        sa.Column('status', sa.String(50), nullable=False, server_default='NOT_CONFIGURED'),
        sa.Column('verified_name', sa.String(255), nullable=True),
        sa.Column('quality_rating', sa.String(50), nullable=True),
        sa.Column('api_version', sa.String(20), nullable=False, server_default='v20.0'),
        sa.Column('webhook_url', sa.String(500), nullable=True),
        sa.Column('last_webhook_received_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('org_id', name='uq_whatsapp_configs_org_id'),
    )
    op.create_index('ix_whatsapp_configs_org_id', 'whatsapp_configs', ['org_id'])
    op.create_index('ix_whatsapp_configs_phone_number_id', 'whatsapp_configs', ['phone_number_id'])
    op.create_index('idx_whatsapp_configs_org_mode', 'whatsapp_configs', ['org_id', 'operating_mode'])

    # 2. whatsapp_messages
    op.create_table(
        'whatsapp_messages',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('org_id', sa.CHAR(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('whatsapp_config_id', sa.CHAR(36), sa.ForeignKey('whatsapp_configs.id', ondelete='SET NULL'), nullable=True),
        sa.Column('order_id', sa.CHAR(36), sa.ForeignKey('orders.id', ondelete='SET NULL'), nullable=True),
        sa.Column('ndr_case_id', sa.CHAR(36), sa.ForeignKey('ndr_cases.id', ondelete='SET NULL'), nullable=True),
        sa.Column('wamid', sa.String(150), unique=True, nullable=True),
        sa.Column('direction', sa.String(20), nullable=False, server_default='OUTBOUND'),
        sa.Column('recipient_phone', sa.String(30), nullable=False),
        sa.Column('sender_phone', sa.String(30), nullable=True),
        sa.Column('message_type', sa.String(50), nullable=False, server_default='TEMPLATE'),
        sa.Column('template_name', sa.String(100), nullable=True),
        sa.Column('body_preview', sa.Text(), nullable=True),
        sa.Column('status', sa.String(30), nullable=False, server_default='QUEUED'),
        sa.Column('error_code', sa.String(50), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('intervention_cost', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('raw_payload', json_col, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_whatsapp_messages_org_id', 'whatsapp_messages', ['org_id'])
    op.create_index('ix_whatsapp_messages_wamid', 'whatsapp_messages', ['wamid'])
    op.create_index('ix_whatsapp_messages_order_id', 'whatsapp_messages', ['order_id'])
    op.create_index('ix_whatsapp_messages_ndr_case_id', 'whatsapp_messages', ['ndr_case_id'])
    op.create_index('ix_whatsapp_messages_recipient_phone', 'whatsapp_messages', ['recipient_phone'])
    op.create_index('idx_whatsapp_messages_org_status', 'whatsapp_messages', ['org_id', 'status'])
    op.create_index('idx_whatsapp_messages_org_order', 'whatsapp_messages', ['org_id', 'order_id'])

    # 3. whatsapp_opt_outs
    op.create_table(
        'whatsapp_opt_outs',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('org_id', sa.CHAR(36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('phone_number', sa.String(30), nullable=False),
        sa.Column('opted_out_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reason', sa.String(100), nullable=False, server_default='CUSTOMER_REQUEST'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('org_id', 'phone_number', name='uq_whatsapp_opt_outs_org_phone'),
    )
    op.create_index('ix_whatsapp_opt_outs_org_id', 'whatsapp_opt_outs', ['org_id'])
    op.create_index('ix_whatsapp_opt_outs_phone_number', 'whatsapp_opt_outs', ['phone_number'])
    op.create_index('idx_whatsapp_opt_outs_org_phone', 'whatsapp_opt_outs', ['org_id', 'phone_number'])

    # 4. whatsapp_webhook_events
    op.create_table(
        'whatsapp_webhook_events',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('org_id', sa.CHAR(36), sa.ForeignKey('organizations.id', ondelete='SET NULL'), nullable=True),
        sa.Column('event_id', sa.String(150), unique=True, nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='PROCESSED'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('raw_payload', json_col, nullable=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_whatsapp_webhook_events_event_id', 'whatsapp_webhook_events', ['event_id'])

    # PostgreSQL Row-Level Security
    if is_postgres:
        op.execute("ALTER TABLE whatsapp_configs ENABLE ROW LEVEL SECURITY;")
        op.execute("""
            CREATE POLICY tenant_isolation_whatsapp_configs ON whatsapp_configs
            FOR ALL
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
            WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
        """)

        op.execute("ALTER TABLE whatsapp_messages ENABLE ROW LEVEL SECURITY;")
        op.execute("""
            CREATE POLICY tenant_isolation_whatsapp_messages ON whatsapp_messages
            FOR ALL
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
            WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
        """)

        op.execute("ALTER TABLE whatsapp_opt_outs ENABLE ROW LEVEL SECURITY;")
        op.execute("""
            CREATE POLICY tenant_isolation_whatsapp_opt_outs ON whatsapp_opt_outs
            FOR ALL
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
            WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
        """)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP POLICY IF EXISTS tenant_isolation_whatsapp_opt_outs ON whatsapp_opt_outs;")
        op.execute("DROP POLICY IF EXISTS tenant_isolation_whatsapp_messages ON whatsapp_messages;")
        op.execute("DROP POLICY IF EXISTS tenant_isolation_whatsapp_configs ON whatsapp_configs;")

    op.drop_table('whatsapp_webhook_events')
    op.drop_table('whatsapp_opt_outs')
    op.drop_table('whatsapp_messages')
    op.drop_table('whatsapp_configs')
