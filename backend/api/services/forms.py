"""
Form and checklist field extraction — Layer 3 → Layer 6.

THE DESTINATION IS THE HARD PART, AND IT IS ALREADY DECIDED
  Pulling `label: value` out of a scanned checklist is the easy half. The question that kept this
  unbuilt was where a field→value pair is allowed to go, and the architecture answers it: a form
  field is **unverified field input**, so it goes to **quarantine**, never to the canonical graph.

  Nothing here writes a `KNOWLEDGE_EDGE`. That is not caution for its own sake — a ticked checkbox
  carries no authority level that would honestly describe it. There is no source to cite, no
  engineer who signed it, and no way to tell a deliberate tick from a stray pen mark. "A
  handwritten checkbox promoted to canonical fact" is the exact failure Layer 6 exists to prevent,
  and the one-way gate with human-only promotion is the mechanism for it.

  So the ceiling is deliberate: this makes form content *reviewable*, not *authoritative*.

WHY `field_observation` AND NOT A NEW `input_type`
  `quarantine_items.input_type` is a CHECK constraint, and adding a value means DROP + re-add
  (a documented pitfall). A form field IS a field observation, so the existing value is honest and
  no migration is needed. The form provenance lives in `session_context` instead.

ponytail: deterministic `label: value` and checkbox parsing, no model call. It handles typed and
OCR'd forms, which is what the corpus has. True layout-aware parsing (cell geometry, multi-column
tables, ruled boxes) needs a vision model and is the upgrade path — add it when a real form defeats
this, not before.
"""

import re
from typing import Any

# "Pressure tested:  16.2 bar" / "Inspector - R. Mehta". Value must be non-empty.
#
# The separator is a colon, or a hyphen/dash **surrounded by whitespace**. An unspaced hyphen is
# NOT a separator: asset tags are hyphenated (`XV-203`, `EQ-101`, `FSL-2240A`) and treating them
# as fields turned every tag in a real checklist into a junk row — label "XV", value "203".
# Observed on `inspection_checklist.pdf` and `work_order_closeout_form.pdf`, which is exactly the
# review-queue noise that trains reviewers to bulk-approve a one-way gate.
#
# The label is bounded to 60 chars so a wrapped prose sentence containing a colon does not
# register as a field — a sentence is not a form field.
_FIELD_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 ._/()#-]{1,59}?)\s*(?::|\s[-—]\s)\s*(\S.*?)\s*$")

# Ticked: [x] [X] [✓] (•) . Unticked: [] [ ] ( ).
_CHECKED_RE = re.compile(r"^\s*[\[(]\s*([xX✓✔])\s*[\])]\s*(.+?)\s*$")
_UNCHECKED_RE = re.compile(r"^\s*[\[(]\s{0,3}[\])]\s*(.+?)\s*$")

# Lines that look like fields but are structure, not content.
_NOISE_PREFIXES = ("page ", "figure ", "table ", "note:", "notes:", "http://", "https://")


def parse_form_fields(text: str) -> list[dict[str, Any]]:
    """Field→value pairs and checkbox states from a form's extracted text.

    Returns dicts of `{label, value, kind}` where `kind` is `field` or `checkbox`. Order is
    preserved so a reviewer sees the form in reading order rather than an arbitrary map order.
    """
    if not text:
        return []

    out: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith(_NOISE_PREFIXES):
            continue

        m = _CHECKED_RE.match(line)
        if m:
            out.append({"label": m.group(2).strip(), "value": True, "kind": "checkbox"})
            continue

        m = _UNCHECKED_RE.match(line)
        if m:
            out.append({"label": m.group(1).strip(), "value": False, "kind": "checkbox"})
            continue

        m = _FIELD_RE.match(line)
        if m:
            label, value = m.group(1).strip(), m.group(2).strip()
            # A "value" that is itself a sentence is prose that happened to contain a colon.
            if len(value) <= 120:
                out.append({"label": label, "value": value, "kind": "field"})
    return out


def quarantine_items_for(
    document_id: str,
    fields: list[dict[str, Any]],
    *,
    asset_id: str | None = None,
    submitted_by: str = "extraction_pipeline",
) -> list[dict[str, Any]]:
    """Quarantine rows for parsed form fields — the ONLY destination they are allowed.

    `asset_id` is passed through unvalidated on purpose: `quarantine_items.asset_id` is a FK, and
    an unresolvable tag must arrive as `None` rather than `""` (a documented FK-failure pitfall).
    Linking the item to an asset is part of human review, not of parsing.
    """
    rows = []
    for f in fields:
        value = f["value"]
        shown = ("checked" if value else "not checked") if f["kind"] == "checkbox" else value
        rows.append({
            "asset_id": asset_id or None,
            "content": f"{f['label']}: {shown}",
            # An existing enum value that is honest — a form field is field input. See module docstring.
            "input_type": "field_observation",
            "submitted_by": submitted_by,
            "session_context": {
                "source": "form_extraction",
                "document_id": document_id,
                "field_label": f["label"],
                "field_value": value,
                "field_kind": f["kind"],
                # States the ceiling on the item itself, so a reviewer promoting it is not relying
                # on the module docstring to know what they are looking at.
                "note": (
                    "Parsed from a form/checklist. Unverified field input: no authority level, "
                    "no signer. Promote only after checking the value against the source document."
                ),
            },
        })
    return rows
