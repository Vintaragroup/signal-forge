/**
 * System Profile Registry
 *
 * A System Profile is a named operator intent that declares:
 *   - which business vertical this SignalForge instance serves
 *   - which module maps to its data layer
 *   - which agents are primary
 *   - future: terminology, enabled UI sections, demo seed, KPI priorities
 *
 * Phase 2B scope: presentation only.
 * No agent filtering, no data filtering, no API changes.
 */

export const SYSTEM_PROFILES = [
  {
    id: "executive_growth",
    label: "Executive Growth Engine",
    description: "Scale executive or media brand accounts with content and outreach.",
    module: "media_growth",
    primaryAgent: "content",
    workflowTemplateId: "executive_growth",
  },
  {
    id: "contractor_growth",
    label: "Contractor Growth Engine",
    description: "B2B pipeline for local services and contractor lead generation.",
    module: "contractor_growth",
    primaryAgent: "outreach",
    workflowTemplateId: "contractor_growth",
  },
  {
    id: "creator_monetization",
    label: "Creator Monetization Engine",
    description: "Fan monetization and content strategy for artists and creators.",
    module: "artist_growth",
    primaryAgent: "content",
    workflowTemplateId: "creator_monetization",
  },
  {
    id: "investor_outreach",
    label: "Investor Outreach Engine",
    description: "Capital outreach and financial pipeline development.",
    module: "insurance_growth",
    primaryAgent: "outreach",
    workflowTemplateId: "investor_outreach",
  },
  {
    id: "recruiting_pipeline",
    label: "Recruiting Pipeline Engine",
    description: "Talent pipeline management and candidate outreach.",
    module: "contractor_growth",
    primaryAgent: "followup",
    workflowTemplateId: "recruiting_pipeline",
  },
  {
    id: "custom",
    label: "Custom",
    description: "No preset — configure each agent task manually.",
    module: "",
    primaryAgent: null,
    workflowTemplateId: "custom",
  },
];

/** O(1) lookup by profile id. */
export const PROFILE_MAP = Object.fromEntries(SYSTEM_PROFILES.map((p) => [p.id, p]));

/** localStorage key used to persist the active profile across sessions. */
export const PROFILE_STORAGE_KEY = "signalforge.profile";
