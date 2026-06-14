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


def _answer_spec(item: dict[str, Any]) -> str:
    """One-line description of the answer the model must give for this item."""
    t = item.get("type", "boolean")
    if t == "category":
        opts = ", ".join(item.get("options", [])) or "(no options defined)"
        return f"choose exactly one of: {opts}"
    if t == "multi_boolean":
        subs = ", ".join(o.get("key", "") for o in item.get("options", []))
        return f"answer true or false for each of: {subs}"
    if t == "text":
        return "a short free-text answer"
    if t == "number":
        lo, hi = item.get("min"), item.get("max")
        if lo is not None or hi is not None:
            lo_s = lo if lo is not None else "?"
            hi_s = hi if hi is not None else "?"
            return f"a number between {lo_s} and {hi_s}"
        return "a number"
    return "answer true or false"


def _render_items_block(items: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"- {it['key']} ({_answer_spec(it)}) — {it.get('label', it['key'])}" for it in items
    )


# Type-agnostic output contract appended to a (per-checklist or default) framing.
# Guarantees a parseable JSON shape regardless of what a UI author types.
_CONTRACT = """\
Checklist items (key (how to answer) — description):
{items_block}

Respond with ONLY a JSON object, no prose, in exactly this shape:
{{
  "description": "<one short sentence describing what is shown>",
  "findings": {{
    "<item_key>": <the answer, in the shape for that item's type>
  }}
}}

Answer shapes by item type:
- true/false item        -> {{"value": true|false, "confidence": 0.0-1.0}}
- choose-one item        -> {{"value": "<one of the listed options>", "confidence": 0.0-1.0}}
- true/false-for-each    -> {{"values": {{"<sub_key>": true|false, ...}}, "confidence": 0.0-1.0}}
- free-text item         -> {{"text": "<answer>", "confidence": 0.0-1.0}}
- number item            -> {{"value": <number>, "confidence": 0.0-1.0}}

Rules:
- Include every checklist item key in "findings".
- "confidence" is always a number in [0.0, 1.0]; when unsure, lower it rather than guessing.
- Judge only what is visible. Do not infer beyond what is shown."""

DEFAULT_FRAMING = (
    "You are an image auditor. You will be shown an image (or, for temporal "
    "review, an ordered sequence of frames) and a checklist. Evaluate the "
    "checklist against what is visible."
)


def _build_prompt(framing: str, items: list[dict[str, Any]], *, n_frames: int | None = None) -> str:
    seq = "" if n_frames is None else f"\nYou are shown {n_frames} ordered frames of a single clip."
    return f"{framing}{seq}\n\n" + _CONTRACT.format(items_block=_render_items_block(items))


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
        framing: str | None = None,
    ) -> None:
        s = get_settings()
        self._settings = s
        self._client = client or anthropic.Anthropic(api_key=s.anthropic_api_key)
        self._prompt_version = prompt_version
        # framing mode (per-checklist or default): code appends the output
        # contract. file mode (explicit prompt_version, e.g. A/B): the file is
        # the whole prompt and must contain an {items_block} placeholder.
        self._framing = framing
        self._prompt = None if framing is not None else load_prompt(prompt_version)

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
        if self._framing is not None:
            prompt = _build_prompt(self._framing, items)
        else:
            assert self._prompt is not None
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
        if self._framing is not None:
            prompt = _build_prompt(self._framing, items, n_frames=len(images))
        else:
            assert self._prompt is not None  # clip uses its own file template
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


def _clamp_conf(entry: dict[str, Any]) -> float:
    try:
        confidence = float(entry.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    return max(0.0, min(1.0, confidence))


def _normalize_findings(
    raw: dict[str, Any], items: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Coerce every checklist key into the canonical shape for its item type.

    Tolerant of malformed model output: missing/garbage values fall back to a
    safe default (false / null / "") so the row is always persistable.
    """
    out: dict[str, dict[str, Any]] = {}
    for item in items:
        key = item["key"]
        itype = item.get("type", "boolean")
        entry = raw.get(key) if isinstance(raw.get(key), dict) else {}
        entry = entry or {}
        conf = _clamp_conf(entry)

        if itype == "category":
            value = entry.get("value")
            options = item.get("options", [])
            out[key] = {"value": value if value in options else None, "confidence": conf}
        elif itype == "multi_boolean":
            given = entry.get("values") if isinstance(entry.get("values"), dict) else {}
            given = given or {}
            values = {
                o["key"]: bool(given.get(o["key"], False))
                for o in item.get("options", [])
                if isinstance(o, dict) and o.get("key")
            }
            out[key] = {"values": values, "confidence": conf}
        elif itype == "text":
            text = entry.get("text")
            out[key] = {"text": str(text) if text is not None else "", "confidence": conf}
        elif itype == "number":
            raw_val = entry.get("value")
            try:
                num: float | None = float(raw_val) if raw_val is not None else None
            except (TypeError, ValueError):
                num = None
            out[key] = {"value": num, "confidence": conf}
        else:  # boolean
            out[key] = {"value": bool(entry.get("value", False)), "confidence": conf}
    return out


class StubReviewer:
    """Deterministic offline reviewer for local dev (EVAS_AI_STUB=true).

    Produces stable findings derived from the image bytes so the pipeline runs
    end-to-end without calling Anthropic. No tokens, no cost.
    """

    model = "stub"

    def __init__(self, prompt_version: str = PROMPT_VERSION) -> None:
        self.prompt_version = prompt_version

    def _stub_value(self, item: dict[str, Any], seed: int, i: int) -> dict[str, Any]:
        t = item.get("type", "boolean")
        if t == "category":
            opts = item.get("options") or ["unknown"]
            return {"value": opts[(seed + i) % len(opts)], "confidence": 0.9}
        if t == "multi_boolean":
            opts = [o for o in item.get("options", []) if isinstance(o, dict) and o.get("key")]
            return {
                "values": {o["key"]: (seed + j) % 2 == 0 for j, o in enumerate(opts)},
                "confidence": 0.9,
            }
        if t == "text":
            return {"text": "stub description (offline)", "confidence": 0.9}
        if t == "number":
            lo = float(item.get("min", 0) or 0)
            hi = float(item.get("max", 10) or 10)
            span = max(1, int(hi - lo) + 1)
            return {"value": lo + float((seed + i) % span), "confidence": 0.9}
        return {"value": (seed + i) % 2 == 0, "confidence": 0.9}

    def _findings(self, image_bytes: bytes, items: list[dict[str, Any]]) -> FrameReview:
        seed = sum(image_bytes[:64])
        findings = {item["key"]: self._stub_value(item, seed, i) for i, item in enumerate(items)}
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


def get_reviewer(
    prompt_version: str | None = None, prompt_template: str | None = None
) -> AiReviewer | StubReviewer:
    """Return the configured reviewer: the offline stub when EVAS_AI_STUB is set.

    Resolution:
    - prompt_version given (prompt A/B) → load that versioned prompt *file* whole.
    - else prompt_template given (per-checklist UI config) → use it as framing,
      with the output contract appended by code.
    - else → default framing + contract.
    """
    version = prompt_version or PROMPT_VERSION
    if get_settings().ai_stub:
        return StubReviewer(prompt_version=version)
    if prompt_version:
        return AiReviewer(prompt_version=version)
    return AiReviewer(prompt_version=version, framing=prompt_template or DEFAULT_FRAMING)
