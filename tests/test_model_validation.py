"""Layer-0 NER model-gate scoring — pure logic, no network.

Guards the partial (span-overlap) matcher that decides entity-F1 true positives: a model that
predicts a broader span ("FISCHER PUMPS LTD.") must still credit the ground-truth entity ("Fischer"),
while a stray short token ("18") must not spuriously match a longer tag ("PG-18").
"""

from workers.model_validation import _span_match


def test_exact_match():
    assert _span_match("EQ-101", "eq-101")            # case-insensitive exact


def test_prediction_wider_than_ground_truth():
    assert _span_match("FISCHER PUMPS LTD.", "fischer")          # gt contained in prediction
    assert _span_match("MERIDIAN HEAT TRANSFER SYSTEMS", "meridian")


def test_ground_truth_wider_than_prediction():
    assert _span_match("Ananya", "ananya iyer")       # prediction contained in gt (>=4 chars)


def test_short_token_does_not_spuriously_match():
    assert not _span_match("18", "pg-18")             # 2-char overlap must not match
    assert not _span_match("EQ", "eq-101")            # 2-char overlap must not match


def test_no_overlap():
    assert not _span_match("XV-203", "eq-101")
    assert not _span_match("", "eq-101")              # empty prediction never matches


# --- Model-gate wiring -------------------------------------------------------------
# Regression: NERService() took no model argument, so run_model_validation.py's
# --model-name (and the Celery gate's model_name) only *labelled* the result — the call
# always used NVIDIA_NIM_NER_MODEL. The gate reported an authoritative-looking F1
# attributed to a model it never invoked, and when the configured model was unreachable it
# scored the regex fallback instead.

def test_ner_service_honours_explicit_model():
    from api.services.ner import NERService

    svc = NERService(model="meta/llama-3.2-11b-vision-instruct")
    assert svc._nim_model == "meta/llama-3.2-11b-vision-instruct"


def test_ner_service_falls_back_to_env_model(monkeypatch):
    from api.services.ner import NERService

    monkeypatch.setenv("NVIDIA_NIM_NER_MODEL", "some/other-model")
    assert NERService()._nim_model == "some/other-model"


def test_model_gate_passes_its_model_to_the_ner_service():
    """The gate must score the model it was asked about, not whatever the env holds."""
    import inspect

    from scripts import run_model_validation
    from workers import model_validation

    for module in (run_model_validation, model_validation):
        src = inspect.getsource(module)
        assert "NERService(model=model_name)" in src, (
            f"{module.__name__} must construct NERService with the requested model"
        )


# =============================================================================
# Run validity — a gate that cannot tell a model score from a regex-fallback score
# is not a gate. Found 2026-08-22: 52 of 55 extractions returned 429/500 and the
# run was still written to history as `passed: true`. See status.md backlog #15.
# =============================================================================

class _StubNER:
    """Returns whatever path label it is told to, mimicking NERService's result dict."""

    def __init__(self, *paths: str):
        self._paths = list(paths)

    async def extract_entities(self, text, *args, **kwargs):
        return {"entities": [], "model": self._paths.pop(0)}


async def _drain(wrapper, n):
    for _ in range(n):
        await wrapper.extract_entities("x")


def test_all_model_paths_are_valid():
    import asyncio

    from api.services.ner import FallbackCountingNER

    w = FallbackCountingNER(_StubNER("nim", "nim", "ollama"))
    asyncio.run(_drain(w, 3))
    assert w.fallback_count == 0
    assert w.validity == "VALID"


def test_a_single_regex_fallback_makes_the_run_suspect():
    import asyncio

    from api.services.ner import FallbackCountingNER

    w = FallbackCountingNER(_StubNER("nim", "nim", "regex"))
    asyncio.run(_drain(w, 3))
    assert w.fallback_count == 1
    assert w.validity == "SUSPECT", "one fallback makes F1 a ceiling, not a measurement"


def test_the_observed_failure_shape_is_suspect():
    """The real run: almost everything fell through to regex, F1 still looked plausible."""
    import asyncio

    from api.services.ner import FallbackCountingNER

    w = FallbackCountingNER(_StubNER(*(["nim"] * 3 + ["regex"] * 52)))
    asyncio.run(_drain(w, 55))
    assert w.fallback_count == 52
    assert w.validity == "SUSPECT"


def test_baseline_skips_suspect_and_legacy_runs():
    """A SUSPECT run must never become the bar a later run is measured against, and rows
    written before `validity` existed are unusable rather than assumed good."""
    from workers.model_validation import _latest_valid_baseline

    rows = [
        {"details": {"validity": "SUSPECT", "f1": 0.73}},   # newest — the degraded run
        {"details": {"f1": 0.73}},                          # legacy: no validity key at all
        {"details": {"validity": "VALID", "f1": 0.805}},    # the one real measurement
    ]
    picked = _latest_valid_baseline(rows)
    assert len(picked) == 1
    assert picked[0]["details"]["f1"] == 0.805


def test_no_valid_baseline_yields_no_baseline_rather_than_a_bad_one():
    from workers.model_validation import _latest_valid_baseline

    assert _latest_valid_baseline([{"details": {"validity": "SUSPECT"}}]) == []
    assert _latest_valid_baseline([{"details": {}}]) == []
    assert _latest_valid_baseline([]) == []
    assert _latest_valid_baseline(None) == []


def test_a_document_is_extracted_once_per_run_not_once_per_partition():
    """The global pass and each asset-class pass share one cache. Before this, every document
    was extracted twice, doubling model calls and letting the global and per-class scores
    derive from two independent extractions that could disagree."""
    import asyncio

    from workers import model_validation

    calls: list[str] = []

    class _CountingNER:
        async def extract_entities(self, text, *args, **kwargs):
            calls.append(text)
            return {"entities": [], "model": "nim"}

    class _ES:
        async def search(self, index=None, body=None):
            doc_id = body["query"]["term"]["document_id"]
            return {"hits": {"hits": [{"_source": {"content": f"text of {doc_id}"}}]}}

    corpus = [
        {"document_id": "DOC-A", "entity_text": "EQ-101", "entity_type": "ASSET_TAG"},
        {"document_id": "DOC-B", "entity_text": "EQ-102", "entity_type": "ASSET_TAG"},
    ]
    class _Settings:
        ELASTICSEARCH_INDEX_DOCUMENTS = "kairos_documents"

    ner, es, settings = _CountingNER(), _ES(), _Settings()
    cache: dict = {}

    async def _run():
        await model_validation.evaluate(ner, es, corpus, settings, cache=cache)
        # the per-asset-class passes re-evaluate subsets of the same corpus
        for row in corpus:
            await model_validation.evaluate(ner, es, [row], settings, cache=cache)

    asyncio.run(_run())
    assert len(calls) == 2, f"expected one extraction per document, got {len(calls)}: {calls}"


def test_unindexed_rows_are_also_extracted_once_per_run():
    """The path taken when a document is missing from Elasticsearch. It dominates in practice
    and was re-extracting on every partition pass, which is most of what pushed a real run
    past the 540 s soft time limit."""
    import asyncio

    from workers import model_validation

    calls: list[str] = []

    class _CountingNER:
        async def extract_entities(self, text, *args, **kwargs):
            calls.append(text)
            return {"entities": [], "model": "nim"}

    class _EmptyES:
        async def search(self, index=None, body=None):
            return {"hits": {"hits": []}}  # nothing indexed

    class _Settings:
        ELASTICSEARCH_INDEX_DOCUMENTS = "kairos_documents"

    corpus = [{"document_id": "DOC-A", "entity_text": "EQ-101", "entity_type": "ASSET_TAG"}]
    ner, es, settings = _CountingNER(), _EmptyES(), _Settings()
    cache: dict = {}

    async def _run():
        await model_validation.evaluate(ner, es, corpus, settings, cache=cache)
        await model_validation.evaluate(ner, es, corpus, settings, cache=cache)

    asyncio.run(_run())
    assert len(calls) == 1, f"expected one extraction, got {len(calls)}"


# =============================================================================
# Taxonomy alignment. The corpus carried 12 `COMPONENT` labels — a type the prompt
# never requests — so 23% of it was unscoreable by construction, and each row also
# booked a false positive against whatever type the model gave the same span.
# Reported F1 0.6733; on the labels that were both annotated and requested it was ~0.92.
# =============================================================================

def test_ner_taxonomy_matches_the_prompt():
    """The exported label space and the prompt's list must not drift — the gate uses the
    constant to decide what is scoreable, so a type in one and not the other silently
    mis-scores the model in whichever direction the mismatch runs."""
    from api.services import ner

    for etype in ner.NER_ENTITY_TYPES:
        assert f"- {etype}:" in ner._NER_PROMPT, f"{etype} is exported but not requested in the prompt"

    import re as _re
    in_prompt = set(_re.findall(r"^- ([A-Z_]+):", ner._NER_PROMPT, _re.MULTILINE))
    assert in_prompt == set(ner.NER_ENTITY_TYPES), (
        f"prompt/constant drift: prompt-only={in_prompt - set(ner.NER_ENTITY_TYPES)}, "
        f"constant-only={set(ner.NER_ENTITY_TYPES) - in_prompt}"
    )


def test_labels_outside_the_taxonomy_are_excluded_not_scored_as_failures():
    """A ground-truth type the extractor is never asked for is a corpus gap, not a miss."""
    import asyncio

    from workers import model_validation

    class _NER:
        async def extract_entities(self, text, *args, **kwargs):
            # finds the span and calls it MATERIAL — plausible, but the corpus says COMPONENT
            return {"entities": [{"text": "bearing", "entity_type": "MATERIAL"}], "model": "nim"}

    class _EmptyES:
        async def search(self, index=None, body=None):
            return {"hits": {"hits": []}}

    class _Settings:
        ELASTICSEARCH_INDEX_DOCUMENTS = "kairos_documents"

    corpus = [
        {"document_id": "DOC-A", "entity_text": "bearing", "entity_type": "COMPONENT"},
        {"document_id": "DOC-A", "entity_text": "EQ-101", "entity_type": "ASSET_TAG"},
    ]
    out = asyncio.run(model_validation.evaluate(_NER(), _EmptyES(), corpus, _Settings(), cache={}))

    assert out["unscoreable_labels"] == 1
    assert out["unscoreable_by_type"] == {"COMPONENT": 1}
    assert out["scored_labels"] == 1, "only the ASSET_TAG row is measurable"
    # and critically: no false positive was booked against MATERIAL for the excluded row
    assert "MATERIAL" not in out["by_entity_type"], (
        "an out-of-taxonomy ground-truth label must not also penalise the type the model chose"
    )


def test_document_type_partition_is_free_in_model_calls():
    """Per-document-type is the cut the problem statement asks for. It must ride the shared
    run cache — a partition that re-extracts would multiply model calls by the number of types
    and is exactly what pushed a real run past the Celery time limit."""
    import asyncio

    from workers import model_validation

    calls: list[str] = []

    class _NER:
        async def extract_entities(self, text, *args, **kwargs):
            calls.append(text)
            return {"entities": [], "model": "nim"}

    class _EmptyES:
        async def search(self, index=None, body=None):
            return {"hits": {"hits": []}}

    class _Settings:
        ELASTICSEARCH_INDEX_DOCUMENTS = "kairos_documents"

    corpus = [
        {"document_id": "DOC-A", "entity_text": "EQ-101", "entity_type": "ASSET_TAG"},
        {"document_id": "DOC-B", "entity_text": "EQ-102", "entity_type": "ASSET_TAG"},
    ]
    cache: dict = {}

    async def _run():
        await model_validation.evaluate(_NER(), _EmptyES(), corpus, _Settings(), cache=cache)
        # asset-class pass, then document-type pass, over the same rows
        for _ in range(2):
            for row in corpus:
                await model_validation.evaluate(_NER(), _EmptyES(), [row], _Settings(), cache=cache)

    asyncio.run(_run())
    assert len(calls) == 2, f"three partition passes must reuse one extraction each, got {len(calls)}"
