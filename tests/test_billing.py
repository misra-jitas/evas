"""Billing report: reconciliation with raw ai_runs, plus endpoint formats."""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from evas.api.app import app
from evas.billing import compute_billing
from evas.db import session_scope
from evas.enums import ReviewStatus, RunStatus, UserRole
from evas.models import AiRun, Checklist, Client, HumanReview, User, Video

client = TestClient(app)

_MONTH = (2026, 5)
_IN_MONTH = datetime.datetime(2026, 5, 15, 12, 0, tzinfo=datetime.UTC)
_OUT_MONTH = datetime.datetime(2026, 4, 15, 12, 0, tzinfo=datetime.UTC)


def _seed_billing_data() -> uuid.UUID:
    with session_scope() as s:
        c = Client(name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}", sampling_config={})
        s.add(c)
        s.flush()
        checklist = Checklist(client_id=c.id, name="cl", version=1, items=[], is_active=True)
        s.add(checklist)
        video = Video(
            client_id=c.id,
            source_uri="s3://b/v.mp4",
            file_hash=uuid.uuid4().hex,
            size_bytes=1000,
            uploaded_at=_IN_MONTH,
        )
        s.add(video)
        s.flush()
        # Two completed runs in-month + one out-of-month (must be excluded).
        for cost, when in [
            (Decimal("0.001234"), _IN_MONTH),
            (Decimal("0.002000"), _IN_MONTH),
            (Decimal("9.999999"), _OUT_MONTH),
        ]:
            s.add(
                AiRun(
                    video_id=video.id,
                    checklist_id=checklist.id,
                    model="m",
                    prompt_version="1.0.0",
                    status=RunStatus.completed,
                    tokens_in=100,
                    tokens_out=50,
                    cost_usd=cost,
                    completed_at=when,
                )
            )
        reviewer = User(
            email=f"r-{uuid.uuid4().hex[:6]}@e.co", full_name="R", role=UserRole.reviewer
        )
        s.add(reviewer)
        s.flush()
        s.add(
            HumanReview(
                video_id=video.id,
                checklist_id=checklist.id,
                reviewer_id=reviewer.id,
                status=ReviewStatus.done,
                assigned_at=_IN_MONTH,
                reviewed_at=_IN_MONTH + datetime.timedelta(minutes=5),
            )
        )
        return c.id


def test_billing_reconciles_with_ai_runs() -> None:
    client_id = _seed_billing_data()
    with session_scope() as s:
        report = compute_billing(s, client_id, *_MONTH)

        # Raw sum of in-month completed runs, computed independently.
        start = datetime.datetime(2026, 5, 1, tzinfo=datetime.UTC)
        end = datetime.datetime(2026, 6, 1, tzinfo=datetime.UTC)
        raw = s.scalar(
            select(func.coalesce(func.sum(AiRun.cost_usd), 0))
            .join(Video, Video.id == AiRun.video_id)
            .where(
                Video.client_id == client_id,
                AiRun.completed_at >= start,
                AiRun.completed_at < end,
            )
        )
        assert Decimal(report.cost_usd) == Decimal(raw).quantize(Decimal("0.000001"))
        assert Decimal(report.cost_usd) == Decimal("0.003234")  # excludes out-of-month run
        assert report.tokens_in == 200
        assert report.human_reviews == 1
        assert report.human_review_seconds == 300
        assert report.storage_bytes == 1000


def test_billing_endpoint_formats(auth_headers) -> None:
    client_id = _seed_billing_data()
    period = "2026-05"

    js = client.get(
        f"/clients/{client_id}/billing", params={"period": period}, headers=auth_headers
    )
    assert js.status_code == 200
    assert js.json()["cost_usd"] == "0.003234"

    csv_resp = client.get(
        f"/clients/{client_id}/billing",
        params={"period": period, "format": "csv"},
        headers=auth_headers,
    )
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert "cost_usd,0.003234" in csv_resp.text

    pdf_resp = client.get(
        f"/clients/{client_id}/billing",
        params={"period": period, "format": "pdf"},
        headers=auth_headers,
    )
    assert pdf_resp.status_code == 200
    assert pdf_resp.content[:4] == b"%PDF"
