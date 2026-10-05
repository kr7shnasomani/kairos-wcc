"""
Seed regulatory framework — merges Concept nodes into Neo4j.
Run inside the API container:
  docker exec kairos-backend-api python scripts/seed_regulations.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from neo4j import AsyncGraphDatabase

from api.config import settings

log = structlog.get_logger(__name__)

REGULATIONS = [
    # ── OISD-117: Safety of Onshore Petroleum Installations ──────────────────
    {
        "concept_id": "OISD-117-4.1.1",
        "framework": "OISD_117",
        "clause_id": "4.1.1",
        "requirement_text": "Rotating equipment (pumps) shall have documented maintenance procedures including inspection intervals, lubrication schedules, and seal replacement criteria.",
        "requires_document_type": ["procedure"],
        "applies_to_equipment_class": "pump",
        "authority_level": 1,
    },
    {
        "concept_id": "OISD-117-4.1.2",
        "framework": "OISD_117",
        "clause_id": "4.1.2",
        "requirement_text": "Pump overhaul records shall be maintained with failure code, root cause, corrective action, and post-maintenance operational test results.",
        "requires_document_type": ["inspection_report"],
        "applies_to_equipment_class": "pump",
        "authority_level": 1,
    },
    {
        "concept_id": "OISD-117-4.2.1",
        "framework": "OISD_117",
        "clause_id": "4.2.1",
        "requirement_text": "Pressure vessels shall be inspected at prescribed intervals per applicable Factories Act and OISD standards; inspection reports shall be retained on-site.",
        "requires_document_type": ["inspection_report"],
        "applies_to_equipment_class": "vessel",
        "authority_level": 1,
    },
    {
        "concept_id": "OISD-117-4.2.2",
        "framework": "OISD_117",
        "clause_id": "4.2.2",
        "requirement_text": "Maximum Allowable Working Pressure (MAWP) documentation shall be current and verified against OEM specification for each pressure vessel.",
        "requires_document_type": ["oem_manual"],
        "applies_to_equipment_class": "vessel",
        "authority_level": 1,
    },
    {
        "concept_id": "OISD-117-4.3.1",
        "framework": "OISD_117",
        "clause_id": "4.3.1",
        "requirement_text": "Safety-critical valves shall have written testing procedures covering test frequency, acceptance criteria, and personnel qualification requirements.",
        "requires_document_type": ["procedure"],
        "applies_to_equipment_class": "valve",
        "authority_level": 1,
    },
    {
        "concept_id": "OISD-117-4.3.2",
        "framework": "OISD_117",
        "clause_id": "4.3.2",
        "requirement_text": "Valve maintenance records shall document leak test results, actuator function, and any found condition outside of tolerance.",
        "requires_document_type": ["inspection_report"],
        "applies_to_equipment_class": "valve",
        "authority_level": 1,
    },
    {
        "concept_id": "OISD-117-5.1.1",
        "framework": "OISD_117",
        "clause_id": "5.1.1",
        "requirement_text": "Compressors shall have an approved maintenance procedure covering inter-stage pressure limits, vibration monitoring criteria, and unloading sequences.",
        "requires_document_type": ["procedure"],
        "applies_to_equipment_class": "compressor",
        "authority_level": 1,
    },
    {
        "concept_id": "OISD-117-5.1.2",
        "framework": "OISD_117",
        "clause_id": "5.1.2",
        "requirement_text": "Emergency shutdown procedures for compressors shall be documented, posted at the equipment, and tested at minimum annually.",
        "requires_document_type": ["procedure"],
        "applies_to_equipment_class": "compressor",
        "authority_level": 1,
    },
    # ── ISO 45001:2018 — Occupational Health & Safety (all equipment) ─────────
    {
        "concept_id": "ISO-45001-8.1.1",
        "framework": "ISO_45001",
        "clause_id": "8.1.1",
        "requirement_text": "Operational planning and control procedures shall be established for all hazardous activities, including documented safe work instructions.",
        "requires_document_type": ["procedure"],
        "applies_to_equipment_class": None,  # applies to all
        "authority_level": 2,
    },
    {
        "concept_id": "ISO-45001-8.2.1",
        "framework": "ISO_45001",
        "clause_id": "8.2.1",
        "requirement_text": "Emergency preparedness and response procedures shall be documented, tested, and communicated to all personnel who may be involved.",
        "requires_document_type": ["procedure"],
        "applies_to_equipment_class": None,
        "authority_level": 2,
    },
    {
        "concept_id": "ISO-45001-9.1.1",
        "framework": "ISO_45001",
        "clause_id": "9.1.1",
        "requirement_text": "Performance monitoring and measurement procedures shall be in place for all safety-critical equipment to track against agreed operational parameters.",
        "requires_document_type": ["procedure"],
        "applies_to_equipment_class": None,
        "authority_level": 2,
    },
    {
        "concept_id": "ISO-45001-10.2.1",
        "framework": "ISO_45001",
        "clause_id": "10.2.1",
        "requirement_text": "Incident investigation procedures shall be documented and applied to all incidents and near-misses; findings shall feed corrective action tracking.",
        "requires_document_type": ["procedure"],
        "applies_to_equipment_class": None,
        "authority_level": 2,
    },
]

CYPHER = """
MERGE (c:Concept {concept_id: $concept_id})
ON CREATE SET
    c.type = 'Regulation',
    c.framework = $framework,
    c.clause_id = $clause_id,
    c.requirement_text = $requirement_text,
    c.applies_to_equipment_class = $applies_to_equipment_class,
    c.requires_document_type = $requires_document_type,
    c.authority_level = $authority_level
ON MATCH SET
    c.requirement_text = $requirement_text,
    c.applies_to_equipment_class = $applies_to_equipment_class,
    c.requires_document_type = $requires_document_type,
    c.authority_level = $authority_level
RETURN c.concept_id AS concept_id
"""


async def seed():
    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
    )
    try:
        async with driver.session(database=settings.NEO4J_DATABASE) as session:
            for reg in REGULATIONS:
                result = await session.run(CYPHER, **reg)
                record = await result.single()
                log.info("regulation.seeded", concept_id=record["concept_id"])
        log.info("seed.complete", total=len(REGULATIONS))
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(seed())
