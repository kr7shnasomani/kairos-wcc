"""
Layer 1 golden-record import — `routers/assets.partition_import_rows`.

Pins the three rejection classes and, most importantly, that bulk import cannot become the
write-side hole in the tenancy boundary `site_scope` closes on the read side.

Service-free: the partition is pure — the caller supplies existing ids and the permitted site.
"""

import pytest

from api.models.asset import AssetBulkImport, AssetImportRow
from api.routers.assets import partition_import_rows


def _row(asset_id=None, site_id="SITE_001", tag=None):
    return AssetImportRow(
        asset_id=asset_id,
        tag_number=tag or f"TAG-{asset_id or 'NEW'}",
        name="Feed Pump",
        equipment_class="PUMP",
        criticality="critical",
        site_id=site_id,
        facility_id="FAC_001",
    )


def _ids(entries):
    return [e["asset_id"] for e in entries]


def _created(part):
    return [r.asset_id for _, r in part["to_create"]]


# ---------------------------------------------------------------------------
# Existing assets are skipped, never overwritten
# ---------------------------------------------------------------------------

def test_existing_assets_are_skipped_not_recreated():
    """
    The point of the skip. Neo4j's `ON CREATE SET` already refuses to clobber, but the Supabase
    write is an `upsert` — so without filtering here a re-import would replace
    `identity_confirmed_by` with whoever ran the import, and the two stores would disagree about
    who confirmed the identity.
    """
    rows = [_row("EQ-101"), _row("EQ-999")]
    part = partition_import_rows(rows, existing_ids={"EQ-101"}, allowed_site=None)

    assert _created(part) == ["EQ-999"]
    assert _ids(part["already_present"]) == ["EQ-101"]


def test_reimporting_the_same_file_creates_nothing_the_second_time():
    """Idempotence is what makes 'fix the bad rows and re-post the whole file' safe advice."""
    rows = [_row("EQ-101"), _row("EQ-102")]
    second = partition_import_rows(rows, existing_ids={"EQ-101", "EQ-102"}, allowed_site=None)

    assert _created(second) == []
    assert len(second["already_present"]) == 2


# ---------------------------------------------------------------------------
# Tenancy boundary
# ---------------------------------------------------------------------------

def test_rows_for_another_site_are_rejected_not_silently_rescoped():
    """A caller must never be told it imported one site while importing another."""
    rows = [_row("EQ-101", site_id="SITE_001"), _row("EQ-201", site_id="SITE_002")]
    part = partition_import_rows(rows, existing_ids=set(), allowed_site="SITE_001")

    assert _created(part) == ["EQ-101"]
    assert _ids(part["site_forbidden"]) == ["EQ-201"]
    assert part["site_forbidden"][0]["site_id"] == "SITE_002"


def test_admin_none_scope_may_import_across_sites():
    rows = [_row("EQ-101", site_id="SITE_001"), _row("EQ-201", site_id="SITE_002")]
    part = partition_import_rows(rows, existing_ids=set(), allowed_site=None)

    assert _created(part) == ["EQ-101", "EQ-201"]
    assert part["site_forbidden"] == []


def test_site_check_precedes_existence_check():
    """A cross-site row must be refused even when that asset already exists — otherwise the
    response leaks which asset ids are present in a site the caller cannot read."""
    rows = [_row("EQ-201", site_id="SITE_002")]
    part = partition_import_rows(rows, existing_ids={"EQ-201"}, allowed_site="SITE_001")

    assert part["already_present"] == []
    assert _ids(part["site_forbidden"]) == ["EQ-201"]


# ---------------------------------------------------------------------------
# Duplicates within one payload
# ---------------------------------------------------------------------------

def test_duplicate_ids_in_one_payload_keep_the_first_and_report_the_rest():
    """Usually means the export was joined wrong — reporting it beats silently collapsing."""
    rows = [_row("EQ-101", tag="TAG-A"), _row("EQ-101", tag="TAG-B"), _row("EQ-102")]
    part = partition_import_rows(rows, existing_ids=set(), allowed_site=None)

    assert _created(part) == ["EQ-101", "EQ-102"]
    assert part["duplicate_in_payload"] == [{"row": 1, "asset_id": "EQ-101"}]


def test_duplicate_report_carries_the_row_index():
    """Row index is the only way an operator finds the offending line in a 5,000-row export."""
    rows = [_row("EQ-101"), _row("EQ-102"), _row("EQ-103"), _row("EQ-102")]
    part = partition_import_rows(rows, existing_ids=set(), allowed_site=None)

    assert part["duplicate_in_payload"] == [{"row": 3, "asset_id": "EQ-102"}]


# ---------------------------------------------------------------------------
# Rows without an asset_id
# ---------------------------------------------------------------------------

def test_rows_without_asset_id_are_always_creatable():
    """An id is generated at write time, so such a row cannot collide with anything."""
    rows = [_row(None), _row(None), _row(None)]
    part = partition_import_rows(rows, existing_ids={"EQ-101"}, allowed_site=None)

    assert len(part["to_create"]) == 3
    assert part["duplicate_in_payload"] == []
    assert part["already_present"] == []


def test_missing_asset_id_still_obeys_the_site_boundary():
    rows = [_row(None, site_id="SITE_002")]
    part = partition_import_rows(rows, existing_ids=set(), allowed_site="SITE_001")

    assert part["to_create"] == []
    assert len(part["site_forbidden"]) == 1


# ---------------------------------------------------------------------------
# Accounting and edges
# ---------------------------------------------------------------------------

def test_every_row_lands_in_exactly_one_bucket():
    """Accounting has to close, or the response under-reports what happened to a row."""
    rows = [
        _row("EQ-101"),                      # create
        _row("EQ-102"),                      # already present
        _row("EQ-101"),                      # duplicate
        _row("EQ-201", site_id="SITE_002"),  # forbidden
        _row(None),                          # create, generated id
    ]
    part = partition_import_rows(rows, existing_ids={"EQ-102"}, allowed_site="SITE_001")

    total = (len(part["to_create"]) + len(part["already_present"])
             + len(part["duplicate_in_payload"]) + len(part["site_forbidden"]))
    assert total == len(rows)


def test_empty_payload_partitions_cleanly():
    part = partition_import_rows([], existing_ids=set(), allowed_site=None)

    assert part == {"to_create": [], "already_present": [],
                    "duplicate_in_payload": [], "site_forbidden": []}


def test_row_indexes_are_positions_in_the_submitted_payload():
    """Indexes must survive filtering — they point at the caller's file, not a filtered subset."""
    rows = [_row("EQ-101"), _row("EQ-102"), _row("EQ-103")]
    part = partition_import_rows(rows, existing_ids={"EQ-101", "EQ-102"}, allowed_site=None)

    assert [i for i, _ in part["to_create"]] == [2]
    assert [e["row"] for e in part["already_present"]] == [0, 1]


# ---------------------------------------------------------------------------
# Model contract
# ---------------------------------------------------------------------------

def test_import_row_has_no_confirmed_by_field():
    """The confirming authority comes from the verified token. A per-row field would let a
    caller attribute a 5,000-asset import to someone else."""
    assert "confirmed_by_user_id" not in AssetImportRow.model_fields


def test_criticality_is_constrained():
    with pytest.raises(ValueError):
        _row("EQ-101").model_copy(update={"criticality": "kind-of-important"}).model_validate(
            {**_row("EQ-101").model_dump(), "criticality": "kind-of-important"}
        )


def test_bulk_payload_rejects_empty_and_oversized():
    with pytest.raises(ValueError):
        AssetBulkImport(assets=[])
    with pytest.raises(ValueError):
        AssetBulkImport(assets=[_row(f"EQ-{i}") for i in range(5001)])
