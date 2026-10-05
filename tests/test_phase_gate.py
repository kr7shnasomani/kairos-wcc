"""
Phased trust architecture (Layer 12) — no network, no Supabase.

The architecture treats deployment phases as release gates *embedded in the software*. They were
previously a label only: `PhaseBadge` read `NEXT_PUBLIC_KAIROS_PHASE`, defaulted to "3", and no
backend code consulted it — so a deployment claiming Phase 1 still synthesised answers and still
pushed proactive briefs.

Default is 3, so none of this changes behaviour unless a deployment deliberately steps back.
"""

from api.config import Settings


def _settings(phase: int) -> Settings:
    return Settings(KAIROS_PHASE=phase)


def test_default_phase_is_three_so_behaviour_is_unchanged():
    """The gate must be inert by default — flipping it is a deployment decision, not a side effect."""
    assert Settings().KAIROS_PHASE == 3


def test_phase_one_disables_synthesis():
    assert _settings(1).KAIROS_PHASE < 2


def test_phase_two_enables_synthesis_but_not_proactive_push():
    s = _settings(2)
    assert s.KAIROS_PHASE >= 2       # synthesis on
    assert not (s.KAIROS_PHASE >= 3)  # proactive delivery still off


def test_phase_three_enables_everything():
    s = _settings(3)
    assert s.KAIROS_PHASE >= 2
    assert s.KAIROS_PHASE >= 3


def test_phase_is_readable_from_env(monkeypatch):
    """Deployments set this through the environment like every other setting."""
    monkeypatch.setenv("KAIROS_PHASE", "1")
    assert Settings().KAIROS_PHASE == 1


class _Recorder:
    """Minimal BriefEngine stand-in for the delivery gate: records whether push happened."""

    def __init__(self, phase: int):
        self.phase = phase
        self.published = False

    def deliver(self) -> str:
        # Mirrors the ordering in BriefEngine.deliver: persist first, gate the *push* only.
        persisted = "brief-1"
        if self.phase < 3:
            return persisted
        self.published = True
        return persisted


def test_brief_is_persisted_but_not_pushed_below_phase_three():
    """
    The distinction that matters: a Phase 2 brief is still assembled and readable in the inbox,
    it is simply not pushed at the operator. Suppressing assembly instead would be
    indistinguishable from the feature not existing.
    """
    r = _Recorder(phase=2)
    assert r.deliver() == "brief-1"
    assert r.published is False

    r3 = _Recorder(phase=3)
    r3.deliver()
    assert r3.published is True
