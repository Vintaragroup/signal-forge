/**
 * workflowDefinitionNormalizer
 *
 * Converts a persisted workflow definition (or null) + fallback templates
 * into a unified resolvedWorkflow shape for WorkflowPage rendering.
 *
 * Rendering priority order:
 *   1. resolved workflow_definition from DB (workflowDefinition arg)
 *   2. fallbackTemplate (profile template from WORKFLOW_TEMPLATES)
 *   3. defaultTemplate (DEFAULT_TEMPLATE)
 *
 * Returns an object with:
 *   stages       — primary render source: { 1: {...}, 2: {...}, ... 7: {...} }
 *   step1Guidance — backward compat, top-level
 *   runCards      — backward compat, from base template
 *   chips         — backward compat, from base template (CommandContextCard chips)
 *   agentFit      — backward compat, from base template
 *   agentLabels   — backward compat, from base template
 *   id, slug, display_name, _fromDB, _dbSlug, _dbDisplayName, _dbStageNums, _source
 */

import { DEFAULT_TEMPLATE } from "../navigation/workflowTemplates.js";

/**
 * @param {Object} params
 * @param {Object|null} params.workflowDefinition  - DB workflow definition object (or null)
 * @param {Object|null} params.fallbackTemplate    - Profile template from WORKFLOW_TEMPLATES (or null)
 * @param {Object|null} params.defaultTemplate     - DEFAULT_TEMPLATE fallback
 * @returns {Object} resolvedWorkflow
 */
export function normalizeWorkflowDefinition({
  workflowDefinition,
  fallbackTemplate,
  defaultTemplate,
}) {
  const base = fallbackTemplate ?? defaultTemplate ?? DEFAULT_TEMPLATE;

  // Build stages 1–7 from base template
  const stages = {};
  for (let n = 1; n <= 7; n++) {
    const baseStage = base.steps?.[n] || { label: `Step ${n}`, subtitle: "" };
    stages[n] = {
      label: baseStage.label || `Step ${n}`,
      subtitle: baseStage.subtitle || "",
      notes: "",
      required: true,
      agent_key: "",
      run_card_type: "",
      chips: [],
    };
  }

  const _fromDB = !!workflowDefinition;
  const _dbStageNums = new Set();

  // Apply DB stage overrides
  if (workflowDefinition) {
    for (const stage of workflowDefinition.stages || []) {
      const n = stage.stage_number;
      if (Number.isInteger(n) && n >= 1 && n <= 7) {
        _dbStageNums.add(n);
        stages[n] = {
          label: stage.label || stages[n].label,
          subtitle: stage.notes || stages[n].subtitle,
          notes: stage.notes || "",
          required: stage.required !== false,
          agent_key: stage.agent_key || "",
          run_card_type: stage.run_card_type || "",
          chips: Array.isArray(stage.chips) ? stage.chips : [],
        };
      }
    }
  }

  // Derive step1Guidance from DB or base template
  const step1Stage = workflowDefinition?.stages?.find((s) => s.stage_number === 1);
  const step1Guidance =
    step1Stage?.notes || workflowDefinition?.notes || base.step1Guidance || "";

  // Determine source label
  let _source;
  if (_fromDB) {
    _source = "client_definition";
  } else if (fallbackTemplate) {
    _source = "profile_template";
  } else {
    _source = "default_template";
  }

  return {
    // Stage data — primary render source
    stages,
    // Backward-compat: step1Guidance at top level
    step1Guidance,
    // Backward-compat: run cards and chip labels from base template
    runCards: base.runCards || [],
    chips: base.chips || {},
    agentFit: base.agentFit || {},
    agentLabels: base.agentLabels || {},
    // Metadata
    id: workflowDefinition?._id || null,
    slug: workflowDefinition?.slug || null,
    display_name: workflowDefinition?.display_name || null,
    _fromDB,
    _dbSlug: workflowDefinition?.slug || null,
    _dbDisplayName: workflowDefinition?.display_name || null,
    _dbStageNums,
    _source,
  };
}
