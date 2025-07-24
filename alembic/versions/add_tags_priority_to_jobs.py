"""Add tags and priority to jobs table

Revision ID: add_tags_priority_fields
Revises: 81481d6f6f74
Create Date: 2025-01-10 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = 'add_tags_priority_fields'
down_revision: Union[str, Sequence[str], None] = '81481d6f6f74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add tags and priority columns to jobs table."""
    # Add tags column (JSON field for list of strings)
    op.add_column('jobs', sa.Column('tags', sqlite.JSON(), nullable=True))

    # Add priority column (integer field with default 0)  
    op.add_column('jobs', sa.Column('priority', sa.Integer(), nullable=True))

    # Update existing rows to have default values
    op.execute("UPDATE jobs SET tags = '[]' WHERE tags IS NULL")
    op.execute("UPDATE jobs SET priority = 0 WHERE priority IS NULL")


def downgrade() -> None:
    """Remove tags and priority columns from jobs table."""
    op.drop_column('jobs', 'priority')
    op.drop_column('jobs', 'tags')
