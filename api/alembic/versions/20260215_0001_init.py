"""init

Revision ID: 20260215_0001
Revises:
Create Date: 2026-02-15
"""

from alembic import op
import sqlalchemy as sa

revision = '20260215_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('jobs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('lang', sa.String(length=5), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('progress_pct', sa.Float(), nullable=False),
        sa.Column('progress_message', sa.String(), nullable=False),
        sa.Column('summary', sa.JSON(), nullable=True),
        sa.Column('price_quote', sa.JSON(), nullable=True),
        sa.Column('preview', sa.JSON(), nullable=True),
        sa.Column('paid', sa.Boolean(), nullable=False),
        sa.Column('checkout_session_id', sa.String(), nullable=True),
        sa.Column('user_email', sa.String(), nullable=True),
        sa.Column('error_code', sa.String(), nullable=True),
        sa.Column('error_detail', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('job_files',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('path', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade() -> None:
    op.drop_table('job_files')
    op.drop_table('jobs')
