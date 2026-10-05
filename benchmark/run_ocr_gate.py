"""
OCR accuracy gate — Layer 0's extension to the OCR artifact.

Scores the OCR path against the ground-truth pairings the golden dataset already declares in
`dataset/00_Reference/dataset_manifest.csv`:

    scanned_oem_bulletin_degraded.png  <- oem_bulletin_fp_sb_2025_04.pdf   ("same content as file 6")
    scanned_inspection_degraded.png    <- insp_he301_2025_q4.pdf           ("same content as file 12")
    handwritten_shift_log.png          <- shift_log.txt                    ("same 2 events as files 22/23")
    handwritten_inspection_note.png    <- shift_log.txt

The metric is **recall of operationally salient tokens** — asset tags, measurements with units,
standards references, dates — not character error rate. See `api/services/ocr_gate.py` for why.

COST
  **Zero model calls. This harness is read-only.** It compares text already indexed in
  Elasticsearch — the image document's against its clean sibling's — and touches Supabase only with
  a SELECT on `documents`. It is free to run and safe to run alongside anything.

  The corollary is the part that matters: **fixing `services/ocr.py` does not change this gate's
  output on its own.** The gate reads what ingestion already indexed, so a document ingested while
  OCR was broken stays UNSCOREABLE until its text is re-extracted and re-indexed. There is no
  reprocess endpoint, and `POST /documents/ingest` dedups on SHA-256, so re-uploading the same bytes
  returns `{"status": "duplicate"}` and does nothing.

REPORTS, DOES NOT BLOCK
  Consistent with `MODEL_GATE_ENFORCE=False`: this prints numbers and exits 0 even on a poor
  score. Handwriting is a documented Layer 3 limitation ("no separate handwriting model"), so a
  low handwriting recall here is the expected reading of a known gap, not a new regression.

    docker compose run --rm --no-deps kairos-backend-api python benchmark/run_ocr_gate.py
"""

import asyncio
import sys

sys.path.insert(0, "/app")

# image filename -> the clean sibling whose extracted text is the reference
PAIRINGS: dict[str, str] = {
    "scanned_oem_bulletin_degraded.png": "oem_bulletin_fp_sb_2025_04.pdf",
    "scanned_inspection_degraded.png": "insp_he301_2025_q4.pdf",
    "handwritten_shift_log.png": "shift_log.txt",
    "handwritten_inspection_note.png": "shift_log.txt",
}

# Handwriting has no dedicated model in this deployment. Grouped so a weak score reads as the
# recorded Layer 3 limitation rather than an unexplained regression.
HANDWRITTEN = {"handwritten_shift_log.png", "handwritten_inspection_note.png"}


async def _text_for(es, settings, document_id: str) -> str:
    resp = await es.search(
        index=settings.ELASTICSEARCH_INDEX_DOCUMENTS,
        body={"query": {"term": {"document_id": document_id}},
              "_source": ["content", "text"], "size": 1},
    )
    hits = resp["hits"]["hits"]
    src = hits[0]["_source"] if hits else {}
    return src.get("content") or src.get("text") or ""


async def main() -> int:
    from elasticsearch import AsyncElasticsearch
    from supabase import create_client

    from api.config import Settings
    from api.services.ocr_gate import score_ocr

    settings = Settings()
    sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

    wanted = set(PAIRINGS) | set(PAIRINGS.values())
    rows = sb.table("documents").select("document_id, file_name, status").execute().data or []
    by_name = {r["file_name"]: r["document_id"] for r in rows
               if r.get("status") == "active" and r["file_name"] in wanted}

    es_kwargs: dict = {"hosts": [settings.ELASTICSEARCH_URL]}
    if settings.ELASTICSEARCH_USERNAME:
        es_kwargs["basic_auth"] = (settings.ELASTICSEARCH_USERNAME, settings.ELASTICSEARCH_PASSWORD)
    es = AsyncElasticsearch(**es_kwargs)

    print("\nOCR ACCURACY GATE — recall of operationally salient tokens")
    print("  reference = the clean sibling declared in dataset_manifest.csv\n")

    results = []
    try:
        for image, reference in PAIRINGS.items():
            img_id, ref_id = by_name.get(image), by_name.get(reference)
            if not img_id or not ref_id:
                print(f"  {image:38} SKIPPED — {'image' if not img_id else 'reference'} not in the vault")
                continue

            ref_text = await _text_for(es, settings, ref_id)
            ocr_text = await _text_for(es, settings, img_id)

            if not ref_text.strip():
                print(f"  {image:38} SKIPPED — reference has no indexed text")
                continue
            if not ocr_text.strip():
                # NOT a score of 0. "The OCR path produced nothing" and "the OCR path produced
                # wrong text" are different failures, and averaging the first into a recall
                # number reports an accuracy problem when the truth is that nothing ran or
                # nothing was indexed. Same discipline as the model gate excluding labels it
                # cannot score: measure the artifact, or say you could not.
                print(f"  {image:38} UNSCOREABLE — no OCR text indexed (nothing to score)")
                results.append((image, {"scoreable": False, "reason": "no_ocr_text"}))
                continue

            score = score_ocr(ref_text, ocr_text)
            if not score["scoreable"]:
                print(f"  {image:38} UNSCOREABLE — the reference carries no salient tokens")
                continue

            kind = "handwritten" if image in HANDWRITTEN else "scanned"
            print(f"  {image:38} {score['salient_recall']:.4f}  "
                  f"({score['recovered_tokens']}/{score['expected_tokens']} tokens, {kind})")
            for cls, v in score["by_class"].items():
                if v["expected"]:
                    print(f"      {cls:14} {v['recovered']}/{v['expected']}")
            if score["missed_tokens"]:
                print(f"      missed: {', '.join(score['missed_tokens'][:8])}")
            results.append((image, score))
    finally:
        await es.close()

    scored = [(n, s) for n, s in results if s.get("scoreable")]
    unscored = [(n, s) for n, s in results if not s.get("scoreable")]
    if unscored:
        print(f"\n  {len(unscored)} image(s) produced NO OCR text and are excluded from the means:")
        for n, s in unscored:
            print(f"    {n}  ({s.get('reason', 'unscoreable')})")
        print("  That is an ingestion/indexing finding, not an OCR accuracy finding — the OCR")
        print("  path emitted nothing for them, so there is no transcription to grade.")
    if not scored:
        print("\n  NOTHING SCOREABLE. The gate is working; the OCR path is not producing indexed")
        print("  text for any paired image. Fix that before reading anything into OCR accuracy.")
        return 0

    hw = [s["salient_recall"] for n, s in scored if n in HANDWRITTEN]
    sc = [s["salient_recall"] for n, s in scored if n not in HANDWRITTEN]
    print("\n  scanned (degraded)   mean recall:", f"{sum(sc)/len(sc):.4f}" if sc else "n/a")
    print("  handwritten          mean recall:", f"{sum(hw)/len(hw):.4f}" if hw else "n/a")
    print("\n  Handwriting is a recorded Layer 3 limitation (no separate handwriting model), so a")
    print("  low score there is the known gap being measured, not a new regression. Recall is the")
    print("  safety-relevant direction: a dropped pressure limit is the failure this catches.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
