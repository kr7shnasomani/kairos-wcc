"""
WhisperService — Layer 3: Voice Transcription via Groq API (whisper-large-v3).
Sends audio bytes to Groq's transcription endpoint; no local model required.
Falls back gracefully when GROQ_API_KEY is not configured.
"""

import os
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

_GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


class WhisperService:
    """
    Transcribes audio via Groq's Whisper-large-v3 API.
    Uses sync httpx — safe to call from Celery tasks.
    """

    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY", "")
        self.model = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3")

    def transcribe(self, audio_bytes: bytes, filename: str = "audio.wav") -> dict[str, Any]:
        """
        Transcribe audio bytes via Groq API.
        Returns {text, language, confidence, segments}.
        confidence is derived from avg_logprob across segments (clamped 0–1).
        """
        if not self.api_key:
            log.warning("whisper.no_api_key", hint="Set GROQ_API_KEY in .env")
            return {
                "text": "",
                "language": "unknown",
                "confidence": 0.0,
                "segments": [],
                "error": "groq_api_key_not_configured",
            }

        # Detect content-type from extension
        ext = os.path.splitext(filename)[-1].lower()
        mime = {
            ".wav": "audio/wav", ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4", ".ogg": "audio/ogg",
            ".flac": "audio/flac", ".webm": "audio/webm",
        }.get(ext, "audio/wav")

        try:
            resp = httpx.post(
                _GROQ_TRANSCRIPTION_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                files={"file": (filename, audio_bytes, mime)},
                data={"model": self.model, "response_format": "verbose_json"},
                timeout=60.0,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.error("whisper.api_error",
                      status=exc.response.status_code,
                      body=exc.response.text[:200])
            return {
                "text": "", "language": "unknown", "confidence": 0.0,
                "segments": [], "error": f"groq_api_{exc.response.status_code}",
            }
        except Exception as exc:
            log.error("whisper.request_failed", error=str(exc))
            return {
                "text": "", "language": "unknown", "confidence": 0.0,
                "segments": [], "error": str(exc),
            }

        data = resp.json()
        segments = data.get("segments", [])

        # avg_logprob from Groq verbose_json: typically -0.5 to 0; map to 0–1
        if segments:
            avg_logprob = sum(s.get("avg_logprob", -0.5) for s in segments) / len(segments)
            confidence = round(min(1.0, max(0.0, 1.0 + avg_logprob)), 4)
        else:
            confidence = 0.8  # no segments = short clip, assume ok

        log.info("whisper.transcribed",
                 text_length=len(data.get("text", "")),
                 language=data.get("language"),
                 confidence=confidence,
                 model=self.model)

        return {
            "text": data.get("text", "").strip(),
            "language": data.get("language", "en"),
            "confidence": confidence,
            "segments": [
                {"start": s["start"], "end": s["end"], "text": s["text"]}
                for s in segments
            ],
        }
