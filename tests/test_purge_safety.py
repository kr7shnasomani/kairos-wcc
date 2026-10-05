"""Purge matchers must never be able to reach real data.

`DOC-X` once sat in a prefix list and `DETACH DELETE`d four real documents on every full-suite
run, because real ids are `DOC-` plus twelve random characters and roughly one in thirty-six
starts with X. This pins the invariants that stop a repeat.

Pure constants. No stack, no secrets, no network.
"""

import pytest

from scripts.purge_test_data import (
    ASSET_PREFIXES,
    DOC_EXACT_IDS,
    DOC_PREFIXES,
    EXACT_ID_SETS,
    WO_EXACT_IDS,
    WO_PREFIXES,
)

# Ids that exist in the demo corpus and must survive any purge. `WO-2026-0714` carries the
# promoted quarantine item `PROMOTED-f17b1416…` that status.md's compliance caveat cites.
REAL_IDS = [
    "WO-2026-0714",
    "DOC-MGAC8EU3P4XJ",
    "DOC-XYZABC123456",  # a real id that happens to start with X — the original incident
    "EQ-101",
    "V-247",
]


@pytest.mark.parametrize("real_id", REAL_IDS)
def test_no_prefix_matches_a_real_id(real_id):
    for prefix in [*ASSET_PREFIXES, *WO_PREFIXES, *DOC_PREFIXES]:
        assert not real_id.startswith(prefix), (
            f"purge prefix {prefix!r} would match real id {real_id!r}"
        )


@pytest.mark.parametrize("real_id", REAL_IDS)
def test_no_exact_id_is_a_real_id(real_id):
    for _, exact_ids in EXACT_ID_SETS:
        assert real_id not in exact_ids


@pytest.mark.parametrize("prefix", [*ASSET_PREFIXES, *WO_PREFIXES, *DOC_PREFIXES])
def test_every_prefix_ends_with_a_separator(prefix):
    """A prefix that stops short of its trailing '-' can match a longer real id. This is the
    single rule that would have prevented the DOC-X data loss."""
    assert prefix.endswith("-"), f"{prefix!r} must end with '-' or it can match real ids"


@pytest.mark.parametrize("exact_id", [*DOC_EXACT_IDS, *WO_EXACT_IDS])
def test_exact_ids_are_not_also_prefixes(exact_id):
    """An id in an _EXACT list must not additionally appear as a prefix — that reintroduces
    prefix matching for the very id that was moved out of it."""
    for prefix in [*ASSET_PREFIXES, *WO_PREFIXES, *DOC_PREFIXES]:
        assert prefix != exact_id


def test_wo_e2e_literal_is_matched_by_equality_not_prefix():
    """The 4 stranded rows are purgeable now, and only by equality."""
    assert "WO-E2E-ELICIT-001" in WO_EXACT_IDS
    assert not any("WO-E2E-ELICIT-001".startswith(p) for p in WO_PREFIXES)
