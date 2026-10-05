"""PII detection + redaction — DPDP export boundary (services/pii.py).

Pure logic, no services required.
"""

from api.services.pii import PIIService

svc = PIIService()


def test_redacts_structured_identifiers():
    text = (
        "Inspector contact: ravi.kumar@refinery.co.in / +91 9876543210. "
        "Employee EMP-4471, shift SH-2205, Aadhaar 1234 5678 9012, PAN ABCDE1234F."
    )
    out = svc.redact(text)
    assert out["pii_found"]
    red = out["redacted_text"]
    for leaked in ("ravi.kumar@refinery.co.in", "9876543210", "EMP-4471", "SH-2205", "1234 5678 9012", "ABCDE1234F"):
        assert leaked not in red, f"{leaked} survived redaction"
    assert set(out["counts"]) == {"EMAIL", "PHONE", "EMPLOYEE_ID", "SHIFT_ID", "AADHAAR", "PAN"}


def test_person_names_masked_with_stable_pseudonym():
    text = "Ravi Kumar signed the closeout. Ravi Kumar also witnessed the hydrotest."
    out = svc.redact(text, person_names=["Ravi Kumar"])
    assert "Ravi Kumar" not in out["redacted_text"]
    # Same person -> same alias, so cross-references in the text survive.
    assert out["redacted_text"].count("[PERSON_1]") == 2


def test_equipment_tags_and_part_numbers_are_not_pii():
    """The redaction pass must not damage operational content."""
    text = "Pump EQ-101 seal replaced with P/N MS-4471-B per OISD-117 clause 4.1.1. Valve XV-203 isolated."
    out = svc.redact(text)
    assert out["redacted_text"] == text
    assert not out["pii_found"]


def test_clean_text_is_returned_unchanged():
    text = "Heat exchanger HE-301 inspected, no findings."
    out = svc.redact(text)
    assert out == {"redacted_text": text, "spans": [], "counts": {}, "pii_found": False}


def test_spans_reference_original_offsets():
    text = "Reach me at ops@plant.in today."
    out = svc.redact(text)
    span = out["spans"][0]
    assert text[span["start"] : span["end"]] == "ops@plant.in"
