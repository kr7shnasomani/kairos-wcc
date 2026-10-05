"""P&ID topology parsing (Layer 3, Path B) — pure logic, no network."""

from api.services.pid import PIDService


def test_parse_plain_json():
    out = PIDService._parse_json('{"equipment_nodes": [{"tag": "P-101"}]}')
    assert out is not None
    assert out["equipment_nodes"][0]["tag"] == "P-101"


def test_parse_strips_markdown_fences_and_prose():
    reply = 'Here is the topology:\n```json\n{"isolation_valves": [{"tag": "XV-203"}]}\n```\nDone.'
    out = PIDService._parse_json(reply)
    assert out is not None
    assert out["isolation_valves"][0]["tag"] == "XV-203"


def test_parse_invalid_returns_none():
    assert PIDService._parse_json("no json here at all") is None
    assert PIDService._parse_json("{broken: json,,,}") is None


def test_fit_b64_passes_small_image_through():
    # 1x1 PNG — well under the inline cap, returned unchanged.
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c6300010000050001a5f645400000000049454e44ae426082"
    )
    fitted = PIDService._fit_b64(png, "image/png")
    assert fitted is not None
    b64, mime = fitted
    assert mime == "image/png" and len(b64) > 0
