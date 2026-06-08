"""Client portal: tenancy isolation, simplified status, no internal data."""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

from evas.api.app import app
from evas.db import session_scope
from evas.enums import (
    GradingMode,
    ReviewStatus,
    RunStatus,
    UserRole,
    VideoStatus,
)
from evas.models import (
    AiFrameFinding,
    AiRun,
    Checklist,
    Client,
    Frame,
    HumanFrameNote,
    HumanReview,
    User,
    Video,
)

client = TestClient(app)


def _seed_reviewed_video(slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Returns (client_id, video_id) for a video with AI + human findings."""
    with session_scope() as s:
        c = Client(name=slug, slug=f"{slug}-{uuid.uuid4().hex[:6]}", sampling_config={})
        s.add(c)
        s.flush()
        checklist = Checklist(
            client_id=c.id,
            name="cl",
            version=1,
            grading_mode=GradingMode.derived,
            items=[{"key": "two_hands", "label": "x", "type": "boolean", "weight": 1.0}],
            is_active=True,
        )
        s.add(checklist)
        v = Video(
            client_id=c.id,
            external_ref="EXT1",
            source_uri="s3://b/v.mp4",
            file_hash=uuid.uuid4().hex,
            status=VideoStatus.human_reviewed,
        )
        s.add(v)
        s.flush()
        frame = Frame(
            video_id=v.id,
            frame_index=0,
            timecode_seconds=Decimal("0.000"),
            timecode_label="00:00:00.000",
            image_uri="s3://frames/v/0.jpg",
        )
        s.add(frame)
        run = AiRun(
            video_id=v.id,
            checklist_id=checklist.id,
            model="secret-model",
            prompt_version="1.0.0",
            status=RunStatus.completed,
            grade=Decimal("5.00"),
            summary="ai summary",
            cost_usd=Decimal("1.23"),
            completed_at=datetime.datetime.now(datetime.UTC),
        )
        s.add(run)
        s.flush()
        s.add(
            AiFrameFinding(
                ai_run_id=run.id,
                frame_id=frame.id,
                findings={"two_hands": {"value": True, "confidence": 0.95}},
                confidence=Decimal("0.950"),
                flagged=True,
            )
        )
        reviewer = User(
            email=f"rv-{uuid.uuid4().hex[:6]}@e.co", full_name="Rv", role=UserRole.reviewer
        )
        s.add(reviewer)
        s.flush()
        hr = HumanReview(
            video_id=v.id,
            checklist_id=checklist.id,
            reviewer_id=reviewer.id,
            status=ReviewStatus.done,
            grade=Decimal("8.00"),
        )
        s.add(hr)
        s.flush()
        s.add(
            HumanFrameNote(
                human_review_id=hr.id,
                frame_id=frame.id,
                note="reviewer note",
                override_findings={"two_hands": {"value": False, "confidence": 1.0}},
            )
        )
        return c.id, v.id


def _headers(make_user, client_id) -> dict[str, str]:
    _, token = make_user(role=UserRole.client_viewer, client_id=client_id)
    return {"Authorization": f"Bearer {token}"}


def test_portal_list_and_tenancy(make_user) -> None:
    client_a, video_a = _seed_reviewed_video("acme")
    client_b, _ = _seed_reviewed_video("globex")
    headers = _headers(make_user, client_a)

    listing = client.get("/portal/videos", headers=headers)
    assert listing.status_code == 200
    rows = listing.json()
    assert len(rows) == 1  # only client A's video
    assert rows[0]["external_ref"] == "EXT1"
    assert rows[0]["status"] == "Reviewed"
    assert rows[0]["final_grade"] == 8.0  # human grade wins over AI 5.0


def test_portal_detail_hides_internal_and_uses_override(make_user) -> None:
    client_a, video_a = _seed_reviewed_video("acme")
    headers = _headers(make_user, client_a)

    detail = client.get(f"/portal/videos/{video_a}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["final_grade"] == 8.0
    # Final finding uses the human override (False), not the AI value (True).
    notable = body["notable_frames"]
    assert notable and notable[0]["findings"]["two_hands"] is False
    assert notable[0]["note"] == "reviewer note"
    # No internal data leaks.
    blob = detail.text.lower()
    assert "secret-model" not in blob
    assert "cost" not in blob
    assert "confidence" not in blob


def test_portal_cross_tenant_404(make_user) -> None:
    client_a, _ = _seed_reviewed_video("acme")
    client_b, video_b = _seed_reviewed_video("globex")
    headers = _headers(make_user, client_a)
    assert client.get(f"/portal/videos/{video_b}", headers=headers).status_code == 404


def test_portal_export_csv(make_user) -> None:
    client_a, _ = _seed_reviewed_video("acme")
    headers = _headers(make_user, client_a)
    resp = client.get("/portal/export.csv", headers=headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "EXT1" in resp.text
