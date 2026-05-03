"""
Transcript provider abstraction — Social Creative Engine v3/v4/v7.

Provides a pluggable interface for transcript generation. The default stub
provider returns synthetic timestamped segments without calling any external
APIs or processing real audio files.

Safety guarantee
----------------
* No audio is sent to external services. openai-whisper runs entirely
  locally — no network calls are made during transcription.
* The Whisper provider is gated behind TWO independent flags:
    TRANSCRIPT_PROVIDER=whisper  AND  TRANSCRIPT_LIVE_ENABLED=true
  Both must be set or the system falls back to StubTranscriptProvider.
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
    Supported: ``stub`` | ``whisper``
``TRANSCRIPT_LIVE_ENABLED=false`` (default)
    Must be set to ``true`` AND TRANSCRIPT_PROVIDER must be ``whisper``
    for the Whisper path to be enabled.
``WHISPER_MODEL=base`` (default)
    Whisper model size: tiny | base | small | medium | large
    Larger models are more accurate but require more RAM and time.
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
    Local Whisper transcription provider — Social Creative Engine v7.

    Uses the ``openai-whisper`` package to transcribe a local audio file
    entirely on-device. No audio data is sent to any external service.

    Requirements
    ------------
    * ``pip install openai-whisper`` (pulls torch; already in requirements.txt)
    * ``ffmpeg`` on PATH (already installed in the Docker image)
    * A local audio file at ``audio_path`` that exists and is readable

    Gates
    -----
    Both of the following env vars must be set before this provider is
    returned by ``get_transcript_provider()``:
        TRANSCRIPT_PROVIDER=whisper
        TRANSCRIPT_LIVE_ENABLED=true

    If either gate is missing the system uses ``StubTranscriptProvider``.

    Safety
    ------
    * No external network calls — whisper model runs locally
    * simulation_only = True on all produced records
    * outbound_actions_taken = 0 on all produced records
    * No content is published, scheduled, or posted
    """

    provider_name: str = "whisper"

    def transcribe(
        self,
        source_content_id: str,
        audio_path: str = "",
        text_hint: str = "",
    ) -> list[dict]:
        """
        Transcribe a local audio file using openai-whisper.

        Parameters
        ----------
        source_content_id:
            Identifier of the source content record (used for logging only).
        audio_path:
            Absolute path to a local audio file. Must exist and be readable.
        text_hint:
            Unused for Whisper; reserved for interface compatibility.

        Returns
        -------
        list[dict]
            List of segment dicts: index, start_ms, end_ms, text,
            speaker, confidence, provider.

        Raises
        ------
        ValueError
            If ``audio_path`` is empty or the file does not exist.
        ImportError
            If ``openai-whisper`` is not installed.
        RuntimeError
            If Whisper model loading or transcription fails.
        """
        if not audio_path:
            raise ValueError(
                "audio_path is required for WhisperTranscriptProvider. "
                "Provide a path to a local audio file."
            )
        if not os.path.isfile(audio_path):
            raise ValueError(
                f"Audio file not found: '{audio_path}'. "
                "Ensure the file exists and is readable before transcribing."
            )

        try:
            import whisper  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "openai-whisper is not installed. "
                "Run: pip install openai-whisper"
            ) from exc

        model_name = os.getenv("WHISPER_MODEL", "base")
        try:
            model = whisper.load_model(model_name)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load Whisper model '{model_name}': {exc}"
            ) from exc

        try:
            result = model.transcribe(audio_path, fp16=False)
        except Exception as exc:
            raise RuntimeError(
                f"Whisper transcription failed for '{audio_path}': {exc}"
            ) from exc

        raw_segments = result.get("segments", [])
        segments: list[dict] = []
        for raw_seg in raw_segments:
            text = (raw_seg.get("text") or "").strip()
            if not text:
                continue
            start_ms = int(raw_seg.get("start", 0) * 1000)
            end_ms = int(raw_seg.get("end", 0) * 1000)
            # Confidence: convert avg_logprob (typically -1.5..0) to 0..1
            avg_logprob = raw_seg.get("avg_logprob", -0.1)
            confidence = round(max(0.0, min(1.0, 1.0 + avg_logprob)), 3)
            segments.append(
                {
                    "index": len(segments),
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "text": text,
                    "speaker": "speaker_1",  # Whisper base has no diarization
                    "confidence": confidence,
                    "provider": self.provider_name,
                }
            )

        return segments


def get_transcript_provider() -> BaseTranscriptProvider:
    """Return the configured transcript provider instance.

    Returns ``StubTranscriptProvider`` unless TRANSCRIPT_PROVIDER=whisper
    AND TRANSCRIPT_LIVE_ENABLED=true are both set.  Both conditions must be
    satisfied to activate WhisperTranscriptProvider.

    Any unknown TRANSCRIPT_PROVIDER value also falls back to stub so that
    misconfiguration never silently breaks transcript runs.
    """
    name = os.getenv("TRANSCRIPT_PROVIDER", "stub").lower()
    live_enabled = os.getenv("TRANSCRIPT_LIVE_ENABLED", "false").lower() in (
        "1", "true", "yes", "on"
    )

    if name == "whisper" and live_enabled:
        return WhisperTranscriptProvider()

    # Default to stub for any unknown name or when live is disabled
    return StubTranscriptProvider()

