"""Per-client monthly billing: usage + cost, with CSV and PDF renderers.

Token and cost figures come straight from ai_runs so they reconcile with the
raw data to the cent (see the reconciliation test).
"""

from __future__ import annotations

import calendar
import csv
import datetime
import io
import uuid
from dataclasses import asdict, dataclass
from decimal import Decimal

from fpdf import FPDF
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from evas.enums import RunStatus
from evas.models import AiRun, Client, Frame, HumanReview, Video


def month_range(year: int, month: int) -> tuple[datetime.datetime, datetime.datetime]:
    start = datetime.datetime(year, month, 1, tzinfo=datetime.UTC)
    last_day = calendar.monthrange(year, month)[1]
    end = datetime.datetime(year, month, last_day, 23, 59, 59, 999999, tzinfo=datetime.UTC)
    return start, end


@dataclass
class BillingReport:
    client_id: str
    client_name: str
    period: str  # YYYY-MM
    videos_processed: int
    frames_extracted: int
    tokens_in: int
    tokens_out: int
    cost_usd: str  # stringified Decimal for exact reconciliation
    human_reviews: int
    human_review_seconds: int
    storage_bytes: int


def compute_billing(session: Session, client_id: uuid.UUID, year: int, month: int) -> BillingReport:
    client = session.get(Client, client_id)
    if client is None or client.deleted_at is not None:
        raise LookupError(f"client {client_id} not found")
    start, end = month_range(year, month)

    videos_processed = session.scalar(
        select(func.count())
        .select_from(Video)
        .where(
            Video.client_id == client_id,
            Video.deleted_at.is_(None),
            Video.uploaded_at >= start,
            Video.uploaded_at <= end,
        )
    )

    frames_extracted = session.scalar(
        select(func.count())
        .select_from(Frame)
        .join(Video, Video.id == Frame.video_id)
        .where(
            Video.client_id == client_id,
            Video.uploaded_at >= start,
            Video.uploaded_at <= end,
        )
    )

    # Cost/tokens from completed ai_runs in the period (reconciles to the cent).
    run_totals = session.execute(
        select(
            func.coalesce(func.sum(AiRun.tokens_in), 0),
            func.coalesce(func.sum(AiRun.tokens_out), 0),
            func.coalesce(func.sum(AiRun.cost_usd), Decimal(0)),
        )
        .select_from(AiRun)
        .join(Video, Video.id == AiRun.video_id)
        .where(
            Video.client_id == client_id,
            AiRun.status == RunStatus.completed,
            AiRun.completed_at >= start,
            AiRun.completed_at <= end,
        )
    ).one()
    tokens_in, tokens_out, cost_usd = run_totals

    review_rows = session.execute(
        select(HumanReview.assigned_at, HumanReview.reviewed_at)
        .join(Video, Video.id == HumanReview.video_id)
        .where(
            Video.client_id == client_id,
            HumanReview.reviewed_at.is_not(None),
            HumanReview.reviewed_at >= start,
            HumanReview.reviewed_at <= end,
        )
    ).all()
    human_reviews = len(review_rows)
    human_review_seconds = int(
        sum((r.reviewed_at - r.assigned_at).total_seconds() for r in review_rows)
    )

    storage_bytes = session.scalar(
        select(func.coalesce(func.sum(Video.size_bytes), 0)).where(
            Video.client_id == client_id, Video.deleted_at.is_(None)
        )
    )

    return BillingReport(
        client_id=str(client_id),
        client_name=client.name,
        period=f"{year:04d}-{month:02d}",
        videos_processed=int(videos_processed or 0),
        frames_extracted=int(frames_extracted or 0),
        tokens_in=int(tokens_in or 0),
        tokens_out=int(tokens_out or 0),
        cost_usd=str(Decimal(cost_usd or 0).quantize(Decimal("0.000001"))),
        human_reviews=human_reviews,
        human_review_seconds=human_review_seconds,
        storage_bytes=int(storage_bytes or 0),
    )


def to_csv(report: BillingReport) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["metric", "value"])
    for key, value in asdict(report).items():
        writer.writerow([key, value])
    return buf.getvalue()


def to_pdf(report: BillingReport) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "EVAS Billing Report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, f"Client: {report.client_name}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Period: {report.period}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    labels = {
        "videos_processed": "Videos processed",
        "frames_extracted": "Frames extracted",
        "tokens_in": "Tokens in",
        "tokens_out": "Tokens out",
        "cost_usd": "AI cost (USD)",
        "human_reviews": "Human reviews",
        "human_review_seconds": "Human review time (s)",
        "storage_bytes": "Storage footprint (bytes)",
    }
    data = asdict(report)
    for key, label in labels.items():
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(70, 8, label)
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 8, str(data[key]), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
