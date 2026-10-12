"""Live ML Decisioning Schema Update.

Revision ID: 008_live_ml_decisioning
Revises: 007_shopify_integration
Create Date: 2026-10-12 17:55:00.000000

Adds ML decision tracking fields to order_evaluations and order_outcomes:
- recommended_action_deterministic
- recommended_action_ml_assisted
- decision_policy_version
- ml_operating_mode
- ml_decision_rationale
- final_recommendation (in outcomes)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '008_live_ml_decisioning'
down_revision: Union[str, None] = '007_shopify_integration'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. order_evaluations columns
    op.add_column('order_evaluations', sa.Column('recommended_action_deterministic', sa.String(50), nullable=True))
    op.add_column('order_evaluations', sa.Column('recommended_action_ml_assisted', sa.String(50), nullable=True))
    op.add_column('order_evaluations', sa.Column('decision_policy_version', sa.String(50), nullable=True))
    op.add_column('order_evaluations', sa.Column('ml_operating_mode', sa.String(50), nullable=True))
    op.add_column('order_evaluations', sa.Column('ml_decision_rationale', sa.Text(), nullable=True))

    # 2. order_outcomes columns
    op.add_column('order_outcomes', sa.Column('ml_assisted_recommendation', sa.String(50), nullable=True))
    op.add_column('order_outcomes', sa.Column('final_recommendation', sa.String(50), nullable=True))
    op.add_column('order_outcomes', sa.Column('ml_operating_mode', sa.String(50), nullable=True))
    op.add_column('order_outcomes', sa.Column('decision_policy_version', sa.String(50), nullable=True))


def downgrade() -> None:
    # 1. order_outcomes columns
    op.drop_column('order_outcomes', 'decision_policy_version')
    op.drop_column('order_outcomes', 'ml_operating_mode')
    op.drop_column('order_outcomes', 'final_recommendation')
    op.drop_column('order_outcomes', 'ml_assisted_recommendation')

    # 2. order_evaluations columns
    op.drop_column('order_evaluations', 'ml_decision_rationale')
    op.drop_column('order_evaluations', 'ml_operating_mode')
    op.drop_column('order_evaluations', 'decision_policy_version')
    op.drop_column('order_evaluations', 'recommended_action_ml_assisted')
    op.drop_column('order_evaluations', 'recommended_action_deterministic')
