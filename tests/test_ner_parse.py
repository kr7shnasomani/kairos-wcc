"""
NER response parsing — truncation recovery (Layer 3).

Service-free: `_parse_response` and `_salvage_objects` are pure string→dict logic, so these run
with no stack, no secrets and no network, and belong to CI's tier-1 `unit` job.

Why this file exists: `max_tokens` is 1024, so an entity-dense document runs out of budget
mid-array. `json.loads` rejected the whole response and the document fell through to the regex
last resort, which matches ASSET_TAG only — so PERSON and ORGANIZATION silently disappeared from
that document. Measured 2026-08-16: 1 of 15 corpus documents, and the reason the Layer-0 F1 stayed
flagged SUSPECT after the timeout cause was fixed.
"""

import json

import pytest

from api.services.ner import NERService


@pytest.fixture
def ner() -> NERService:
    return NERService()


def _payload(n: int) -> str:
    return json.dumps(
        [{"text": f"EQ-{100 + i}", "entity_type": "ASSET_TAG", "confidence": 0.9} for i in range(n)]
    )


def test_well_formed_response_is_not_flagged_recovered(ner):
    out = ner._parse_response(_payload(3), source="nim")
    assert out["total_entities"] == 3
    assert out["parse_recovered"] is False


def test_markdown_fenced_response_still_parses(ner):
    out = ner._parse_response(f"```json\n{_payload(2)}\n```", source="nim")
    assert out["total_entities"] == 2
    assert out["parse_recovered"] is False


def test_truncated_array_keeps_the_complete_objects(ner):
    """The real failure: the response stops part-way through the last object."""
    truncated = _payload(4)[:-30]            # cut mid-object, no closing bracket
    out = ner._parse_response(truncated, source="nim")
    assert out is not None, "a truncated response must not discard the whole extraction"
    assert out["total_entities"] >= 3
    assert out["parse_recovered"] is True
    assert out["model"] == "nim", "the model did produce these — the path is still nim, not regex"


def test_trailing_prose_after_the_array_is_tolerated(ner):
    out = ner._parse_response(_payload(2) + "\n\nNote: only two tags were found.", source="nim")
    assert out["total_entities"] == 2
    assert out["parse_recovered"] is True


def test_entity_text_containing_braces_does_not_break_the_scanner(ner):
    payload = json.dumps([{"text": '{"nested"} EQ-101', "entity_type": "ASSET_TAG", "confidence": 0.9}])
    out = ner._parse_response(payload[:-1], source="nim")   # truncate the closing bracket
    assert out is not None
    assert out["total_entities"] == 1
    assert out["entities"][0]["text"] == '{"nested"} EQ-101'


def test_unrecoverable_garbage_still_returns_none(ner):
    """Salvage must not invent a result — a genuine failure still has to fail."""
    assert ner._parse_response("not json at all, no objects here", source="nim") is None


def test_non_list_json_is_rejected(ner):
    assert ner._parse_response('{"text": "EQ-101"}', source="nim") is None


def test_salvage_skips_objects_missing_required_keys(ner):
    payload = '[{"text": "EQ-101", "entity_type": "ASSET_TAG"}, {"confidence": 0.4}, '
    out = ner._parse_response(payload, source="nim")
    assert out["total_entities"] == 1
    assert out["parse_recovered"] is True
