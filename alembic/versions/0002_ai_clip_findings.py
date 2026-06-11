"""add ai_clip_findings (Milestone 3 — temporal/clip review)

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-07

The single approved schema addition for Milestone 3. Mirrors ai_frame_findings
but references clips. evas_schema.sql has been updated to match.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UPGRADE_SQL = r"""
CREATE TABLE ai_clip_findings (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ai_run_id    uuid NOT NULL REFERENCES ai_runs(id) ON DELETE CASCADE,
    clip_id      uuid NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    description  text,
    findings     jsonb NOT NULL,
    confidence   numeric(4,3),
    flagged      boolean NOT NULL DEFAULT false,
    UNIQUE (ai_run_id, clip_id)
);
CREATE INDEX idx_acf_run ON ai_clip_findings (ai_run_id);
CREATE INDEX idx_acf_flagged ON ai_clip_findings (ai_run_id) WHERE flagged;
"""

DOWNGRADE_SQL = r"""
DROP TABLE IF EXISTS ai_clip_findings;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UPGRADE_SQL)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWNGRADE_SQL)
