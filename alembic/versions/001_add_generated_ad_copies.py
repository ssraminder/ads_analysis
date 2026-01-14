"""Add generated_ad_copies table

Revision ID: 001_add_generated_ad_copies
Revises:
Create Date: 2026-01-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_add_generated_ad_copies'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create generated_ad_copies table
    op.create_table(
        'generated_ad_copies',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('keyword_id', sa.Integer(), nullable=False),
        sa.Column('headline_1', sa.String(30), nullable=False),
        sa.Column('headline_2', sa.String(30), nullable=False),
        sa.Column('headline_3', sa.String(30), nullable=True),
        sa.Column('description_1', sa.String(90), nullable=False),
        sa.Column('description_2', sa.String(90), nullable=True),
        sa.Column('display_path_1', sa.String(15), nullable=True),
        sa.Column('display_path_2', sa.String(15), nullable=True),
        sa.Column('call_to_action', sa.String(50), nullable=True),
        sa.Column('target_audience', sa.String(200), nullable=True),
        sa.Column('unique_selling_points', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('tone', sa.String(50), nullable=False, server_default='professional'),
        sa.Column('conversion_focus', sa.String(100), nullable=True),
        sa.Column('competitor_insights_used', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('quality_score', sa.Integer(), nullable=True),
        sa.Column('is_favorite', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['keyword_id'], ['keywords.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index('ix_generated_ad_copies_keyword_id', 'generated_ad_copies', ['keyword_id'])
    op.create_index('ix_generated_ad_copies_keyword_created', 'generated_ad_copies', ['keyword_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_generated_ad_copies_keyword_created', table_name='generated_ad_copies')
    op.drop_index('ix_generated_ad_copies_keyword_id', table_name='generated_ad_copies')
    op.drop_table('generated_ad_copies')
