"""
Per-asset-class model gate + its enforcement path (Layer 0) — no network, no Supabase.

The architecture: "A model that passes on global metrics but fails on a specific asset class
(e.g. rotating equipment) is blocked for that class until retrained." The gate previously scored
per *entity type* only, and recorded `passed: false` without blocking anything — the hard
deployment gate was a report.

Enforcement routes through the circuit breaker that already halts extraction per asset class, so
there is one mechanism and one place to check, not two that can disagree.
"""

from api.config import Settings
from api.services.circuit_breaker import CircuitBreakerService


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_a, **_kw):
        return self

    def eq(self, *_a):
        return self

    def order(self, *_a, **_kw):
        return self

    def limit(self, _n):
        return self

    def execute(self):
        return type("Result", (), {"data": self._rows})()


class FakeSupabase:
    def __init__(self, rows):
        self._rows = rows

    def table(self, _name):
        return _Query(self._rows)


class BrokenSupabase:
    def table(self, _name):
        raise RuntimeError("supabase unreachable")


def _gate_row(blocked: list[str]) -> list[dict]:
    return [{"details": {"blocked_asset_classes": blocked}}]


def test_enforcement_is_off_by_default():
    """
    On a small corpus a single class can fail on noise. An enforcing gate would halt extraction
    for that class mid-demo, so it must be opt-in.
    """
    assert Settings().MODEL_GATE_ENFORCE is False


async def test_regressed_class_is_blocked():
    cb = CircuitBreakerService(FakeSupabase(_gate_row(["rotating_equipment"])))
    assert await cb.model_gate_block("rotating_equipment") is True

    state = await cb.check("rotating_equipment")
    assert state["halted"] is True
    assert state["reason"] == "model_gate_regression"


async def test_other_classes_are_unaffected_by_another_class_failing():
    """Blocking must be per class — a rotating-equipment regression cannot halt vessels."""
    cb = CircuitBreakerService(FakeSupabase(_gate_row(["rotating_equipment"])))
    assert await cb.model_gate_block("vessel") is False


async def test_advisory_gate_result_blocks_nothing():
    """With enforcement off the gate publishes an empty block list, so the breaker stays open."""
    cb = CircuitBreakerService(FakeSupabase(_gate_row([])))
    assert await cb.model_gate_block("rotating_equipment") is False


async def test_no_gate_history_does_not_block():
    cb = CircuitBreakerService(FakeSupabase([]))
    assert await cb.model_gate_block("rotating_equipment") is False


async def test_lookup_failure_does_not_halt_extraction():
    """
    Fail open on a reporting lookup. A model-gate history read is advisory; letting its failure
    halt extraction would turn an observability problem into an outage.
    """
    cb = CircuitBreakerService(BrokenSupabase())
    assert await cb.model_gate_block("rotating_equipment") is False
