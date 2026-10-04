"""
Temporal activity worker — Layer 3 Perception Engine + Layer 4 Graph pipeline.
Connects to the Temporal server and executes DocumentIngestionWorkflow activities.

Run:  python -m workers.temporal_worker
"""

import asyncio
import os

import structlog
from temporalio.client import Client
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from workflows.document_pipeline import (
    DocumentIngestionWorkflow,
    index_text,
    index_vectors,
    link_to_graph,
    mark_complete,
    run_ner,
    run_ocr,
    store_in_vault,
)

log = structlog.get_logger(__name__)


async def main():
    temporal_address = os.environ.get("TEMPORAL_ADDRESS", "kairos-temporal:7233")
    task_queue = os.environ.get("TEMPORAL_TASK_QUEUE", "kairos-ingestion")

    log.info("temporal_worker.connecting", address=temporal_address, queue=task_queue)

    client = await Client.connect(temporal_address)

    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[DocumentIngestionWorkflow],
        activities=[
            store_in_vault,
            run_ocr,
            run_ner,
            link_to_graph,
            index_vectors,
            index_text,
            mark_complete,
        ],
        workflow_runner=UnsandboxedWorkflowRunner(),
    )

    log.info("temporal_worker.started", queue=task_queue)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
