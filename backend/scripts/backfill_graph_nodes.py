"""
Backfill Layer 4 node types onto the existing corpus.

All six designed node types write correctly, but only forward: `Event` has been written by the
six event routes and `Person` / `Organisation` by the extraction path only since 2026-08-17.
Anything ingested before that exists in Supabase and nowhere in the graph, so a traversal cannot
reach it. The write path is closed; this closes the data gap behind it.

Two halves, deliberately separable because they cost wildly different amounts:

  --events    `operational_events` -> `Event` + `OCCURRED_ON`. Pure data movement, **no model
              calls**, safe to re-run. This is the half worth doing unconditionally.
  --entities  Re-extract `PERSON` / `ORGANIZATION` from document text. Costs ~1 NIM call per
              document and is subject to the same rate limits that repeatedly killed the model
              gate, so it is opt-in and paced.

Dry-run by default: prints the gap and writes nothing. Pass --apply to write.

    python scripts/backfill_graph_nodes.py                    # report the gap
    python scripts/backfill_graph_nodes.py --events --apply   # cheap half
    python scripts/backfill_graph_nodes.py --entities --apply # model calls

Idempotent: every write is a MERGE, so re-running converges rather than duplicating.
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime

sys.path.insert(0, "/app")

import structlog
from neo4j import AsyncGraphDatabase
from supabase import create_client

from api.config import Settings

log = structlog.get_logger(__name__)

# Paces the model-call half. The gate's corpus loop fired calls back to back and NVIDIA's shared
# endpoint answered with 429s until almost nothing reached the model — the same failure would make
# a backfill silently write regex output. One document at a time, with a gap between.
_ENTITY_CALL_DELAY_S = 1.5
_MIN_CONFIDENCE = 0.7  # Layer 6: below this a mention is a candidate, not a fact


async def _event_gap(supabase, driver) -> tuple[list[dict], int]:
    """Events in Supabase that have no `Event` node in the graph."""
    rows = await asyncio.to_thread(
        lambda: supabase.table("operational_events")
        .select("event_id, event_type, occurred_at, asset_id, event_subtype, source_system")
        .execute()
    )
    events = rows.data or []
    if not events:
        return [], 0

    async with driver.session() as session:
        result = await session.run("MATCH (e:Event) RETURN collect(e.event_id) AS ids")
        record = await result.single()
        present = set(record["ids"] or []) if record else set()

    missing = [e for e in events if e["event_id"] not in present]
    return missing, len(events)


async def _backfill_events(supabase, driver, apply: bool) -> None:
    from api.services.graph import GraphService

    missing, total = await _event_gap(supabase, driver)
    print(f"\nEvents: {total} in Supabase, {len(missing)} missing from the graph")
    if not missing:
        print("  nothing to do")
        return
    if not apply:
        for e in missing[:10]:
            print(f"    would write {e['event_id']}  {e['event_type']}  asset={e['asset_id']}")
        if len(missing) > 10:
            print(f"    ... and {len(missing) - 10} more")
        return

    graph = GraphService(driver)
    written = 0
    for e in missing:
        await graph.merge_event_node(
            event_id=e["event_id"],
            event_type=e["event_type"],
            occurred_at=e["occurred_at"],
            asset_id=e.get("asset_id"),
            props={
                "event_subtype": e.get("event_subtype"),
                "source_system": e.get("source_system"),
                "backfilled": True,
            },
        )
        written += 1
    print(f"  wrote {written} Event nodes")


async def _entity_gap(supabase, driver, force: bool = False) -> tuple[list[dict], int]:
    """Documents still needing a Person/Organisation extraction pass.

    Absence of an edge is NOT sufficient on its own: a document that genuinely mentions nobody
    never acquires one, so it is indistinguishable from one never processed and was re-extracted
    on every run. Measured cost of that: run 2 spent 102 NIM calls to gain 4 nodes.

    So a document is also skipped once it carries `entity_backfill_at`, stamped when an extraction
    **reached the model**. A run that fell through to the regex path is deliberately NOT stamped —
    regex cannot emit `PERSON` or `ORGANIZATION` at all, so marking it would bake in a miss that
    only looks like an absence of people.
    """
    rows = await asyncio.to_thread(
        lambda: supabase.table("documents").select("document_id, document_type").execute()
    )
    docs = rows.data or []
    if not docs:
        return [], 0

    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (d:Document)-[r:KNOWLEDGE_EDGE]->(n)
            WHERE n:Person OR n:Organisation
            RETURN collect(DISTINCT d.document_id) AS ids
            """
        )
        record = await result.single()
        covered = set(record["ids"] or []) if record else set()

        attempted: set[str] = set()
        if not force:
            result = await session.run(
                "MATCH (d:Document) WHERE d.entity_backfill_at IS NOT NULL "
                "RETURN collect(d.document_id) AS ids"
            )
            record = await result.single()
            attempted = set(record["ids"] or []) if record else set()

    return [d for d in docs if d["document_id"] not in covered and d["document_id"] not in attempted], len(docs)


async def _partition_by_text(settings, docs: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split candidate documents into those with indexed text and those without.

    Document text lives in Elasticsearch, not in `documents`. A doc missing from the index cannot
    be extracted at all, and treating that as "pending" is what makes a gap look stuck.
    """
    from elasticsearch import AsyncElasticsearch

    es_kwargs: dict = {"hosts": [settings.ELASTICSEARCH_URL]}
    if settings.ELASTICSEARCH_USERNAME:
        es_kwargs["basic_auth"] = (settings.ELASTICSEARCH_USERNAME, settings.ELASTICSEARCH_PASSWORD)
    es = AsyncElasticsearch(**es_kwargs)
    have, lack = [], []
    try:
        for doc in docs:
            try:
                resp = await es.search(
                    index=settings.ELASTICSEARCH_INDEX_DOCUMENTS,
                    body={"query": {"term": {"document_id": doc["document_id"]}},
                          "_source": ["content", "text"], "size": 1},
                )
                hits = resp["hits"]["hits"]
                src = hits[0]["_source"] if hits else {}
                text = src.get("content") or src.get("text") or ""
            except Exception:  # noqa: BLE001 — an unreachable index is not a per-document verdict
                text = ""
            (have if text.strip() else lack).append(doc)
    finally:
        await es.close()
    return have, lack


async def _backfill_entities(supabase, driver, settings, apply: bool, force: bool = False) -> None:
    missing, total = await _entity_gap(supabase, driver, force=force)

    # A document with no indexed text can never be extracted, so counting it in the same number
    # as "not yet done" produces a gap that never closes and a run that reports 0 extractions
    # while still claiming work remains. Observed 2026-08-23: 14 of 14 remaining were unindexed.
    # They are NOT marked `entity_backfill_at` — re-indexing must make them eligible again — but
    # they are reported separately so nobody chases a number that cannot move.
    extractable, no_text = await _partition_by_text(settings, missing)

    print(f"\nPerson/Organisation: {total} documents, {len(missing)} with no such edge")
    if no_text:
        print(f"  {len(no_text)} of those have NO text in Elasticsearch — an indexing gap, not an")
        print("  extraction gap. Re-ingest or re-index them; this script cannot help.")
    missing = extractable
    print("  Counts documents with no Person/Organisation edge AND no `entity_backfill_at` marker.")
    print("  The marker is what stops a document that genuinely mentions nobody from being")
    print("  re-extracted forever; --force ignores it after an NER model change.")
    if not missing:
        print("  nothing to do")
        return
    if not apply:
        # Wall clock is dominated by NIM latency, not by the pacing delay. Measured NER calls in
        # the model gate ran ~20-50 s each, with 60 s timeouts when the shared endpoint is busy —
        # so quote the call cost, not the sleep, or the estimate is off by an order of magnitude.
        lo = len(missing) * (20 + _ENTITY_CALL_DELAY_S) / 60
        hi = len(missing) * (60 + _ENTITY_CALL_DELAY_S) / 60
        print(f"  would re-extract {len(missing)} documents (~{len(missing)} NIM calls)")
        print(f"  estimated wall clock {lo:.0f}-{hi:.0f} min at the 20-60 s/call observed in the gate")
        return

    from api.services.graph import GraphService
    from api.services.ner import FallbackCountingNER, NERService

    ner = FallbackCountingNER(NERService())
    graph = GraphService(driver)
    es_docs = 0
    nodes = 0

    # Document text lives in Elasticsearch, not in `documents` — that table holds provenance
    # (hash, vault_url, authority) and the body is indexed separately. Same source the model
    # gate reads, so a document invisible to the gate is invisible here too.
    from elasticsearch import AsyncElasticsearch

    es_kwargs: dict = {"hosts": [settings.ELASTICSEARCH_URL]}
    if settings.ELASTICSEARCH_USERNAME:
        es_kwargs["basic_auth"] = (settings.ELASTICSEARCH_USERNAME, settings.ELASTICSEARCH_PASSWORD)
    es = AsyncElasticsearch(**es_kwargs)

    for doc in missing:
        try:
            resp = await es.search(
                index=settings.ELASTICSEARCH_INDEX_DOCUMENTS,
                body={
                    "query": {"term": {"document_id": doc["document_id"]}},
                    "_source": ["content", "text"],
                    "size": 1,
                },
            )
            hits = resp["hits"]["hits"]
            src = hits[0]["_source"] if hits else {}
            text = src.get("content") or src.get("text") or ""
        except Exception as exc:  # noqa: BLE001 — one unindexed document must not abort the run
            log.warning("backfill.doc_fetch_failed", document_id=doc["document_id"], error=str(exc))
            continue
        if not text.strip():
            continue

        result = await ner.extract_entities(text)
        es_docs += 1
        # Only a model-backed pass counts as attempted. `model` self-reports the path taken.
        reached_model = (result or {}).get("model") in ("nim", "ollama")
        if reached_model:
            async with driver.session() as session:
                await session.run(
                    "MERGE (d:Document {document_id: $doc}) SET d.entity_backfill_at = $ts",
                    doc=doc["document_id"], ts=datetime.now(UTC).isoformat(),
                )
        for entity in (result or {}).get("entities", []):
            etype = (entity.get("entity_type") or "").upper()
            if etype not in ("PERSON", "ORGANIZATION"):
                continue
            name = (entity.get("text") or "").strip()
            if not name or entity.get("confidence", 0.0) < _MIN_CONFIDENCE:
                continue
            node_id = graph.entity_node_id(etype, name)
            if etype == "PERSON":
                await graph.merge_person_node(node_id, {"name": name, "source": "backfill"})
            else:
                await graph.merge_organisation_node(node_id, {"name": name, "source": "backfill"})
            nodes += 1
        await asyncio.sleep(_ENTITY_CALL_DELAY_S)

    # A backfill that silently ran on the regex fallback would write ASSET_TAG-shaped noise and
    # no Person/Organisation at all, while reporting success. Say which path produced this.
    await es.close()
    print(f"  extracted {es_docs} documents, merged {nodes} Person/Organisation nodes")
    print(f"  extraction paths: {dict(ner.paths)} — validity {ner.validity}")
    if ner.validity != "VALID":
        print("  WARNING: some extractions never reached the model. Re-run the affected documents;")
        print("  the regex fallback cannot produce PERSON or ORGANIZATION at all.")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", action="store_true", help="backfill Event nodes (no model calls)")
    parser.add_argument("--entities", action="store_true", help="backfill Person/Organisation (model calls)")
    parser.add_argument("--apply", action="store_true", help="write; otherwise report the gap only")
    parser.add_argument("--force", action="store_true",
                        help="re-extract documents already marked `entity_backfill_at` (use after "
                             "an NER model change, when a prior pass no longer represents the model)")
    args = parser.parse_args()

    both = not args.events and not args.entities
    settings = Settings()
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD)
    )
    try:
        print("DRY RUN — nothing will be written. Pass --apply to write." if not args.apply
              else "APPLYING — writes are MERGEs and safe to re-run.")
        if args.events or both:
            await _backfill_events(supabase, driver, args.apply)
        if args.entities or both:
            await _backfill_entities(supabase, driver, settings, args.apply, force=args.force)
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
