// Display names for coded API values.
//
// DESIGN.md §5.4: never render a raw database value. /assets printed
// `he-3xx_series` and `rotating_centrifugal_pump` straight into KPI cards —
// a missing presentation layer, not a styling bug, and systemic.
//
// Domains are enumerated in docs/design/DATA-CONTRACT.md §2.

export type LabelDomain =
  | "equipment_class"
  | "criticality"
  | "input_type"
  | "review_status"
  | "document_type"
  | "document_status"
  | "event_type"
  | "moc_status"
  | "conflict_status"
  | "plant_state"
  | "offboarding_status";

/** Values whose naive humanisation would be wrong — acronyms, hyphenation, domain spelling. */
const OVERRIDES: Record<string, string> = {
  "he-3xx_series": "HE-3xx series",
  non_critical: "Non-critical",
  safety_critical: "Safety-critical",
  pid_drawing: "P&ID drawing",
  oem_manual: "OEM manual",
  ptw: "PTW",
  ptw_generated: "PTW generated",
  moc: "MoC",
  pending_moc: "Pending MoC",
  sla: "SLA",
  rca: "RCA",
  rca_pack_generated: "RCA pack generated",
  eam_source: "EAM source",
};

/** snake_case / kebab-case → Sentence case. */
function humanise(value: string): string {
  const spaced = value.replace(/[_-]+/g, " ").trim();
  if (!spaced) return "—";
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** The display form of a coded value. Em dash when absent — never an empty cell. */
export function label(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return OVERRIDES[value] ?? humanise(value);
}

// ponytail: one flat override map rather than per-domain tables. Values are
// unique across domains today; nest by domain only if two ever collide.
export function labelOf(_domain: LabelDomain, value: string | null | undefined): string {
  return label(value);
}

/**
 * "1 signal", not "1 signals" — review items 33 and 36.
 * Pass an explicit plural for irregular nouns.
 */
export function plural(count: number, singular: string, pluralForm?: string): string {
  const word = count === 1 ? singular : (pluralForm ?? `${singular}s`);
  return `${count} ${word}`;
}
