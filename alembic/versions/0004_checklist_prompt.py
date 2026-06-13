"""add checklists.prompt_template (UI-editable per-checklist framing)

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-13

Adds a nullable `prompt_template` column to `checklists`. It holds the
UI-editable *framing* for a client's review (the role/instructions prose); the
machine-readable output contract is appended by the AI layer at review time, so
findings stay parseable regardless of what an author types. NULL falls back to
the default framing. evas_schema.sql has been updated to match.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE checklists ADD COLUMN IF NOT EXISTS prompt_template text")


def downgrade() -> None:
    op.execute("ALTER TABLE checklists DROP COLUMN IF EXISTS prompt_template")
