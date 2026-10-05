"""
Off-boarding `session_id` path params resolve to 404, never 500.

`offboarding_sessions.id` is a UUID column (db/schema.sql:292). Before the fix, the raw
path segment went straight to PostgREST, so three separate inputs produced a 500 on a
public route:

  * a non-UUID segment                → 22P02 "invalid input syntax for type uuid"
  * a probe for a route that does not exist (`/offboarding/sessions`)
                                      → same 22P02, because `/{session_id}` matched it
  * a well-formed UUID with no row    → PGRST116, raised by `.single()`

The third is the subtle one: `.single()` *raises* on zero rows rather than returning an
empty result, which made the `if not result.data → 404` branch in the handler unreachable.
Both halves of the fix are asserted here — validation for the first two, `maybe_single()`
for the third.

Pure logic: `valid_offboarding_session_id` takes a string and either returns it or raises
HTTPException. No stack, no secrets, no network — this belongs in the service-free tier.
It is a sibling of `valid_quarantine_item_id`, which `test_quarantine_item_id.py` covers for
the same failure on `quarantine_items`.
"""

import pytest
from fastapi import HTTPException

from api.dependencies import valid_offboarding_session_id as _session_uuid

# A real id from the seed programme (EXPERT-RKUMAR), and the canonical nil UUID: both are
# well-formed, so validation must let them through and leave "does this row exist?" to the
# handler's 404. Validation is a shape check, not an existence check.
VALID = [
    "6a3acd01-a8c3-4fe5-a43e-923fedf4611c",
    "00000000-0000-0000-0000-000000000000",
    "6A3ACD01-A8C3-4FE5-A43E-923FEDF4611C",  # upper case is the same UUID
]

INVALID = [
    "sessions",  # the reported probe — a literal path that has no route
    "NOPE-123",
    "",
    "123",
    "6a3acd01-a8c3-4fe5-a43e",  # truncated
    "6a3acd01-a8c3-4fe5-a43e-923fedf4611c-extra",
    "../../etc/passwd",
    "6a3acd01_a8c3_4fe5_a43e_923fedf4611c",  # underscores, not hyphens
]


@pytest.mark.parametrize("session_id", VALID)
def test_wellformed_uuid_passes_through(session_id):
    assert _session_uuid(session_id) == session_id


@pytest.mark.parametrize("session_id", INVALID)
def test_malformed_id_raises_404_not_500(session_id):
    with pytest.raises(HTTPException) as exc:
        _session_uuid(session_id)
    assert exc.value.status_code == 404, "an unparseable id is 'not found', never a server error"


def test_none_is_404_not_typeerror():
    """Defensive: a None slipping through must still land on 404, not an unhandled TypeError."""
    with pytest.raises(HTTPException) as exc:
        _session_uuid(None)  # type: ignore[arg-type]
    assert exc.value.status_code == 404


def test_the_reported_probe_is_404():
    """
    Regression lock for the original report: GET /elicitation/offboarding/sessions returned
    500. There is no `/sessions` route — the segment was swallowed by `/{session_id}`.
    """
    with pytest.raises(HTTPException) as exc:
        _session_uuid("sessions")
    assert exc.value.status_code == 404


def test_handlers_use_maybe_single_not_single():
    """
    `.single()` raises PGRST116 on zero rows, which turns a missing programme into a 500 and
    makes the handler's own 404 unreachable. Asserted against the source because the
    behaviour only differs when a real PostgREST call returns no rows, which the
    service-free tier cannot exercise.
    """
    from pathlib import Path

    import api.routers.elicitation as module

    source = Path(module.__file__).read_text()
    assert "OffboardingSessionIdDep" in source, "handlers must take the shared validated dep"
    offboarding = source[source.index('@router.post("/offboarding"') :]
    assert ".single()" not in offboarding, (
        "an off-boarding handler still calls .single(); it raises on zero rows and "
        "resurrects the 500. Use .maybe_single() so the handler's 404 is reachable."
    )
    assert ".maybe_single()" in offboarding
