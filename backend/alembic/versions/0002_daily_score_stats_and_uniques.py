"""add aggregation sufficient stats and uniqueness constraints

Revision ID: 0002_daily_score_stats_and_uniques
Revises: 0001_initial
Create Date: 2026-02-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0002_daily_score_stats_and_uniques'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('daily_scores') as batch_op:
        batch_op.add_column(sa.Column('valid_count', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('score_sum_unweighted', sa.Float(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('weighted_numerator', sa.Float(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('weighted_denominator', sa.Float(), nullable=False, server_default='0'))

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE daily_scores
            SET
                valid_count = CASE WHEN mention_count > unclear_count THEN mention_count - unclear_count ELSE 0 END,
                score_sum_unweighted = CASE
                    WHEN mention_count > unclear_count THEN score_unweighted * (mention_count - unclear_count)
                    ELSE 0
                END,
                weighted_denominator = CASE
                    WHEN mention_count > unclear_count THEN (mention_count - unclear_count)
                    ELSE 0
                END,
                weighted_numerator = CASE
                    WHEN mention_count > unclear_count THEN score_weighted * (mention_count - unclear_count)
                    ELSE 0
                END
            """
        )
    )

    conn.execute(
        sa.text(
            """
            DELETE FROM mentions
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM mentions
                GROUP BY target_type, target_id, ticker
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            DELETE FROM stance
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM stance
                GROUP BY target_type, target_id, ticker
            )
            """
        )
    )

    with op.batch_alter_table('mentions') as batch_op:
        batch_op.create_unique_constraint('uq_mentions_target_ticker', ['target_type', 'target_id', 'ticker'])
    with op.batch_alter_table('stance') as batch_op:
        batch_op.create_unique_constraint('uq_stance_target_ticker', ['target_type', 'target_id', 'ticker'])


def downgrade() -> None:
    with op.batch_alter_table('stance') as batch_op:
        batch_op.drop_constraint('uq_stance_target_ticker', type_='unique')
    with op.batch_alter_table('mentions') as batch_op:
        batch_op.drop_constraint('uq_mentions_target_ticker', type_='unique')

    with op.batch_alter_table('daily_scores') as batch_op:
        batch_op.drop_column('weighted_denominator')
        batch_op.drop_column('weighted_numerator')
        batch_op.drop_column('score_sum_unweighted')
        batch_op.drop_column('valid_count')
