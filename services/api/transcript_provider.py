"""
Transcript provider abstraction — Social Creative Engine v3/v4.

Provides a pluggable interface for transcript generation. The default stub
provider returns synthetic timestamped segments without calling any external
APIs or processing real audio files.

Safety guarantee
----------------
* No audio is sent to external services unless TRANSCRIPT_PROVIDER is set
  to a live provider AND TRANSCRIPT_LIVE_ENABLED=true.
* No content is published, scheduled, or posted.
* simulation_only = True on all records produced by this module.

Provider interface
------------------
All providers must implement::

    def transcribe(
        self,
        source_content_id: str,
        audio_path: str = "",
        text_hint: str = "",
    ) -> list[dict]:
        ...

Each returned dict must contain:
    index, start_ms, end_ms, text, speaker, confidence, provider

Adding a real provider
----------------------
Implement a class following the interface above. Register it in
``get_transcript_provider()`` under its env-var name. Gate with
``TRANSCRIPT_LIVE_ENABLED=true`` to prevent accidental live calls.

Env vars
--------
``TRANSCRIPT_PROVIDER=stub`` (default)
    Supported: ``stub`` | ``whisper`` (not yet live)
``TRANSCRIPT_LIVE_ENABLED=false`` (default)
    Must be set to ``true`` AND TRANSCRIPT_PROVIDER must be non-stub
    for any live transcription path to be enabled.
"""
from __future__ import annotations

import math
import os


class BaseTranscriptProvider:
    """
    Interface that all transcript providers must satisfy.

    Subclasses must set ``provider_name`` and implement ``transcribe()``.
    """

    provider_name: str = "base"

    def transcribe(
        self,
        source_content_id: str,
        audio_path: str = "",
        text_hint: str = "",
    ) -> list[dict]:
        raise NotImplementedError  # pragma: no cover


class StubTranscriptProvider(BaseTranscriptProvider):
    """
    Stub provider — always safe, always local.

    Splits ``text_hint`` (or a built-in sample sentence) into word chunks and
    returns synthetic timestamped segment dicts.  No files are read; no
    external calls are made.
    """

    provider_name: str = "stub"

    _SAMPLE_TEXT = (
        "Welcome back. Today we are talking about one of the most important things in your business. "
        "Customer trust is everything. You have to earn it every single day. "
        "The way you earn it is by showing up consistently, delivering real value, and keeping your word. "
        "That is how we built our company from nothing to something real. "
        "Every estimate got a next-day follow-up from a real person, not a robot. "
        "By the end of the week we had ten jobs booked. Simple system, executed consistently. "
        "No tricks, no gimmicks — just showing up and doing the work every single time."
    )

    def transcribe(
        self,
        source_content_id: str,
        audio_path: str = "",
        text_hint: str = "",
    ) -> list[dict]:
        """
        Return a list of transcript segment dicts.

        Each segment contains:
            index, start_ms, end_ms, text, speaker, confidence, provider
        """
        base_text = text_hint.strip() if text_hint.strip() else self._SAMPLE_TEXT
        words = base_text.split()
        chunk_size = max(8, math.ceil(len(words) / 6))

        segments: list[dict] = []
        start_ms = 0
        for i in range(0, len(words), chunk_size):
            chunk = words[i : i + chunk_size]
            text = " ".join(chunk)
            # ~580 ms per word average spoken pace
            duration_ms = len(chunk) * 580
            segments.append(
                {
                    "index": len(segments),
                    "start_ms": start_ms,
                    "end_ms": start_ms + duration_ms,
                    "text": text,
                    "speaker": "speaker_1",
                    "confidence": 0.92,
                    "provider": self.provider_name,
                }
            )
            start_ms += duration_ms + 200  # 200 ms gap between segments

        return segments


class WhisperTranscriptProvider(BaseTranscriptProvider):
    """
    Placeholder for future OpenAI Whisper / local Whisper integration.

    Not yet implemented. Raises ``NotImplementedError`` if called, so it
    fails loudly rather than silently returning wrong data.

    To activate in the future:
    1. Implement ``transcribe()`` using the openai SDK or whisper CLI.
    2. Set TRANSCRIPT_PROVIDER=whisper and TRANSCRIPT_LIVE_ENABLED=true.
    3. Add tests in test_social_creative_engine_v4.py.

    Safety: must never send audio to any external service unless the
    operator has explicitly enabled TRANSCRIPT_LIVE_ENABLED=true.
    """

    provider_name: str = "whisper"

    def transcribe(
        self,
        source_content_id: str,
        audio_path: str = "",
        text_hint: str = "",
    ) -> list[dict]:
        raise NotImplementedError(
            "WhisperTranscriptProvider is not yet implemented. "
            "Set TRANSCRIPT_PROVIDER=stub to use the safe stub provider."
        )


def get_transcript_provider() -> BaseTranscriptProvider:
    """Return the configured transcript provider instance.

    Returns ``StubTranscriptProvider`` unless TRANSCRIPT_PROVIDER is set to
    a known live provider AND TRANSCRIPT_LIVE_ENABLED=true.  Both conditions
    must be satisfied to use a non-stub provider.
    """
    name = os.getenv("TRANSCRIPT_PROVIDER", "stub").lower()
    live_enabled = os.getenv("TRANSCRIPT_LIVE_ENABLED", "false").lower() in (
        "1", "true", "yes", "on"
    )

    if name == "whisper" and live_enabled:
        return WhisperTranscriptProvider()

    # Default to stub for any unknown name or when live is disabled
    return StubTranscriptProvider()

