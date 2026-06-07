"""Human review endpoints: assign, grade, frame notes/overrides, QA second pass.

Reviewer/admin only. Human overrides live in human_frame_notes; AI results are
never modified. Completing a non-QA review advances the video to human_reviewed
and enqueues a video.human_reviewed webhook.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from evas.api.schemas import (
    FrameNoteUpsert,
    HumanReviewCreate,
    HumanReviewOut,
    HumanReviewUpdate,
)
from evas.audit import record_status_change, write_audit
from evas.auth import require_roles
from evas.db import get_session
from evas.enums import ReviewStatus, UserRole, VideoStatus
from evas.models import Checklist, Frame, HumanFrameNote, HumanReview, User, Video
from evas.webhooks import EVENT_HUMAN_REVIEWED, enqueue_notify

router = APIRouter(tags=["human-review"])
_staff = require_roles(UserRole.admin, UserRole.reviewer)


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _to_out(hr: HumanReview) -> HumanReviewOut:
    return HumanReviewOut(
        id=hr.id,
        video_id=hr.video_id,
        checklist_id=hr.checklist_id,
        reviewer_id=hr.reviewer_id,
        is_qa_review=hr.is_qa_review,
        qa_of_review=hr.qa_of_review,
        status=hr.status.value,
        grade=float(hr.grade) if hr.grade is not None else None,
        notes=hr.notes,
        assigned_at=hr.assigned_at,
        reviewed_at=hr.reviewed_at,
    )


def _active_checklist(session: Session, client_id: uuid.UUID) -> Checklist:
    checklist = session.scalars(
        select(Checklist)
        .where(Checklist.client_id == client_id, Checklist.is_active.is_(True))
        .order_by(Checklist.version.desc())
    ).first()
    if checklist is None:
        raise HTTPException(status_code=409, detail="client has no active checklist")
    return checklist


def _get_review(session: Session, review_id: uuid.UUID) -> HumanReview:
    hr = session.get(HumanReview, review_id)
    if hr is None:
        raise HTTPException(status_code=404, detail="review not found")
    return hr


@router.post("/videos/{video_id}/human-reviews", response_model=HumanReviewOut, status_code=201)
def assign_review(
    video_id: uuid.UUID,
    req: HumanReviewCreate,
    session: Session = Depends(get_session),
    user: User = Depends(_staff),
) -> HumanReviewOut:
    video = session.get(Video, video_id)
    if video is None or video.deleted_at is not None:
        raise HTTPException(status_code=404, detail="video not found")
    reviewer_id = req.reviewer_id or user.id
    # Reviewers may only self-assign; admins may assign anyone.
    if user.role == UserRole.reviewer and reviewer_id != user.id:
        raise HTTPException(status_code=403, detail="reviewers may only self-assign")
    checklist = _active_checklist(session, video.client_id)
    hr = HumanReview(
        video_id=video.id,
        checklist_id=checklist.id,
        reviewer_id=reviewer_id,
        status=ReviewStatus.assigned,
    )
    session.add(hr)
    session.flush()
    write_audit(
        session,
        entity_type="human_review",
        entity_id=hr.id,
        action="assigned",
        new_value={"reviewer_id": str(reviewer_id), "video_id": str(video.id)},
        user_id=user.id,
    )
    return _to_out(hr)


@router.get("/human-reviews", response_model=list[HumanReviewOut])
def list_reviews(
    session: Session = Depends(get_session),
    user: User = Depends(_staff),
    reviewer_id: uuid.UUID | None = None,
    status: ReviewStatus | None = None,
) -> list[HumanReviewOut]:
    stmt = select(HumanReview)
    if reviewer_id is not None:
        stmt = stmt.where(HumanReview.reviewer_id == reviewer_id)
    if status is not None:
        stmt = stmt.where(HumanReview.status == status)
    stmt = stmt.order_by(HumanReview.assigned_at.desc())
    return [_to_out(hr) for hr in session.scalars(stmt).all()]


@router.get("/videos/{video_id}/human-reviews", response_model=list[HumanReviewOut])
def reviews_for_video(
    video_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(_staff),
) -> list[HumanReviewOut]:
    rows = session.scalars(
        select(HumanReview)
        .where(HumanReview.video_id == video_id)
        .order_by(HumanReview.assigned_at.desc())
    ).all()
    return [_to_out(hr) for hr in rows]


@router.patch("/human-reviews/{review_id}", response_model=HumanReviewOut)
def update_review(
    review_id: uuid.UUID,
    req: HumanReviewUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(_staff),
) -> HumanReviewOut:
    hr = _get_review(session, review_id)
    if user.role == UserRole.reviewer and hr.reviewer_id != user.id:
        raise HTTPException(status_code=403, detail="not your review")

    if req.grade is not None and (hr.grade is None or float(hr.grade) != req.grade):
        old_grade = str(hr.grade) if hr.grade is not None else None
        hr.grade = Decimal(str(req.grade))
        write_audit(
            session,
            entity_type="human_review",
            entity_id=hr.id,
            action="grade_changed",
            old_value={"grade": old_grade},
            new_value={"grade": str(hr.grade)},
            user_id=user.id,
        )
    if req.notes is not None:
        hr.notes = req.notes
    if req.status is not None and req.status != hr.status:
        old_status = hr.status.value
        hr.status = req.status
        if req.status == ReviewStatus.done:
            hr.reviewed_at = _utcnow()
        write_audit(
            session,
            entity_type="human_review",
            entity_id=hr.id,
            action="status_changed",
            old_value={"status": old_status},
            new_value={"status": req.status.value},
            user_id=user.id,
        )
        if req.status == ReviewStatus.done and not hr.is_qa_review and hr.grade is not None:
            _complete_video_review(session, hr, user)

    return _to_out(hr)


def _complete_video_review(session: Session, hr: HumanReview, user: User) -> None:
    video = session.get(Video, hr.video_id)
    if video is None:
        return
    if video.status != VideoStatus.human_reviewed:
        old = video.status.value
        video.status = VideoStatus.human_reviewed
        record_status_change(
            session,
            entity_type="video",
            entity_id=video.id,
            old_status=old,
            new_status=VideoStatus.human_reviewed.value,
            user_id=user.id,
        )
    enqueue_notify(session, video.id, EVENT_HUMAN_REVIEWED)


@router.put("/human-reviews/{review_id}/frames/{frame_id}", status_code=200)
def upsert_frame_note(
    review_id: uuid.UUID,
    frame_id: uuid.UUID,
    req: FrameNoteUpsert,
    session: Session = Depends(get_session),
    user: User = Depends(_staff),
) -> dict[str, str]:
    hr = _get_review(session, review_id)
    if user.role == UserRole.reviewer and hr.reviewer_id != user.id:
        raise HTTPException(status_code=403, detail="not your review")
    frame = session.get(Frame, frame_id)
    if frame is None or frame.video_id != hr.video_id:
        raise HTTPException(status_code=404, detail="frame not found for this review's video")

    note = session.scalars(
        select(HumanFrameNote).where(
            HumanFrameNote.human_review_id == hr.id, HumanFrameNote.frame_id == frame_id
        )
    ).first()
    if note is None:
        note = HumanFrameNote(human_review_id=hr.id, frame_id=frame_id)
        session.add(note)
    note.note = req.note
    note.override_findings = req.override_findings
    return {"status": "ok"}


@router.post("/human-reviews/{review_id}/qa", response_model=HumanReviewOut, status_code=201)
def create_qa_review(
    review_id: uuid.UUID,
    req: HumanReviewCreate,
    session: Session = Depends(get_session),
    user: User = Depends(_staff),
) -> HumanReviewOut:
    parent = _get_review(session, review_id)
    if parent.is_qa_review:
        raise HTTPException(status_code=409, detail="cannot QA a QA review")
    reviewer_id = req.reviewer_id or user.id
    qa = HumanReview(
        video_id=parent.video_id,
        checklist_id=parent.checklist_id,
        reviewer_id=reviewer_id,
        is_qa_review=True,
        qa_of_review=parent.id,
        status=ReviewStatus.assigned,
    )
    session.add(qa)
    session.flush()
    write_audit(
        session,
        entity_type="human_review",
        entity_id=qa.id,
        action="qa_assigned",
        new_value={"qa_of_review": str(parent.id), "reviewer_id": str(reviewer_id)},
        user_id=user.id,
    )
    return _to_out(qa)
