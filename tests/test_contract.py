"""
Response-shape contract tests.

Every bug found in the frontend-integration sweep was the same class: the
backend's real response shape differed from what the frontend types / docs/API.md
claimed (e.g. `total_gaps` was an object, not a number; circuit-breaker states
carried `halted`/`z_score`, not `status`/`override_rate`). Backend unit tests
passed and frontend `tsc` passed — neither could catch a *contract* mismatch.

These tests pin the top-level shape of the endpoints that drifted, so a future
backend change that breaks the documented contract fails CI here instead of the UI.
Assert keys + types only — never exact values (those are data-dependent).
"""

import pytest


async def test_compliance_dashboard_shape(admin_client):
    body = (await admin_client.get("/compliance/dashboard")).json()
    # total_gaps is a severity-keyed object, NOT a number (bug: UI rendered [object Object]).
    assert set(body["total_gaps"]) >= {"critical", "major", "minor"}
    assert isinstance(body["total_gaps"]["critical"], int)
    assert "by_framework" in body and "by_asset_class" in body
    assert "by_severity" not in body  # the shape the frontend wrongly assumed


async def test_sla_report_shape(admin_client):
    body = (await admin_client.get("/governance/sla-report")).json()
    assert isinstance(body["overdue_conflicts"], list)
    assert isinstance(body["overdue_quarantine_items"], list)  # not "overdue_quarantine"
    assert "overdue_conflicts_total" in body
    assert "escalated_this_run" in body and "checked_at" in body


async def test_circuit_breaker_shape(admin_client):
    body = (await admin_client.get("/governance/circuit-breaker")).json()
    assert isinstance(body["states"], list)  # not "entries"
    assert "halted_count" in body
    for state in body["states"]:
        assert isinstance(state["halted"], bool)  # boolean, not a "status" string
        assert {"asset_class", "z_score", "reason", "override_count_7d"} <= set(state)


async def test_validation_corpus_shape(admin_client):
    body = (await admin_client.get("/governance/validation-corpus/stats")).json()
    assert "total_corpus_size" in body  # not "total"
    assert isinstance(body["by_entity_type"], dict)
    assert "by_asset_class" not in body  # the field the frontend wrongly Object.entries'd


async def test_model_gate_history_shape(admin_client):
    body = (await admin_client.get("/governance/model-gate/history")).json()
    assert isinstance(body["items"], list)  # not "history"
    assert "total" in body


async def test_offboarding_list_shape(admin_client):
    body = (await admin_client.get("/elicitation/offboarding")).json()
    assert isinstance(body["items"], list)  # not a bare array
    assert "total" in body


async def test_blast_radius_and_topology_shape(admin_client):
    # Needs a pid_drawing document; skip cleanly if the golden dataset isn't loaded.
    docs = (await admin_client.get("/documents/?limit=50")).json().get("items", [])
    pid = next((d for d in docs if d.get("document_type") == "pid_drawing"), None)
    if pid is None:
        pytest.skip("no pid_drawing document loaded")
    doc_id = pid["document_id"]

    blast = (await admin_client.get(f"/governance/blast-radius/{doc_id}")).json()
    assert "affected_count" in blast
    assert isinstance(blast["affected"], list)  # edge/target pairs, not "affected_assets"

    topo = (await admin_client.get(f"/documents/{doc_id}/topology")).json()
    assert "topology" in topo  # nested object, not flat equipment/valves lists
    assert "equipment_nodes" in topo["topology"]
