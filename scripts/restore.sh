#!/usr/bin/env bash
# Restore an EVAS Postgres dump produced by scripts/backup.sh.
#
#   scripts/restore.sh backups/evas_evas_20260607T020000Z.dump
#
# DANGER: drops and recreates objects in the target database. Confirm the
# target before running. Env: PGHOST PGPORT PGUSER PGDATABASE PGPASSWORD.
set -euo pipefail

DUMP="${1:?usage: restore.sh <dump-file>}"
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5433}"
PGUSER="${PGUSER:-evas}"
PGDATABASE="${PGDATABASE:-evas}"

echo "About to restore '$DUMP' into ${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE}"
read -r -p "Type the database name to confirm: " CONFIRM
[ "$CONFIRM" = "$PGDATABASE" ] || { echo "aborted"; exit 1; }

# --clean --if-exists drops existing objects first; single transaction so a
# failed restore rolls back cleanly.
pg_restore -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" \
  --clean --if-exists --no-owner --single-transaction "$DUMP"
echo "restore complete"
