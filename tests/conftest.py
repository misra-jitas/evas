"""Test fixtures: a migrated Postgres test DB, an in-memory fake S3, and a fake
AI reviewer. The DB connection points at the Docker Postgres (port 5433); a
dedicated `evas_test` database is created and migrated once per session.
"""

from __future__ import annotations

import os
import subprocess
import sys

import psycopg2
import pytest

# Point EVAS at an isolated test database BEFORE importing the app.
_PG = {"host": "localhost", "port": 5433, "user": "evas", "password": "evas"}
_TEST_DB = "evas_test"
os.environ["EVAS_DATABASE_URL"] = (
    f"postgresql+psycopg2://{_PG['user']}:{_PG['password']}@{_PG['host']}:{_PG['port']}/{_TEST_DB}"
)
os.environ.setdefault("EVAS_ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("EVAS_S3_BUCKET_FRAMES", "evas-frames")
# Keep tests hermetic from a developer's local .env: the fake AI reviewer and
# explicit bootstrap settings are controlled by the tests themselves.
os.environ["EVAS_AI_STUB"] = "false"
os.environ["EVAS_BOOTSTRAP_TOKEN"] = ""


def _create_test_db() -> None:
    conn = psycopg2.connect(dbname="postgres", **_PG)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (_TEST_DB,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{_TEST_DB}"')
    finally:
        conn.close()


@pytest.fixture(scope="session", autouse=True)
def _migrated_db() -> None:
    _create_test_db()
    env = {**os.environ}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        capture_output=True,
    )


@pytest.fixture(autouse=True)
def _clean_tables() -> None:
    """Truncate all data between tests (worker commits independently)."""
    from sqlalchemy import text

    from evas.db import engine

    with engine.begin() as conn:
        tables = (
            conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                    "AND tablename <> 'alembic_version'"
                )
            )
            .scalars()
            .all()
        )
        if tables:
            joined = ", ".join(f'"{t}"' for t in tables)
            conn.execute(text(f"TRUNCATE {joined} RESTART IDENTITY CASCADE"))


class FakeS3:
    """In-memory object store keyed by s3:// URI."""

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.storage_classes: dict[str, str] = {}

    def put(self, uri: str, data: bytes) -> None:
        self.store[uri] = data

    def download_to_file(self, uri: str, dest_path: str) -> None:
        with open(dest_path, "wb") as fh:
            fh.write(self.store[uri])

    def upload_file(self, local_path: str, bucket: str, key: str, content_type=None) -> str:
        with open(local_path, "rb") as fh:
            data = fh.read()
        uri = f"s3://{bucket}/{key}"
        self.store[uri] = data
        return uri

    def get_object_bytes(self, uri: str) -> bytes:
        return self.store[uri]

    def list_objects(self, uri_prefix: str) -> list[str]:
        return sorted(uri for uri in self.store if uri.startswith(uri_prefix))

    def delete_object(self, uri: str) -> None:
        self.store.pop(uri, None)

    def set_storage_class(self, uri: str, storage_class: str) -> None:
        self.storage_classes[uri] = storage_class


@pytest.fixture
def fake_s3(monkeypatch: pytest.MonkeyPatch) -> FakeS3:
    s3 = FakeS3()
    # Patch the names as imported into each pipeline module.
    monkeypatch.setattr("evas.pipeline.ingest.download_to_file", s3.download_to_file)
    monkeypatch.setattr("evas.pipeline.extract.download_to_file", s3.download_to_file)
    monkeypatch.setattr("evas.pipeline.extract.upload_file", s3.upload_file)
    monkeypatch.setattr("evas.pipeline.review.get_object_bytes", s3.get_object_bytes)
    monkeypatch.setattr("evas.pipeline.retention.delete_object", s3.delete_object)
    monkeypatch.setattr("evas.pipeline.retention.set_storage_class", s3.set_storage_class)
    monkeypatch.setattr("evas.pipeline.sync.list_objects", s3.list_objects)
    return s3


class FakeReviewer:
    """Deterministic stand-in for the Anthropic vision reviewer."""

    model = "claude-haiku-4-5-fake"

    def __init__(self, prompt_version: str = "1.0.0") -> None:
        self.prompt_version = prompt_version

    def _result(self, items):
        from evas.ai import FrameReview

        findings = {}
        for i, item in enumerate(items):
            # Alternate values; make one item low-confidence to exercise flagging.
            findings[item["key"]] = {
                "value": (i % 2 == 0),
                "confidence": 0.5 if item["key"] == "holding_broom" else 0.95,
            }
        return FrameReview(
            description="fake review",
            findings=findings,
            tokens_in=100,
            tokens_out=20,
            cost_usd=0.0001,
        )

    def review_frame(self, image_bytes: bytes, items, media_type: str = "image/jpeg"):
        return self._result(items)

    def review_clip(self, images, items, media_type: str = "image/jpeg"):
        return self._result(items)


@pytest.fixture
def fake_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    import evas.ai

    monkeypatch.setattr(
        evas.ai, "AiReviewer", lambda *a, **k: FakeReviewer(k.get("prompt_version", "1.0.0"))
    )


@pytest.fixture
def make_user():
    """Factory creating a user and returning (user_id, bearer_token)."""
    import uuid as _uuid

    from evas.auth import create_access_token
    from evas.db import session_scope
    from evas.enums import UserRole
    from evas.models import User

    def _make(role: UserRole = UserRole.admin, client_id=None):
        with session_scope() as s:
            user = User(
                email=f"{role.value}-{_uuid.uuid4().hex[:8]}@example.com",
                full_name="Test User",
                role=role,
                client_id=client_id,
            )
            s.add(user)
            s.flush()
            return user.id, create_access_token(user)

    return _make


@pytest.fixture
def auth_headers(make_user):
    """Authorization header for a fresh admin user."""
    _, token = make_user()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_video_bytes(tmp_path) -> bytes:
    """Generate a tiny 2s test video with ffmpeg and return its bytes."""
    out = tmp_path / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=3:size=320x240:rate=10",
            "-pix_fmt",
            "yuv420p",
            str(out),
        ],
        check=True,
    )
    return out.read_bytes()
