"""
Cross-source timestamp alignment (Layer 4) — pure logic, no network, no Supabase.

The trap this guards against is in what gets compared. Comparing `occurred_at` against
`ingested_at` would flag essentially every document in the golden corpus — those values sit months
apart by design for historical records — and bury real clock skew under thousands of false
positives. Drift means *the same correlated event reported by two different source systems at two
different times*, and nothing else.
"""

from api.services.timestamp_alignment import TimestampAlignmentService as TAS

TOLERANCE = 60


def _ev(source: str, ts: str, event_id: str = "e1") -> dict:
    return {"event_id": event_id, "source_system": source, "occurred_at": ts}


def test_two_systems_agreeing_is_not_drift():
    r = TAS.analyse(
        [_ev("sap_pm", "2026-07-15T08:00:00Z"), _ev("cmms", "2026-07-15T08:05:00Z", "e2")],
        TOLERANCE,
    )
    assert r["drift_detected"] is False
    assert r["drift_minutes"] == 5.0


def test_four_hour_skew_between_systems_is_drift():
    """The architecture's own example: SAP PM four hours ahead of the maintenance log."""
    r = TAS.analyse(
        [_ev("sap_pm", "2026-07-15T12:00:00Z"), _ev("cmms", "2026-07-15T08:00:00Z", "e2")],
        TOLERANCE,
    )
    assert r["drift_detected"] is True
    assert r["drift_minutes"] == 240.0
    assert r["reason"] == "cross_system_drift"


def test_same_source_at_different_times_is_not_drift():
    """
    Two events from one system are two events, not one event with clock skew. Counting them
    would manufacture drift out of ordinary event volume.
    """
    r = TAS.analyse(
        [_ev("cmms", "2026-07-15T08:00:00Z"), _ev("cmms", "2026-07-15T20:00:00Z", "e2")],
        TOLERANCE,
    )
    assert r["drift_detected"] is False
    assert r["reason"] == "single_source"


def test_single_event_cannot_drift():
    r = TAS.analyse([_ev("sap_pm", "2026-07-15T08:00:00Z")], TOLERANCE)
    assert r["drift_detected"] is False
    assert r["reason"] == "single_source"


def test_normalises_to_the_best_synchronised_clock():
    """The historian is the site-canonical reference — the most precisely clock-synced system."""
    r = TAS.analyse(
        [
            _ev("cmms", "2026-07-15T12:00:00Z"),
            _ev("historian", "2026-07-15T08:00:00Z", "e2"),
            _ev("email_archive", "2026-07-15T14:00:00Z", "e3"),
        ],
        TOLERANCE,
    )
    assert r["canonical_source"] == "historian"
    assert r["canonical_timestamp"].startswith("2026-07-15T08:00:00")


def test_unparseable_timestamps_are_skipped_not_treated_as_zero():
    """A bad timestamp read as epoch-zero would report ~56 years of drift."""
    r = TAS.analyse(
        [_ev("sap_pm", "not-a-timestamp"), _ev("cmms", "2026-07-15T08:00:00Z", "e2")],
        TOLERANCE,
    )
    assert r["drift_detected"] is False
    assert r["reason"] == "single_source"  # only one usable source remained


def test_no_usable_timestamps_reports_cleanly():
    r = TAS.analyse([_ev("sap_pm", ""), _ev("cmms", None, "e2")], TOLERANCE)
    assert r["drift_detected"] is False
    assert r["reason"] == "no_usable_timestamps"
    assert r["canonical_timestamp"] is None


def test_tolerance_is_configurable():
    events = [_ev("sap_pm", "2026-07-15T09:30:00Z"), _ev("cmms", "2026-07-15T08:00:00Z", "e2")]
    assert TAS.analyse(events, tolerance_minutes=60)["drift_detected"] is True
    assert TAS.analyse(events, tolerance_minutes=120)["drift_detected"] is False


def test_widest_pair_wins_across_three_systems():
    r = TAS.analyse(
        [
            _ev("historian", "2026-07-15T08:00:00Z"),
            _ev("cmms", "2026-07-15T08:30:00Z", "e2"),
            _ev("email_archive", "2026-07-15T11:00:00Z", "e3"),
        ],
        TOLERANCE,
    )
    assert r["drift_minutes"] == 180.0
    assert r["drift_detected"] is True


# =============================================================================
# Temporal validity comparisons — a Cypher type mismatch that failed silently
# =============================================================================

import pathlib  # noqa: E402
import re  # noqa: E402

# `valid_to` / `valid_from` are stored as ISO-8601 STRINGS. In Cypher, comparing a STRING to a
# DATETIME yields NULL — not False, not an error — so `WHERE (r.valid_to IS NULL OR
# r.valid_to > datetime())` evaluates to `(false OR null)` = null and the row is dropped.
#
# Measured on the live graph before the fix: that predicate matched **0** active edges where the
# cast form matched **35**. Two headline mechanisms were inert as a result — `detect_conflict`
# never found an existing edge (so no conflict was ever raised on edge creation) and
# `close_validity_windows_for_document` closed nothing (so document supersession was a no-op).
#
# Nothing errored, no test went red, and every affected query returned a plausible empty list.
_BROKEN = re.compile(r"r\.valid_(?:to|from)\s*[<>]=?\s*datetime\(\)")

_SOURCE_DIRS = ("api", "workers", "workflows", "scripts")


def _cypher_sources() -> list[pathlib.Path]:
    root = pathlib.Path(__file__).resolve().parent.parent
    files: list[pathlib.Path] = []
    for d in _SOURCE_DIRS:
        base = root / d
        if not base.exists():                      # running from a different layout
            base = root / "backend" / d
        if base.exists():
            files += sorted(base.rglob("*.py"))
    return files


def test_no_string_property_is_compared_to_the_datetime_function():
    """Compare `datetime(r.valid_to)` against `datetime()`, or a raw property against a string
    parameter — never a raw property against `datetime()`."""
    offenders = [
        f"{p}:{i}"
        for p in _cypher_sources()
        for i, line in enumerate(p.read_text().splitlines(), 1)
        if _BROKEN.search(line)
    ]
    assert not offenders, (
        "String validity property compared to datetime() — this silently matches nothing:\n  "
        + "\n  ".join(offenders)
    )


def test_the_guard_actually_catches_the_broken_form():
    """A guard that cannot fail protects nothing."""
    assert _BROKEN.search("WHERE (r.valid_to IS NULL OR r.valid_to > datetime())")
    assert _BROKEN.search("AND r.valid_from <= datetime()")
    assert not _BROKEN.search("WHERE (r.valid_to IS NULL OR datetime(r.valid_to) > datetime())")
    assert not _BROKEN.search("AND r.valid_from <= $as_of")


def test_source_files_were_actually_scanned():
    """Guards against the scan silently finding no files and passing vacuously."""
    assert len(_cypher_sources()) > 20
