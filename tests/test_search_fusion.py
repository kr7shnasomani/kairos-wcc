"""Retrieval fusion — RRF + representative merge (services/search_service.py).

Pure logic: _fuse/_better/_edge_snippet take plain lists, no services required.
"""

from api.models.document import SearchResult
from api.services.search_service import SearchService

svc = SearchService.__new__(SearchService)  # logic-only; no clients needed


def _r(doc_id, authority=4, score=0.0, method="exact", snippet="", title=""):
    return SearchResult(
        document_id=doc_id,
        document_type="procedure",
        title=title,
        snippet=snippet,
        authority_level=authority,
        status="active",
        relevance_score=score,
        retrieval_method=method,
    )


def test_bm25_scale_does_not_beat_cosine():
    """
    An ES hit with a huge BM25 score must not outrank a Qdrant hit at the same authority
    just because BM25 is unbounded. Both are rank 1 in their own source, so the document
    both sources agree on wins.
    """
    es = [_r("DOC-ONLY-ES", score=98.6, method="exact"), _r("DOC-BOTH", score=12.0, method="exact")]
    vec = [_r("DOC-BOTH", score=0.91, method="semantic"), _r("DOC-ONLY-VEC", score=0.88, method="semantic")]

    out = svc._fuse([es, vec], limit=10)
    assert out[0].document_id == "DOC-BOTH", [r.document_id for r in out]
    # Appearing in two sources is recorded, not hidden.
    assert "+" in out[0].retrieval_method


def test_authority_still_outranks_relevance():
    """Authority-first is a deliberate safety property — RRF only orders within a level."""
    low_authority_strong = [_r("DOC-FIELD", authority=5, method="semantic")]
    high_authority_weak = [_r("DOC-REG", authority=1, method="exact")]
    out = svc._fuse([low_authority_strong, high_authority_weak], limit=10)
    assert [r.document_id for r in out] == ["DOC-REG", "DOC-FIELD"]


def test_merge_keeps_the_longest_snippet():
    """
    Collapsing duplicates must not discard the losing record's text: the semantic chunk
    often holds the fact while the exact hit holds only a short excerpt.
    """
    short = [_r("DOC-1", authority=3, snippet="MAWP table.", method="exact")]
    long = [_r("DOC-1", authority=4, snippet="MAWP for HE-301 is 24 bar per OEM spec.", method="semantic")]
    out = svc._fuse([short, long], limit=10)
    assert len(out) == 1
    assert out[0].authority_level == 3, "most authoritative record wins"
    assert "24 bar" in out[0].snippet, "richer snippet must survive the merge"


def test_documents_without_ids_are_dropped():
    out = svc._fuse([[_r("")]], limit=10)
    assert out == []


def test_graph_edge_renders_readable_snippet():
    """A graph hit must carry text, or synthesis sees an empty source."""
    hits = [
        {
            "edge": {
                "document_id": "OEM-1",
                "relationship_type": "DOCUMENTED_BY",
                "authority_level": 3,
                "confidence": 0.92,
                "valid_from": "2025-01-01T00:00:00+00:00",
                "verification_status": "verified",
            },
            "target": {"title": "EQ-101 seal manual", "document_id": "OEM-1"},
        }
    ]
    out = svc._normalize_graph(hits, "EQ-101")
    assert len(out) == 1
    snippet = out[0].snippet
    assert snippet, "graph snippet must not be empty"
    assert "EQ-101" in snippet and "EQ-101 seal manual" in snippet
    assert out[0].is_quarantine is False


def test_unverified_graph_edge_is_flagged_quarantine():
    hits = [{"edge": {"document_id": "QN-1", "verification_status": "unverified"}, "target": {}}]
    out = svc._normalize_graph(hits, "EQ-101")
    assert out[0].is_quarantine is True
