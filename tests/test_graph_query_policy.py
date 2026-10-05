"""Graph query policy — ARCHITECTURE.md §7.

The section's failing mode is a temporal graph query that plans as a scan or walks unbounded.
`scripts/verify_graph_perf.py` covers plan shape and needs a live Neo4j; this covers the part
that can be enforced statically, so an unbounded traversal cannot reach a review.

Pure source inspection. No stack, no secrets, no network.
"""

import re

import pytest

from api.services import graph as graph_module

SOURCE = __import__("inspect").getsource(graph_module)

# `[:REL*` with no upper bound. An upper bound is required, and it may be a literal (`*1..10`)
# or the interpolated policy constant (`*1..{MAX_TRAVERSAL_DEPTH}`) — hence `(\d|\{)`.
_UNBOUNDED = re.compile(r"\[:[A-Z_|]+\*(?!\d*\.\.(?:\d|\{))")


def test_no_unbounded_variable_length_traversal():
    """An unbounded `*` on a temporal graph is the pathological case §7 is written about:
    it makes the planner's work a function of graph size rather than query scope."""
    offenders = _UNBOUNDED.findall(SOURCE)
    assert not offenders, (
        f"unbounded variable-length traversal(s) in graph.py: {offenders} — "
        f"bound them with MAX_TRAVERSAL_DEPTH"
    )


def test_traversal_depth_comes_from_the_policy_constant():
    """A literal depth inlined per query is not a policy — the next traversal added would pick
    its own number and nothing would notice."""
    assert isinstance(graph_module.MAX_TRAVERSAL_DEPTH, int)
    assert 1 <= graph_module.MAX_TRAVERSAL_DEPTH <= 25, "a depth this large is not a bound"
    assert f"*1..{graph_module.MAX_TRAVERSAL_DEPTH}" not in SOURCE.replace(
        "{MAX_TRAVERSAL_DEPTH}", "SENTINEL"
    ), "depth is hardcoded inline; interpolate MAX_TRAVERSAL_DEPTH instead"


@pytest.mark.parametrize(
    "pattern",
    [
        r"\[:[A-Z_|]+\*1\.\.\{MAX_TRAVERSAL_DEPTH\}\]",  # the interpolated form
    ],
)
def test_the_bounded_traversal_is_present(pattern):
    assert re.search(pattern, SOURCE), "expected the depth-bounded PARENT_OF traversal"


def test_blast_radius_is_row_capped():
    """Blast radius is not anchored on an indexed node, so its ceiling is a LIMIT. Without one a
    contaminated document could return the whole edge set."""
    assert "LIMIT 500" in SOURCE, "blast-radius query must stay row-capped"


# ── Conflict semantics — what may be reported as a contradiction ─────────────────
#
# `detect_conflict` fires when two edges share a `relationship_type` from different documents.
# It never compares what those edges assert, because a KNOWLEDGE_EDGE has no value property, so
# for provenance types the question is unanswerable and the answer was always "conflict". Live
# effect: 93 of 94 stored conflicts were `DOCUMENTED_BY`, i.e. "two documents describe this
# asset" — the normal state of any archive — and they buried the one real engineering conflict.

from api.services.graph import GraphService  # noqa: E402


@pytest.mark.parametrize("rel", sorted(GraphService.NON_ASSERTING_RELATIONSHIPS))
def test_provenance_edges_cannot_contradict(rel):
    """These record where knowledge came from, not what is true, so two of them never disagree."""
    assert GraphService.is_asserting_relationship(rel) is False


@pytest.mark.parametrize(
    "rel",
    ["MAX_OPERATING_PRESSURE", "Max Operating Pressure", "HAS_MATERIAL_SPEC", "ISOLATION_POINT"],
)
def test_parameter_edges_can_still_contradict(rel):
    """The other half of the guard: narrowing detection must not switch it off. A real parameter
    assertion — the HE-301 pressure limit is the live example — must still be eligible."""
    assert GraphService.is_asserting_relationship(rel) is True


def test_relationship_matching_is_case_insensitive():
    """Promotion accepts a caller-supplied `relationship_type`, so casing is not guaranteed."""
    assert GraphService.is_asserting_relationship("documented_by") is False
    assert GraphService.is_asserting_relationship("Documented_By") is False


def test_missing_relationship_type_is_treated_as_asserting():
    """Fail toward reporting. Hiding a conflict because its type was absent is the dangerous
    direction; showing one extra row is merely noise."""
    assert GraphService.is_asserting_relationship(None) is True
    assert GraphService.is_asserting_relationship("") is True


def test_detect_conflict_returns_early_for_provenance_edges():
    """Pinned on the source: the guard must sit before the Cypher, so ingesting a document does
    not pay a Neo4j round trip per edge to be told there is no conflict."""
    body = __import__("inspect").getsource(GraphService.detect_conflict)
    guard = body.index("is_asserting_relationship")
    query = body.index("MATCH (src:")
    assert guard < query, "the relationship-type guard must run before the conflict query"


def test_documented_by_is_excluded_at_read_time_too():
    """The rows already written cannot be deleted — they live in a cloud store — so the conflicts
    list has to filter them on the way out, using this same set rather than its own copy."""
    from api.routers import governance as governance_module

    src = __import__("inspect").getsource(governance_module.list_conflicts)
    assert "NON_ASSERTING_RELATIONSHIPS" in src, "read filter must reuse the shared set"
    assert ".not_.in_(" in src, "filter belongs in the query, or count/range go wrong"
