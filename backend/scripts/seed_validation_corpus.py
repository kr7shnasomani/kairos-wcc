"""
Seed the Layer-0 NER validation corpus with human-verified ground-truth entities.

Grounded in ``dataset/00_Reference/00_KAIROS_CANON.md``. This is the labeled set that
``benchmark/run_benchmark.py``'s sibling ``scripts/run_model_validation.py`` scores the NER model
against (precision / recall / F1 per entity type).

Methodology: entities are anchored to **clean-text documents** (CSV / TXT, no OCR) so the score
isolates NER quality from OCR noise, and only entities *actually present in the indexed content* are
labeled (you cannot expect NER to find what the text does not contain). Idempotent — clears prior
golden rows and re-inserts.

Run inside the API container, after documents are ingested:
  docker exec kairos-backend-api python scripts/seed_validation_corpus.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog

from api.config import settings

log = structlog.get_logger(__name__)

PROMOTED_BY = "golden_dataset"

# file_name -> [(entity_text, entity_type)] — types match the NER taxonomy (ASSET_TAG regex covers
# tag-like tokens incl. part / bulletin numbers; PERSON / ORGANIZATION from the model).
#
# EXPANDED 2026-08-15: 13 -> 40 labels. Every entry below was verified to appear in that
# document's *indexed* text before being added, so none is aspirational; the loader re-checks and
# warns on any that drift.
#
# ON "Rajgarh Petrochemical Complex", which appears in 13 of these documents and would have been
# the cheapest way to inflate ORGANIZATION: it is deliberately NOT labelled. It reads equally well
# as ORGANIZATION (the operating company) or LOCATION (the site), so labelling it either way scores
# the model wrong for a defensible answer — a false negative on one type and a false positive on
# the other. A ground truth that punishes correct behaviour is worse than a smaller one.
#
# The consequence is worth stating plainly: ORGANIZATION only reaches n=3, because the golden
# corpus genuinely contains just two unambiguous vendors (Fischer, Meridian). That type's small
# sample is a property of the dataset, not of the labelling effort, and no amount of relabelling
# fixes it — it needs new source documents naming more organisations.
GOLDEN: dict[str, list[tuple[str, str]]] = {
    "work_orders_eq101_family.csv": [
        ("EQ-101", "ASSET_TAG"), ("EQ-102", "ASSET_TAG"), ("EQ-103", "ASSET_TAG"),
        ("FSL-2240A", "ASSET_TAG"), ("FSL-2240B", "ASSET_TAG"),
    ],
    "shift_log.txt": [
        ("EQ-101", "ASSET_TAG"), ("PG-18", "ASSET_TAG"),
    ],
    "oem_bulletin_fp_sb_2025_04.pdf": [
        ("FSL-2240A", "ASSET_TAG"), ("FSL-2240B", "ASSET_TAG"), ("Fischer", "ORGANIZATION"),
    ],
    "oem_bulletin_mht_pb_2026_11.pdf": [
        ("Meridian", "ORGANIZATION"),
    ],
    # PERSON anchored to clean prose where names extract reliably (dense CSV notes-columns do not).
    "inspection_checklist.pdf": [
        ("XV-203", "ASSET_TAG"), ("Ananya Iyer", "PERSON"), ("Vikram Desai", "PERSON"),
    ],
    "oem_manual_eq1xx_seal.pdf": [
        ("EQ-101", "ASSET_TAG"), ("FSL-2240A", "ASSET_TAG"), ("Fischer", "ORGANIZATION"),
    ],
    # Sign-off blocks: two names in clean prose, plus the superseded/current part pair.
    "work_order_closeout_form.pdf": [
        ("EQ-101", "ASSET_TAG"), ("FSL-2240A", "ASSET_TAG"), ("FSL-2240B", "ASSET_TAG"),
        ("Suresh Yadav", "PERSON"), ("Ananya Iyer", "PERSON"),
    ],
    # The isolation-boundary permit — densest ASSET_TAG document in the corpus, and two signatories.
    "ptw_v247.pdf": [
        ("XV-203", "ASSET_TAG"), ("XV-204", "ASSET_TAG"), ("PG-18", "ASSET_TAG"),
        ("V-247", "ASSET_TAG"), ("Rohit Menon", "PERSON"), ("Vikram Desai", "PERSON"),
    ],
    "sop_he_gen_11.pdf": [
        ("HE-301", "ASSET_TAG"), ("HE-302", "ASSET_TAG"), ("HE-303", "ASSET_TAG"),
    ],
    "mp_he_hydrotest_03.pdf": [
        ("HE-301", "ASSET_TAG"), ("HE-302", "ASSET_TAG"), ("HE-303", "ASSET_TAG"),
    ],
    "insp_he301_2025_q4.pdf": [
        ("HE-301", "ASSET_TAG"), ("Ananya Iyer", "PERSON"),
    ],
    "insp_he302_2025_q4.pdf": [
        ("HE-302", "ASSET_TAG"),
    ],
    # Per-unit SOPs: one tag each, but they widen the document spread so the score is not
    # dominated by a handful of long documents.
    "sop_he_301_04.pdf": [("HE-301", "ASSET_TAG")],
    "sop_he_302_04.pdf": [("HE-302", "ASSET_TAG")],
    "sop_he_303_04.pdf": [("HE-303", "ASSET_TAG")],
}


async def _run() -> None:
    from elasticsearch import AsyncElasticsearch
    from supabase import create_client

    sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    es_kwargs: dict = {"hosts": [settings.ELASTICSEARCH_URL]}
    if settings.ELASTICSEARCH_USERNAME:
        es_kwargs["basic_auth"] = (settings.ELASTICSEARCH_USERNAME, settings.ELASTICSEARCH_PASSWORD)
    es = AsyncElasticsearch(**es_kwargs)

    # idempotent reset
    sb.table("validation_corpus").delete().eq("promoted_by", PROMOTED_BY).execute()

    async def content_for(document_id: str) -> str:
        resp = await es.search(
            index=settings.ELASTICSEARCH_INDEX_DOCUMENTS,
            body={"query": {"term": {"document_id": document_id}}, "_source": ["content"], "size": 1},
        )
        hits = resp["hits"]["hits"]
        return (hits[0]["_source"].get("content") or "") if hits else ""

    rows: list[dict] = []
    try:
        for file_name, entities in GOLDEN.items():
            res = sb.table("documents").select("document_id").eq("file_name", file_name).limit(1).execute()
            if not res.data:
                log.warning("valcorpus.doc_missing", file=file_name)
                continue
            document_id = res.data[0]["document_id"]
            content = (await content_for(document_id)).lower()
            for text, etype in entities:
                if text.lower() not in content:
                    log.warning("valcorpus.entity_absent", file=file_name, entity=text)
                    continue
                rows.append({
                    "document_id": document_id, "entity_text": text, "entity_type": etype,
                    "authority": "human_promotion", "promoted_by": PROMOTED_BY,
                })
        if rows:
            sb.table("validation_corpus").insert(rows).execute()
    finally:
        await es.close()

    by_type: dict[str, int] = {}
    for r in rows:
        by_type[r["entity_type"]] = by_type.get(r["entity_type"], 0) + 1
    log.info("valcorpus.seeded", total=len(rows), by_type=by_type)


if __name__ == "__main__":
    asyncio.run(_run())
