"""
Instrumentation coverage map (Layer 5) — which physical components are actually monitored.

The architecture derives this from two sources: the engineering drawing topology extracted by
Layer 3 (which instruments exist and where they sit) and the historian tag registry (which of those
are connected and reporting). Layer 10 queries it to decide whether a maintenance action can be
evaluated by telemetry at all, or must fall back to human-verified closeout documentation.

**This replaces fabricated data.** The previous implementation (a Go handler) returned hardcoded
`{asset}-VIBE` / `{asset}-TEMP` / `seal_housing` / `75%` for every asset on both of its branches —
including the one labelled `source: "knowledge_graph"` — so every asset in the system appeared
instrumented and the telemetry check always ran. That is exactly the fabrication the project's
disclosure rule forbids.

Only **engineer-verified** topology counts. An unverified drawing is a model's candidate reading,
not evidence that a sensor exists — treating it as coverage would launder an extraction into a
telemetry claim. Supabase-only by design, so the Celery attribution worker can use it directly
without an HTTP hop.
"""

import asyncio
from typing import Any

import structlog

from api.services.topology import TopologyVerificationService

log = structlog.get_logger(__name__)


class OtCoverageService:
    def __init__(self, supabase):
        self.supabase = supabase

    async def _pid_documents_for_asset(self, asset_id: str) -> list[str]:
        result = await asyncio.to_thread(
            lambda: self.supabase.table("document_asset_links")
            .select("document_id")
            .eq("asset_id", asset_id)
            .execute()
        )
        return [r["document_id"] for r in (result.data or [])]

    async def _topology_for_document(self, document_id: str) -> dict[str, Any] | None:
        result = await asyncio.to_thread(
            lambda: self.supabase.table("quarantine_items")
            .select("session_context")
            .eq("content", f"PID_TOPOLOGY_MANIFEST:{document_id}")
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return (result.data[0].get("session_context") or {}).get("topology") or {}

    async def asset_coverage(self, asset_id: str) -> dict[str, Any]:
        """
        Instrumentation coverage for one asset, derived from verified drawing topology.

        `coverage_type`:
          - `none`   — no verified instrumentation for this asset. The honest answer whenever no
                       drawing has been verified; never a guess.
          - `macro`  — equipment is on a verified drawing but no verified instrumentation loop
                       covers it. This is the brownfield case the architecture describes: overall
                       readings exist, component condition is not directly measured.
          - `direct` — at least one verified instrumentation loop, with named instrument tags.
        """
        documents = await self._pid_documents_for_asset(asset_id)
        topo_svc = TopologyVerificationService(self.supabase)

        sensor_tags: list[str] = []
        equipment_tags: list[str] = []
        verified_loops = 0
        total_loops = 0
        source_documents: list[str] = []

        for document_id in documents:
            topology = await self._topology_for_document(document_id)
            if not topology:
                continue
            source_documents.append(document_id)
            statuses = await topo_svc.element_statuses(document_id)

            for loop in topology.get("instrumentation_loops") or []:
                total_loops += 1
                element_id = str(loop.get("id", ""))
                if statuses.get(element_id, {}).get("verification_status") != "verified":
                    continue  # a candidate reading is not a sensor
                verified_loops += 1
                for tag in loop.get("instruments") or []:
                    if tag and tag not in sensor_tags:
                        sensor_tags.append(str(tag))

            for equip in topology.get("equipment_nodes") or []:
                element_id = str(equip.get("id", ""))
                if statuses.get(element_id, {}).get("verification_status") == "verified":
                    tag = equip.get("tag")
                    if tag and tag not in equipment_tags:
                        equipment_tags.append(str(tag))

        if sensor_tags:
            coverage_type = "direct"
        elif equipment_tags:
            coverage_type = "macro"
        else:
            coverage_type = "none"

        result = {
            "asset_id": asset_id,
            "coverage_type": coverage_type,
            "has_direct_sensors": bool(sensor_tags),
            "sensor_tags": sensor_tags,
            "verified_loops": verified_loops,
            "total_loops": total_loops,
            # Named so a caller can never mistake "we have not verified a drawing" for
            # "this equipment has no sensors".
            "derived_from": "verified_pid_topology",
            "source_documents": source_documents,
            "unverified_topology_present": total_loops > verified_loops,
        }
        log.info(
            "ot_coverage.derived",
            asset_id=asset_id,
            coverage_type=coverage_type,
            sensor_tags=len(sensor_tags),
            verified_loops=verified_loops,
            total_loops=total_loops,
        )
        return result
