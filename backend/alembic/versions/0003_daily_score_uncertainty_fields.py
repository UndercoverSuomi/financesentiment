"""add uncertainty fields to daily_scores

Revision ID: 0003_daily_score_uncertainty_fields
Revises: 0002_daily_score_stats_and_uniques
Create Date: 2026-02-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0003_daily_score_uncertainty_fields'
down_revision = '0002_daily_score_stats_and_uniques'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('daily_scores') as batch_op:
        batch_op.add_column(sa.Column('score_stddev_unweighted', sa.Float(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('ci95_low_unweighted', sa.Float(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('ci95_high_unweighted', sa.Float(), nullable=False, server_default='0'))

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE daily_scores
            SET
                score_stddev_unweighted = 0,
                ci95_low_unweighted = score_unweighted,
                ci95_high_unweighted = score_unweighted
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table('daily_scores') as batch_op:
        batch_op.drop_column('ci95_high_unweighted')
        batch_op.drop_column('ci95_low_unweighted')
        batch_op.drop_column('score_stddev_unweighted')
