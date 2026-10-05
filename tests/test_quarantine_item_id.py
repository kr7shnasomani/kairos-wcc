"""Quarantine `item_id` path guard — a malformed id must 404, never 500.

`quarantine_items.item_id` is a UUID column, so a non-UUID path segment made PostgREST
raise `22P02` *before* the handler's own 404 branch was reached; the global exception
handler turned that into a 500. Four routes read that table by id and all four shared
the bug.

Pure logic + signature introspection. No stack, no secrets, no network.
"""

import inspect

import pytest
from fastapi import HTTPException

from api.dependencies import QuarantineItemIdDep, valid_quarantine_item_id
from api.routers import events, governance


def test_wellformed_uuid_passes_through_unchanged():
    ok = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"
    assert valid_quarantine_item_id(ok) == ok


@pytest.mark.parametrize(
    "bad",
    [
        "NONEXISTENT",          # what the e2e sweep probed with
        "not-a-uuid",
        "123",
        "3f2504e0-4f89-11d3-9a0c",  # truncated — right shape, wrong length
        "",
    ],
)
def test_malformed_id_is_404_not_500(bad):
    with pytest.raises(HTTPException) as exc:
        valid_quarantine_item_id(bad)
    assert exc.value.status_code == 404, "a bad id is 'not found', never a server error"


@pytest.mark.parametrize(
    "handler",
    [
        governance.promote_quarantine_item,
        governance.dispute_quarantine_item,
        governance.request_quarantine_info,
        events.resolve_deviation_flag,
    ],
    ids=["promote", "dispute", "request-info", "deviation-flag-resolve"],
)
def test_every_quarantine_route_is_wired_to_the_guard(handler):
    """The guard only protects what it is wired to, and reverting one signature is silent:
    the route keeps working for valid ids and 500s again only on a malformed one."""
    assert inspect.signature(handler).parameters["item_id"].annotation is QuarantineItemIdDep
