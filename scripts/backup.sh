#!/usr/bin/env bash
# Postgres backup for EVAS. Writes a timestamped compressed dump.
# Restore with scripts/restore.sh. Intended to run nightly via cron.
#
#   0 2 * * *  /srv/evas/scripts/backup.sh >> /var/log/evas-backup.log 2>&1
#
# Configuration via env (falls back to the local Docker stack):
#   PGHOST (localhost) PGPORT (5433) PGUSER (evas) PGDATABASE (evas)
#   PGPASSWORD (required for non-interactive) BACKUP_DIR (./backups)
set -euo pipefail

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5433}"
PGUSER="${PGUSER:-evas}"
PGDATABASE="${PGDATABASE:-evas}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$BACKUP_DIR/evas_${PGDATABASE}_${STAMP}.dump"

# Custom format (-Fc) supports parallel, selective restore via pg_restore.
pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -Fc -f "$OUT"
echo "wrote $OUT ($(du -h "$OUT" | cut -f1))"

# Retain the last 14 dumps.
ls -1t "$BACKUP_DIR"/evas_*.dump 2>/dev/null | tail -n +15 | xargs -r rm -f
