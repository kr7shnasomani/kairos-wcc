"""
Purge integration-test residue from every store.

Tests create ephemeral entities against the live stack (see tests/conftest.py) with
well-known id prefixes and never tear them down, so junk accumulates in Neo4j,
Supabase, and Elasticsearch. This removes exactly those rows — nothing canonical.

Run inside the API container:
  docker exec kairos-backend-api python scripts/purge_test_data.py

Used as a library too: tests/conftest.py imports `purge()` for a session teardown.
For a full deterministic reset prefer `make nuke && make init-all && seed && load-dataset`.
"""

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
import structlog
from neo4j import AsyncGraphDatabase
from supabase import create_client

from api.config import settings

log = structlog.get_logger(__name__)

# Test-id prefixes minted by tests/ (uid()-suffixed). Keep in sync with conftest.py.
#
# Every entry here is matched as a PREFIX (`STARTS WITH` / `LIKE 'p%'` / an ES
# prefix query), so a short one is a live data-loss risk: real ids are `DOC-` plus
# twelve random characters, and roughly one document in thirty-six starts with X.
# `DOC-X` sat in this list because one test uses that exact id as a literal, and as
# a prefix it matched four real documents in the graph and DETACH DELETEd them —
# on every full-suite run, since conftest calls this as an autouse teardown. Exact
# ids belong in the _EXACT lists below, never here.
ASSET_PREFIXES = ["ASSET-TEST-", "ASSET-DEDUP-", "ASSET-EV-", "ASSET-ACK-", "ASSET-FRESH-"]
WO_PREFIXES = ["WO-ATTR-", "WO-GO-", "WO-RESP-", "WO-VOICE-", "WO-TEST-"]
DOC_PREFIXES = ["DOC-INSP-"]

# Whole ids a test writes verbatim. Matched by equality — see the note above.
DOC_EXACT_IDS = ["DOC-X"]  # tests/test_annotations.py
# `WO-E2E-ELICIT-001` is a literal typed by hand during the 2026-08-16 E2E sweep, not a fixture
# family — no test generates it, so it never had a prefix and accumulated 4 quarantine rows.
# It is matched by EQUALITY on purpose. A `WO-E2E-` prefix would be needless risk and a bare
# `WO-` prefix would be catastrophic: `WO-2026-0714` is real dataset content whose promoted
# quarantine item (`PROMOTED-f17b1416…`) the compliance benchmark caveat in status.md cites.
WO_EXACT_IDS = ["WO-E2E-ELICIT-001"]

# Pairs a prefix list with the whole ids that belong to the same family. Replaces an identity
# check against DOC_PREFIXES, which made exact-id purging a one-off for documents only.
EXACT_ID_SETS: list[tuple[list[str], list[str]]] = [
    (DOC_PREFIXES, DOC_EXACT_IDS),
    (WO_PREFIXES, WO_EXACT_IDS),
]

# Supabase deletes in FK-safe order — every child of assets/documents/briefs/conflicts
# is removed before its parent. `brief_feedback` (→ briefs) and `moc_items` (→ conflicts)
# are handled separately below because they need a parent-id subquery.
SUPABASE_TARGETS: list[tuple[str, str, list[str]]] = [
    ("document_asset_links", "asset_id", ASSET_PREFIXES),
    ("document_asset_links", "document_id", DOC_PREFIXES),
    ("extraction_jobs", "document_id", DOC_PREFIXES),
    ("ner_annotations", "document_id", DOC_PREFIXES),
    ("validation_corpus", "document_id", DOC_PREFIXES),
    ("elicitation_sessions", "asset_id", ASSET_PREFIXES),
    ("quarantine_items", "asset_id", ASSET_PREFIXES),
    ("quarantine_items", "work_order_id", WO_PREFIXES),
    ("knowledge_conflicts", "asset_id", ASSET_PREFIXES),
    ("briefs", "asset_id", ASSET_PREFIXES),
    ("operational_events", "asset_id", ASSET_PREFIXES),
    ("asset_alias_map", "canonical_asset_id", ASSET_PREFIXES),
    ("documents", "document_id", DOC_PREFIXES),
    ("assets", "asset_id", ASSET_PREFIXES),  # last — everything above FKs to it
]

# ES indices → (field, prefixes).
ES_TARGETS: list[tuple[str, str, list[str]]] = [
    (settings.ELASTICSEARCH_INDEX_ASSETS, "asset_id", ASSET_PREFIXES),
    (settings.ELASTICSEARCH_INDEX_DOCUMENTS, "document_id", DOC_PREFIXES),
    (settings.ELASTICSEARCH_INDEX_EVENTS, "asset_id", ASSET_PREFIXES),
]


async def _purge_neo4j() -> int:
    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD)
    )
    deleted = 0
    try:
        for label, key, prefixes in (("Asset", "asset_id", ASSET_PREFIXES), ("Document", "document_id", DOC_PREFIXES)):
            for prefix in prefixes:
                # DETACH DELETE removes the node and every KNOWLEDGE_EDGE touching it.
                summary = (await driver.execute_query(
                    f"MATCH (n:{label}) WHERE n.{key} STARTS WITH $prefix DETACH DELETE n",
                    prefix=prefix, database_=settings.NEO4J_DATABASE,
                )).summary
                deleted += summary.counters.nodes_deleted

        if DOC_EXACT_IDS:
            summary = (await driver.execute_query(
                "MATCH (n:Document) WHERE n.document_id IN $ids DETACH DELETE n",
                ids=DOC_EXACT_IDS, database_=settings.NEO4J_DATABASE,
            )).summary
            deleted += summary.counters.nodes_deleted
    finally:
        await driver.close()
    return deleted


def _ids_for_asset_prefixes(sb, table: str, id_col: str) -> list[str]:
    """Collect the primary ids of rows whose asset_id matches a test prefix (for FK-child cleanup)."""
    ors = ",".join(f"asset_id.like.{p}%" for p in ASSET_PREFIXES)
    rows = sb.table(table).select(id_col).or_(ors).execute().data or []
    return [r[id_col] for r in rows]


def _purge_supabase() -> int:
    sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    deleted = 0

    # FK children that need a parent-id subquery (Supabase client can't express one inline).
    try:
        brief_ids = _ids_for_asset_prefixes(sb, "briefs", "brief_id")
        if brief_ids:
            deleted += len((sb.table("brief_feedback").delete().in_("brief_id", brief_ids).execute()).data or [])
        conflict_ids = _ids_for_asset_prefixes(sb, "knowledge_conflicts", "conflict_id")
        if conflict_ids:
            deleted += len((sb.table("moc_items").delete().in_("conflict_id", conflict_ids).execute()).data or [])
        for prefix in ASSET_PREFIXES:
            deleted += len((sb.table("moc_items").delete().like("asset_id", f"{prefix}%").execute()).data or [])
    except Exception as exc:  # transient Supabase error — don't abort Neo4j/ES cleanup already done
        log.warning("purge.supabase.fk_children.skip", error=str(exc))

    for table, column, prefixes in SUPABASE_TARGETS:
        for prefix in prefixes:
            try:
                res = sb.table(table).delete().like(column, f"{prefix}%").execute()
                deleted += len(res.data or [])
            except Exception as exc:  # column may not exist on a given table — skip, don't fail the run
                log.warning("purge.supabase.skip", table=table, column=column, error=str(exc))

    for table, column, prefixes in SUPABASE_TARGETS:
        for prefix_list, exact_ids in EXACT_ID_SETS:
            if prefixes is not prefix_list or not exact_ids:
                continue
            try:
                deleted += len((sb.table(table).delete().in_(column, exact_ids).execute()).data or [])
            except Exception as exc:  # noqa: BLE001 — same tolerance as the prefix pass above
                log.warning("purge.supabase.exact.skip", table=table, column=column, error=str(exc))
    return deleted


def _purge_elasticsearch() -> int:
    deleted = 0
    auth = None
    if settings.ELASTICSEARCH_USERNAME:
        auth = (settings.ELASTICSEARCH_USERNAME, settings.ELASTICSEARCH_PASSWORD)
    with httpx.Client(base_url=settings.ELASTICSEARCH_URL, auth=auth, timeout=30) as client:
        for index, field, prefixes in ES_TARGETS:
            should: list[dict[str, Any]] = [{"prefix": {field: p}} for p in prefixes]
            if prefixes is DOC_PREFIXES and DOC_EXACT_IDS:
                should.append({"terms": {field: DOC_EXACT_IDS}})
            if not should:
                continue
            try:
                r = client.post(
                    f"/{index}/_delete_by_query",
                    json={"query": {"bool": {"should": should, "minimum_should_match": 1}}},
                    params={"conflicts": "proceed", "ignore_unavailable": "true"},
                )
                if r.status_code < 300:
                    deleted += r.json().get("deleted", 0)
            except httpx.HTTPError as exc:
                log.warning("purge.es.skip", index=index, error=str(exc))
    return deleted


async def purge() -> dict[str, int]:
    """Delete test-prefixed rows from Neo4j, Supabase, and Elasticsearch. Returns per-store counts."""
    neo, es = await _purge_neo4j(), _purge_elasticsearch()
    sb = _purge_supabase()
    result = {"neo4j": neo, "supabase": sb, "elasticsearch": es}
    log.info("purge.done", **result)
    return result
    # ponytail: Qdrant skipped — test assets rarely reach the vector index; add a
    # payload-filter delete on kairos_documents/kairos_knowledge if that changes.


if __name__ == "__main__":
    counts = asyncio.run(purge())
    print(f"Purged test data: {counts}")
