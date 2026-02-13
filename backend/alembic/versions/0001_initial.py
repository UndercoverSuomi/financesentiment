"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-02-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'pull_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('pulled_at_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('date_bucket_berlin', sa.Date(), nullable=False),
        sa.Column('subreddit', sa.String(length=64), nullable=False),
        sa.Column('sort', sa.String(length=32), nullable=False),
        sa.Column('t_param', sa.String(length=32), nullable=False),
        sa.Column('limit', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
    )
    op.create_index('ix_pull_runs_pulled_at_utc', 'pull_runs', ['pulled_at_utc'])
    op.create_index('ix_pull_runs_date_bucket_berlin', 'pull_runs', ['date_bucket_berlin'])
    op.create_index('ix_pull_runs_subreddit', 'pull_runs', ['subreddit'])

    op.create_table(
        'submissions',
        sa.Column('id', sa.String(length=32), primary_key=True),
        sa.Column('subreddit', sa.String(length=64), nullable=False),
        sa.Column('created_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('selftext', sa.Text(), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.Column('num_comments', sa.Integer(), nullable=False),
        sa.Column('permalink', sa.Text(), nullable=False),
        sa.Column('pull_run_id', sa.Integer(), sa.ForeignKey('pull_runs.id', ondelete='CASCADE'), nullable=False),
    )
    op.create_index('ix_submissions_subreddit', 'submissions', ['subreddit'])
    op.create_index('ix_submissions_created_utc', 'submissions', ['created_utc'])
    op.create_index('ix_submissions_pull_run_id', 'submissions', ['pull_run_id'])

    op.create_table(
        'comments',
        sa.Column('id', sa.String(length=32), primary_key=True),
        sa.Column('submission_id', sa.String(length=32), sa.ForeignKey('submissions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('parent_id', sa.String(length=32), nullable=True),
        sa.Column('depth', sa.Integer(), nullable=False),
        sa.Column('author', sa.String(length=128), nullable=True),
        sa.Column('created_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('permalink', sa.Text(), nullable=False),
    )
    op.create_index('ix_comments_submission_id', 'comments', ['submission_id'])
    op.create_index('ix_comments_created_utc', 'comments', ['created_utc'])

    op.create_table(
        'external_content',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('submission_id', sa.String(length=32), sa.ForeignKey('submissions.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('external_url', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_external_content_submission_id', 'external_content', ['submission_id'])

    op.create_table(
        'images',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('submission_id', sa.String(length=32), sa.ForeignKey('submissions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('image_url', sa.Text(), nullable=False),
        sa.Column('local_path', sa.Text(), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False),
    )
    op.create_index('ix_images_submission_id', 'images', ['submission_id'])

    op.create_table(
        'mentions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('target_type', sa.String(length=16), nullable=False),
        sa.Column('target_id', sa.String(length=32), nullable=False),
        sa.Column('ticker', sa.String(length=16), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('span_start', sa.Integer(), nullable=False),
        sa.Column('span_end', sa.Integer(), nullable=False),
    )
    op.create_index('ix_mentions_ticker', 'mentions', ['ticker'])
    op.create_index('ix_mentions_target_type_target_id', 'mentions', ['target_type', 'target_id'])

    op.create_table(
        'stance',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('target_type', sa.String(length=16), nullable=False),
        sa.Column('target_id', sa.String(length=32), nullable=False),
        sa.Column('ticker', sa.String(length=16), nullable=False),
        sa.Column('stance_label', sa.String(length=16), nullable=False),
        sa.Column('stance_score', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('model_version', sa.String(length=64), nullable=False),
        sa.Column('context_text', sa.Text(), nullable=False),
    )
    op.create_index('ix_stance_ticker', 'stance', ['ticker'])
    op.create_index('ix_stance_target_type_target_id', 'stance', ['target_type', 'target_id'])

    op.create_table(
        'daily_scores',
        sa.Column('date_bucket_berlin', sa.Date(), nullable=False),
        sa.Column('subreddit', sa.String(length=64), nullable=False),
        sa.Column('ticker', sa.String(length=16), nullable=False),
        sa.Column('score_unweighted', sa.Float(), nullable=False),
        sa.Column('score_weighted', sa.Float(), nullable=False),
        sa.Column('mention_count', sa.Integer(), nullable=False),
        sa.Column('bullish_count', sa.Integer(), nullable=False),
        sa.Column('bearish_count', sa.Integer(), nullable=False),
        sa.Column('neutral_count', sa.Integer(), nullable=False),
        sa.Column('unclear_count', sa.Integer(), nullable=False),
        sa.Column('unclear_rate', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('date_bucket_berlin', 'subreddit', 'ticker'),
    )
    op.create_index('ix_daily_scores_date_subreddit_ticker', 'daily_scores', ['date_bucket_berlin', 'subreddit', 'ticker'])

    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # Alembic defaults this column to VARCHAR(32), but our revision IDs are longer.
        op.execute(sa.text('ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)'))


def downgrade() -> None:
    op.drop_index('ix_daily_scores_date_subreddit_ticker', table_name='daily_scores')
    op.drop_table('daily_scores')

    op.drop_index('ix_stance_target_type_target_id', table_name='stance')
    op.drop_index('ix_stance_ticker', table_name='stance')
    op.drop_table('stance')

    op.drop_index('ix_mentions_target_type_target_id', table_name='mentions')
    op.drop_index('ix_mentions_ticker', table_name='mentions')
    op.drop_table('mentions')

    op.drop_index('ix_images_submission_id', table_name='images')
    op.drop_table('images')

    op.drop_index('ix_external_content_submission_id', table_name='external_content')
    op.drop_table('external_content')

    op.drop_index('ix_comments_created_utc', table_name='comments')
    op.drop_index('ix_comments_submission_id', table_name='comments')
    op.drop_table('comments')

    op.drop_index('ix_submissions_pull_run_id', table_name='submissions')
    op.drop_index('ix_submissions_created_utc', table_name='submissions')
    op.drop_index('ix_submissions_subreddit', table_name='submissions')
    op.drop_table('submissions')

    op.drop_index('ix_pull_runs_subreddit', table_name='pull_runs')
    op.drop_index('ix_pull_runs_date_bucket_berlin', table_name='pull_runs')
    op.drop_index('ix_pull_runs_pulled_at_utc', table_name='pull_runs')
    op.drop_table('pull_runs')
