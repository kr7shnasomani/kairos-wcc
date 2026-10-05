"""Cross-functional discovery harness — the mapping that decides the result.

`FUNCTION_OF` maps `document_type` to the plant function that owns it. A type missing from it
becomes "unmapped" and belongs to NO silo, so it is invisible to every silo arm while still
reachable by the full arm — which manufactures cross-functional "discoveries" out of a mapping
oversight. The null result this harness reported is only trustworthy if the mapping is complete.

Pure constants. No stack, no secrets, no network.
"""

import sys

sys.path.insert(0, "/app/benchmark")

from run_cross_functional import FUNCTION_OF, _reached  # noqa: E402

# Every `document_type` the schema and corpus actually use. Kept here rather than read from the
# database so the test states the expectation instead of agreeing with whatever is present.
KNOWN_DOCUMENT_TYPES = {
    "procedure", "inspection_report", "oem_manual", "shift_log",
    "ptw", "regulation", "pid_drawing",
}


def test_every_known_document_type_belongs_to_a_function():
    missing = KNOWN_DOCUMENT_TYPES - set(FUNCTION_OF)
    assert not missing, (
        f"unmapped document_type(s): {sorted(missing)} — these belong to no silo, so they are "
        f"invisible to every silo arm and inflate the cross-functional count"
    )


def test_mapping_introduces_no_unknown_types():
    """A stale key is the other direction of the same error: it suggests a silo that no document
    can populate, making that function look artificially empty."""
    extra = set(FUNCTION_OF) - KNOWN_DOCUMENT_TYPES
    assert not extra, f"FUNCTION_OF has types no document uses: {sorted(extra)}"


def test_more_than_one_function_exists():
    """With a single function there is no counterfactual — every question is trivially answerable
    inside 'the' silo and the measurement is vacuous."""
    assert len(set(FUNCTION_OF.values())) >= 2


def test_reached_requires_every_term_for_must_all():
    q = {"must_all": ["XV-203", "XV-204"]}
    assert _reached("isolation via XV-203 and XV-204", q)
    assert not _reached("isolation via XV-203 only", q)


def test_reached_requires_any_term_for_answer_any():
    q = {"answer_any": ["2018", "2021"]}
    assert _reached("failures in 2021", q)
    assert not _reached("failures in 1999", q)


def test_a_question_with_no_answer_key_never_counts_as_reached():
    """Otherwise an unkeyed question scores as a hit in every arm and flattens the comparison."""
    assert not _reached("anything at all", {})
