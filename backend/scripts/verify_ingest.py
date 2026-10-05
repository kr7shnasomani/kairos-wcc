"""Verify one ingested document reached every store. Read-only — writes nothing.

Run after each demo ingest. A pipeline that reports `complete` can still have
lost a single indexing activity (observed 2026-08-24: DOC-D47USJNBJD73 finished
100% with no error but never reached Elasticsearch), and the only way to tell is
to ask each store directly.

    docker exec kairos-backend-api python /app/scripts/verify_ingest.py DOC-XXXX

Exits non-zero if any store is missing the document.
"""

import asyncio
import os
import sys

import structlog

log = structlog.get_logger()


async def check_supabase(document_id: str) -> tuple[bool, str]:
    from supabase import create_client

    from api.config import get_settings

    settings = get_settings()
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

    docs = await asyncio.to_thread(
        lambda: client.table("documents").select("*").eq("document_id", document_id).execute()
    )
    if not docs.data:
        return False, "no documents row"
    row = docs.data[0]

    jobs = await asyncio.to_thread(
        lambda: client.table("extraction_jobs").select("*").eq("document_id", document_id).execute()
    )
    if not jobs.data:
        return False, "vault row present but no extraction_jobs row"
    job = jobs.data[0]
    detail = (
        f"{row['file_name']} · stage={job['pipeline_stage']} {job['progress_pct']}% "
        f"· ocr={job['ocr_confidence']} · entities={job['entity_count']} · edges={job['graph_edges']}"
    )
    if job["error"]:
        return False, f"{detail} · error={job['error']}"
    return job["pipeline_stage"] == "complete", detail


async def check_neo4j(document_id: str) -> tuple[bool, str]:
    from neo4j import AsyncGraphDatabase

    driver = AsyncGraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
    )
    try:
        result = await driver.execute_query(
            """
            MATCH (a)-[r:KNOWLEDGE_EDGE]-(b)
            WHERE r.document_id = $did
            RETURN count(r) AS edges,
                   collect(DISTINCT coalesce(a.asset_id, b.asset_id))[0..5] AS assets
            """,
            did=document_id,
        )
        record = result.records[0]
        edges = record["edges"]
        assets = [a for a in record["assets"] if a]
        return edges > 0, f"{edges} edge(s) · assets={assets or 'none'}"
    finally:
        await driver.close()


async def check_qdrant(document_id: str) -> tuple[bool, str]:
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    from api.config import get_settings

    settings = get_settings()
    client = AsyncQdrantClient(
        url=os.environ["QDRANT_URL"], api_key=os.environ.get("QDRANT_API_KEY") or None
    )
    try:
        points, _ = await client.scroll(
            collection_name=settings.QDRANT_COLLECTION_DOCUMENTS,
            scroll_filter=Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
            ),
            limit=100,
        )
        return len(points) > 0, f"{len(points)} chunk(s)"
    finally:
        await client.close()


async def check_elasticsearch(document_id: str) -> tuple[bool, str]:
    from elasticsearch import AsyncElasticsearch

    from api.config import get_settings

    settings = get_settings()
    es = AsyncElasticsearch([settings.ELASTICSEARCH_URL])
    try:
        if not await es.exists(index=settings.ELASTICSEARCH_INDEX_DOCUMENTS, id=document_id):
            return False, "not indexed — exact-token search will miss this document"
        doc = await es.get(index=settings.ELASTICSEARCH_INDEX_DOCUMENTS, id=document_id)
        return True, f"{len(doc['_source'].get('content', ''))} chars indexed"
    finally:
        await es.close()


CHECKS = [
    ("Supabase (vault + job)", check_supabase),
    ("Neo4j (graph)", check_neo4j),
    ("Qdrant (semantic)", check_qdrant),
    ("Elasticsearch (exact)", check_elasticsearch),
]


async def main(document_id: str) -> int:
    print(f"\nVerifying {document_id}\n" + "-" * 72)
    failures = []
    for name, check in CHECKS:
        try:
            ok, detail = await check(document_id)
        except Exception as exc:  # a store that cannot be reached is a failure, not a skip
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        print(f"  {'PASS' if ok else 'FAIL'}  {name:24} {detail}")
        if not ok:
            failures.append(name)
    print("-" * 72)
    if failures:
        print(f"  {len(failures)} store(s) missing: {', '.join(failures)}\n")
        return 1
    print("  All stores have this document.\n")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: verify_ingest.py <DOCUMENT_ID>")
    sys.exit(asyncio.run(main(sys.argv[1])))
