// Demo fallback MoC cases — built on call so module load stays clock-free.
import type { MocItem } from "@/lib/types";
import { nowMs } from "@/lib/utils";

const DAY = 86_400_000;

export function mocFixture(id: string): MocItem | null {
  const now = nowMs();
  const fixtures: MocItem[] = [
    {
      moc_id: "MOC-2024-001",
      asset_id: "P-101",
      parameter: "operating_pressure",
      source_a: { value: "12.5 bar", document_id: "DOC-OEM-001" },
      source_b: { value: "14.0 bar", document_id: "DOC-INSP-007" },
      blast_radius_count: 7,
      status: "pending",
      created_at: new Date(now - DAY).toISOString(),
      draft_content: "EWR Draft: Operating pressure discrepancy on P-101. Source OEM-001 records 12.5 bar; recent inspection DOC-INSP-007 records 14.0 bar. Recommend engineering review of seal ratings before next scheduled maintenance window.",
    },
    {
      moc_id: "MOC-2024-002",
      asset_id: "V-247",
      parameter: "relief_valve_setpoint",
      source_a: { value: "16 bar", document_id: "DOC-PROC-003" },
      source_b: { value: "18 bar", document_id: "DOC-OEM-008" },
      blast_radius_count: 3,
      status: "pending",
      created_at: new Date(now - 2 * DAY).toISOString(),
      draft_content: null,
    },
    {
      moc_id: "MOC-2024-003",
      asset_id: "EQ-101",
      parameter: "maintenance_interval_days",
      source_a: { value: "90", document_id: "DOC-PROC-011" },
      source_b: { value: "120", document_id: "DOC-OEM-002" },
      blast_radius_count: 2,
      status: "approved",
      created_at: new Date(now - 5 * DAY).toISOString(),
      draft_content: null,
    },
  ];
  return fixtures.find((f) => f.moc_id === id) ?? null;
}
