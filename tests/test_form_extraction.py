"""Form / checklist extraction — Layer 3 → Layer 6.

The load-bearing property is the **destination**: parsed form fields go to quarantine and never
to the canonical graph. A ticked checkbox carries no authority a KNOWLEDGE_EDGE could honestly
record, and "a handwritten checkbox promoted to canonical fact" is the exact failure Layer 6
exists to prevent.

Pure logic. No stack, no secrets, no network.
"""

import inspect

from api.services.forms import parse_form_fields, quarantine_items_for

FORM = """
Inspection Checklist — HE-301
Inspector: R. Mehta
Date: 2026-06-12
Pressure tested: 16.2 bar
[x] Shell-side isolation verified
[ ] Tube bundle removed
(✓) Gaskets replaced
Page 1 of 2
Notes: see attached photographs for the corroded section near the inlet nozzle
"""


# =============================================================================
# The destination — the part that matters
# =============================================================================

def test_every_field_goes_to_quarantine_as_field_input():
    rows = quarantine_items_for("DOC-1", parse_form_fields(FORM))
    assert rows, "expected parsed fields"
    assert all(r["input_type"] == "field_observation" for r in rows)


def test_nothing_in_this_module_writes_a_knowledge_edge():
    """The one-way gate only holds if the parser cannot bypass it."""
    import ast

    from api.services import forms

    # AST, not a substring search: the module's prose explains *why* a form field gets no
    # authority level and cannot write a KNOWLEDGE_EDGE, so searching the raw source matches the
    # explanation instead of the behaviour. Unparsing a docstring-stripped tree leaves only code.
    tree = ast.parse(inspect.getsource(forms))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(
                getattr(body[0], "value", None), ast.Constant
            ) and isinstance(body[0].value.value, str):
                body.pop(0)
    code = ast.unparse(tree)

    assert "KNOWLEDGE_EDGE" not in code
    assert "create_knowledge_edge" not in code
    assert "authority_level" not in code, "a form field has no authority level to assign"
    assert "merge_" not in code, "nothing here may MERGE a graph node"


def test_each_item_states_its_own_ceiling_to_the_reviewer():
    """A reviewer promoting an item must not have to read the module docstring to learn it is
    unverified field input."""
    rows = quarantine_items_for("DOC-1", parse_form_fields(FORM))
    note = rows[0]["session_context"]["note"]
    assert "Unverified field input" in note
    assert "no authority" in note


def test_unresolvable_asset_is_none_never_empty_string():
    """`quarantine_items.asset_id` is a FK: "" fails the constraint, None is correct."""
    rows = quarantine_items_for("DOC-1", parse_form_fields(FORM), asset_id="")
    assert rows[0]["asset_id"] is None


# =============================================================================
# Parsing
# =============================================================================

def test_labelled_fields_are_extracted():
    fields = {f["label"]: f["value"] for f in parse_form_fields(FORM) if f["kind"] == "field"}
    assert fields["Inspector"] == "R. Mehta"
    assert fields["Pressure tested"] == "16.2 bar"


def test_checkbox_state_is_captured_both_ways():
    boxes = {f["label"]: f["value"] for f in parse_form_fields(FORM) if f["kind"] == "checkbox"}
    assert boxes["Shell-side isolation verified"] is True
    assert boxes["Tube bundle removed"] is False
    assert boxes["Gaskets replaced"] is True


def test_structural_lines_are_not_mistaken_for_fields():
    labels = [f["label"] for f in parse_form_fields(FORM)]
    assert not any(l.lower().startswith("page") for l in labels)


def test_prose_containing_a_colon_is_not_a_field():
    """A sentence is not a form field. Treating it as one fills the review queue with noise,
    which trains reviewers to bulk-approve — the worst outcome for a one-way gate."""
    labels = [f["label"] for f in parse_form_fields(FORM)]
    assert "Notes" not in labels


def test_empty_input_is_handled():
    assert parse_form_fields("") == []
    assert parse_form_fields("   \n  \n") == []
    assert quarantine_items_for("DOC-1", []) == []
