"""
Graph query-performance regression check — `ARCHITECTURE.md §7`.

The architecture names "query performance regression testing as part of the Layer 0 validation
gate for graph schema changes" as non-optional. This is that check.

WHAT IT ASSERTS, AND WHY IT ASSERTS THAT
  Plan **shape**, not timings and not dbHits ceilings. The regression this exists to catch already
  happened once: `asset_id_unique` was silently dropped by the schema loader, and the Layer 4 hot
  path degraded from `NodeUniqueIndexSeek` (1 row / 2 dbHits) to `NodeByLabelScan` over every
  Asset. Nothing went red — the queries still returned correct rows, just by reading the whole
  label. At 10 assets that is invisible in a timing; on a real graph it is the difference between
  a seek and a table scan.

  A dbHits ceiling would be the obvious assertion and is the wrong one: it moves with the data, so
  it either has to be loosened until it means nothing or it goes red on ordinary corpus growth. A
  gate that cries wolf gets deleted. Plan shape is data-independent — an anchored query either
  seeks its anchor or it does not.

  dbHits are printed for information, never asserted.

USAGE
  docker compose run --rm --no-deps kairos-backend-api python scripts/verify_graph_perf.py

Exits non-zero on any violation, so it can gate a schema change in CI or a Makefile target.
"""

import asyncio
import sys
from typing import Any

from neo4j import AsyncGraphDatabase

from api.config import Settings

# Plan operators that mean "the anchor was not used". Seeing one of these in a query that names a
# specific asset_id is the regression.
_SCAN_OPERATORS = {"NodeByLabelScan", "AllNodesScan"}


def _operator(plan: dict) -> str:
    """Bare operator name.

    Neo4j suffixes `operatorType` with a per-query planner hash (`NodeByLabelScan@2016aa75`), so
    comparing the raw string against a known-operator set silently never matches — the scan branch
    below was dead until this was added, and the generic "no index seek" fallback was doing the
    detecting without ever printing the constraint hint that makes the failure actionable.
    """
    return plan["operatorType"].split("@", 1)[0]


def _walk(plan: dict, depth: int = 0):
    yield depth, _operator(plan), plan.get("dbHits"), plan.get("rows")
    for child in plan.get("children", []) or []:
        yield from _walk(child, depth + 1)


async def _profile(session, cypher: str, params: dict) -> list[tuple]:
    result = await session.run(f"PROFILE {cypher}", **params)
    _ = [r async for r in result]  # PROFILE needs the stream drained before the plan is final
    summary = await result.consume()
    return list(_walk(summary.profile))


CHECKS: list[dict[str, Any]] = [
    {
        "name": "Layer 4 hot path — asset knowledge at a point in time",
        "cypher": """
        MATCH (a:Asset {asset_id: $asset_id})-[r:KNOWLEDGE_EDGE]->(target)
        WHERE r.valid_from <= $as_of
          AND (r.valid_to IS NULL OR r.valid_to > $as_of)
          AND r.authority_level <= $authority_min
        RETURN r, target
        """,
        "params": {"asset_id": "EQ-101", "as_of": "2026-08-23T00:00:00+00:00", "authority_min": 5},
        "must_seek": True,
    },
    {
        "name": "Asset hierarchy traversal (depth-bounded)",
        "cypher": """
        MATCH (a:Asset {asset_id: $asset_id})<-[:PARENT_OF*1..10]-(ancestor:Asset)
        RETURN ancestor
        """,
        "params": {"asset_id": "EQ-101"},
        "must_seek": True,
    },
    {
        "name": "Blast radius by document",
        "cypher": """
        MATCH (source)-[r:KNOWLEDGE_EDGE {document_id: $document_id}]->(target)
        RETURN r, source, target
        LIMIT 500
        """,
        "params": {"document_id": "DOC-MGAC8EU3P4XJ"},
        # Not anchored on an indexed node — it starts from a relationship property, so a scan is
        # the expected plan and asserting a seek here would be asserting something false.
        "must_seek": False,
    },
]


async def main() -> int:
    settings = Settings()
    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD)
    )
    failures: list[str] = []
    try:
        async with driver.session(database=settings.NEO4J_DATABASE) as session:
            for check in CHECKS:
                print(f"\n{check['name']}")
                try:
                    steps = await _profile(session, check["cypher"], check["params"])
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{check['name']}: PROFILE failed — {type(exc).__name__}: {exc}")
                    print(f"  ERROR: {exc}")
                    continue

                operators = {op for _, op, _, _ in steps}
                for depth, op, hits, rows in steps:
                    print(f"  {'  ' * depth}{op:30} dbHits={hits} rows={rows}")

                if not check["must_seek"]:
                    continue
                scans = operators & _SCAN_OPERATORS
                seeks = {o for o in operators if "IndexSeek" in o}
                if scans:
                    failures.append(
                        f"{check['name']}: plans as {sorted(scans)} — the anchor is not being used. "
                        "Check that the uniqueness constraint on the anchor property exists "
                        "(`SHOW CONSTRAINTS`); `scripts/init_neo4j.py` has silently dropped it before."
                    )
                elif not seeks:
                    failures.append(
                        f"{check['name']}: no index seek in the plan ({sorted(operators)}). "
                        "An anchored query should resolve its anchor through an index."
                    )
    finally:
        await driver.close()

    print()
    if failures:
        print("GRAPH PERF REGRESSION:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"graph perf OK — {len(CHECKS)} checks, every anchored query resolves through an index seek")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
