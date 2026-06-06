"""ffprobe metadata extraction and ffmpeg frame sampling."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass
class ProbeResult:
    duration_seconds: float | None
    fps: float | None
    width: int | None
    height: int | None
    codec: str | None
    size_bytes: int | None
    raw: dict[str, Any]


def _parse_fraction(value: str | None) -> float | None:
    if not value:
        return None
    if "/" in value:
        num, _, den = value.partition("/")
        try:
            d = float(den)
            return float(num) / d if d else None
        except ValueError:
            return None
    try:
        return float(value)
    except ValueError:
        return None


def probe_video(path: str) -> ProbeResult:
    """Run ffprobe and pull out the fields the videos table records."""
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(proc.stdout)
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)

    duration = fmt.get("duration")
    size = fmt.get("size")
    result = ProbeResult(
        duration_seconds=float(duration) if duration else None,
        fps=_parse_fraction(video_stream.get("avg_frame_rate")) if video_stream else None,
        width=int(video_stream["width"]) if video_stream and "width" in video_stream else None,
        height=int(video_stream["height"]) if video_stream and "height" in video_stream else None,
        codec=video_stream.get("codec_name") if video_stream else None,
        size_bytes=int(size) if size else None,
        raw=data,
    )
    return result


def format_timecode(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mmm."""
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


@dataclass
class ExtractedFrame:
    index: int
    timecode_seconds: float
    timecode_label: str
    local_path: str


def extract_frames(
    video_path: str,
    out_dir: str,
    *,
    interval_seconds: float,
    max_frames: int,
    frame_width: int,
) -> list[ExtractedFrame]:
    """Sample one frame every `interval_seconds`, scaled to `frame_width`.

    Returns up to `max_frames` frames. Timecodes are computed from the sampling
    interval (frame i ≈ i * interval_seconds).
    """
    os.makedirs(out_dir, exist_ok=True)
    pattern = os.path.join(out_dir, "frame_%06d.jpg")
    # fps=1/interval samples at the requested rate; scale keeps aspect (-2 = even).
    vf = f"fps=1/{interval_seconds},scale={frame_width}:-2"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            video_path,
            "-vf",
            vf,
            "-frames:v",
            str(max_frames),
            "-q:v",
            "3",
            pattern,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    files = sorted(f for f in os.listdir(out_dir) if f.startswith("frame_") and f.endswith(".jpg"))
    frames: list[ExtractedFrame] = []
    for i, fname in enumerate(files[:max_frames]):
        timecode = i * interval_seconds
        frames.append(
            ExtractedFrame(
                index=i,
                timecode_seconds=timecode,
                timecode_label=format_timecode(timecode),
                local_path=os.path.join(out_dir, fname),
            )
        )
    return frames
