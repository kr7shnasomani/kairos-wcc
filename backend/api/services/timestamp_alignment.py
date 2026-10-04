"""
Timestamp alignment across source systems (Layer 4).

The architecture calls this a first-class ingestion requirement: brownfield plants run EAM, DMS,
SCADA and email-archive systems whose server clocks are not synchronised to a common NTP source.
A work order timestamped four hours ahead of the maintenance log for the same physical event
produces incorrect temporal ordering in the graph, which silently corrupts time-travel RCA.

**What is compared, and what is deliberately not.** Drift means *the same correlated event,
reported by two different source systems, at two different times*. It does **not** mean
`occurred_at` vs `ingested_at` — a document legitimately occurring months before it was ingested
is history, not clock skew, and comparing those two would flag essentially every document in a
golden corpus and bury the real signal.

Correlation is not re-derived here: Layer 8 already groups events for the same physical action
under a shared `compound_event_id` (`event_bus.correlate_events`). This reuses that grouping.

Report-only unless `TIMESTAMP_DRIFT_ENFORCE` is set.
"""

import asyncio
from datetime import datetime
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# Normalisation target. The architecture names the historian as the site-canonical reference:
# it is the most precisely clock-synchronised system in an industrial plant. Lower rank wins.
_SOURCE_CLOCK_AUTHORITY = {
    "historian": 1,
    "pi_web_api": 1,
    "scada": 2,
    "dcs": 2,
    "sap_pm": 3,
    "eam": 3,
    "cmms": 4,
    "email_archive": 5,
    "manual": 6,
}
_UNKNOWN_SOURCE_RANK = 5


def _rank(source_system: str) -> int:
    return _SOURCE_CLOCK_AUTHORITY.get((source_system or "").lower(), _UNKNOWN_SOURCE_RANK)


def _parse(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


class TimestampAlignmentService:
    def __init__(self, supabase, settings):
        self.supabase = supabase
        self.settings = settings

    async def _compound_siblings(self, compound_event_id: str) -> list[dict[str, Any]]:
        result = await asyncio.to_thread(
            lambda: self.supabase.table("operational_events")
            .select("event_id, source_system, occurred_at, asset_id, event_type")
            .eq("compound_event_id", compound_event_id)
            .execute()
        )
        return result.data or []

    @staticmethod
    def analyse(events: list[dict[str, Any]], tolerance_minutes: int) -> dict[str, Any]:
        """
        Pure drift analysis over one compound event's sibling rows.

        Only *cross-system* pairs count. Two events from the same source system at different times
        are two events, not one event with clock skew — counting them would manufacture drift out
        of ordinary event volume.
        """
        parsed = [
            (e.get("source_system") or "unknown", _parse(e.get("occurred_at")), e.get("event_id"))
            for e in events
        ]
        usable = [(src, ts, eid) for src, ts, eid in parsed if ts is not None]

        distinct_sources = {src for src, _, _ in usable}
        if len(distinct_sources) < 2:
            return {
                "drift_detected": False,
                "drift_minutes": 0.0,
                "reason": "single_source" if usable else "no_usable_timestamps",
                "sources": sorted(distinct_sources),
                "canonical_timestamp": usable[0][1].isoformat() if usable else None,
                "canonical_source": usable[0][0] if usable else None,
            }

        # Widest disagreement between any two *different* sources.
        max_drift = 0.0
        for i, (src_a, ts_a, _) in enumerate(usable):
            for src_b, ts_b, _ in usable[i + 1:]:
                if src_a == src_b:
                    continue
                max_drift = max(max_drift, abs((ts_a - ts_b).total_seconds()) / 60.0)

        # Normalise to the best-synchronised clock present, ties broken by earliest.
        canonical_src, canonical_ts, _ = min(usable, key=lambda x: (_rank(x[0]), x[1]))

        return {
            "drift_detected": max_drift > tolerance_minutes,
            "drift_minutes": round(max_drift, 2),
            "tolerance_minutes": tolerance_minutes,
            "reason": "cross_system_drift" if max_drift > tolerance_minutes else "within_tolerance",
            "sources": sorted(distinct_sources),
            "canonical_timestamp": canonical_ts.isoformat(),
            "canonical_source": canonical_src,
        }

    async def check_compound_event(self, compound_event_id: str, asset_id: str | None = None) -> dict[str, Any]:
        """
        Run the alignment pass for one compound event.

        Always reports. Opens an administrative-track conflict for human review **only** when
        `TIMESTAMP_DRIFT_ENFORCE` is on — the default is off so this can be observed against real
        data before it starts creating review load.
        """
        events = await self._compound_siblings(compound_event_id)
        result = self.analyse(events, self.settings.TIMESTAMP_DRIFT_TOLERANCE_MINUTES)
        result["compound_event_id"] = compound_event_id
        result["enforced"] = bool(self.settings.TIMESTAMP_DRIFT_ENFORCE)

        if not result["drift_detected"]:
            return result

        log.warning(
            "timestamp_alignment.drift_detected",
            compound_event_id=compound_event_id,
            drift_minutes=result["drift_minutes"],
            sources=result["sources"],
            enforced=result["enforced"],
        )
        if not self.settings.TIMESTAMP_DRIFT_ENFORCE:
            result["action"] = "reported_only"
            return result

        # Administrative track: a clock discrepancy is a data-quality issue for a steward, not a
        # safety-critical parameter conflict, so it must never open an engineering MoC.
        try:
            await asyncio.to_thread(
                lambda: self.supabase.table("knowledge_conflicts").insert({
                    "track": "administrative",
                    "asset_id": asset_id or (events[0].get("asset_id") if events else None),
                    "parameter": "event_timestamp",
                    "source_a": {"source_system": result["sources"][0]},
                    "source_b": {"source_system": result["sources"][-1]},
                    "severity": "minor",
                }).execute()
            )
            result["action"] = "conflict_opened"
        except Exception as exc:  # noqa: BLE001 — never let a reporting failure block ingestion
            log.warning("timestamp_alignment.conflict_insert_failed", error=str(exc))
            result["action"] = "conflict_insert_failed"
        return result
