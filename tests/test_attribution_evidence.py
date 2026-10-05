"""STAGED — copy to tests/test_attribution_evidence.py after SOAK_DONE (~12:35).

Outcome attribution evidence selection (workers/attribution.py, Layer 10).

Pure logic: `_attribute` and `_classify_attestation` take plain dicts/strings, no clients.
The regression that matters is `test_brownfield_asset_can_now_be_attributed` — before the fix,
`genuine_failure` was unreachable on every uninstrumented asset.
"""

from workers.attribution import _attribute, _classify_attestation

_SAME_FAMILY = {"matched": True}
_DIFF_FAMILY = {"matched": False}
_EXECUTED = {"compliant": True}
_NOT_EXECUTED = {"compliant": False}
_NO_ATTESTATION = {"checked": False}

_TELEMETRY_FAILED = {"evidence_role": "primary", "conclusive": True, "failed": True}
_TELEMETRY_RECOVERED = {"evidence_role": "primary", "conclusive": True, "failed": False}
_UNINSTRUMENTED = {"evidence_role": "supporting", "conclusive": False, "failed": False}
_UNAVAILABLE = {"evidence_role": "unavailable", "conclusive": False, "failed": False}

_ATTESTED_GOOD = {"conclusive": True, "repair_verified": True}
_ATTESTED_BAD = {"conclusive": True, "repair_verified": False}
_ATTESTATION_MISSING = {"conclusive": False, "repair_verified": False}


# ── Instrumented path (unchanged behaviour) ──────────────────────────────────

def test_instrumented_all_three_confirm():
    out = _attribute(_TELEMETRY_FAILED, _NO_ATTESTATION, _SAME_FAMILY, _EXECUTED)
    assert out["genuine_failure"] is True
    assert out["primary_evidence"] == "telemetry_baseline"


def test_instrumented_telemetry_recovered_is_not_a_failure():
    assert _attribute(_TELEMETRY_RECOVERED, _NO_ATTESTATION, _SAME_FAMILY, _EXECUTED)["genuine_failure"] is False


def test_different_failure_family_is_counterfactual():
    """Original was a seal failure, new is electrical — never penalise the seal recommendation."""
    assert _attribute(_TELEMETRY_FAILED, _NO_ATTESTATION, _DIFF_FAMILY, _EXECUTED)["genuine_failure"] is False


def test_execution_deviation_is_not_a_recommendation_failure():
    """Recommended a replacement, the work order records a repack — that is an execution story."""
    assert _attribute(_TELEMETRY_FAILED, _NO_ATTESTATION, _SAME_FAMILY, _NOT_EXECUTED)["genuine_failure"] is False


# ── Brownfield path — the regression ─────────────────────────────────────────

def test_brownfield_asset_can_now_be_attributed():
    """
    REGRESSION. Uninstrumented asset, repair verified good at closeout, same failure family
    recurred, action executed as recommended → the recommendation is what failed.

    Before the fix this was unreachable: the uninstrumented branch returned `failed: False`
    into an unconditional AND, so `genuine_failure` was False no matter what the human recorded.
    """
    out = _attribute(_UNINSTRUMENTED, _ATTESTED_GOOD, _SAME_FAMILY, _EXECUTED)
    assert out["genuine_failure"] is True
    assert out["primary_evidence"] == "work_order_closeout_attestation"


def test_brownfield_without_attestation_concludes_nothing():
    """Absence of evidence is not evidence — a silent technician must not trigger a downgrade."""
    out = _attribute(_UNINSTRUMENTED, _ATTESTATION_MISSING, _SAME_FAMILY, _EXECUTED)
    assert out["genuine_failure"] is False
    assert out["conclusive"] is False


def test_brownfield_negative_attestation_is_a_repair_story():
    """Recorded as still faulty at closeout → the repair never restored it; not the recommendation."""
    assert _attribute(_UNINSTRUMENTED, _ATTESTED_BAD, _SAME_FAMILY, _EXECUTED)["genuine_failure"] is False


def test_unavailable_evidence_never_concludes():
    """Coverage lookup or historian down — decide nothing rather than defaulting to 'fine'."""
    out = _attribute(_UNAVAILABLE, _NO_ATTESTATION, _SAME_FAMILY, _EXECUTED)
    assert out["genuine_failure"] is False
    assert out["primary_evidence"] == "none"


# ── Attestation phrase classification ────────────────────────────────────────

def test_positive_attestation_needs_run_and_normal_result():
    out = _classify_attestation("Ran equipment 30 minutes at design load, no abnormal noise or vibration observed.")
    assert out["repair_verified"] is True and out["conclusive"] is True


def test_action_alone_is_not_a_verification():
    """'replaced the seal' is the action check's job — it says nothing about post-repair state."""
    out = _classify_attestation("Replaced mechanical seal FSL-2240A.")
    assert out["repair_verified"] is False
    assert out["conclusive"] is False, "must not be read as a negative attestation either"


def test_negative_wording_wins_over_positive():
    """'ran ... still vibrating' must never classify as a good repair on the run phrase alone."""
    out = _classify_attestation("Ran unit at design load, still excessive vibration on the drive end.")
    assert out["repair_verified"] is False
    assert out["conclusive"] is True and out["reason"] == "attestation_negative"


def test_empty_notes_are_inconclusive():
    assert _classify_attestation("")["reason"] == "no_close_notes"
    assert _classify_attestation("   ")["conclusive"] is False
