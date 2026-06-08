# EVAS Operations

## Job queue: polling vs SQS

The worker polls `processing_jobs` with `FOR UPDATE SKIP LOCKED`. This is
sufficient while **total daily job volume stays under ~50k jobs/day** (a few
jobs/second) with a small number of worker processes. Each video produces
roughly 4–5 jobs (ingest, extract_frames, ai_review, notify, optional
clip-review), so ~50k jobs ≈ ~10k videos/day.

Move to SQS when any of these hold:
- sustained queue depth (`/admin/metrics` `queue_depth`) stays high despite
  added workers, i.e. arrival rate > drain rate;
- you need more than ~4–8 worker processes (polling contention / DB load);
- p95 job pickup latency exceeds your SLA.

Until then, scale by running more `evas worker` processes — `SKIP LOCKED`
makes them safe to run concurrently.

## Metrics & alerts

`GET /admin/metrics` (admin) returns:
- `dead_jobs` — jobs that exhausted `max_attempts`. Alert if > 0.
- `queue_depth` / `running_jobs` — backlog. Alert on sustained growth.
- `webhook_failures` — deliveries attempted but not delivered. Alert if rising.
- `cost_spikes` — per-client day-over-day AI cost increase ≥ threshold
  (`?cost_spike_pct=`, default 50%). Alert per entry.

Scrape this from your monitoring system (or wrap in a cron that pages on
thresholds).

## Backups

- **Nightly dump**: `scripts/backup.sh` (cron at 02:00). Custom-format dumps,
  14-day retention. Set `PGPASSWORD`/`BACKUP_DIR` in the cron environment.
- **Restore**: `scripts/restore.sh <dump>` — drops & recreates objects in the
  target DB inside a single transaction; prompts for confirmation.
- **Test restores** quarterly into a scratch database and run
  `alembic current` + the test suite against it.

## Retention

`evas retention-sweep` (cron at 03:00) enqueues `purge_frames` (delete frame
images after `clients.frame_retention_days`, keep rows) and `archive`
(transition source video to S3 Glacier after `clients.video_archive_days`).
Use `--dry-run` to preview without queuing.
