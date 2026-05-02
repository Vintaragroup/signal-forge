"""
Prompt generator library — Social Creative Engine v4.5.

Generates structured visual prompts for faceless short-form creative content.
Default generation engine target: ComfyUI.  Architecture is compatible with
future engines: Seedance, Higgsfield, Runway, avatar (with permissions), and
manual editing.

Safety guarantees
-----------------
* Default to faceless visuals — negative prompt always blocks identifiable
  faces and likenesses.
* ``use_likeness=True`` requires ``avatar_permissions=True`` or
  ``likeness_permissions=True`` on the client profile; otherwise raises
  ``PermissionError``.
* No voice clone instructions are generated under any circumstances.
* No external API calls are made during prompt generation.
* No ComfyUI, Seedance, Higgsfield, or Runway calls happen from this module.
* All ``PromptGenerationResult`` objects carry ``simulation_only=True`` and
  ``outbound_actions_taken=0``.
* Prompts are created with ``status='draft'`` and must be reviewed before any
  asset generation can occur.
* Source URL, snippet transcript text, and snippet usage status are preserved
  on every result.

Supported prompt types
----------------------
faceless_motivational, cinematic_broll, abstract_motion, business_explainer,
quote_card_motion, podcast_clip_visual, educational_breakdown,
luxury_brand_story, product_service_ad

Supported generation engine targets
------------------------------------
comfyui, seedance, higgsfield, runway, manual

Usage
-----
from prompt_generator import generate_prompt, PROMPT_TYPES, GENERATION_ENGINES

result = generate_prompt(
    prompt_type="faceless_motivational",
    snippet_text="Every estimate got a next-day check-in text from a real person.",
    brief={"goal": "grow contractor pipeline", "platform": "Instagram"},
    engine="comfyui",
    snippet_id="abc123",
    client_id="client456",
)
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

PROMPT_TYPES: frozenset[str] = frozenset(
    {
        "faceless_motivational",
        "cinematic_broll",
        "abstract_motion",
        "business_explainer",
        "quote_card_motion",
        "podcast_clip_visual",
        "educational_breakdown",
        "luxury_brand_story",
        "product_service_ad",
    }
)

GENERATION_ENGINES: frozenset[str] = frozenset(
    {"comfyui", "seedance", "higgsfield", "runway", "manual"}
)

# Types that inherently require likeness or avatar rendering.
# Currently empty — all supported types are faceless.
# Add types here when avatar/likeness variants are built.
_LIKENESS_REQUIRED_TYPES: frozenset[str] = frozenset()

_NEGATIVE_PROMPT_BASE = (
    "realistic human face, identifiable person, likeness, specific individual, "
    "avatar of named person, voice cloning instructions, low quality, blurry, "
    "watermark, text artifacts, nsfw"
)

_ENGINE_NOTES: dict[str, str] = {
    "comfyui": (
        "Target ComfyUI local workflow. No remote API call is made from "
        "SignalForge. Operator must run ComfyUI separately and import result."
    ),
    "seedance": (
        "Seedance engine integration is not yet implemented. "
        "Export this prompt for manual use with Seedance."
    ),
    "higgsfield": (
        "Higgsfield engine integration is not yet implemented. "
        "Export this prompt for manual use with Higgsfield."
    ),
    "runway": (
        "Runway engine integration is not yet implemented. "
        "Export this prompt for manual use with Runway Gen."
    ),
    "manual": (
        "Manual prompt — operator uses this with any external tool of their "
        "choice. No automation is triggered by SignalForge."
    ),
}


# ---------------------------------------------------------------------------
# Value object
# ---------------------------------------------------------------------------


@dataclass
class PromptGenerationResult:
    """
    Structured visual prompt for a single short-form creative segment.

    Fields
    ------
    client_id, snippet_id, brief_id : str
        Traceability IDs preserved from the request.
    prompt_type : str
        One of ``PROMPT_TYPES``.
    generation_engine_target : str
        Target engine from ``GENERATION_ENGINES``.  Default ``'comfyui'``.
    positive_prompt : str
        Main generation prompt text.
    negative_prompt : str
        Negative prompt text; always includes the base face/likeness block.
    visual_style : str
        Short style descriptor (e.g. "cinematic, high contrast").
    camera_direction : str
        Camera or viewport movement instruction.
    lighting : str
        Lighting environment description.
    motion_notes : str
        Motion and animation guidance.
    scene_beats : list[str]
        Ordered list of scene beat descriptions.
    caption_overlay_suggestion : str
        Suggested on-screen text derived from snippet transcript.
    safety_notes : str
        Human-readable safety notes for the operator.
    status : str
        ``'draft'`` on creation.  Progresses through review.
    simulation_only : bool
        Always ``True``.
    outbound_actions_taken : int
        Always ``0``.
    source_url : str
        Original source URL preserved from the snippet.
    snippet_transcript : str
        Transcript text preserved from the snippet.
    snippet_usage_status : str
        Usage/approval status of the originating snippet.
    error : str
        Non-empty if generation failed.
    """

    # Traceability
    client_id: str = ""
    snippet_id: str = ""
    brief_id: str = ""

    # Type + engine
    prompt_type: str = "faceless_motivational"
    generation_engine_target: str = "comfyui"

    # Prompts
    positive_prompt: str = ""
    negative_prompt: str = _NEGATIVE_PROMPT_BASE

    # Visual parameters
    visual_style: str = ""
    camera_direction: str = ""
    lighting: str = ""
    motion_notes: str = ""
    scene_beats: list[str] = field(default_factory=list)

    # Caption
    caption_overlay_suggestion: str = ""

    # Operator-facing safety context
    safety_notes: str = ""

    # Review lifecycle
    status: str = "draft"

    # Safety invariants — never changed by this module
    simulation_only: bool = True
    outbound_actions_taken: int = 0

    # Source preservation
    source_url: str = ""
    snippet_transcript: str = ""
    snippet_usage_status: str = ""

    # Error (non-empty on failure path)
    error: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_str(value: object) -> str:
    return str(value).strip() if value else ""


def _truncate(text: str, max_chars: int) -> str:
    text = text.strip()
    return text[:max_chars].rstrip() if len(text) > max_chars else text


def _build_faceless_motivational(snippet_text: str, brief: dict) -> dict:
    goal = _safe_str(brief.get("goal") or "growth and success")
    return {
        "positive_prompt": (
            f"Cinematic faceless motivational video, abstract energy, "
            f"dynamic motion graphics, bold typography overlay, "
            f"theme: {goal}, "
            f"no faces, no identifiable people, 9:16 vertical format"
        ),
        "visual_style": "cinematic, high contrast, modern",
        "camera_direction": "slow push-in, slight upward tilt",
        "lighting": "dramatic rim lighting, warm tones",
        "motion_notes": "subtle particle effects, smooth text transitions",
        "scene_beats": [
            "Opening: abstract motion background establishes energy",
            "Mid: bold text appears with quote from transcript",
            "Close: brand safe zone fade out",
        ],
        "caption_overlay_suggestion": _truncate(snippet_text, 80),
    }


def _build_cinematic_broll(snippet_text: str, brief: dict) -> dict:
    platform = _safe_str(brief.get("platform") or "social")
    return {
        "positive_prompt": (
            f"Cinematic B-roll footage, professional environment, no faces shown, "
            f"shallow depth of field, natural light, platform: {platform}, "
            f"mood: professional and aspirational, 9:16 vertical"
        ),
        "visual_style": "cinematic, desaturated, film grain",
        "camera_direction": "handheld slight drift, rack focus",
        "lighting": "natural window light, golden hour",
        "motion_notes": "slow motion B-roll cuts at 0.5s intervals",
        "scene_beats": [
            "Hands at keyboard or tools — no face visible",
            "Product or workspace detail shot",
            "Abstract environment transition",
        ],
        "caption_overlay_suggestion": _truncate(snippet_text, 80),
    }


def _build_abstract_motion(snippet_text: str, brief: dict) -> dict:
    tone = _safe_str(brief.get("tone") or "energetic")
    return {
        "positive_prompt": (
            f"Abstract motion design, fluid shapes, flowing particles, "
            f"color palette: bold and modern, tone: {tone}, "
            f"no faces, no people, pure visual motion, 9:16 vertical"
        ),
        "visual_style": "abstract, neon accents, smooth gradients",
        "camera_direction": "virtual camera through abstract space",
        "lighting": "neon glow, backlit particles",
        "motion_notes": "loopable motion background, 6-15 seconds",
        "scene_beats": [
            "Color wash opens with sound beat",
            "Text reveal centered on screen",
            "Particle burst closes segment",
        ],
        "caption_overlay_suggestion": _truncate(snippet_text, 80),
    }


def _build_business_explainer(snippet_text: str, brief: dict) -> dict:
    offer = _safe_str(brief.get("offer") or "solution")
    return {
        "positive_prompt": (
            f"Clean business explainer animation, flat design icons, "
            f"infographic style, offer: {offer}, no faces, professional, "
            f"white or light background, 9:16 vertical"
        ),
        "visual_style": "flat design, minimal, professional",
        "camera_direction": "static frame with animated elements sliding in",
        "lighting": "even, bright, studio quality",
        "motion_notes": "icon animations, step-by-step reveal",
        "scene_beats": [
            "Problem stated with icon",
            "Solution steps revealed one by one",
            "Call to action with offer highlight",
        ],
        "caption_overlay_suggestion": _truncate(snippet_text, 80),
    }


def _build_quote_card_motion(snippet_text: str, brief: dict) -> dict:
    quote_preview = _truncate(snippet_text, 60) or "Your quote here"
    return {
        "positive_prompt": (
            f"Animated quote card, bold typography, subtle background motion, "
            f"no faces, clean layout, "
            f'quote text: "{quote_preview}", '
            f"9:16 vertical format"
        ),
        "visual_style": "typographic, minimal, bold",
        "camera_direction": "static, slight parallax on background",
        "lighting": "soft gradient background",
        "motion_notes": "text appears word by word, background subtle pulse",
        "scene_beats": [
            "Background establishes brand color",
            "Quote text animates in word by word",
            "Logo or handle appears in safe zone",
        ],
        "caption_overlay_suggestion": _truncate(snippet_text, 120),
    }


def _build_podcast_clip_visual(snippet_text: str, brief: dict) -> dict:
    return {
        "positive_prompt": (
            "Podcast clip visual, waveform animation, microphone silhouette, "
            "no identifiable faces, branded color background, "
            "audio visualizer style, 9:16 vertical"
        ),
        "visual_style": "dark background, waveform accent, branded",
        "camera_direction": "static split screen: waveform + text",
        "lighting": "dark studio atmosphere, accent glow on waveform",
        "motion_notes": "waveform pulses with audio beat markers",
        "scene_beats": [
            "Show waveform animation with episode context",
            "Transcript quote appears as subtitle",
            "Outro with channel branding",
        ],
        "caption_overlay_suggestion": _truncate(snippet_text, 100),
    }


def _build_educational_breakdown(snippet_text: str, brief: dict) -> dict:
    audience = _safe_str(brief.get("audience") or "general audience")
    return {
        "positive_prompt": (
            f"Educational breakdown visual, numbered steps, clean diagrams, "
            f"for audience: {audience}, no faces, clear typography, "
            f"infographic aesthetic, 9:16 vertical"
        ),
        "visual_style": "clean, educational, structured",
        "camera_direction": "pan down through numbered list",
        "lighting": "bright, even, academic",
        "motion_notes": "each step slides in sequentially",
        "scene_beats": [
            "Title card states topic",
            "Steps 1-3 reveal with icons",
            "Summary screen with key takeaway",
        ],
        "caption_overlay_suggestion": _truncate(snippet_text, 80),
    }


def _build_luxury_brand_story(snippet_text: str, brief: dict) -> dict:
    brand = _safe_str(brief.get("offer") or "the brand")
    return {
        "positive_prompt": (
            f"Luxury brand story visual, high-end product aesthetic, "
            f"no faces, aspirational lifestyle detail shots, "
            f"brand context: {brand}, cinematic color grading, 9:16 vertical"
        ),
        "visual_style": "luxurious, dark tones, gold accents",
        "camera_direction": "slow macro push-in on product detail",
        "lighting": "studio lighting, specular highlights on surfaces",
        "motion_notes": "smooth slow motion reveal at 50% speed",
        "scene_beats": [
            "Brand texture or material detail opens",
            "Product in aspirational environment",
            "Wordmark reveal with tagline",
        ],
        "caption_overlay_suggestion": _truncate(snippet_text, 80),
    }


def _build_product_service_ad(snippet_text: str, brief: dict) -> dict:
    offer = _safe_str(brief.get("offer") or "offer")
    cta = _safe_str(brief.get("goal") or "learn more")
    return {
        "positive_prompt": (
            f"Product/service advertisement visual, clean and direct, "
            f"offer: {offer}, call to action: {cta}, "
            f"no faces, modern design, 9:16 vertical"
        ),
        "visual_style": "bold, direct, commercial",
        "camera_direction": "product hero shot, static or slow orbit",
        "lighting": "bright commercial lighting, clean shadows",
        "motion_notes": "product enters from edge, text counter-animates",
        "scene_beats": [
            "Problem hook in first 2 seconds",
            "Product/service presented as solution",
            "CTA with offer details",
        ],
        "caption_overlay_suggestion": _truncate(snippet_text, 80),
    }


_BUILDERS: dict[str, object] = {
    "faceless_motivational": _build_faceless_motivational,
    "cinematic_broll": _build_cinematic_broll,
    "abstract_motion": _build_abstract_motion,
    "business_explainer": _build_business_explainer,
    "quote_card_motion": _build_quote_card_motion,
    "podcast_clip_visual": _build_podcast_clip_visual,
    "educational_breakdown": _build_educational_breakdown,
    "luxury_brand_story": _build_luxury_brand_story,
    "product_service_ad": _build_product_service_ad,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_prompt(
    prompt_type: str,
    snippet_text: str = "",
    brief: dict | None = None,
    engine: str = "comfyui",
    client_id: str = "",
    snippet_id: str = "",
    brief_id: str = "",
    source_url: str = "",
    snippet_usage_status: str = "",
    avatar_permissions: bool = False,
    likeness_permissions: bool = False,
    use_likeness: bool = False,
) -> PromptGenerationResult:
    """
    Generate a structured visual prompt for a short-form creative segment.

    Parameters
    ----------
    prompt_type : str
        Must be one of ``PROMPT_TYPES``.
    snippet_text : str
        Transcript text from the source snippet.
    brief : dict | None
        Optional content brief dict providing goal, platform, offer, etc.
    engine : str
        Target engine from ``GENERATION_ENGINES``.  Defaults to ``'comfyui'``.
    client_id : str
        Client profile ID for traceability.
    snippet_id : str
        Source snippet ID for traceability.
    brief_id : str
        Brief ID for traceability.
    source_url : str
        Original source URL preserved on the result.
    snippet_usage_status : str
        Approval status of the originating snippet preserved on the result.
    avatar_permissions : bool
        Whether the client profile has avatar generation permissions.
    likeness_permissions : bool
        Whether the client profile has likeness usage permissions.
    use_likeness : bool
        If ``True``, requires ``avatar_permissions=True`` or
        ``likeness_permissions=True``.  Raises ``PermissionError`` otherwise.

    Returns
    -------
    PromptGenerationResult

    Raises
    ------
    ValueError
        If ``prompt_type`` or ``engine`` is not in the allowed sets.
    PermissionError
        If ``use_likeness=True`` but neither permissions flag is set.
    """
    if prompt_type not in PROMPT_TYPES:
        raise ValueError(
            f"Unknown prompt_type '{prompt_type}'. "
            f"Valid types: {sorted(PROMPT_TYPES)}"
        )

    if engine not in GENERATION_ENGINES:
        raise ValueError(
            f"Unknown engine '{engine}'. "
            f"Valid engines: {sorted(GENERATION_ENGINES)}"
        )

    # Likeness / avatar gate — never allow unless permissions are explicit
    if use_likeness and not (avatar_permissions or likeness_permissions):
        raise PermissionError(
            "Likeness and avatar prompts require explicit client permission. "
            "Set avatar_permissions=True or likeness_permissions=True on the "
            "client profile before enabling use_likeness."
        )

    # Future-proofing: prompt types that inherently need likeness
    if prompt_type in _LIKENESS_REQUIRED_TYPES and not (
        avatar_permissions or likeness_permissions
    ):
        raise PermissionError(
            f"Prompt type '{prompt_type}' requires avatar or likeness "
            "permissions. Set the appropriate flag on the client profile."
        )

    brief = brief or {}
    snippet_text = (snippet_text or "").strip()

    builder = _BUILDERS[prompt_type]
    built = builder(snippet_text, brief)  # type: ignore[operator]

    engine_note = _ENGINE_NOTES.get(engine, "")
    safety_notes = (
        f"Default faceless visual — {engine_note} "
        f"No faces, likenesses, or voice cloning are requested. "
        f"Prompt requires operator review before any asset generation."
    )

    return PromptGenerationResult(
        client_id=client_id,
        snippet_id=snippet_id,
        brief_id=brief_id,
        prompt_type=prompt_type,
        generation_engine_target=engine,
        positive_prompt=built.get("positive_prompt", ""),
        negative_prompt=_NEGATIVE_PROMPT_BASE,
        visual_style=built.get("visual_style", ""),
        camera_direction=built.get("camera_direction", ""),
        lighting=built.get("lighting", ""),
        motion_notes=built.get("motion_notes", ""),
        scene_beats=list(built.get("scene_beats", [])),
        caption_overlay_suggestion=built.get("caption_overlay_suggestion", ""),
        safety_notes=safety_notes,
        status="draft",
        simulation_only=True,
        outbound_actions_taken=0,
        source_url=source_url,
        snippet_transcript=snippet_text,
        snippet_usage_status=snippet_usage_status,
        error="",
    )
