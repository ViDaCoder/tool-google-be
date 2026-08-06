"""add_missing_tables

Revision ID: a1b2c3d4e5f6
Revises: e35cfafe98d5
Create Date: 2026-08-06 11:35:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'e35cfafe98d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Tạo bảng system_settings
    op.create_table('system_settings',
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('key')
    )

    # 2. Tạo bảng gmail_proxies
    op.create_table('gmail_proxies',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('gmail_id', sa.Integer(), nullable=False),
        sa.Column('proxy_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['gmail_id'], ['gmail_accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['proxy_id'], ['proxies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('gmail_id')
    )

    # 3. Tạo bảng review_drafts
    op.create_table('review_drafts',
        sa.Column('id', sa.String(length=100), nullable=False),
        sa.Column('business_id', sa.String(length=100), nullable=False),
        sa.Column('business_name', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=255), nullable=True),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('tone', sa.String(length=50), nullable=False),
        sa.Column('language', sa.String(length=10), nullable=False),
        sa.Column('length', sa.String(length=20), nullable=False),
        sa.Column('custom_keywords', sa.JSON(), nullable=False),
        sa.Column('reviews', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('review_drafts')
    op.drop_table('gmail_proxies')
    op.drop_table('system_settings')
