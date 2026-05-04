const DEMO_ENABLED_KEY = "signalforge.demo.enabled";
const DEMO_STATE_KEY = "signalforge.demo.state";

function nowIso() {
  return new Date().toISOString();
}

function daysAgo(days) {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString();
}

const seedState = {
  currentStep: 1,
  outreachRun: false,
  responseSimulated: false,
  dealShown: false,
  contacts: [
    {
      _id: "demo-contact-1",
      contact_key: "demo-maya-rivera",
      name: "Maya Rivera",
      company: "Demo Apex Roofing",
      role: "Owner",
      email: "maya.demo@example.invalid",
      module: "contractor_growth",
      source: "demo_seed",
      contact_status: "demo_contact",
      contact_score: 94,
      segment: "high_priority",
      priority_reason: "Demo record: high-intent local contractor with urgent growth goal.",
      notes: "Demo Mode synthetic contact. No real message will be sent.",
      imported_at: daysAgo(4),
      updated_at: daysAgo(1),
      is_demo: true,
    },
    {
      _id: "demo-contact-2",
      contact_key: "demo-eli-hart",
      name: "Eli Hart",
      company: "Demo Northline HVAC",
      role: "Operations Lead",
      email: "eli.demo@example.invalid",
      module: "contractor_growth",
      source: "demo_seed",
      contact_status: "demo_contact",
      contact_score: 82,
      segment: "warm_fit",
      priority_reason: "Demo record: strong fit with seasonal demand signals.",
      notes: "Demo Mode synthetic contact. No real message will be sent.",
      imported_at: daysAgo(3),
      updated_at: daysAgo(1),
      is_demo: true,
    },
  ],
  leads: [
    {
      _id: "demo-lead-1",
      company_slug: "demo-apex-roofing",
      company_name: "Demo Apex Roofing",
      business_type: "roofing contractor",
      location: "Austin, TX",
      module: "contractor_growth",
      source: "demo_seed",
      review_status: "demo_qualified",
      outreach_status: "draft_ready",
      lead_score: 91,
      score: 91,
      marketing_gap: "Demo signal: strong reviews, weak estimate follow-up system.",
      recommended_action: "Run a human-reviewed outreach draft around faster estimate follow-up.",
      updated_at: daysAgo(1),
      is_demo: true,
    },
    {
      _id: "demo-lead-2",
      company_slug: "demo-northline-hvac",
      company_name: "Demo Northline HVAC",
      business_type: "HVAC contractor",
      location: "Denver, CO",
      module: "contractor_growth",
      source: "demo_seed",
      review_status: "demo_qualified",
      outreach_status: "not_started",
      lead_score: 78,
      score: 78,
      marketing_gap: "Demo signal: seasonal demand but no visible follow-up campaign.",
      recommended_action: "Prepare a local growth audit offer for human review.",
      updated_at: daysAgo(2),
      is_demo: true,
    },
  ],
  messages: [
    {
      _id: "demo-draft-1",
      draft_key: "demo-apex-roofing-outreach",
      recipient_name: "Maya Rivera",
      company: "Demo Apex Roofing",
      module: "contractor_growth",
      source: "demo_seed",
      target_type: "contact",
      target_id: "demo-contact-1",
      target_key: "demo-maya-rivera",
      subject_line: "Demo: tighten estimate follow-up this month",
      message_body: "Hi Maya, I noticed Demo Apex Roofing has strong local demand but a few signs that estimate follow-up could be tightened. SignalForge would flag this as a good fit for a short, human-reviewed outreach sequence focused on booked estimates and missed follow-ups. No real message is sent from Demo Mode.",
      review_status: "needs_review",
      send_status: "not_sent",
      response_status: "",
      created_at: daysAgo(1),
      updated_at: daysAgo(1),
      is_demo: true,
    },
    {
      _id: "demo-draft-2",
      draft_key: "demo-northline-hvac-outreach",
      recipient_name: "Eli Hart",
      company: "Demo Northline HVAC",
      module: "contractor_growth",
      source: "demo_seed",
      target_type: "contact",
      target_id: "demo-contact-2",
      target_key: "demo-eli-hart",
      subject_line: "Demo: seasonal follow-up workflow",
      message_body: "Hi Eli, this demo draft shows how SignalForge can turn local contractor signals into review-only outreach. A human operator would review, edit, and send outside SignalForge if appropriate.",
      review_status: "approved",
      send_status: "manual_demo_send_logged",
      response_status: "requested_info",
      response_events: [
        {
          outcome: "requested_info",
          note: "Preloaded demo response: asked for a short seasonal follow-up example.",
          logged_at: daysAgo(1),
          is_demo: true,
        },
      ],
      created_at: daysAgo(1),
      updated_at: daysAgo(1),
      is_demo: true,
    },
  ],
  content_briefs: [
    {
      _id: "demo-brief-1",
      workspace_slug: "demo",
      module: "contractor_growth",
      campaign_name: "Demo: Local Contractor Brand Awareness",
      audience: "Small roofing and HVAC contractors in TX",
      platform: "Instagram",
      goal: "Generate 5 booked discovery calls",
      offer: "Free growth audit session",
      tone: "friendly, confident, educational",
      notes: "Focus on summer season demand surge.",
      status: "approved",
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(4),
      updated_at: daysAgo(1),
    },
    {
      _id: "demo-brief-2",
      workspace_slug: "demo",
      module: "contractor_growth",
      campaign_name: "Demo: Referral Network Push",
      audience: "Contractors with 2-5 employees",
      platform: "LinkedIn",
      goal: "Build referral network with 10 new partners",
      offer: "Referral bonus for qualified introductions",
      tone: "professional, direct",
      notes: "Target decision makers only.",
      status: "draft",
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(2),
      updated_at: daysAgo(2),
    },
  ],
  content_drafts: [
    {
      _id: "demo-draft-content-1",
      workspace_slug: "demo",
      module: "contractor_growth",
      brief_id: "demo-brief-1",
      platform: "Instagram",
      content_type: "post",
      title: "Summer Growth Tips for Contractors",
      body: "[Demo] Summer is peak season — are you ready? Our clients see 3x more inquiries from May to August. Here are 3 quick wins to capture that demand…\n\n1. Update your Google profile photos\n2. Ask every happy customer for a Google review\n3. Post before/after job photos weekly\n\nNeed help scaling fast? Let's talk.",
      hashtags: ["contractor", "smallbusiness", "growthstrategy", "roofing", "summerbusiness"],
      call_to_action: "DM us \"AUDIT\" for a free growth session.",
      status: "needs_review",
      generated_by_agent: "content_agent",
      agent_run_id: "demo-agent-run-1",
      selected_model: "gpt-4o-mini",
      routing_reason: "Draft task routed to draft model",
      complexity: "low",
      outbound_actions_taken: 0,
      simulation_only: true,
      review_events: [],
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(1),
      updated_at: daysAgo(1),
    },
    {
      _id: "demo-draft-content-2",
      workspace_slug: "demo",
      module: "contractor_growth",
      brief_id: "demo-brief-1",
      platform: "Instagram",
      content_type: "caption",
      title: "Before/After Showcase Caption",
      body: "[Demo] From worn shingles to spotless curb appeal in just one day. Our client in Austin called it the best investment of the summer. Ready to show off your best work?",
      hashtags: ["beforeandafter", "roofing", "austintx", "contractorlife"],
      call_to_action: "Tag a contractor who does great work!",
      status: "approved",
      generated_by_agent: "content_agent",
      agent_run_id: "demo-agent-run-1",
      selected_model: "gpt-4o-mini",
      routing_reason: "Draft task routed to draft model",
      complexity: "low",
      outbound_actions_taken: 0,
      simulation_only: true,
      review_events: [
        { decision: "approve", note: "Demo approval", reviewed_at: daysAgo(0) },
      ],
      review_note: "Demo approval",
      reviewed_at: daysAgo(0),
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(2),
      updated_at: daysAgo(0),
    },
  ],
  deals: [
    {
      _id: "demo-deal-1",
      company: "Demo Apex Roofing",
      person: "Maya Rivera",
      module: "contractor_growth",
      source: "demo_seed",
      contact_id: "demo-contact-1",
      message_draft_id: "demo-draft-1",
      outcome: "proposal_sent",
      deal_status: "proposal_sent",
      deal_value: 4500,
      note: "Demo deal outcome waiting for simulated response.",
      created_at: daysAgo(1),
      updated_at: daysAgo(1),
      is_demo: true,
    },
  ],
  // -------------------------------------------------------------------------
  // Social Creative Engine v2 — seed data
  // -------------------------------------------------------------------------
  client_profiles: [
    {
      _id: "demo-client-1",
      workspace_slug: "demo",
      client_name: "Demo Apex Roofing",
      brand_name: "Apex Roofing",
      approved_source_channels: ["demo-channel-1"],
      allowed_content_types: ["post", "caption", "reel_script"],
      disallowed_topics: ["pricing disputes", "competitor bashing"],
      likeness_permissions: false,
      voice_permissions: false,
      avatar_permissions: false,
      compliance_notes: "Demo client. All records are synthetic. No real person represented.",
      status: "active",
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(5),
      updated_at: daysAgo(1),
    },
  ],
  source_channels: [
    {
      _id: "demo-channel-1",
      workspace_slug: "demo",
      client_id: "demo-client-1",
      platform: "youtube",
      channel_name: "Apex Roofing Tips",
      channel_url: "https://youtube.com/@apexroofingtips.demo.invalid",
      approved_for_ingestion: true,
      approved_for_reuse: true,
      notes: "Demo channel. Used for synthetic content ingestion.",
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(4),
      updated_at: daysAgo(1),
    },
    {
      _id: "demo-channel-2",
      workspace_slug: "demo",
      client_id: "demo-client-1",
      platform: "instagram",
      channel_name: "Apex Roofing IG",
      channel_url: "https://instagram.com/apexroofingtips.demo.invalid",
      approved_for_ingestion: false,
      approved_for_reuse: false,
      notes: "Demo channel — not yet approved for ingestion.",
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(3),
      updated_at: daysAgo(2),
    },
  ],
  source_content: [
    {
      _id: "demo-source-content-1",
      workspace_slug: "demo",
      client_id: "demo-client-1",
      source_channel_id: "demo-channel-1",
      platform: "youtube",
      source_url: "https://youtube.com/watch?v=demoabc123.invalid",
      title: "How We Closed 10 Roofing Jobs in One Week",
      creator: "Apex Roofing",
      published_at: daysAgo(14),
      duration_seconds: 482,
      performance_metadata: { views: 8200, likes: 341, comments: 47 },
      discovery_score: 0.88,
      discovery_reason: "High engagement, strong local authority signal.",
      status: "approved",
      review_events: [],
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(3),
      updated_at: daysAgo(1),
    },
    {
      _id: "demo-source-content-2",
      workspace_slug: "demo",
      client_id: "demo-client-1",
      source_channel_id: "demo-channel-1",
      platform: "youtube",
      source_url: "https://youtube.com/watch?v=demodef456.invalid",
      title: "The Biggest Mistake New Roofers Make",
      creator: "Apex Roofing",
      published_at: daysAgo(21),
      duration_seconds: 310,
      performance_metadata: { views: 3900, likes: 182, comments: 23 },
      discovery_score: 0.71,
      discovery_reason: "Good hook, moderate engagement.",
      status: "approved",
      review_events: [{ decision: "approve", note: "Demo approved.", reviewed_at: daysAgo(1) }],
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(2),
      updated_at: daysAgo(2),
    },
  ],
  content_transcripts: [
    {
      _id: "demo-transcript-1",
      workspace_slug: "demo",
      source_content_id: "demo-source-content-1",
      transcript_text: "Hey everyone, I want to walk you through exactly how we closed 10 roofing jobs in one week — no tricks, no gimmicks. First thing we did was clean up our follow-up game. Every estimate got a next-day check-in text from a real person. Then we started asking every happy customer for a Google review right at job completion. By Thursday we had four new five-star reviews and our phone started ringing more. By the end of the week, ten jobs booked.",
      status: "complete",
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(2),
      updated_at: daysAgo(2),
    },
  ],
  content_snippets: [
    {
      _id: "demo-snippet-1",
      workspace_slug: "demo",
      source_content_id: "demo-source-content-1",
      transcript_id: "demo-transcript-1",
      speaker: "Host",
      start_time: 12.4,
      end_time: 28.1,
      transcript_text: "Every estimate got a next-day check-in text from a real person.",
      score: 0.94,
      score_reason: "Strong authority hook, actionable, fits short-form format.",
      theme: "follow_up_system",
      hook_angle: "Quick win operators can copy immediately",
      platform_fit: ["instagram", "tiktok", "linkedin"],
      status: "approved",
      review_events: [{ decision: "approve", note: "Demo approved", reviewed_at: daysAgo(1) }],
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(2),
      updated_at: daysAgo(1),
    },
    {
      _id: "demo-snippet-2",
      workspace_slug: "demo",
      source_content_id: "demo-source-content-1",
      transcript_id: "demo-transcript-1",
      speaker: "Host",
      start_time: 44.7,
      end_time: 57.3,
      transcript_text: "By the end of the week, ten jobs booked.",
      score: 0.81,
      score_reason: "Punchy close, strong social proof signal.",
      theme: "results",
      hook_angle: "Social proof with specific numbers",
      platform_fit: ["instagram", "youtube_shorts"],
      status: "needs_review",
      review_events: [],
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(2),
      updated_at: daysAgo(2),
    },
    {
      _id: "demo-snippet-3",
      workspace_slug: "demo",
      source_content_id: "demo-source-content-1",
      transcript_id: "demo-transcript-1",
      speaker: "Host",
      start_time: 60.0,
      end_time: 71.5,
      transcript_text: "We started asking every happy customer for a Google review right at job completion.",
      score: 0.76,
      score_reason: "Actionable tip, trust builder.",
      theme: "reputation",
      hook_angle: "Simple habit that compounds over time",
      platform_fit: ["linkedin", "facebook"],
      status: "needs_review",
      review_events: [],
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(2),
      updated_at: daysAgo(2),
    },
    {
      _id: "demo-snippet-4",
      workspace_slug: "demo",
      source_content_id: "demo-source-content-2",
      transcript_id: "demo-transcript-1",
      speaker: "Host",
      start_time: 5.0,
      end_time: 18.2,
      transcript_text: "The biggest mistake new roofers make is trying to compete on price instead of speed and follow-through.",
      score: 0.88,
      score_reason: "Contrarian hook, high shareability, strong positioning angle.",
      theme: "positioning",
      hook_angle: "Contrarian insight that reframes the competition problem",
      platform_fit: ["instagram", "tiktok", "linkedin"],
      status: "approved",
      review_events: [{ decision: "approve", note: "Demo approved — strong contrarian hook.", reviewed_at: daysAgo(1) }],
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(2),
      updated_at: daysAgo(1),
    },
  ],
  creative_assets: [
    {
      _id: "demo-asset-1",
      workspace_slug: "demo",
      client_id: "demo-client-1",
      source_content_id: "demo-source-content-1",
      snippet_id: "demo-snippet-1",
      asset_type: "image",
      title: "Follow-Up Quote Card",
      description: "Text overlay quote card from demo snippet 1.",
      file_path: "",
      prompt_used: "[Demo] Minimal roofing brand quote card on dark background.",
      tool_run_id: "",
      status: "needs_review",
      review_events: [],
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(1),
      updated_at: daysAgo(1),
    },
    {
      _id: "demo-asset-2",
      workspace_slug: "demo",
      client_id: "demo-client-1",
      source_content_id: "demo-source-content-1",
      snippet_id: "demo-snippet-2",
      asset_type: "reel",
      title: "10 Jobs Booked Reel",
      description: "Short-form vertical video from demo source content.",
      file_path: "",
      prompt_used: "[Demo] Vertical reel with bold caption overlay.",
      tool_run_id: "",
      status: "needs_review",
      review_events: [],
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(1),
      updated_at: daysAgo(1),
    },
  ],
  // v3 seed data
  audio_extraction_runs: [
    {
      _id: "demo-audio-run-1",
      workspace_slug: "demo",
      source_content_id: "demo-source-content-1",
      source_url: "https://youtube.com/watch?v=demoabc123.invalid",
      notes: "Demo audio extraction run.",
      extractor: "stub",
      status: "skipped",
      skip_reason: "ffmpeg_disabled",
      output_path: "",
      error: "",
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(2),
      updated_at: daysAgo(2),
    },
  ],
  transcript_runs: [
    {
      _id: "demo-transcript-run-1",
      workspace_slug: "demo",
      source_content_id: "demo-source-content-1",
      audio_extraction_run_id: "demo-audio-run-1",
      provider: "stub",
      language: "en",
      segment_count: 4,
      status: "complete",
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(2),
      updated_at: daysAgo(2),
    },
  ],
  transcript_segments: [
    {
      _id: "demo-seg-1",
      workspace_slug: "demo",
      source_content_id: "demo-source-content-1",
      transcript_run_id: "demo-transcript-run-1",
      index: 0,
      start_ms: 0,
      end_ms: 4640,
      text: "Hey everyone, I want to walk you through exactly how we closed 10 roofing jobs in one week.",
      speaker: "speaker_1",
      confidence: 0.92,
      provider: "stub",
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(2),
    },
    {
      _id: "demo-seg-2",
      workspace_slug: "demo",
      source_content_id: "demo-source-content-1",
      transcript_run_id: "demo-transcript-run-1",
      index: 1,
      start_ms: 4840,
      end_ms: 9680,
      text: "First thing we did was clean up our follow-up game. Every estimate got a next-day check-in text from a real person.",
      speaker: "speaker_1",
      confidence: 0.92,
      provider: "stub",
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(2),
    },
    {
      _id: "demo-seg-3",
      workspace_slug: "demo",
      source_content_id: "demo-source-content-1",
      transcript_run_id: "demo-transcript-run-1",
      index: 2,
      start_ms: 9880,
      end_ms: 14720,
      text: "Then we started asking every happy customer for a Google review right at job completion.",
      speaker: "speaker_1",
      confidence: 0.92,
      provider: "stub",
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(2),
    },
    {
      _id: "demo-seg-4",
      workspace_slug: "demo",
      source_content_id: "demo-source-content-1",
      transcript_run_id: "demo-transcript-run-1",
      index: 3,
      start_ms: 14920,
      end_ms: 18360,
      text: "By the end of the week, ten jobs booked.",
      speaker: "speaker_1",
      confidence: 0.92,
      provider: "stub",
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(2),
    },
  ],

  // Social Creative Engine v4
  media_intake_records: [
    {
      _id: "demo-media-intake-1",
      workspace_slug: "demo",
      source_content_id: "demo-source-content-1",
      intake_method: "url_metadata_only",
      media_path: "",
      source_url: "https://youtube.com/watch?v=demoabc123.invalid",
      extension: "",
      status: "registered",
      skip_reason: "url_download_not_enabled",
      error: "",
      approved_for_download: false,
      notes: "Demo media intake record — URL metadata only.",
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(2),
      updated_at: daysAgo(2),
    },
  ],
  prompt_generations: [
    {
      _id: "demo-prompt-gen-1",
      workspace_slug: "demo",
      client_id: "demo-company-1",
      snippet_id: "demo-snippet-1",
      brief_id: "",
      prompt_type: "faceless_motivational",
      generation_engine_target: "comfyui",
      positive_prompt:
        "Cinematic faceless motivational video, abstract energy, dynamic motion graphics, bold typography overlay, theme: grow contractor pipeline, no faces, no identifiable people, 9:16 vertical format",
      negative_prompt:
        "realistic human face, identifiable person, likeness, specific individual, avatar of named person, voice cloning instructions, low quality, blurry, watermark, text artifacts, nsfw",
      visual_style: "cinematic, high contrast, modern",
      camera_direction: "slow push-in, slight upward tilt",
      lighting: "dramatic rim lighting, warm tones",
      motion_notes: "subtle particle effects, smooth text transitions",
      scene_beats: [
        "Opening: abstract motion background establishes energy",
        "Mid: bold text appears with quote from transcript",
        "Close: brand safe zone fade out",
      ],
      caption_overlay_suggestion: "Every estimate got a next-day check-in text.",
      safety_notes:
        "Default faceless visual — no faces, likenesses, or voice cloning requested. Requires operator review.",
      status: "approved",
      review_events: [
        { decision: "approve", note: "Looks great for demo.", reviewed_at: daysAgo(1) },
      ],
      notes: "",
      use_likeness: false,
      simulation_only: true,
      outbound_actions_taken: 0,
      source_url: "https://youtube.com/watch?v=demoabc123.invalid",
      snippet_transcript: "Every estimate got a next-day check-in text from a real person.",
      snippet_usage_status: "approved",
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(2),
      updated_at: daysAgo(1),
    },
    {
      _id: "demo-prompt-gen-2",
      workspace_slug: "demo",
      client_id: "demo-company-1",
      snippet_id: "demo-snippet-1",
      brief_id: "",
      prompt_type: "podcast_clip_visual",
      generation_engine_target: "manual",
      positive_prompt:
        "Podcast clip visual, waveform animation, microphone silhouette, no identifiable faces, branded color background, audio visualizer style, 9:16 vertical",
      negative_prompt:
        "realistic human face, identifiable person, likeness, specific individual, avatar of named person, voice cloning instructions, low quality, blurry, watermark, text artifacts, nsfw",
      visual_style: "dark background, waveform accent, branded",
      camera_direction: "static split screen: waveform + text",
      lighting: "dark studio atmosphere, accent glow on waveform",
      motion_notes: "waveform pulses with audio beat markers",
      scene_beats: [
        "Show waveform animation with episode context",
        "Transcript quote appears as subtitle",
        "Outro with channel branding",
      ],
      caption_overlay_suggestion: "Every estimate got a next-day check-in text from a real p",
      safety_notes:
        "Default faceless visual — no faces, likenesses, or voice cloning requested. Requires operator review.",
      status: "draft",
      review_events: [],
      notes: "Needs operator review before asset generation.",
      use_likeness: false,
      simulation_only: true,
      outbound_actions_taken: 0,
      source_url: "https://youtube.com/watch?v=demoabc123.invalid",
      snippet_transcript: "Every estimate got a next-day check-in text from a real person.",
      snippet_usage_status: "approved",
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(1),
      updated_at: daysAgo(1),
    },
    {
      _id: "demo-prompt-gen-3",
      workspace_slug: "demo",
      client_id: "demo-client-1",
      snippet_id: "demo-snippet-4",
      brief_id: "",
      prompt_type: "business_explainer",
      generation_engine_target: "comfyui",
      positive_prompt:
        "Business explainer animation, clean minimal style, text on screen, no faces, professional blue palette, contrarian framing with bold title card, 9:16 vertical",
      negative_prompt:
        "realistic human face, identifiable person, likeness, specific individual, nsfw, low quality, blurry, watermark",
      visual_style: "minimal, corporate, bold typography",
      camera_direction: "static frame with animated text elements",
      lighting: "bright clean studio, flat design",
      motion_notes: "text slides in on beat, minimal transitions",
      scene_beats: [
        "Problem statement: roofers competing on price",
        "Reframe: speed and follow-through wins",
        "CTA: discover your competitive edge",
      ],
      caption_overlay_suggestion: "Stop competing on price. Win on speed.",
      safety_notes: "Faceless business explainer — no likeness or voice cloning. Operator review required.",
      status: "approved",
      review_events: [
        { decision: "approve", note: "Demo approved — contrarian hook approved.", reviewed_at: daysAgo(0) },
      ],
      notes: "",
      use_likeness: false,
      simulation_only: true,
      outbound_actions_taken: 0,
      source_url: "https://youtube.com/watch?v=demodef456.invalid",
      snippet_transcript: "The biggest mistake new roofers make is trying to compete on price instead of speed and follow-through.",
      snippet_usage_status: "approved",
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(1),
      updated_at: daysAgo(0),
    },
  ],
  asset_renders: [
    {
      _id: "demo-render-1",
      workspace_slug: "demo",
      client_id: "demo-company-1",
      snippet_id: "demo-snippet-1",
      prompt_generation_id: "demo-prompt-gen-1",
      asset_type: "video",
      generation_engine: "comfyui",
      source_audio_path: "",
      add_captions: true,
      notes: "",
      status: "approved",
      comfyui_enabled: false,
      ffmpeg_enabled: false,
      comfyui_result: { skipped: true, skip_reason: "comfyui_disabled", simulation_only: true, outbound_actions_taken: 0 },
      assembly_result: { mock: true, skip_reason: "ffmpeg_disabled", simulation_only: true, outbound_actions_taken: 0 },
      file_path: "/tmp/signalforge_renders/mock_demo-render-1.mp4",
      preview_url: "https://placehold.co/540x960/1e293b/ffffff?text=Demo+Render+1",
      duration_seconds: 30.0,
      resolution: "1080x1920",
      review_events: [
        { decision: "approve", note: "Looks great for demo.", reviewed_at: daysAgo(0) },
      ],
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(1),
      updated_at: daysAgo(0),
    },
    {
      _id: "demo-render-2",
      workspace_slug: "demo",
      client_id: "demo-company-1",
      snippet_id: "demo-snippet-1",
      prompt_generation_id: "demo-prompt-gen-1",
      asset_type: "video",
      generation_engine: "comfyui",
      source_audio_path: "",
      add_captions: false,
      notes: "Second demo render awaiting review.",
      status: "needs_review",
      comfyui_enabled: false,
      ffmpeg_enabled: false,
      comfyui_result: { skipped: true, skip_reason: "comfyui_disabled", simulation_only: true, outbound_actions_taken: 0 },
      assembly_result: { mock: true, skip_reason: "ffmpeg_disabled", simulation_only: true, outbound_actions_taken: 0 },
      file_path: "/tmp/signalforge_renders/mock_demo-render-2.mp4",
      preview_url: "https://placehold.co/540x960/1e293b/ffffff?text=Demo+Render+2",
      duration_seconds: 28.5,
      resolution: "1080x1920",
      review_events: [],
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(0),
      updated_at: daysAgo(0),
    },
  ],

  // -------------------------------------------------------------------------
  // v10 POC Demo — extra snippets (total 4), extra prompt generations (total 3)
  // -------------------------------------------------------------------------
  // (Snippet 4 — added to content_snippets seed above via patch below)

  // -------------------------------------------------------------------------
  // v10 POC Demo — Manual Publish Log
  // -------------------------------------------------------------------------
  manual_publish_logs: [
    {
      _id: "demo-publog-1",
      workspace_slug: "demo",
      client_id: "demo-client-1",
      render_id: "demo-render-1",
      platform: "instagram",
      post_type: "reel",
      caption: "[Demo] Every estimate got a next-day check-in text. Here's how we booked 10 jobs in one week. No real post was published.",
      published_at: daysAgo(1),
      notes: "Demo publish log. SignalForge did not publish or schedule anything.",
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(1),
      updated_at: daysAgo(1),
    },
  ],

  // -------------------------------------------------------------------------
  // v10 POC Demo — Asset Performance Records (2)
  // -------------------------------------------------------------------------
  asset_performance_records: [
    {
      _id: "demo-perf-1",
      workspace_slug: "demo",
      client_id: "demo-client-1",
      render_id: "demo-render-1",
      snippet_id: "demo-snippet-1",
      publish_log_id: "demo-publog-1",
      platform: "instagram",
      views: 4800,
      likes: 312,
      comments: 48,
      shares: 91,
      saves: 127,
      reach: 4200,
      impressions: 5600,
      watch_time_seconds: 22,
      performance_score: 8.4,
      score_reason: "High saves + share ratio. Strong hook retention.",
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(1),
      updated_at: daysAgo(1),
    },
    {
      _id: "demo-perf-2",
      workspace_slug: "demo",
      client_id: "demo-client-1",
      render_id: "demo-render-2",
      snippet_id: "demo-snippet-2",
      publish_log_id: "demo-publog-1",
      platform: "instagram",
      views: 2100,
      likes: 145,
      comments: 19,
      shares: 33,
      saves: 58,
      reach: 1900,
      impressions: 2400,
      watch_time_seconds: 18,
      performance_score: 6.2,
      score_reason: "Solid mid-tier performance. Good saves, moderate reach.",
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(1),
      updated_at: daysAgo(1),
    },
  ],

  // -------------------------------------------------------------------------
  // v10 POC Demo — Creative Performance Summary (1)
  // -------------------------------------------------------------------------
  creative_performance_summaries: [
    {
      _id: "demo-perf-summary-1",
      workspace_slug: "demo",
      client_id: "demo-client-1",
      total_records: 2,
      avg_performance_score: 7.3,
      top_platform: "instagram",
      top_snippet_id: "demo-snippet-1",
      top_render_id: "demo-render-1",
      recommendations: [
        "The follow-up system hook drives 2× saves vs. results hooks. Prioritize for next batch.",
        "Reel format outperforms static image in all metrics. Allocate 80% of next sprint to reels.",
        "Optimal post window appears to be Tuesday 7–9 AM based on demo engagement pattern.",
      ],
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(1),
      updated_at: daysAgo(1),
    },
  ],

  // -------------------------------------------------------------------------
  // v10 POC Demo — Campaign Pack + Report + Export
  // -------------------------------------------------------------------------
  campaign_packs: [
    {
      _id: "demo-pack-1",
      workspace_slug: "demo",
      client_id: "demo-client-1",
      campaign_name: "Demo: Apex Roofing — Summer Growth Pack",
      description: "Full pipeline demo pack: source content → snippets → prompts → renders → performance.",
      status: "active",
      source_content_ids: ["demo-source-content-1"],
      snippet_ids: ["demo-snippet-1", "demo-snippet-2"],
      render_ids: ["demo-render-1", "demo-render-2"],
      prompt_generation_ids: ["demo-prompt-gen-1", "demo-prompt-gen-2"],
      linked_at: daysAgo(1),
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(2),
      updated_at: daysAgo(1),
    },
  ],
  campaign_reports: [
    {
      _id: "demo-report-1",
      workspace_slug: "demo",
      client_id: "demo-client-1",
      campaign_pack_id: "demo-pack-1",
      status: "approved",
      summary: "Demo campaign delivered 2 renders across Instagram. Avg performance score 7.3. Top hook: follow-up system. Recommended next step: produce 3 additional reel variations using approved snippets.",
      top_performers: [{ render_id: "demo-render-1", score: 8.4, platform: "instagram" }],
      total_views: 6900,
      total_saves: 185,
      avg_score: 7.3,
      review_events: [
        { decision: "approve", note: "Demo report approved for client review.", reviewed_at: daysAgo(0) },
      ],
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(1),
      updated_at: daysAgo(0),
    },
  ],
  campaign_exports: [
    {
      _id: "demo-export-1",
      workspace_slug: "demo",
      client_id: "demo-client-1",
      campaign_pack_id: "demo-pack-1",
      campaign_report_id: "demo-report-1",
      export_path: "/tmp/signalforge_exports/demo/demo-pack-1/export_demo_v10.md",
      status: "complete",
      notes: "Demo client export package. No file was uploaded or emailed.",
      simulation_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(0),
      updated_at: daysAgo(0),
    },
  ],

  // -------------------------------------------------------------------------
  // v10 POC Demo — Client Intelligence + Lead-Content Correlations
  // -------------------------------------------------------------------------
  client_intelligence: [
    {
      _id: "demo-intel-1",
      workspace_slug: "demo",
      client_id: "demo-client-1",
      estimated_roi: 112.5,
      top_hook_themes: ["follow_up_system", "results", "reputation"],
      top_platforms: ["instagram", "youtube_shorts"],
      content_velocity: "2 renders / sprint",
      engagement_trend: "upward",
      recommendations: [
        "Double down on follow-up system hook angle — highest saves and shares.",
        "Build a 5-part reel series from approved transcript segments.",
        "Test LinkedIn carousel format for B2B contractor audience segment.",
      ],
      simulation_only: true,
      advisory_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(0),
      updated_at: daysAgo(0),
    },
  ],
  lead_content_correlations: [
    {
      _id: "demo-corr-1",
      workspace_slug: "demo",
      client_id: "demo-client-1",
      lead_id: "demo-lead-1",
      content_snippet_id: "demo-snippet-1",
      correlation_score: 0.91,
      correlation_reason: "Demo lead (Apex Roofing) matches the follow-up system hook angle with high confidence. Top performer in same niche.",
      recommended_content_angle: "follow_up_system",
      simulation_only: true,
      advisory_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(0),
      updated_at: daysAgo(0),
    },
    {
      _id: "demo-corr-2",
      workspace_slug: "demo",
      client_id: "demo-client-1",
      lead_id: "demo-lead-2",
      content_snippet_id: "demo-snippet-3",
      correlation_score: 0.74,
      correlation_reason: "Demo lead (Northline HVAC) aligns with reputation-building hook. Seasonal demand angle is secondary fit.",
      recommended_content_angle: "reputation",
      simulation_only: true,
      advisory_only: true,
      outbound_actions_taken: 0,
      is_demo: true,
      demo_label: "Demo Mode",
      created_at: daysAgo(0),
      updated_at: daysAgo(0),
    },
  ],
};

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function readState() {
  const raw = window.localStorage.getItem(DEMO_STATE_KEY);
  if (!raw) return clone(seedState);
  try {
    return { ...clone(seedState), ...JSON.parse(raw) };
  } catch {
    return clone(seedState);
  }
}

function writeState(state) {
  window.localStorage.setItem(DEMO_STATE_KEY, JSON.stringify(state));
  window.dispatchEvent(new Event("signalforge-demo-change"));
  return state;
}

function withDemoLabel(records) {
  return records.map((record) => ({ ...record, is_demo: true, demo_label: "Demo Mode" }));
}

export function isDemoModeEnabled() {
  return window.localStorage.getItem(DEMO_ENABLED_KEY) === "true";
}

export function startDemoMode() {
  window.localStorage.setItem(DEMO_ENABLED_KEY, "true");
  return writeState(clone(seedState));
}

export function stopDemoMode() {
  window.localStorage.setItem(DEMO_ENABLED_KEY, "false");
  window.dispatchEvent(new Event("signalforge-demo-change"));
}

export function resetDemoData() {
  // Clears demo state and reloads seeded synthetic records. Does not touch MongoDB.
  window.localStorage.removeItem(DEMO_STATE_KEY);
  const fresh = clone(seedState);
  window.localStorage.setItem(DEMO_STATE_KEY, JSON.stringify(fresh));
  window.dispatchEvent(new Event("signalforge-demo-change"));
  return fresh;
}

export function getDemoState() {
  return readState();
}

export function runDemoOutreach() {
  const state = readState();
  state.outreachRun = true;
  state.currentStep = Math.max(state.currentStep, 2);
  state.messages = state.messages.map((message) => ({ ...message, demo_label: "Demo Mode", updated_at: nowIso() }));
  return writeState(state);
}

export function approveDemoContentDraft(draftId) {
  const state = readState();
  state.content_drafts = (state.content_drafts || []).map((draft) =>
    draft._id === draftId
      ? {
          ...draft,
          status: "approved",
          review_note: "Demo review saved. No post published.",
          reviewed_at: nowIso(),
          updated_at: nowIso(),
          review_events: [
            ...(draft.review_events || []),
            { decision: "approve", note: "Demo review", reviewed_at: nowIso() },
          ],
        }
      : draft,
  );
  writeState(state);
  return (state.content_drafts || []).find((d) => d._id === draftId) || {};
}

export function approveDemoMessage(messageId) {
  const state = readState();
  state.currentStep = Math.max(state.currentStep, 4);
  state.messages = state.messages.map((message) =>
    message._id === messageId
      ? {
          ...message,
          review_status: "approved",
          review_decision: "approve",
          review_note: "Demo approval only. No real message was sent.",
          reviewed_at: nowIso(),
          updated_at: nowIso(),
          send_status: "not_sent",
        }
      : message,
  );
  return writeState(state);
}

export function reviewDemoSnippet(snippetId, decision, note = "") {
  const state = readState();
  const newStatus = decision === "approve" ? "approved" : decision === "reject" ? "rejected" : "needs_review";
  state.content_snippets = (state.content_snippets || []).map((snippet) =>
    snippet._id === snippetId
      ? {
          ...snippet,
          status: newStatus,
          review_decision: decision,
          review_note: note || "Demo review saved. No post published.",
          reviewed_at: nowIso(),
          updated_at: nowIso(),
          review_events: [
            ...(snippet.review_events || []),
            { decision, note: note || "Demo review", reviewed_at: nowIso() },
          ],
        }
      : snippet,
  );
  writeState(state);
  return (state.content_snippets || []).find((s) => s._id === snippetId) || {};
}

export function reviewDemoCreativeAsset(assetId, decision, note = "") {
  const state = readState();
  const newStatus = decision === "approve" ? "approved" : decision === "reject" ? "rejected" : "needs_review";
  state.creative_assets = (state.creative_assets || []).map((asset) =>
    asset._id === assetId
      ? {
          ...asset,
          status: newStatus,
          review_decision: decision,
          review_note: note || "Demo review saved. No post published.",
          reviewed_at: nowIso(),
          updated_at: nowIso(),
          review_events: [
            ...(asset.review_events || []),
            { decision, note: note || "Demo review", reviewed_at: nowIso() },
          ],
        }
      : asset,
  );
  writeState(state);
  return (state.creative_assets || []).find((a) => a._id === assetId) || {};
}

export function reviewDemoPromptGeneration(genId, decision, note = "") {  const state = readState();
  const newStatus =
    decision === "approve"
      ? "approved"
      : decision === "reject"
        ? "rejected"
        : "needs_revision";
  state.prompt_generations = (state.prompt_generations || []).map((gen) =>
    gen._id === genId
      ? {
          ...gen,
          status: newStatus,
          review_decision: decision,
          review_note: note || "Demo review saved.",
          reviewed_at: nowIso(),
          updated_at: nowIso(),
          review_events: [
            ...(gen.review_events || []),
            { decision, note: note || "Demo review", reviewed_at: nowIso() },
          ],
        }
      : gen,
  );
  writeState(state);
  return (state.prompt_generations || []).find((g) => g._id === genId) || {};
}

export function reviewDemoAssetRender(renderId, decision, note = "") {
  const state = readState();
  const newStatus =
    decision === "approve"
      ? "approved"
      : decision === "reject"
        ? "rejected"
        : "needs_revision";
  state.asset_renders = (state.asset_renders || []).map((render) =>
    render._id === renderId
      ? {
          ...render,
          status: newStatus,
          review_decision: decision,
          review_note: note || "Demo review saved. No post published.",
          reviewed_at: nowIso(),
          updated_at: nowIso(),
          review_events: [
            ...(render.review_events || []),
            { decision, note: note || "Demo review", reviewed_at: nowIso() },
          ],
        }
      : render,
  );
  writeState(state);
  return (state.asset_renders || []).find((r) => r._id === renderId) || {};
}

export function simulateDemoResponse(messageId) {
  const state = readState();
  state.responseSimulated = true;
  state.currentStep = Math.max(state.currentStep, 5);
  state.messages = state.messages.map((message) =>
    message._id === messageId
      ? {
          ...message,
          send_status: "manual_demo_send_logged",
          response_status: "call_booked",
          response_events: [
            {
              outcome: "call_booked",
              note: "Demo response: prospect asked for a quick estimate follow-up workflow review.",
              logged_at: nowIso(),
              is_demo: true,
            },
          ],
          updated_at: nowIso(),
        }
      : message,
  );
  state.deals = state.deals.map((deal) =>
    deal.message_draft_id === messageId ? { ...deal, outcome: "negotiation", deal_status: "negotiation", updated_at: nowIso() } : deal,
  );
  return writeState(state);
}

export function showDemoDealOutcome() {
  const state = readState();
  state.dealShown = true;
  state.currentStep = 5;
  state.deals = state.deals.map((deal) =>
    deal._id === "demo-deal-1"
      ? {
          ...deal,
          outcome: "closed_won",
          deal_status: "closed_won",
          deal_value: 4500,
          note: "Demo outcome: closed-won starter engagement. No invoice or CRM update was created.",
          updated_at: nowIso(),
        }
      : deal,
  );
  return writeState(state);
}

export function demoOverview() {
  const state = readState();
  const contacts = state.contacts;
  const leads = state.leads;
  const messages = state.messages;
  const deals = state.deals;
  const closedWon = deals.filter((deal) => deal.outcome === "closed_won" || deal.deal_status === "closed_won");
  const responses = messages.filter((message) => message.response_status);
  return {
    demo_mode: true,
    kpis: {
      total_contacts: contacts.length,
      total_leads: leads.length,
      message_drafts: messages.length,
      sent_messages: messages.filter((message) => message.send_status === "manual_demo_send_logged").length,
      responses: responses.length,
      meetings: messages.filter((message) => message.response_status === "call_booked").length,
      deals: deals.length,
      closed_won_revenue: closedWon.reduce((sum, deal) => sum + Number(deal.deal_value || 0), 0),
    },
    pipeline_funnel: [
      { stage: "Demo Contacts", count: contacts.length, tone: "blue" },
      { stage: "Demo Leads", count: leads.length, tone: "purple" },
      { stage: "Demo Drafts", count: messages.length, tone: "amber" },
      { stage: "Approved", count: messages.filter((message) => message.review_status === "approved").length, tone: "green" },
      { stage: "Responses", count: responses.length, tone: "blue" },
      { stage: "Closed Won", count: closedWon.length, tone: "green" },
    ],
    responses_by_status: responses.reduce((counts, message) => ({ ...counts, [message.response_status]: (counts[message.response_status] || 0) + 1 }), { not_set: messages.length - responses.length }),
    deals_by_outcome: deals.reduce((counts, deal) => ({ ...counts, [deal.outcome]: (counts[deal.outcome] || 0) + 1 }), {}),
    revenue_over_time: closedWon.map((deal) => ({ date: String(deal.updated_at || "").slice(0, 10), revenue: Number(deal.deal_value || 0) })),
    top_modules: [{ module: "contractor_growth", contacts: contacts.length, messages: messages.length, deals: deals.length, revenue: closedWon.reduce((sum, deal) => sum + Number(deal.deal_value || 0), 0) }],
    tasks: [
      { label: "Demo drafts needing review", count: messages.filter((message) => message.review_status === "needs_review").length, tone: "review" },
      { label: "Demo responses", count: responses.length, tone: "interested" },
      { label: "Demo deal outcomes", count: deals.length, tone: "closed_won" },
    ],
    next_actions: [
      { key: "demo", label: "Continue Demo", helper: "Walk the guided demo from outreach through deal outcome.", count: state.currentStep, tone: "demo", page: "demo" },
      { key: "review", label: "Review Drafts", helper: "Approve a synthetic draft. No message is sent.", count: messages.filter((message) => message.review_status === "needs_review").length, tone: "review", page: "messages", filters: { review_status: "needs_review" } },
    ],
    agent_activity: [],
  };
}

export function generateDemoSnippets(sourceContentId) {
  const state = readState();
  const segments = (state.transcript_segments || []).filter(
    (seg) => seg.source_content_id === sourceContentId,
  );
  const now = nowIso();
  const newSnippets = segments.map((seg, i) => ({
    _id: `demo-generated-snippet-${sourceContentId}-${i}`,
    workspace_slug: "demo",
    source_content_id: sourceContentId,
    transcript_run_id: seg.transcript_run_id,
    transcript_id: seg.transcript_run_id,
    speaker: seg.speaker || "speaker_1",
    start_time: Math.round(seg.start_ms / 1000),
    end_time: Math.round(seg.end_ms / 1000),
    transcript_text: seg.text,
    score: 0.72,
    score_reason: "heuristic score (demo)",
    theme: "general",
    hook_angle: "",
    platform_fit: [],
    status: "needs_review",
    review_events: [],
    generation_source: "auto",
    segment_index: seg.index,
    simulation_only: true,
    outbound_actions_taken: 0,
    is_demo: true,
    demo_label: "Demo Mode",
    created_at: now,
    updated_at: now,
  }));
  state.content_snippets = [...(state.content_snippets || []), ...newSnippets];
  writeState(state);
  return newSnippets;
}

// =============================================================================
// v10 POC Demo Progress — localStorage key separate from demo state
// =============================================================================

const DEMO_PROGRESS_KEY = "signalforge.demo.progress";
const DEMO_PROGRESS_TOTAL = 13;

export function getDemoProgress() {
  try {
    const raw = window.localStorage.getItem(DEMO_PROGRESS_KEY);
    if (!raw) return { step: 0, started: false, completed: false };
    return JSON.parse(raw);
  } catch {
    return { step: 0, started: false, completed: false };
  }
}

export function setDemoProgress(step) {
  const clamped = Math.max(0, Math.min(DEMO_PROGRESS_TOTAL, step));
  const progress = {
    step: clamped,
    started: clamped > 0,
    completed: clamped >= DEMO_PROGRESS_TOTAL,
    updated_at: new Date().toISOString(),
  };
  window.localStorage.setItem(DEMO_PROGRESS_KEY, JSON.stringify(progress));
  window.dispatchEvent(new Event("signalforge-demo-change"));
  return progress;
}

export function nextDemoStep() {
  const current = getDemoProgress();
  return setDemoProgress((current.step || 0) + 1);
}

export function prevDemoStep() {
  const current = getDemoProgress();
  return setDemoProgress(Math.max(1, (current.step || 1) - 1));
}

export function jumpDemoStep(n) {
  return setDemoProgress(n);
}

export function resetDemoProgress() {
  window.localStorage.removeItem(DEMO_PROGRESS_KEY);
  window.dispatchEvent(new Event("signalforge-demo-change"));
  return { step: 0, started: false, completed: false };
}

export function demoItems(collection) {
  const state = readState();
  return withDemoLabel(state[collection] || []);
}