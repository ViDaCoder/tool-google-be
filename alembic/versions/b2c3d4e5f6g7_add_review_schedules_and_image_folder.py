"""add_review_schedules_and_image_folder

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-10 17:03:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6g7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Bổ sung cột image_folder vào bảng businesses (nếu chưa có)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('businesses')]
    if 'image_folder' not in columns:
        op.add_column('businesses', sa.Column('image_folder', sa.String(length=500), nullable=True))

    # 2. Tạo bảng review_schedules (nếu chưa có)
    tables = inspector.get_table_names()
    if 'review_schedules' not in tables:
        op.create_table('review_schedules',
            sa.Column('id', sa.String(length=100), nullable=False),
            sa.Column('business_id', sa.String(length=100), nullable=False),
            sa.Column('gmail', sa.String(length=255), nullable=False),
            sa.Column('proxy', sa.String(length=255), nullable=False),
            sa.Column('rating', sa.Integer(), nullable=False, server_default='5'),
            sa.Column('review_text', sa.Text(), nullable=False),
            sa.Column('images', sa.JSON(), nullable=False),
            sa.Column('scheduled_at', sa.DateTime(), nullable=False),
            sa.Column('auto_submit', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('headless', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
            sa.Column('status_text', sa.Text(), nullable=True),
            sa.Column('user_email', sa.String(length=255), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )


def downgrade() -> None:
    op.drop_table('review_schedules')
    op.drop_column('businesses', 'image_folder')
