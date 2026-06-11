"""Anthropic vision client for per-frame checklist review.

Prompt templates are versioned in prompts/ with semver filenames. The active
version is recorded on each ai_runs row (prompt_version).
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any, Literal

import anthropic
from anthropic.types import ImageBlockParam, MessageParam, TextBlockParam

from evas.config import get_settings

ImageMediaType = Literal["image/jpeg", "image/png", "image/gif", "image/webp"]

PROMPT_VERSION = "1.0.0"

# Anthropic list price for claude-haiku-4-5 (USD per token). Update if pricing
# changes; this drives ai_runs.cost_usd for per-client margin tracking.
_PRICE_IN_PER_TOKEN = 1.00 / 1_000_000
_PRICE_OUT_PER_TOKEN = 5.00 / 1_000_000

_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "prompts")


@dataclass
class FrameReview:
    description: str | None
    findings: dict[str, dict[str, Any]]  # {key: {"value": bool, "confidence": float}}
    tokens_in: int
    tokens_out: int
    cost_usd: float


CLIP_PROMPT_VERSION = "1.0.0"


def load_prompt(version: str = PROMPT_VERSION) -> str:
    path = os.path.join(_PROMPTS_DIR, f"frame_review-{version}.txt")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def load_clip_prompt(version: str = CLIP_PROMPT_VERSION) -> str:
    path = os.path.join(_PROMPTS_DIR, f"clip_review-{version}.txt")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _render_items_block(items: list[dict[str, Any]]) -> str:
    return "\n".join(f"- {it['key']} — {it.get('label', it['key'])}" for it in items)


_CLIP_PROMPT = load_clip_prompt()


def estimate_cost(tokens_in: int, tokens_out: int) -> float:
    return tokens_in * _PRICE_IN_PER_TOKEN + tokens_out * _PRICE_OUT_PER_TOKEN


def _image_block(image_bytes: bytes, media_type: ImageMediaType) -> ImageBlockParam:
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    return ImageBlockParam(
        type="image", source={"type": "base64", "media_type": media_type, "data": b64}
    )


class AiReviewer:
    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        prompt_version: str = PROMPT_VERSION,
    ) -> None:
        s = get_settings()
        self._settings = s
        self._client = client or anthropic.Anthropic(api_key=s.anthropic_api_key)
        self._prompt_version = prompt_version
        self._prompt = load_prompt(prompt_version)

    @property
    def model(self) -> str:
        return self._settings.ai_model

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    def _complete(
        self, content: list[ImageBlockParam | TextBlockParam], items: list[dict[str, Any]]
    ) -> FrameReview:
        messages: list[MessageParam] = [{"role": "user", "content": content}]
        message = self._client.messages.create(
            model=self._settings.ai_model,
            max_tokens=self._settings.ai_max_tokens,
            messages=messages,
        )
        text = "".join(block.text for block in message.content if block.type == "text")
        parsed = _parse_json_response(text)
        tokens_in = message.usage.input_tokens
        tokens_out = message.usage.output_tokens
        return FrameReview(
            description=parsed.get("description"),
            findings=_normalize_findings(parsed.get("findings", {}), items),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=estimate_cost(tokens_in, tokens_out),
        )

    def review_frame(
        self,
        image_bytes: bytes,
        items: list[dict[str, Any]],
        media_type: ImageMediaType = "image/jpeg",
    ) -> FrameReview:
        prompt = self._prompt.format(items_block=_render_items_block(items))
        content: list[ImageBlockParam | TextBlockParam] = [
            _image_block(image_bytes, media_type),
            TextBlockParam(type="text", text=prompt),
        ]
        return self._complete(content, items)

    def review_clip(
        self,
        images: list[bytes],
        items: list[dict[str, Any]],
        media_type: ImageMediaType = "image/jpeg",
    ) -> FrameReview:
        """Review a temporal clip from its ordered frame sequence."""
        prompt = _CLIP_PROMPT.format(items_block=_render_items_block(items), n=len(images))
        content: list[ImageBlockParam | TextBlockParam] = [
            _image_block(img, media_type) for img in images
        ]
        content.append(TextBlockParam(type="text", text=prompt))
        return self._complete(content, items)


def _parse_json_response(text: str) -> dict[str, Any]:
    text = text.strip()
    # Tolerate a fenced ```json block.
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[len("json") :]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object in model response: {text[:200]!r}")
    parsed: dict[str, Any] = json.loads(text[start : end + 1])
    return parsed


def _normalize_findings(
    raw: dict[str, Any], items: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Coerce every checklist key to {"value": bool, "confidence": float}."""
    out: dict[str, dict[str, Any]] = {}
    for item in items:
        key = item["key"]
        entry = raw.get(key) or {}
        value = bool(entry.get("value", False))
        try:
            confidence = float(entry.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        out[key] = {"value": value, "confidence": max(0.0, min(1.0, confidence))}
    return out


class StubReviewer:
    """Deterministic offline reviewer for local dev (EVAS_AI_STUB=true).

    Produces stable findings derived from the image bytes so the pipeline runs
    end-to-end without calling Anthropic. No tokens, no cost.
    """

    model = "stub"

    def __init__(self, prompt_version: str = PROMPT_VERSION) -> None:
        self.prompt_version = prompt_version

    def _findings(self, image_bytes: bytes, items: list[dict[str, Any]]) -> FrameReview:
        seed = sum(image_bytes[:64])
        findings = {
            item["key"]: {"value": (seed + i) % 2 == 0, "confidence": 0.9}
            for i, item in enumerate(items)
        }
        return FrameReview(
            description="stub review (offline)",
            findings=findings,
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
        )

    def review_frame(
        self, image_bytes: bytes, items: list[dict[str, Any]], media_type: str = "image/jpeg"
    ) -> FrameReview:
        return self._findings(image_bytes, items)

    def review_clip(
        self, images: list[bytes], items: list[dict[str, Any]], media_type: str = "image/jpeg"
    ) -> FrameReview:
        return self._findings(b"".join(images[:1]) or b"\x00", items)


def get_reviewer(prompt_version: str | None = None) -> AiReviewer | StubReviewer:
    """Return the configured reviewer: the offline stub when EVAS_AI_STUB is set.

    prompt_version overrides the active frame-prompt version (used by prompt A/B).
    """
    version = prompt_version or PROMPT_VERSION
    if get_settings().ai_stub:
        return StubReviewer(prompt_version=version)
    return AiReviewer(prompt_version=version)
