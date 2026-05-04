"""
Snippet Scorer — Social Creative Engine v6.5

Deterministic scoring of content snippets for hook strength and content quality.

No external API calls are made.  All results carry simulation_only=True and
outbound_actions_taken=0.

Scoring dimensions
------------------
hook_strength       (0–10)  First-impression hook quality
clarity_score       (0–10)  Readability and concision
emotional_impact    (0–10)  Emotional resonance and personal connection
shareability_score  (0–10)  Virality indicators (contrarian, curiosity, stats)
platform_fit_score  (0–10)  Short-form vertical video suitability

Overall score is a weighted average:
    hook_strength      × 0.30
    clarity_score      × 0.20
    emotional_impact   × 0.20
    shareability_score × 0.20
    platform_fit_score × 0.10

Hook extraction
---------------
hook_text         First compelling phrase extracted from transcript (≤ 120 chars)
hook_type         One of: curiosity | bold_statement | contrarian |
                          emotional | educational | story
alternative_hooks 2–3 deterministic rewrite variants

Usage
-----
    from snippet_scorer import score_snippet, SCORE_THRESHOLD_DEFAULT

    result = score_snippet("Stop doing this one thing that's killing your leads.")
    print(result.overall_score)   # e.g. 7.4
    print(result.hook_type)       # "contrarian"
    print(result.alternative_hooks)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

SCORE_THRESHOLD_DEFAULT: float = 6.0

HOOK_TYPES: frozenset[str] = frozenset(
    {
        "curiosity",
        "bold_statement",
        "contrarian",
        "emotional",
        "educational",
        "story",
    }
)

# Weighted contribution of each dimension to overall_score
_WEIGHTS: dict[str, float] = {
    "hook_strength": 0.30,
    "clarity_score": 0.20,
    "emotional_impact": 0.20,
    "shareability_score": 0.20,
    "platform_fit_score": 0.10,
}


# ---------------------------------------------------------------------------
# Value object
# ---------------------------------------------------------------------------


@dataclass
class SnippetScoreResult:
    """
    Structured scoring result for one content snippet.

    Fields
    ------
    hook_strength, clarity_score, emotional_impact,
    shareability_score, platform_fit_score : float
        Individual dimension scores clamped to [0.0, 10.0].
    overall_score : float
        Weighted average of the five dimensions, clamped to [0.0, 10.0].
    score_reason : str
        Human-readable summary of the scoring rationale.
    hook_text : str
        Extracted hook phrase from the first sentence of the transcript.
    hook_type : str
        Classified hook type (one of HOOK_TYPES).
    alternative_hooks : list[str]
        2–3 deterministic alternative hook phrasings.
    simulation_only : bool
        Always True — no external API calls are made.
    outbound_actions_taken : int
        Always 0.
    """

    hook_strength: float = 0.0
    clarity_score: float = 0.0
    emotional_impact: float = 0.0
    shareability_score: float = 0.0
    platform_fit_score: float = 0.0
    overall_score: float = 0.0
    score_reason: str = ""
    hook_text: str = ""
    hook_type: str = "bold_statement"
    alternative_hooks: list[str] = field(default_factory=list)
    simulation_only: bool = True
    outbound_actions_taken: int = 0


# ---------------------------------------------------------------------------
# Pattern libraries
# ---------------------------------------------------------------------------

_CURIOSITY_PATTERNS: list[str] = [
    r"here'?s? why",
    r"the reason",
    r"what nobody tells?",
    r"little[- ]known",
    r"secret(ly)?",
    r"you won'?t believe",
    r"surprising(ly)?",
    r"actually\b",
]

_BOLD_PATTERNS: list[str] = [
    r"\b(most|all|every|always|never|best|worst|only|number\s+one|#1)\b",
    r"\b\d+\b.{0,20}\b(tip|step|way|reason|thing|secret|hack|mistake)\b",
]

_CONTRARIAN_PATTERNS: list[str] = [
    r"stop (doing|saying|thinking|using)",
    r"wrong about",
    r"(nobody|no one) tells?",
    r"\bmyth\b",
    r"actually (bad|wrong|false|terrible)",
    r"don'?t (do|use|follow|trust|rely)",
    r"quit\b",
    r"unlearn",
]

_EMOTIONAL_KEYWORDS: list[str] = [
    "transform",
    "struggle",
    "pain",
    "amazing",
    "incredible",
    "fear",
    "love",
    "hate",
    "breakthrough",
    "powerful",
    "life-changing",
    "fail",
    "success",
    "dream",
    "hope",
    "lost",
    "found",
    "vulnerable",
    "terrified",
    "excited",
    "overwhelmed",
]

_EDUCATIONAL_PATTERNS: list[str] = [
    r"how to\b",
    r"step[- ]by[- ]step",
    r"\b\d+\s+(step|tip|way|reason|thing|hack)s?\b",
    r"\blearn\b",
    r"\bguide\b",
    r"\btutorial\b",
    r"explained?",
    r"\bformula\b",
    r"\bframework\b",
]

_STORY_PATTERNS: list[str] = [
    r"\bwhen i\b",
    r"\bhow i\b",
    r"\bmy (story|journey|experience|struggle|mistake)\b",
    r"\bone day\b",
    r"\bi (was|used to|didn'?t|couldn'?t|wouldn'?t)\b",
    r"\bit (started|began|happened|changed)\b",
    r"\byears ago\b",
]

_JARGON_PATTERNS: list[str] = [
    r"\bsynergy\b",
    r"\bleverage\b",
    r"\butilize\b",
    r"\bparadigm\b",
    r"\bbandwidth\b",
    r"\bscalable\b",
    r"\bpivot\b",
    r"\bblockchain\b",
]

_FILLER_PATTERNS: list[str] = [
    r"\bum\b",
    r"\buh\b",
    r"\byou know\b",
    r"\bbasically\b",
    r"\bliterally\b",
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _clamp(v: float) -> float:
    return max(0.0, min(10.0, round(v, 1)))


def _matches_any(text: str, patterns: list[str]) -> int:
    """Count distinct pattern matches (capped at list length)."""
    count = 0
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            count += 1
    return count


def _truncate_words(text: str, n: int) -> str:
    words = text.strip().split()
    return " ".join(words[:n])


# ---------------------------------------------------------------------------
# Dimension scorers
# ---------------------------------------------------------------------------


def _score_hook_strength(text: str) -> float:
    score = 0.0
    if "?" in text:
        score += 2.5
    if "!" in text:
        score += 0.5
    if re.search(
        r"\b(never|always|stop|start|best|worst|most|every|only|quit|unlearn)\b",
        text,
        re.IGNORECASE,
    ):
        score += 2.0
    if re.search(r"\b\d+\b", text):
        score += 1.5
    if len(text.strip().split()) <= 20:
        score += 2.0
    elif len(text.strip().split()) <= 40:
        score += 1.0
    if re.search(r"\b(you|your|we)\b", text, re.IGNORECASE):
        score += 1.0
    if re.search(r"^\s*[A-Z]", text):  # starts with capital — declarative
        score += 0.5
    return _clamp(score)


def _score_clarity(text: str) -> float:
    score = 5.0
    words = text.split()
    word_count = len(words)
    if word_count < 20:
        score += 2.0
    elif word_count < 40:
        score += 1.0
    elif word_count > 80:
        score -= 2.0
    filler_count = _matches_any(text, _FILLER_PATTERNS)
    score -= filler_count * 0.8
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    if sentences:
        avg_len = sum(len(s.split()) for s in sentences) / len(sentences)
        if avg_len < 15:
            score += 1.5
        elif avg_len > 30:
            score -= 1.0
    return _clamp(score)


def _score_emotional_impact(text: str) -> float:
    score = 0.0
    lower = text.lower()
    matched = sum(1 for kw in _EMOTIONAL_KEYWORDS if kw in lower)
    score += min(4.0, matched * 1.5)
    if re.search(r"\b(you|your)\b", text, re.IGNORECASE):
        score += 2.0
    if re.search(r"\b(i |i'| me | my )\b", text, re.IGNORECASE):
        score += 1.5
    if "!" in text:
        score += 0.5
    if re.search(r"\b(now|today|tonight|this week|right now)\b", text, re.IGNORECASE):
        score += 0.5
    return _clamp(score)


def _score_shareability(text: str) -> float:
    score = 0.0
    contrarian = _matches_any(text, _CONTRARIAN_PATTERNS)
    score += min(3.0, contrarian * 2.0)
    curiosity = _matches_any(text, _CURIOSITY_PATTERNS)
    score += min(2.0, curiosity * 1.5)
    if re.search(r"\b\d+\b", text):
        score += 1.5
    if len(text.strip().split()) <= 25:
        score += 1.5
    if re.search(
        r"\b(tip|hack|secret|truth|myth|mistake|lesson|warning)\b",
        text,
        re.IGNORECASE,
    ):
        score += 1.5
    return _clamp(score)


def _score_platform_fit(text: str) -> float:
    score = 5.0
    words = text.split()
    word_count = len(words)
    if word_count <= 30:
        score += 2.0
    elif word_count <= 60:
        score += 1.0
    elif word_count > 100:
        score -= 2.0
    jargon_count = _matches_any(text, _JARGON_PATTERNS)
    score -= jargon_count * 0.8
    if re.search(
        r"\b(how to|tip|step|mistake|secret|hack|learn)\b", text, re.IGNORECASE
    ):
        score += 1.5
    if re.search(r"[?!]", text):
        score += 0.5
    return _clamp(score)


# ---------------------------------------------------------------------------
# Hook type classification
# ---------------------------------------------------------------------------


def _detect_hook_type(text: str) -> str:
    """Classify the dominant hook type from the transcript text."""
    if _matches_any(text, _CONTRARIAN_PATTERNS) >= 1:
        return "contrarian"
    if _matches_any(text, _STORY_PATTERNS) >= 1:
        return "story"
    lower = text.lower()
    emotional_hits = sum(1 for kw in _EMOTIONAL_KEYWORDS[:8] if kw in lower)
    has_personal = bool(re.search(r"\b(i |my |i')\b", text, re.IGNORECASE))
    if emotional_hits >= 1 and has_personal:
        return "emotional"
    if _matches_any(text, _CURIOSITY_PATTERNS) >= 1:
        return "curiosity"
    if _matches_any(text, _EDUCATIONAL_PATTERNS) >= 1:
        return "educational"
    return "bold_statement"


# ---------------------------------------------------------------------------
# Hook text extraction
# ---------------------------------------------------------------------------


def _extract_hook_text(transcript_text: str) -> str:
    """
    Extract the first compelling phrase from a transcript.

    Returns the first sentence (up to 120 characters) or the first 120
    characters of the text if no sentence boundary is found.
    """
    text = transcript_text.strip()
    if not text:
        return ""
    m = re.match(r"^(.{10,120}?[.!?])", text)
    if m:
        return m.group(1).strip()
    if len(text) <= 120:
        return text
    return text[:120].rstrip()


# ---------------------------------------------------------------------------
# Alternative hook generation
# ---------------------------------------------------------------------------


def _build_alternatives(
    hook_text: str,
    hook_type: str,
    transcript_text: str,
) -> list[str]:
    """
    Generate 2–3 deterministic alternative hook phrasings.

    Variants are derived from the hook_text and transcript without any
    external API calls.
    """
    core = _truncate_words(hook_text.rstrip(".!?"), 10)
    snippet_core = _truncate_words(transcript_text, 10).rstrip(".!?")
    alts: list[str] = []

    # Curiosity reframe
    alts.append(f"Here's what most people get wrong about {core.lower()}…")

    # Question hook
    first_words = _truncate_words(hook_text, 7).rstrip(".!?")
    alts.append(f"Did you know {first_words.lower()}?")

    # Bold declarative
    alts.append(f"The truth: {snippet_core}.")

    return alts[:3]


# ---------------------------------------------------------------------------
# Score reason builder
# ---------------------------------------------------------------------------


def _build_score_reason(
    hook_strength: float,
    clarity_score: float,
    emotional_impact: float,
    shareability_score: float,
    platform_fit_score: float,
    overall_score: float,
    hook_type: str,
) -> str:
    parts: list[str] = []

    if hook_strength >= 7:
        parts.append("strong hook")
    elif hook_strength < 4:
        parts.append("weak hook")

    if clarity_score >= 7:
        parts.append("clear and concise")
    elif clarity_score < 4:
        parts.append("lacks clarity")

    if emotional_impact >= 6:
        parts.append("emotionally engaging")
    elif emotional_impact < 3:
        parts.append("low emotional impact")

    if shareability_score >= 7:
        parts.append("highly shareable")
    elif shareability_score < 4:
        parts.append("low shareability")

    if platform_fit_score >= 7:
        parts.append("strong platform fit")
    elif platform_fit_score < 4:
        parts.append("poor platform fit")

    parts.append(f"hook type: {hook_type}")

    if overall_score >= 7.5:
        prefix = "High quality"
    elif overall_score >= 5.5:
        prefix = "Moderate quality"
    else:
        prefix = "Needs improvement"

    return f"{prefix} — {', '.join(parts)}. Overall: {overall_score:.1f}/10."


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_snippet(transcript_text: str) -> SnippetScoreResult:
    """
    Score a content snippet deterministically from its transcript text.

    Parameters
    ----------
    transcript_text : str
        The raw transcript text of the snippet to score.

    Returns
    -------
    SnippetScoreResult
        Populated with all scoring dimensions, hook extraction, and safety
        invariants (simulation_only=True, outbound_actions_taken=0).

    Notes
    -----
    * Scoring is purely deterministic — same input always produces same output.
    * No external API calls are made.
    * Scores are clamped to [0.0, 10.0].
    * Empty text returns all zeros with hook_type="bold_statement".
    """
    text = (transcript_text or "").strip()

    if not text:
        return SnippetScoreResult(
            score_reason="Empty transcript — all scores are 0.",
            simulation_only=True,
            outbound_actions_taken=0,
        )

    hook_strength = _score_hook_strength(text)
    clarity_score = _score_clarity(text)
    emotional_impact = _score_emotional_impact(text)
    shareability_score = _score_shareability(text)
    platform_fit_score = _score_platform_fit(text)

    overall_score = _clamp(
        hook_strength * _WEIGHTS["hook_strength"]
        + clarity_score * _WEIGHTS["clarity_score"]
        + emotional_impact * _WEIGHTS["emotional_impact"]
        + shareability_score * _WEIGHTS["shareability_score"]
        + platform_fit_score * _WEIGHTS["platform_fit_score"]
    )

    hook_text = _extract_hook_text(text)
    hook_type = _detect_hook_type(text)
    alternative_hooks = (
        _build_alternatives(hook_text, hook_type, text) if hook_text else []
    )

    score_reason = _build_score_reason(
        hook_strength,
        clarity_score,
        emotional_impact,
        shareability_score,
        platform_fit_score,
        overall_score,
        hook_type,
    )

    return SnippetScoreResult(
        hook_strength=hook_strength,
        clarity_score=clarity_score,
        emotional_impact=emotional_impact,
        shareability_score=shareability_score,
        platform_fit_score=platform_fit_score,
        overall_score=overall_score,
        score_reason=score_reason,
        hook_text=hook_text,
        hook_type=hook_type,
        alternative_hooks=alternative_hooks,
        simulation_only=True,
        outbound_actions_taken=0,
    )


# ---------------------------------------------------------------------------
# Hook cleanup & editorial title generation (v10.3)
# ---------------------------------------------------------------------------

@dataclass
class HookCleanupResult:
    """
    Editorial display fields derived from a raw extracted hook_text.

    These fields are separate from and do not modify the original hook_text
    or transcript.  simulation_only is always True.
    """

    cleaned_hook_text: str = ""
    display_title: str = ""
    caption_hook_suggestions: list[str] = field(default_factory=list)
    hook_cleanup_notes: str = ""
    simulation_only: bool = True
    outbound_actions_taken: int = 0


# Patterns that indicate the raw hook is a mid-sentence fragment
_MID_SENTENCE_STARTS = re.compile(
    r"^(your|my|our|their|its|his|her|the|a|an|this|that|these|those|"
    r"and|but|or|so|yet|for|nor|because|since|although|though|"
    r"if|when|while|after|before|as|with|without|by|in|on|at|to|of|"
    r"here is what i know|here'?s? what i know|choice:|here is|here'?s?)\b",
    re.IGNORECASE,
)

# Prefix fragments to strip before building a display title
_STRIP_PREFIXES = [
    r"^here is what i know\s*:\s*",
    r"^here'?s?\s+what\s+i\s+know\s*:\s*",
    r"^here is\s+",
    r"^here'?s?\s+",
    r"^choice\s*:\s*",
    r"^the\s+choice\s*:\s*",
    r"^and\s+",
    r"^but\s+",
    r"^so\s+",
]


def _strip_leading_fragment(text: str) -> str:
    """Remove known leading fragment prefixes from a raw hook."""
    for pat in _STRIP_PREFIXES:
        cleaned = re.sub(pat, "", text, flags=re.IGNORECASE).strip()
        if cleaned and cleaned != text.strip():
            return cleaned
    return text.strip()


def _to_title_case(text: str) -> str:
    """Title-case a string, preserving interior acronyms."""
    minor_words = {"a", "an", "and", "at", "but", "by", "for", "in",
                   "nor", "of", "on", "or", "so", "the", "to", "yet"}
    words = text.strip().split()
    result = []
    for i, word in enumerate(words):
        if i == 0 or i == len(words) - 1:
            result.append(word.capitalize())
        elif word.lower() in minor_words:
            result.append(word.lower())
        else:
            result.append(word.capitalize())
    return " ".join(result)


def _infer_display_title(raw_hook: str, transcript_text: str) -> tuple[str, str]:
    """
    Return (display_title, cleanup_notes).

    Rules:
    - If raw_hook is a question starting with a capital: title-case as-is
    - If raw_hook has a strip prefix (e.g. "here is what I know:"): strip it
    - If raw_hook is a mid-sentence fragment: search transcript for the full
      sentence and reconstruct a thematic title
    - Fallback: title-case the stripped hook
    - No quotation marks around the output
    """
    stripped = raw_hook.strip().rstrip(".")
    notes_parts: list[str] = []

    # Always try stripping known leading fragments first
    after_strip = _strip_leading_fragment(stripped)
    if after_strip != stripped:
        notes_parts.append(f'Stripped leading fragment from: "{stripped}"')
        stripped = after_strip

    # Clean question with no mid-sentence start — title-case as-is
    if stripped.endswith("?") and not _MID_SENTENCE_STARTS.match(stripped):
        title = _to_title_case(stripped)
        note = ((" ".join(notes_parts) + " ") if notes_parts else "") + "Clean question hook — title-cased."
        return title, note.strip()

    # If still a mid-sentence fragment, try to find fuller context
    if _MID_SENTENCE_STARTS.match(stripped) and transcript_text:
        sentences = re.split(r"[.!?]+", transcript_text)
        raw_lower = raw_hook.lower()
        for sent in sentences:
            if raw_lower[:20].strip() in sent.lower():
                # Found host sentence — use beginning of it
                sent_stripped = sent.strip()
                if sent_stripped and len(sent_stripped) > len(stripped):
                    stripped = _strip_leading_fragment(sent_stripped)
                    notes_parts.append("Reconstructed from host sentence in transcript.")
                    break

    # Rephrase "you are not defined by your past" style if hook ends with
    # contextual phrase starting with lowercase
    display = _to_title_case(stripped.rstrip(".!?"))

    notes = " ".join(notes_parts) if notes_parts else "No changes required."
    return display, notes


def clean_hook_and_title(raw_hook: str, transcript_text: str = "") -> HookCleanupResult:
    """
    Produce editorial display fields from a raw extracted hook_text fragment.

    Parameters
    ----------
    raw_hook : str
        The raw ``hook_text`` extracted by the scorer (may be a mid-sentence
        fragment with lowercase start or leading noise like "here is what I know:").
    transcript_text : str
        The full transcript text of the snippet, used only to reconstruct
        context when the raw hook is a fragment.  Not modified.

    Returns
    -------
    HookCleanupResult
        Contains cleaned_hook_text (polished single hook phrase),
        display_title (title-cased heading), caption_hook_suggestions
        (2–3 short-form caption variants), and hook_cleanup_notes.
        simulation_only is always True, outbound_actions_taken always 0.

    Notes
    -----
    * Original hook_text and transcript_text are never modified.
    * No external API calls.
    * No quotation marks around output fields.
    """
    if not raw_hook or not raw_hook.strip():
        return HookCleanupResult(
            hook_cleanup_notes="Empty raw hook — no cleanup possible.",
            simulation_only=True,
            outbound_actions_taken=0,
        )

    display_title, notes = _infer_display_title(raw_hook, transcript_text)

    # cleaned_hook_text: declarative sentence version (lower bar than title)
    cleaned = display_title
    if not cleaned.rstrip("?!").endswith(cleaned.rstrip("?!")):
        pass  # preserve question mark
    # Ensure ends with punctuation
    if not cleaned[-1] in ".?!":
        cleaned = cleaned + "."

    # Caption hook suggestions: short variations for social captions
    base = display_title.rstrip(".?!")
    suggestions: list[str] = []
    if "?" in display_title:
        suggestions.append(display_title)
        suggestions.append(f"Here's what nobody tells you: {base.lower()}.")
        suggestions.append(f"Ask yourself this: {base.lower()}?")
    else:
        suggestions.append(f"{base}.")
        suggestions.append(f"Remember this: {base.lower()}.")
        suggestions.append(f"This changed everything for me — {base.lower()}.")

    return HookCleanupResult(
        cleaned_hook_text=cleaned,
        display_title=display_title,
        caption_hook_suggestions=suggestions[:3],
        hook_cleanup_notes=notes,
        simulation_only=True,
        outbound_actions_taken=0,
    )
