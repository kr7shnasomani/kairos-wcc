"""
P&ID topology verification (Layer 3 extraction → Layer 7 canonical gate).

The architecture makes one requirement non-negotiable regardless of model accuracy: every
engineering drawing topology extraction must undergo *element-by-element* engineer verification
before it enters the canonical graph. Safety-critical topology — isolation boundaries and
instrumentation loops — cannot be treated as canonical until a qualified engineer has confirmed
each element.

No new storage. The ingestion pipeline (`workflows/document_pipeline.py`) already writes, per
element: a `Concept` node, an unverified `CONTAINS_TOPOLOGY_ELEMENT` edge, and a `quarantine_items`
row. Verification therefore *reuses* the quarantine review lifecycle and *promotes the existing
edge* — it does not create a parallel state machine.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# Element groups whose extraction the architecture names as safety-critical. Until every element
# in these groups is confirmed, the drawing's topology is not canonical.
SAFETY_CRITICAL_GROUPS = frozenset({"isolation_boundaries", "instrumentation_loops"})

# An engineer's decision → the quarantine lifecycle state it maps onto.
# "corrected" is a confirmation carrying an edit, so it promotes like "confirmed".
_DECISION_TO_REVIEW_STATUS = {
    "confirmed": "promoted",
    "corrected": "promoted",
    "rejected": "disputed",
}

# Quarantine review state → the verification status the graph and the UI speak.
_REVIEW_STATUS_TO_VERIFICATION = {
    "promoted": "verified",
    "disputed": "disputed",
}


def _verification_of(review_status: str | None) -> str:
    """Anything not explicitly promoted or disputed is still unverified — including 'archived'."""
    return _REVIEW_STATUS_TO_VERIFICATION.get(review_status or "", "unverified")


class TopologyVerificationService:
    def __init__(self, supabase, graph=None):
        self.supabase = supabase
        self.graph = graph

    async def _element_rows(self, document_id: str) -> list[dict[str, Any]]:
        """
        Every per-element quarantine row for a drawing, excluding the topology manifest.

        The manifest is filtered **in Python, not in the query**. Element rows carry no
        `element_type` key at all, so a `.neq("session_context->>element_type", ...)` filter
        compares against SQL NULL — which yields NULL rather than TRUE and silently drops every
        element row. That returned an empty element map for drawings that plainly had elements.
        """
        result = await asyncio.to_thread(
            lambda: self.supabase.table("quarantine_items")
            .select("item_id, review_status, reviewer_id, reviewed_at, session_context")
            .eq("session_context->>source_document_id", document_id)
            .execute()
        )
        return [
            row
            for row in (result.data or [])
            if (row.get("session_context") or {}).get("element_type") != "topology_manifest"
        ]

    async def element_statuses(self, document_id: str) -> dict[str, dict[str, Any]]:
        """
        Per-element verification state, keyed by element id.

        This replaces a hardcoded `"verification_status": "unverified"` literal that made every
        element on every drawing render identically regardless of what a reviewer had actually done.
        """
        statuses: dict[str, dict[str, Any]] = {}
        for row in await self._element_rows(document_id):
            ctx = row.get("session_context") or {}
            element_id = ctx.get("id")
            if not element_id:
                continue
            statuses[str(element_id)] = {
                "item_id": str(row["item_id"]),
                "element_group": ctx.get("element_group", ""),
                "verification_status": _verification_of(row.get("review_status")),
                "reviewed_by": row.get("reviewer_id"),
                "reviewed_at": row.get("reviewed_at"),
            }
        return statuses

    @staticmethod
    def summarize(statuses: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """
        Roll per-element state up to the drawing.

        `verified` requires *every* element to be resolved and none disputed. A drawing with a
        single disputed element is not canonical, which is the entire point of the gate.
        """
        total = len(statuses)
        verified = sum(1 for s in statuses.values() if s["verification_status"] == "verified")
        disputed = sum(1 for s in statuses.values() if s["verification_status"] == "disputed")

        safety_total = sum(1 for s in statuses.values() if s["element_group"] in SAFETY_CRITICAL_GROUPS)
        safety_verified = sum(
            1
            for s in statuses.values()
            if s["element_group"] in SAFETY_CRITICAL_GROUPS and s["verification_status"] == "verified"
        )

        if total == 0:
            document_status = "unverified"
        elif verified == total:
            document_status = "verified"
        elif verified > 0 or disputed > 0:
            document_status = "partially_verified"
        else:
            document_status = "unverified"

        return {
            "verification_status": document_status,
            "elements_total": total,
            "elements_verified": verified,
            "elements_disputed": disputed,
            "safety_critical_total": safety_total,
            "safety_critical_verified": safety_verified,
            # The canonical gate: safety-critical topology confirmed element by element.
            "canonical_ready": safety_total > 0 and safety_verified == safety_total and disputed == 0,
        }

    async def verify_elements(
        self,
        document_id: str,
        decisions: list[dict[str, Any]],
        reviewer_id: str,
    ) -> dict[str, Any]:
        """
        Apply a batch of engineer decisions, then promote each confirmed element's existing graph
        edge. Returns the refreshed summary.

        Unknown element ids are reported rather than silently ignored — a reviewer confirming an
        element that is not in the drawing means the client and the graph disagree.
        """
        known = await self.element_statuses(document_id)
        now = datetime.now(UTC).isoformat()
        applied: list[str] = []
        unknown: list[str] = []

        for decision in decisions:
            element_id = str(decision.get("element_id", ""))
            verdict = str(decision.get("decision", ""))
            if element_id not in known:
                unknown.append(element_id)
                continue
            review_status = _DECISION_TO_REVIEW_STATUS.get(verdict)
            if review_status is None:
                unknown.append(element_id)
                continue

            update: dict[str, Any] = {
                "review_status": review_status,
                "reviewer_id": reviewer_id,
                "reviewed_at": now,
            }
            item_id = known[element_id]["item_id"]
            await asyncio.to_thread(
                lambda u=update, i=item_id: self.supabase.table("quarantine_items")
                .update(u)
                .eq("item_id", i)
                .execute()
            )

            # Promote (or dispute) the edge the extraction pipeline already wrote.
            if self.graph is not None:
                try:
                    await self.graph.set_topology_element_verification(
                        document_id=document_id,
                        element_id=element_id,
                        verification_status=_verification_of(review_status),
                        verified_by=reviewer_id,
                    )
                except Exception as exc:  # graph unreachable must not lose the human decision
                    log.warning(
                        "topology.edge_promote_failed",
                        document_id=document_id,
                        element_id=element_id,
                        error=str(exc),
                    )
            applied.append(element_id)

        statuses = await self.element_statuses(document_id)
        summary = self.summarize(statuses)
        log.info(
            "topology.elements_verified",
            document_id=document_id,
            applied=len(applied),
            unknown=len(unknown),
            document_status=summary["verification_status"],
            canonical_ready=summary["canonical_ready"],
        )
        return {**summary, "applied": applied, "unknown_elements": unknown}
