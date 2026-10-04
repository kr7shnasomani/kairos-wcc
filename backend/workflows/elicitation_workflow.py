"""
Elicitation Engine workflows — Layer 6: Tacit Knowledge Elicitation.
MicroInterviewWorkflow: generates graph-derived diagnostic questions at work order closeout.
StoreElicitationResponseWorkflow: routes operator responses into quarantine for human review.
"""

import asyncio
import json
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from neo4j import AsyncGraphDatabase
from supabase import create_client
from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from api.config import Settings
from api.services.llm import LLMService

log = structlog.get_logger(__name__)

_ACTIVITY_TIMEOUT = timedelta(minutes=5)
_RETRY_POLICY = RetryPolicy(maximum_attempts=3, backoff_coefficient=2.0)


def _get_neo4j():
    return AsyncGraphDatabase.driver(
        os.environ.get("NEO4J_URI", "bolt://kairos-neo4j:7687"),
        auth=(
            os.environ.get("NEO4J_USERNAME", "neo4j"),
            os.environ.get("NEO4J_PASSWORD", "kairos_dev_password"),
        ),
    )


def _get_supabase():
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


@activity.defn
async def generate_interview_questions(params: dict[str, Any]) -> dict[str, Any]:
    work_order_id = params["work_order_id"]
    asset_id = params["asset_id"]
    failure_code = params.get("failure_code", "")
    triggered_by = params.get("triggered_by", "system")

    supabase = _get_supabase()
    now = datetime.now(UTC).isoformat()

    session_row = await asyncio.to_thread(
        lambda: supabase.table("elicitation_sessions").insert({
            "work_order_id": work_order_id,
            "asset_id": asset_id,
            "triggered_by": triggered_by,
            "status": "pending",
            "questions": [],
        }).execute()
    )
    session_id = session_row.data[0]["session_id"]

    # Query Neo4j for known vs unknown failure modes on this asset
    driver = _get_neo4j()
    known: list[str] = []
    unknown: list[str] = []
    try:
        async with driver.session(database=os.environ.get("NEO4J_DATABASE", "neo4j")) as neo4j_session:
            result = await neo4j_session.run(
                """
                MATCH (a:Asset {asset_id: $asset_id})-[r]->(n)
                WHERE (r.valid_to IS NULL OR datetime(r.valid_to) > datetime())
                  AND r.authority_level <= 3
                  AND r.valid_from <= $as_of
                RETURN n.name AS mode,
                       r.confidence AS confidence,
                       r.verification_status AS vstatus
                ORDER BY r.confidence DESC
                LIMIT 25
                """,
                asset_id=asset_id,
                as_of=now,
            )
            async for rec in result:
                mode = rec["mode"]
                if not mode:
                    continue
                if rec["vstatus"] == "verified" and (rec["confidence"] or 0) >= 0.7:
                    known.append(mode)
                else:
                    unknown.append(mode)
    finally:
        await driver.close()

    # Generate questions via LLM
    settings = Settings()
    llm = LLMService(settings)
    prompt = (
        f"Generate 3-5 targeted diagnostic questions for asset {asset_id} "
        f"with failure code '{failure_code}'. "
        f"Known failure modes: {known or ['none documented']}. "
        f"Unknown/unverified failure modes: {unknown or ['none']}. "
        "Be specific, not generic. Focus on gaps in the knowledge base."
    )
    # Use "text" key — matches what LLMService._format_context reads
    context_items: list[dict[str, Any]] = [
        {"text": f"Known failure mode: {m}", "confidence": 0.9, "authority_level": 2}
        for m in known
    ] + [
        {"text": f"Unverified failure mode: {m}", "confidence": 0.4, "authority_level": 4}
        for m in unknown
    ]
    # Ensure at least one context item so synthesize() doesn't short-circuit on empty context
    if not context_items:
        context_items = [{
            "text": f"No prior failure history documented for asset {asset_id}.",
            "confidence": 0.5,
            "authority_level": 3,
        }]

    llm_result = await llm.synthesize(prompt, context_items)
    answer_text = llm_result.get("answer") or ""

    # NIM returns full synthesis block: "ANSWER: 1. Q? 2. Q?\nCONFIDENCE: ..."
    # Extract just the ANSWER section first, then split on numbered items
    answer_match = re.search(r"ANSWER:\s*(.+?)(?:\nCONFIDENCE:|$)", answer_text, re.DOTALL | re.IGNORECASE)
    answer_block = answer_match.group(1).strip() if answer_match else answer_text

    questions: list[str] = []
    for part in re.split(r"\d+[\.\)]\s+", answer_block):
        q = part.strip().rstrip()
        if q and "?" in q:
            questions.append(q)
        if len(questions) >= 5:
            break

    # Also try line-by-line for models that return one question per line
    if not questions:
        for line in answer_text.split("\n"):
            line = line.strip().lstrip("0123456789.-) ")
            if line and "?" in line:
                questions.append(line)
            if len(questions) >= 5:
                break

    if not questions:
        log.warning("elicitation.llm_no_questions",
                    session_id=session_id, answer_preview=answer_text[:200])
        raise RuntimeError(
            f"LLM returned no parseable questions for {asset_id}. "
            f"Response: {answer_text[:300]}"
        )

    await asyncio.to_thread(
        lambda: supabase.table("elicitation_sessions").update({
            "questions": questions,
            "status": "questions_ready",
            "updated_at": datetime.now(UTC).isoformat(),
        }).eq("session_id", session_id).execute()
    )

    log.info("elicitation.questions_generated",
             session_id=session_id, asset_id=asset_id, count=len(questions))
    return {"session_id": session_id, "questions": questions}


@activity.defn
async def store_elicitation_response(params: dict[str, Any]) -> dict[str, Any]:
    work_order_id = params["work_order_id"]
    responses = params["responses"]  # list of {question, answer}
    asset_id = params.get("asset_id") or None
    submitted_by = params.get("submitted_by", "system")
    questions = params.get("questions", [])

    supabase = _get_supabase()

    row = await asyncio.to_thread(
        lambda: supabase.table("quarantine_items").insert({
            "asset_id": asset_id,
            "content": json.dumps(responses),
            "input_type": "elicitation_response",
            "submitted_by": submitted_by,
            "work_order_id": work_order_id,
            "session_context": {
                "questions": questions,
                "work_order_id": work_order_id,
                "response_count": len(responses),
            },
        }).execute()
    )
    item_id = row.data[0]["item_id"]

    await asyncio.to_thread(
        lambda: supabase.table("elicitation_sessions").update({
            "status": "completed",
            "updated_at": datetime.now(UTC).isoformat(),
        }).eq("work_order_id", work_order_id).execute()
    )

    log.info("elicitation.response_stored", item_id=item_id, work_order_id=work_order_id)
    return {"item_id": item_id, "status": "quarantined"}


@workflow.defn
class MicroInterviewWorkflow:
    @workflow.run
    async def run(self, params: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            generate_interview_questions,
            params,
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=_RETRY_POLICY,
        )


@workflow.defn
class StoreElicitationResponseWorkflow:
    @workflow.run
    async def run(self, params: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            store_elicitation_response,
            params,
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=_RETRY_POLICY,
        )
