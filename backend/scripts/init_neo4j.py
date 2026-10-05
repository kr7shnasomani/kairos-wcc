"""
Init script — Apply Neo4j schema (constraints + indices).
Run: python backend/scripts/init_neo4j.py
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from neo4j import AsyncGraphDatabase

from api.config import settings

log = structlog.get_logger(__name__)

SCHEMA_FILE = Path(__file__).parent.parent / "db" / "neo4j" / "init_schema.cypher"


async def apply_schema():
    log.info("neo4j.schema_init_started", uri=settings.NEO4J_URI)

    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
    )

    try:
        # Test connection
        async with driver.session(database=settings.NEO4J_DATABASE) as session:
            result = await session.run("RETURN 'connected' AS status")
            record = await result.single()
            log.info("neo4j.connected", status=record["status"])

        # Read and apply schema
        schema_cypher = SCHEMA_FILE.read_text()

        # Strip `//` line comments BEFORE splitting on `;`, not after.
        #
        # THE BUG THIS FIXES: the old form split on `;` first and then dropped any
        # chunk that *started with* `//`. Every statement in the schema file that
        # follows a comment block lands in a chunk beginning with that comment — so
        # each one was silently discarded. Not skipped-with-a-warning: filtered out
        # before the loop, so nothing was logged and the run still reported success.
        #
        # Six statements never reached Aura, including `asset_id_unique` — leaving
        # the graph's most important node type with no uniqueness constraint and no
        # index behind `asset_id`, which is why the Layer 4 hot path planned as a
        # NodeByLabelScan. Assets are written with MERGE, which needs that
        # constraint to be safe under concurrency.
        body = "\n".join(
            line for line in schema_cypher.splitlines()
            if not line.strip().startswith("//")
        )
        statements = [s.strip() for s in body.split(";") if s.strip()]

        applied = 0
        failed: list[int] = []
        async with driver.session(database=settings.NEO4J_DATABASE) as session:
            for i, statement in enumerate(statements, 1):
                try:
                    await session.run(statement)
                    applied += 1
                    log.info("neo4j.statement_applied", index=i, preview=statement[:60])
                except Exception as e:
                    failed.append(i)
                    log.warning("neo4j.statement_skipped", index=i, preview=statement[:60], error=str(e))

        # Report what actually landed. The old form logged len(statements) as
        # "applied", so a run where every statement failed still read as a success.
        log.info(
            "neo4j.schema_init_complete",
            statements_total=len(statements),
            statements_applied=applied,
            statements_failed=len(failed),
            failed_indexes=failed,
        )

    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(apply_schema())
