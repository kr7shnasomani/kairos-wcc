"""
Shared image utilities for the NIM CV / VLM inline base64 ceiling.

Previously, `OCRService._shrink_for_inline` (services/ocr.py) and
`PIDService._fit_b64` (services/pid.py) each defined their own version of
this algorithm and their own copy of `_NIM_IMAGE_SIZE_LIMIT`. Both are now
thin wrappers that call `shrink_image_for_nim()` below.

Design notes carried over from the original implementations:
- JPEG first, dimensions second: these are photographic scans/drawings, so
  re-encoding buys far more than dropping resolution. An 11x-over scan often
  clears the ceiling after the JPEG step alone, losing zero resolution.
- Scale steps start at 1.0 (unscaled) so callers never pay for a resize they
  do not need.
- Returns None when even the smallest step does not fit, so callers can log
  a clear failure rather than silently dropping the image.

Differences between the two callers that are preserved by their wrappers:
- `OCRService._shrink_for_inline` returns raw `(bytes, mime_str)` — the CV
  API receives raw bytes.
- `PIDService._fit_b64` returns `(b64_str, mime_str)` — the VLM receives an
  already-encoded string in a JSON payload.
"""

import base64
import io

import structlog

log = structlog.get_logger(__name__)

# Inline base64 cap for both the NIM CV API and the NIM VLM chat endpoint.
# Defined here once; imported by ocr.py and pid.py.
_NIM_IMAGE_SIZE_LIMIT = 180_000  # base64 chars


def shrink_image_for_nim(img_bytes: bytes) -> tuple[bytes, str] | None:
    """
    Re-encode an oversized image to fit the NIM inline base64 ceiling.

    Returns (raw_bytes, mime_str) on success, None if no step fits.

    Strategy: JPEG re-encode at full resolution first (huge wins for
    photographic scans/drawings), then progressive downscale.  Callers that
    need a base64 string should encode the returned bytes themselves.
    """
    try:
        from PIL import Image
    except Exception as exc:
        log.error("image_utils.pillow_unavailable", error=str(exc))
        return None

    try:
        img = Image.open(io.BytesIO(img_bytes))
        img.load()
        img = img.convert("RGB")  # JPEG has no alpha channel

        for scale in (1.0, 0.75, 0.5, 0.35, 0.25):
            candidate = img if scale == 1.0 else img.resize(
                (max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                Image.LANCZOS,
            )
            buf = io.BytesIO()
            candidate.save(buf, format="JPEG", quality=85, optimize=True)
            data = buf.getvalue()
            # Compute b64 length arithmetically — avoids building a multi-MB
            # string just to measure it.
            if 4 * ((len(data) + 2) // 3) <= _NIM_IMAGE_SIZE_LIMIT:
                return data, "image/jpeg"

        return None
    except Exception as exc:
        log.error("image_utils.shrink_failed", error=str(exc))
        return None


def shrink_image_for_nim_b64(img_bytes: bytes, img_mime: str) -> tuple[str, str] | None:
    """
    Same as `shrink_image_for_nim` but returns an already-encoded base64
    string instead of raw bytes.  Used by PIDService._fit_b64, which passes
    the string directly into a JSON VLM payload.

    If the image is already under the ceiling it is base64-encoded as-is
    without re-encoding (preserving the original mime type).
    """
    b64 = base64.b64encode(img_bytes).decode()
    if len(b64) <= _NIM_IMAGE_SIZE_LIMIT:
        return b64, img_mime

    result = shrink_image_for_nim(img_bytes)
    if result is None:
        return None
    data, mime = result
    return base64.b64encode(data).decode(), mime
