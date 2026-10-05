"""
Instrumentation coverage map (Layer 5) — no network, no Supabase.

This replaces fabricated data. The previous Go handler returned hardcoded `{asset}-VIBE` /
`{asset}-TEMP` / 75% for *every* asset on both branches, including the one labelled
`source: "knowledge_graph"`. Because coverage was never 0, Layer 10's telemetry check always ran
as the primary evidence — the brownfield downgrade the architecture describes was unreachable.

The load-bearing property under test: coverage counts only **engineer-verified** topology, and an
asset with no verified drawing reports `none` rather than inventing a sensor.
"""

from api.services.ot_coverage import OtCoverageService

ASSET = "EQ-101"
DOC = "DOC-PID-1"

TOPOLOGY = {
    "equipment_nodes": [{"id": "TOPO-EQ-001", "tag": "P-101", "equipment_class": "pump"}],
    "instrumentation_loops": [
        {"id": "TOPO-LOOP-001", "loop_id": "FIC-3047", "instruments": ["FT-3047", "FV-3047"]},
        {"id": "TOPO-LOOP-002", "loop_id": "TIC-9001", "instruments": ["TT-9001"]},
    ],
}


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_a, **_kw):
        return self

    def eq(self, *_a):
        return self

    def neq(self, *_a):
        return self

    def limit(self, _n):
        return self

    def execute(self):
        return type("Result", (), {"data": self._rows})()


class FakeSupabase:
    """Routes by table name; element review states drive what counts as verified."""

    def __init__(self, element_states: dict[str, str], topology=TOPOLOGY, linked=True):
        self.element_states = element_states
        self.topology = topology
        self.linked = linked

    def table(self, name: str):
        if name == "document_asset_links":
            return _Query([{"document_id": DOC}] if self.linked else [])
        if name == "quarantine_items":
            return _Query(self._quarantine_rows())
        return _Query([])

    def _quarantine_rows(self):
        # One manifest row plus one row per element. Both reads hit `quarantine_items`; the
        # manifest carries `topology`, the element rows carry `id` + review_status.
        rows = [{
            "item_id": "manifest",
            "review_status": "pending",
            "reviewer_id": None,
            "reviewed_at": None,
            "session_context": {
                "source_document_id": DOC,
                "element_type": "topology_manifest",
                "topology": self.topology,
            },
        }]
        for element_id, state in self.element_states.items():
            rows.append({
                "item_id": f"item-{element_id}",
                "review_status": state,
                "reviewer_id": None,
                "reviewed_at": None,
                "session_context": {"id": element_id, "element_group": "instrumentation_loops",
                                    "source_document_id": DOC},
            })
        return rows


async def test_verified_loops_yield_direct_coverage_with_real_tags():
    sb = FakeSupabase({"TOPO-LOOP-001": "promoted", "TOPO-LOOP-002": "promoted"})
    cov = await OtCoverageService(sb).asset_coverage(ASSET)

    assert cov["coverage_type"] == "direct"
    assert cov["has_direct_sensors"] is True
    # Real tags off the drawing — never the fabricated {asset}-VIBE / {asset}-TEMP.
    assert cov["sensor_tags"] == ["FT-3047", "FV-3047", "TT-9001"]
    assert f"{ASSET}-VIBE" not in cov["sensor_tags"]
    assert cov["derived_from"] == "verified_pid_topology"


async def test_unverified_topology_is_not_coverage():
    """A model's candidate reading is not evidence that a sensor exists."""
    sb = FakeSupabase({"TOPO-LOOP-001": "pending", "TOPO-LOOP-002": "pending"})
    cov = await OtCoverageService(sb).asset_coverage(ASSET)

    assert cov["has_direct_sensors"] is False
    assert cov["sensor_tags"] == []
    # The drawing has instrumentation awaiting review — that is backlog, not absence.
    assert cov["unverified_topology_present"] is True


async def test_partially_verified_reports_only_the_verified_tags():
    sb = FakeSupabase({"TOPO-LOOP-001": "promoted", "TOPO-LOOP-002": "pending"})
    cov = await OtCoverageService(sb).asset_coverage(ASSET)

    assert cov["sensor_tags"] == ["FT-3047", "FV-3047"]
    assert cov["verified_loops"] == 1
    assert cov["total_loops"] == 2


async def test_asset_with_no_linked_drawing_reports_none_not_a_guess():
    sb = FakeSupabase({}, linked=False)
    cov = await OtCoverageService(sb).asset_coverage(ASSET)

    assert cov["coverage_type"] == "none"
    assert cov["sensor_tags"] == []
    assert cov["has_direct_sensors"] is False


async def test_verified_equipment_without_loops_is_macro_coverage():
    """The brownfield case: equipment is known, component condition is not directly measured."""
    topo = {"equipment_nodes": TOPOLOGY["equipment_nodes"], "instrumentation_loops": []}
    sb = FakeSupabase({"TOPO-EQ-001": "promoted"}, topology=topo)
    cov = await OtCoverageService(sb).asset_coverage(ASSET)

    assert cov["coverage_type"] == "macro"
    assert cov["has_direct_sensors"] is False


async def test_duplicate_instrument_tags_are_not_double_counted():
    topo = {
        "equipment_nodes": [],
        "instrumentation_loops": [
            {"id": "TOPO-LOOP-001", "instruments": ["FT-3047"]},
            {"id": "TOPO-LOOP-002", "instruments": ["FT-3047"]},
        ],
    }
    sb = FakeSupabase({"TOPO-LOOP-001": "promoted", "TOPO-LOOP-002": "promoted"}, topology=topo)
    cov = await OtCoverageService(sb).asset_coverage(ASSET)

    assert cov["sensor_tags"] == ["FT-3047"]
