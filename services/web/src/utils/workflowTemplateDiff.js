/**
 * workflowTemplateDiff
 *
 * Compares a persisted workflow definition against a fallback template to
 * count how many stages have been customized.
 *
 * Compared fields per stage: label, chips, run_card_type, notes
 */

/**
 * @param {Object} params
 * @param {Object|null} params.workflowDefinition - DB workflow definition object
 * @param {Object|null} params.fallbackTemplate   - Profile template from WORKFLOW_TEMPLATES
 * @returns {number} Number of stages that differ from the fallback template
 */
export function getWorkflowOverrideCount({ workflowDefinition, fallbackTemplate }) {
  if (!workflowDefinition || !workflowDefinition.stages) return 0;
  if (!fallbackTemplate || !fallbackTemplate.steps) return 0;

  let count = 0;

  for (const stage of workflowDefinition.stages) {
    const n = stage.stage_number;
    if (!n || n < 1 || n > 7) continue;

    const base = fallbackTemplate.steps?.[n];
    if (!base) {
      // Stage number not in base template — it's an override
      count++;
      continue;
    }

    const labelDiffers = stage.label && stage.label !== base.label;
    const notesDiffers = stage.notes && stage.notes.trim() !== "";
    const runCardDiffers = stage.run_card_type && stage.run_card_type.trim() !== "";
    const chipsDiffer = Array.isArray(stage.chips) && stage.chips.length > 0;

    if (labelDiffers || notesDiffers || runCardDiffers || chipsDiffer) {
      count++;
    }
  }

  return count;
}
