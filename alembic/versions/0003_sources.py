"""add sources (source registration + sync) — EVAS_SOURCES

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-08

Adds the `sources` table (a pointer to a place full of videos), a nullable
`videos.source_id` FK, and the `sync_source` job_type. evas_schema.sql has been
updated to match (the value lives inline in the CREATE TYPE there — fresh installs
get it for free; this migration adds it to existing databases).

Enum-outside-transaction: `ALTER TYPE ... ADD VALUE` cannot run inside a
transaction block on some Postgres configurations, and a newly added label may
not be used in the same transaction it was created in. We therefore add the
value inside an `autocommit_block()` (a real COMMIT around the statement) before
the rest of the DDL. `IF NOT EXISTS` keeps it idempotent / safe to re-run.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Everything except the enum-value add runs in the normal migration transaction.
UPGRADE_SQL = r"""
CREATE TYPE source_type   AS ENUM ('s3', 'url');
CREATE TYPE source_status AS ENUM ('connected', 'syncing', 'error', 'disabled');

CREATE TABLE sources (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id         uuid NOT NULL REFERENCES clients(id),
    label             text NOT NULL,
    type              source_type NOT NULL,
    uri_prefix        text NOT NULL,
    credential_ref    text,
    sampling_override jsonb,
    status            source_status NOT NULL DEFAULT 'connected',
    auto_sync         boolean NOT NULL DEFAULT false,
    last_synced_at    timestamptz,
    last_error        text,
    last_sync_result  jsonb,
    created_at        timestamptz NOT NULL DEFAULT now(),
    deleted_at        timestamptz,
    UNIQUE (client_id, uri_prefix)
);
CREATE INDEX idx_sources_client ON sources (client_id) WHERE deleted_at IS NULL;

ALTER TABLE videos ADD COLUMN source_id uuid REFERENCES sources(id);

-- Expose source_id on the review board so video lists can be scoped to a source.
-- CREATE OR REPLACE only allows appending columns, so source_id goes last.
CREATE OR REPLACE VIEW video_review_board AS
SELECT
    v.id,
    v.client_id,
    v.external_ref,
    v.status,
    v.priority,
    latest_ai.grade   AS ai_grade,
    latest_ai.model   AS ai_model,
    hr.grade          AS human_grade,
    hr.reviewer_id,
    CASE
        WHEN latest_ai.grade IS NOT NULL AND hr.grade IS NOT NULL
        THEN abs(latest_ai.grade - hr.grade)
    END AS grade_discrepancy,
    v.uploaded_at,
    v.source_id
FROM videos v
LEFT JOIN LATERAL (
    SELECT grade, model FROM ai_runs
    WHERE ai_runs.video_id = v.id AND ai_runs.status = 'completed'
    ORDER BY completed_at DESC LIMIT 1
) latest_ai ON true
LEFT JOIN LATERAL (
    SELECT grade, reviewer_id FROM human_reviews
    WHERE human_reviews.video_id = v.id AND NOT is_qa_review
    ORDER BY reviewed_at DESC NULLS LAST LIMIT 1
) hr ON true
WHERE v.deleted_at IS NULL;
"""

# Restore the original (source_id-less) view before dropping the column it reads.
# CREATE OR REPLACE can't drop a column, so the view is dropped and recreated.
DOWNGRADE_SQL = r"""
DROP VIEW IF EXISTS video_review_board;
CREATE VIEW video_review_board AS
SELECT
    v.id,
    v.client_id,
    v.external_ref,
    v.status,
    v.priority,
    latest_ai.grade   AS ai_grade,
    latest_ai.model   AS ai_model,
    hr.grade          AS human_grade,
    hr.reviewer_id,
    CASE
        WHEN latest_ai.grade IS NOT NULL AND hr.grade IS NOT NULL
        THEN abs(latest_ai.grade - hr.grade)
    END AS grade_discrepancy,
    v.uploaded_at
FROM videos v
LEFT JOIN LATERAL (
    SELECT grade, model FROM ai_runs
    WHERE ai_runs.video_id = v.id AND ai_runs.status = 'completed'
    ORDER BY completed_at DESC LIMIT 1
) latest_ai ON true
LEFT JOIN LATERAL (
    SELECT grade, reviewer_id FROM human_reviews
    WHERE human_reviews.video_id = v.id AND NOT is_qa_review
    ORDER BY reviewed_at DESC NULLS LAST LIMIT 1
) hr ON true
WHERE v.deleted_at IS NULL;

ALTER TABLE videos DROP COLUMN IF EXISTS source_id;
DROP TABLE IF EXISTS sources;
DROP TYPE IF EXISTS source_status;
DROP TYPE IF EXISTS source_type;
"""


def upgrade() -> None:
    # Add the new job_type label OUTSIDE the migration transaction first.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'sync_source'")
    op.get_bind().exec_driver_sql(UPGRADE_SQL)


def downgrade() -> None:
    # Postgres cannot drop an enum value, so 'sync_source' on job_type is left in
    # place (harmless). Everything else is reversed.
    op.get_bind().exec_driver_sql(DOWNGRADE_SQL)
