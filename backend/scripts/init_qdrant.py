"""
Init script — Create Qdrant collections with correct vector dimensions.
Run: python backend/scripts/init_qdrant.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

from api.config import settings

log = structlog.get_logger(__name__)

# Payload fields we filter on — Qdrant Cloud REQUIRES an index on any field used in a filter
# (local Qdrant is lenient). Without these, asset-scoped / quarantine searches 400 on cloud.
PAYLOAD_INDEXES = {
    "asset_id": PayloadSchemaType.KEYWORD,
    "document_id": PayloadSchemaType.KEYWORD,
    "is_quarantine": PayloadSchemaType.BOOL,
    # Required by the superseded-document filter in VectorStoreService.search. Qdrant Cloud
    # rejects a filter on an UNINDEXED field with HTTP 400 — and because hybrid_search gathers
    # with return_exceptions=True, that 400 was swallowed as `search.qdrant_failed` and hybrid
    # retrieval silently degraded to Elasticsearch-only. Measured: semantic arm 0/37 on the
    # retrieval baseline. Any new payload filter needs its index added here.
    "status": PayloadSchemaType.KEYWORD,
}

COLLECTIONS = {
    settings.QDRANT_COLLECTION_KNOWLEDGE: {
        "description": "Extracted knowledge fragments — facts, parameters, relationships",
        "size": settings.EMBEDDING_DIMENSION,
        "distance": Distance.COSINE,
    },
    settings.QDRANT_COLLECTION_DOCUMENTS: {
        "description": "Full document chunks for RAG-style retrieval",
        "size": settings.EMBEDDING_DIMENSION,
        "distance": Distance.COSINE,
    },
}


async def init_collections():
    log.info("qdrant.init_started", url=settings.QDRANT_URL)

    client = AsyncQdrantClient(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY or None,
    )

    try:
        existing = await client.get_collections()
        existing_names = {c.name for c in existing.collections}
        log.info("qdrant.existing_collections", collections=list(existing_names))

        for name, config in COLLECTIONS.items():
            if name in existing_names:
                log.info("qdrant.collection_exists", name=name)
            else:
                await client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(size=config["size"], distance=config["distance"]),
                )
                log.info("qdrant.collection_created", name=name, size=config["size"])

            # Payload indexes (idempotent — skip if already present). Required by Qdrant Cloud.
            for field, schema in PAYLOAD_INDEXES.items():
                try:
                    await client.create_payload_index(collection_name=name, field_name=field, field_schema=schema)
                    log.info("qdrant.payload_index_created", name=name, field=field)
                except Exception as exc:  # noqa: BLE001 — already-exists is fine
                    log.info("qdrant.payload_index_skip", name=name, field=field, reason=str(exc)[:60])

        log.info("qdrant.init_complete")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(init_collections())
