"""Acknowledgment signing + delivery ordering (routers/briefs.py).

Pure logic — no clients. The signature is the audit evidence for a PTW dual sign-off, so the
properties that matter are that it is deterministic, and that it actually binds every fact it
claims to bind (brief, user, action, time).
"""

from api.routers.briefs import _sign_acknowledgment

_ARGS = ("secret", "b-1", "user-a", "acknowledged", "2026-08-17T05:00:00+00:00")


def test_signature_is_deterministic():
    assert _sign_acknowledgment(*_ARGS) == _sign_acknowledgment(*_ARGS)


def test_signature_binds_each_field():
    """
    Change any one fact and the signature must change. If it did not, a signature captured on
    one brief could be replayed onto another — which is the forgery the signing exists to stop.
    """
    base = _sign_acknowledgment(*_ARGS)
    variants = [
        ("secret", "b-2", "user-a", "acknowledged", _ARGS[4]),          # different brief
        ("secret", "b-1", "user-b", "acknowledged", _ARGS[4]),          # different signer
        ("secret", "b-1", "user-a", "countersigned", _ARGS[4]),         # ack vs countersign
        ("secret", "b-1", "user-a", "acknowledged", "2026-08-17T06:00:00+00:00"),  # different time
        ("other-secret", "b-1", "user-a", "acknowledged", _ARGS[4]),    # different key
    ]
    for v in variants:
        assert _sign_acknowledgment(*v) != base, v


def test_ack_and_countersign_differ_for_same_user_and_time():
    """The two signatures in a dual sign-off must never collide into one value."""
    ack = _sign_acknowledgment("s", "b-1", "u", "acknowledged", _ARGS[4])
    counter = _sign_acknowledgment("s", "b-1", "u", "countersigned", _ARGS[4])
    assert ack != counter


# =============================================================================
# Brief source citations — operator-facing provenance, not graph internals
# =============================================================================

from api.services.brief_engine import _resolve_source_documents, _sources_from_graph  # noqa: E402


def _edge(doc_id="DOC-1", rel="DOCUMENTED_BY", auth=4, verified=False):
    return {"edge": {
        "document_id": doc_id,
        "relationship_type": rel,
        "authority_level": auth,
        "verification_status": "verified" if verified else "unverified",
    }}


def test_relationship_type_is_humanised_not_raw():
    """`relevant_excerpt` used to be the raw edge type ("DOCUMENTED_BY")."""
    s = _sources_from_graph([_edge()])[0]
    assert "DOCUMENTED_BY" not in s.relevant_excerpt
    assert "document link" in s.relevant_excerpt


def test_unverified_link_is_disclosed_in_the_excerpt():
    assert "not yet engineer-verified" in _sources_from_graph([_edge(verified=False)])[0].relevant_excerpt
    assert "not yet engineer-verified" not in _sources_from_graph([_edge(verified=True)])[0].relevant_excerpt


def test_a_vault_document_is_not_badged_as_quarantine():
    """Regression: `is_quarantine` was set from `verification_status != "verified"`. Every edge
    starts unverified by design, so every source — including authority-4 permits — was badged as
    an unverified field observation, and the badge stopped discriminating anything."""
    assert _sources_from_graph([_edge(auth=4, verified=False)])[0].is_quarantine is False


class _DocQuery:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def in_(self, *_a):
        return self

    def execute(self):
        class _R:
            pass

        r = _R()
        r.data = self._rows
        return r


class _DocSupabase:
    def __init__(self, rows):
        self._rows = rows

    def table(self, _name):
        return _DocQuery(self._rows)


async def test_source_gets_a_real_title_and_vault_link():
    """An operator saw `title: "DOC-CPLLSP2QYWUN"` and `vault_url: null` — an opaque id with no
    way to open the document from a point-of-action surface."""
    sb = _DocSupabase([{
        "document_id": "DOC-1", "file_name": "ptw_v247.pdf",
        "document_type": "ptw", "vault_url": "https://vault/ptw_v247.pdf",
    }])
    s = (await _resolve_source_documents(sb, _sources_from_graph([_edge()])))[0]

    assert s.title == "ptw_v247.pdf"
    assert s.document_type == "ptw"
    assert s.vault_url == "https://vault/ptw_v247.pdf"


async def test_lookup_failure_keeps_the_citation():
    """A brief with a terse id still beats a brief with no provenance."""
    class _Broken:
        def table(self, _n):
            raise RuntimeError("supabase down")

    s = (await _resolve_source_documents(_Broken(), _sources_from_graph([_edge()])))[0]
    assert s.document_id == "DOC-1"
