"""EVAS command-line interface.

Commands:
  seed-client      create a client + the example checklist
  create-user      create a user (admin/reviewer/client_viewer)
  token            mint a JWT for an existing user (dev convenience)
  import-csv       batch-enqueue ingest jobs from a CSV of S3 URIs
  worker           run the polling worker (foreground)
  drain            process queued jobs until none remain (useful for tests/dev)
  export           write the findings JSON for one or all videos
  retention-sweep  enqueue purge_frames/archive jobs per client retention policy
"""

from __future__ import annotations

import csv
import datetime
import logging
import os
import subprocess
import tempfile
import uuid

import click
from botocore.exceptions import ClientError
from sqlalchemy import func, select

from evas import worker as worker_module
from evas.audit import write_audit
from evas.auth import create_access_token
from evas.checklists import EXAMPLE_CHECKLIST_ITEMS, EXAMPLE_CHECKLIST_NAME
from evas.config import get_settings
from evas.db import session_scope
from evas.enums import JobType, UserRole, VideoPriority
from evas.export import export_to_file
from evas.jobs import enqueue
from evas.models import AiRun, Checklist, Client, Frame, User, Video
from evas.storage import get_s3_client, upload_file


@click.group()
def cli() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@cli.command("seed-client")
@click.option("--name", required=True)
@click.option("--slug", required=True)
def seed_client(name: str, slug: str) -> None:
    """Create a client and its active example checklist."""
    with session_scope() as session:
        client = Client(
            name=name,
            slug=slug,
            sampling_config={"interval_seconds": 1, "max_frames": 300, "frame_width": 640},
        )
        session.add(client)
        session.flush()
        checklist = Checklist(
            client_id=client.id,
            name=EXAMPLE_CHECKLIST_NAME,
            version=1,
            items=EXAMPLE_CHECKLIST_ITEMS,
            is_active=True,
        )
        session.add(checklist)
        session.flush()
        write_audit(
            session,
            entity_type="client",
            entity_id=client.id,
            action="created",
            new_value={"slug": slug},
        )
        write_audit(
            session,
            entity_type="checklist",
            entity_id=checklist.id,
            action="created",
            new_value={"name": EXAMPLE_CHECKLIST_NAME, "version": 1},
        )
        click.echo(f"client_id={client.id}")
        click.echo(f"checklist_id={checklist.id}")


@cli.command("create-user")
@click.option("--email", required=True)
@click.option("--full-name", required=True)
@click.option("--role", required=True, type=click.Choice([r.value for r in UserRole]))
@click.option("--client-id", type=click.UUID, default=None, help="Required for client_viewer.")
def create_user(email: str, full_name: str, role: str, client_id: uuid.UUID | None) -> None:
    """Create a user. client_viewer must have a --client-id."""
    user_role = UserRole(role)
    if user_role == UserRole.client_viewer and client_id is None:
        raise click.ClickException("client_viewer requires --client-id")
    with session_scope() as session:
        user = User(email=email, full_name=full_name, role=user_role, client_id=client_id)
        session.add(user)
        session.flush()
        write_audit(
            session,
            entity_type="user",
            entity_id=user.id,
            action="created",
            new_value={"email": email, "role": role},
        )
        click.echo(f"user_id={user.id}")


@cli.command("token")
@click.option("--email", required=True)
def token(email: str) -> None:
    """Mint a JWT for an existing active user (dev convenience; bypasses bootstrap)."""
    with session_scope() as session:
        user = session.scalars(select(User).where(User.email == email)).first()
        if user is None or not user.is_active:
            raise click.ClickException("unknown or inactive user")
        click.echo(create_access_token(user))


@cli.command("import-csv")
@click.argument("csv_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--client-id", required=True, type=click.UUID)
def import_csv(csv_path: str, client_id: uuid.UUID) -> None:
    """Enqueue an ingest job per row.

    CSV columns: source_uri[, external_ref, original_filename, priority].
    """
    count = 0
    with open(csv_path, newline="", encoding="utf-8") as fh, session_scope() as session:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None or "source_uri" not in reader.fieldnames:
            raise click.ClickException("CSV must have a 'source_uri' column")
        for row in reader:
            source_uri = (row.get("source_uri") or "").strip()
            if not source_uri:
                continue
            priority = (row.get("priority") or "normal").strip() or "normal"
            job = enqueue(
                session,
                job_type=JobType.ingest,
                payload={
                    "client_id": str(client_id),
                    "source_uri": source_uri,
                    "external_ref": (row.get("external_ref") or None),
                    "original_filename": (row.get("original_filename") or None),
                    "priority": VideoPriority(priority).value,
                },
            )
            session.flush()
            count += 1
            click.echo(f"queued ingest job {job.id} for {source_uri}")
    click.echo(f"enqueued {count} ingest job(s)")


@cli.command("worker")
def worker() -> None:
    """Run the polling worker in the foreground."""
    worker_module.run_forever()


@cli.command("drain")
@click.option("--max-jobs", default=1000, show_default=True)
def drain(max_jobs: int) -> None:
    """Process queued jobs until none remain (or max-jobs reached)."""
    done = 0
    while done < max_jobs and worker_module.run_once():
        done += 1
    click.echo(f"processed {done} job(s)")


@cli.command("export")
@click.option("--video-id", type=click.UUID, default=None, help="Export one video; omit for all.")
@click.option("--out-dir", default=None)
def export(video_id: uuid.UUID | None, out_dir: str | None) -> None:
    """Write findings JSON file(s)."""
    with session_scope() as session:
        if video_id is not None:
            ids = [video_id]
        else:
            ids = list(session.scalars(select(Video.id).where(Video.deleted_at.is_(None))).all())
        for vid in ids:
            path = export_to_file(session, vid, out_dir)
            click.echo(f"wrote {path}")


@cli.command("retention-sweep")
def retention_sweep() -> None:
    """Enqueue purge_frames/archive jobs per each client's retention policy."""
    now = datetime.datetime.now(datetime.UTC)
    purge_jobs = archive_jobs = 0
    with session_scope() as session:
        clients = session.scalars(select(Client).where(Client.deleted_at.is_(None))).all()
        for client in clients:
            videos = session.scalars(
                select(Video).where(Video.client_id == client.id, Video.deleted_at.is_(None))
            ).all()
            for video in videos:
                age_days = (now - video.uploaded_at).total_seconds() / 86400
                if (
                    client.frame_retention_days is not None
                    and age_days >= client.frame_retention_days
                ):
                    unpurged = session.scalar(
                        select(func.count())
                        .select_from(Frame)
                        .where(Frame.video_id == video.id, Frame.purged.is_(False))
                    )
                    if unpurged:
                        enqueue(session, job_type=JobType.purge_frames, video_id=video.id)
                        purge_jobs += 1
                if (
                    client.video_archive_days is not None
                    and age_days >= client.video_archive_days
                    and not video.metadata_.get("archived")
                ):
                    enqueue(session, job_type=JobType.archive, video_id=video.id)
                    archive_jobs += 1
    click.echo(f"enqueued {purge_jobs} purge_frames and {archive_jobs} archive job(s)")


@cli.command("create-buckets")
def create_buckets() -> None:
    """Create the configured S3 buckets (idempotent; works against MinIO)."""
    settings = get_settings()
    s3 = get_s3_client()
    for bucket in (settings.s3_bucket_videos, settings.s3_bucket_frames):
        try:
            s3.create_bucket(Bucket=bucket)
            click.echo(f"created bucket {bucket}")
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                click.echo(f"bucket {bucket} already exists")
            else:
                raise


@cli.command("demo")
@click.option("--slug", required=True, help="Client slug created by seed-client.")
@click.option("--duration", default=3, show_default=True)
def demo(slug: str, duration: int) -> None:
    """Generate a test video and run it through the whole pipeline locally."""
    settings = get_settings()
    with session_scope() as session:
        client = session.scalars(select(Client).where(Client.slug == slug)).first()
        if client is None:
            raise click.ClickException(f"no client with slug {slug!r}; run seed-client first")
        client_id = client.id

    os.makedirs(settings.work_dir, exist_ok=True)
    fd, video_path = tempfile.mkstemp(dir=settings.work_dir, suffix=".mp4")
    os.close(fd)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"testsrc=duration={duration}:size=320x240:rate=10",
                "-pix_fmt",
                "yuv420p",
                video_path,
            ],
            check=True,
        )
        key = f"demo/{uuid.uuid4().hex}.mp4"
        source_uri = upload_file(video_path, settings.s3_bucket_videos, key, "video/mp4")
        click.echo(f"uploaded {source_uri}")
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)

    with session_scope() as session:
        enqueue(
            session,
            job_type=JobType.ingest,
            payload={"client_id": str(client_id), "source_uri": source_uri},
        )
    processed = 0
    while worker_module.run_once():
        processed += 1
    click.echo(f"processed {processed} job(s)")

    with session_scope() as session:
        video = session.scalars(select(Video).where(Video.source_uri == source_uri)).one()
        run = session.scalars(select(AiRun).where(AiRun.video_id == video.id)).first()
        click.echo(f"video {video.id} status={video.status.value}")
        if run is not None:
            click.echo(f"ai grade={run.grade} model={run.model} cost=${run.cost_usd}")
        path = export_to_file(session, video.id)
        click.echo(f"export written to {path}")


if __name__ == "__main__":
    cli()
