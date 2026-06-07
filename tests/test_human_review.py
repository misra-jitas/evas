"""Human review + QA endpoints, audit, and human_reviewed transition."""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from evas.api.app import app
from evas.checklists import EXAMPLE_CHECKLIST_ITEMS, EXAMPLE_CHECKLIST_NAME
from evas.db import session_scope
from evas.enums import JobType, VideoStatus
from evas.models import (
    AuditLog,
    Checklist,
    Client,
    Frame,
    HumanFrameNote,
    HumanReview,
    ProcessingJob,
    Video,
)

client = TestClient(app)


def _seed_video_with_frame() -> tuple[uuid.UUID, uuid.UUID]:
    with session_scope() as s:
        c = Client(name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}", sampling_config={})
        s.add(c)
        s.flush()
        s.add(
            Checklist(
                client_id=c.id,
                name=EXAMPLE_CHECKLIST_NAME,
                version=1,
                items=EXAMPLE_CHECKLIST_ITEMS,
                is_active=True,
            )
        )
        v = Video(
            client_id=c.id,
            source_uri="s3://b/v.mp4",
            file_hash=uuid.uuid4().hex,
            status=VideoStatus.ai_reviewed,
        )
        s.add(v)
        s.flush()
        f = Frame(
            video_id=v.id,
            frame_index=0,
            timecode_seconds=Decimal("0.000"),
            timecode_label="00:00:00.000",
            image_uri="s3://frames/v/0.jpg",
        )
        s.add(f)
        s.flush()
        return v.id, f.id


def test_assign_grade_complete_flow(auth_headers) -> None:
    video_id, frame_id = _seed_video_with_frame()

    # Assign
    r = client.post(f"/videos/{video_id}/human-reviews", json={}, headers=auth_headers)
    assert r.status_code == 201
    review_id = r.json()["id"]
    assert r.json()["status"] == "assigned"

    # Frame note with an override of the AI finding
    note = client.put(
        f"/human-reviews/{review_id}/frames/{frame_id}",
        json={
            "note": "looks off",
            "override_findings": {"two_hands": {"value": False, "confidence": 1.0}},
        },
        headers=auth_headers,
    )
    assert note.status_code == 200

    # Grade + complete
    upd = client.patch(
        f"/human-reviews/{review_id}",
        json={"status": "done", "grade": 7.5, "notes": "ok"},
        headers=auth_headers,
    )
    assert upd.status_code == 200
    assert upd.json()["status"] == "done"
    assert upd.json()["grade"] == 7.5

    with session_scope() as s:
        video = s.get(Video, video_id)
        assert video.status == VideoStatus.human_reviewed

        note_row = s.scalars(
            select(HumanFrameNote).where(HumanFrameNote.frame_id == frame_id)
        ).one()
        assert note_row.override_findings["two_hands"]["value"] is False

        # grade_changed + status_changed audited for the review
        actions = set(
            s.scalars(select(AuditLog.action).where(AuditLog.entity_type == "human_review")).all()
        )
        assert {"assigned", "grade_changed", "status_changed"} <= actions

        # video.human_reviewed enqueued a notify job
        notify = s.scalars(
            select(ProcessingJob).where(ProcessingJob.job_type == JobType.notify)
        ).all()
        assert len(notify) == 1
        assert notify[0].payload["event"] == "video.human_reviewed"


def test_qa_second_pass(auth_headers) -> None:
    video_id, _ = _seed_video_with_frame()
    r = client.post(f"/videos/{video_id}/human-reviews", json={}, headers=auth_headers)
    review_id = r.json()["id"]

    qa = client.post(f"/human-reviews/{review_id}/qa", json={}, headers=auth_headers)
    assert qa.status_code == 201
    assert qa.json()["is_qa_review"] is True
    assert qa.json()["qa_of_review"] == review_id

    with session_scope() as s:
        qa_row = s.get(HumanReview, uuid.UUID(qa.json()["id"]))
        assert qa_row.is_qa_review and qa_row.qa_of_review == uuid.UUID(review_id)


def test_human_review_requires_staff(make_user) -> None:
    from evas.enums import UserRole

    video_id, _ = _seed_video_with_frame()
    with session_scope() as s:
        cid = s.scalars(select(Client.id)).first()
    _, token = make_user(role=UserRole.client_viewer, client_id=cid)
    resp = client.post(
        f"/videos/{video_id}/human-reviews",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
