"""
Validates the compliance gap/dashboard/audit Cypher against a live Neo4j.

Runs inside the API container against the local-stores Neo4j:
  docker compose run --rm --no-deps \
    -e NEO4J_URI=bolt://kairos-neo4j:7687 -e NEO4J_USERNAME=neo4j -e NEO4J_PASSWORD=... \
    kairos-backend-api python scripts/verify_compliance_cypher.py

Two things are checked:
  1. EXPLAIN — every query plans without error (catches Cypher the test fixture never hits).
  2. Semantics — on a fixture where the old cross-join and the new clause-aware query
     disagree, the new one must classify each (clause, asset) pair correctly.

Fixture (both assets are pumps, so both clauses apply to both):
  4.1.1 requires ['procedure']          EQ-101 -> procedure  (edge verified)
  4.1.2 requires ['inspection_report']  EQ-102 -> procedure  (edge unverified)
  no inspection_report exists anywhere

Expected: EQ-101/4.1.1 covered (absent) · EQ-101/4.1.2 gap
          EQ-102/4.1.1 unverified_evidence · EQ-102/4.1.2 gap
The previous query returned all four as gaps.
"""

import asyncio
import sys

from neo4j import AsyncGraphDatabase

from api.config import settings
from api.routers.compliance import _AUDIT_CYPHER, _DASHBOARD_CYPHER, _GAP_CYPHER

FAR = "9999-12-31T23:59:59+00:00"

SEED = """
CREATE (r1:Concept {concept_id:'OISD-117-4.1.1', type:'Regulation', framework:'OISD_117',
        clause_id:'4.1.1', requirement_text:'Pumps shall have documented maintenance procedures.',
        applies_to_equipment_class:'pump', requires_document_type:['procedure'], authority_level:1})
CREATE (r2:Concept {concept_id:'OISD-117-4.1.2', type:'Regulation', framework:'OISD_117',
        clause_id:'4.1.2', requirement_text:'Pump overhaul records shall be maintained.',
        applies_to_equipment_class:'pump', requires_document_type:['inspection_report'], authority_level:1})
CREATE (a1:Asset {asset_id:'EQ-101', tag_number:'EQ-101', equipment_class:'pump', site_id:'SITE-1'})
CREATE (a2:Asset {asset_id:'EQ-102', tag_number:'EQ-102', equipment_class:'pump', site_id:'SITE-1'})
CREATE (d1:Document {document_id:'DOC-SOP-1', document_type:'procedure'})
CREATE (d2:Document {document_id:'DOC-SOP-2', document_type:'procedure'})
CREATE (a1)-[:KNOWLEDGE_EDGE {edge_id:'e1', relationship_type:'DOCUMENTED_BY',
        valid_from:'2025-01-01T00:00:00+00:00', valid_to:$far, authority_level:4,
        document_id:'DOC-SOP-1', confidence:0.9, verification_status:'verified'}]->(d1)
CREATE (a2)-[:KNOWLEDGE_EDGE {edge_id:'e2', relationship_type:'DOCUMENTED_BY',
        valid_from:'2025-01-01T00:00:00+00:00', valid_to:$far, authority_level:4,
        document_id:'DOC-SOP-2', confidence:0.9, verification_status:'unverified'}]->(d2)
"""

QUERIES = {
    "_GAP_CYPHER": (_GAP_CYPHER, {"framework": None, "asset_id": None, "site_id": None, "limit": 100}),
    "_DASHBOARD_CYPHER": (_DASHBOARD_CYPHER, {"site_id": None}),
    "_AUDIT_CYPHER": (_AUDIT_CYPHER, {"framework": "OISD_117", "clauses": None}),
}


async def main() -> int:
    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD)
    )
    failures: list[str] = []
    try:
        async with driver.session(database=settings.NEO4J_DATABASE) as s:
            # Seed first so EXPLAIN plans against real labels/properties.
            await (await s.run("MATCH (n) DETACH DELETE n")).consume()
            await (await s.run(SEED, far=FAR)).consume()

            # --- 1. EXPLAIN every query (plan-time validation) ---
            print("EXPLAIN:")
            for name, (cypher, params) in QUERIES.items():
                try:
                    res = await s.run(f"EXPLAIN {cypher}", **params)
                    plan = (await res.consume()).plan
                    ops = _operators(plan)
                    flags = [o for o in ("CartesianProduct", "AllNodesScan", "Eager") if o in ops]
                    print(f"  {name:<20} plans OK   notable: {', '.join(flags) or 'none'}")
                except Exception as exc:
                    failures.append(f"{name} failed to plan: {exc}")
                    print(f"  {name:<20} PLAN ERROR: {exc}")

            # --- 2. Semantics on a discriminating fixture ---
            rows = [r.data() async for r in await s.run(_GAP_CYPHER, **QUERIES["_GAP_CYPHER"][1])]
            got = {(r["asset_id"], r["clause_id"]): r["status"] for r in rows}
            print("\nGAP findings:")
            for k in sorted(got):
                print(f"  {k[0]} / {k[1]:<7} -> {got[k]}")

            expected = {
                ("EQ-101", "4.1.2"): "gap",
                ("EQ-102", "4.1.1"): "unverified_evidence",
                ("EQ-102", "4.1.2"): "gap",
            }
            if got != expected:
                failures.append(f"gap mismatch\n   expected {expected}\n   got      {got}")

            dash = [r.data() async for r in await s.run(_DASHBOARD_CYPHER, site_id=None)]
            gaps = sum(r["gap_count"] for r in dash if r["status"] == "gap")
            unver = sum(r["gap_count"] for r in dash if r["status"] == "unverified_evidence")
            print(f"\nDASHBOARD: {gaps} gap(s), {unver} unverified_evidence")
            if (gaps, unver) != (2, 1):
                failures.append(f"dashboard expected 2 gaps / 1 unverified, got {gaps} / {unver}")

            audit = [r.data() async for r in await s.run(_AUDIT_CYPHER, framework="OISD_117", clauses=None)]
            by_clause = {r["clause_id"]: r["evidence"] for r in audit}
            print("\nAUDIT evidence per clause:")
            for cid in sorted(by_clause):
                print(f"  {cid}: {len(by_clause[cid])} doc(s)")
            if len(by_clause.get("4.1.1", [])) != 2:
                failures.append(f"4.1.1 should collect both procedure docs, got {by_clause.get('4.1.1')}")
            if by_clause.get("4.1.2"):
                failures.append(f"4.1.2 requires inspection_report; none exists, got {by_clause.get('4.1.2')}")

            await (await s.run("MATCH (n) DETACH DELETE n")).consume()
    finally:
        await driver.close()

    print()
    for f in failures:
        print("FAIL:", f)
    if failures:
        return 1
    print("ALL COMPLIANCE CYPHER CHECKS PASSED")
    return 0


def _operators(plan: dict | None) -> set[str]:
    """Flattens a Neo4j plan tree into the set of operator names it uses."""
    if not plan:
        return set()
    names = {plan.get("operatorType", "").split("@")[0]}
    for child in plan.get("children", []) or []:
        names |= _operators(child)
    return names


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
