"""
Document submission-pattern audit — `ARCHITECTURE.md §8` anti-poisoning mitigation 3.

Poisoning through ingestion needs volume. A single falsified document is what the human
promotion gate exists for; what that gate cannot see is a source account quietly submitting far
more than its peers, because it reviews documents one at a time and never looks at the shape of
who is submitting.

REPORTS, NEVER BLOCKS. A legitimate bulk import and an attack look identical from here — the
output is a prompt for a human to ask why, not a verdict. Exits 0 even when it flags.

Deliberately a script, not an endpoint: a new read route would need a matching action in
`kairos.rego` **and** in `_sensitive_actions`, or the catch-all would grant it to every role.
That is real authorization surface to add for a control nobody needs in the UI.

    docker compose run --rm --no-deps kairos-backend-api python scripts/audit_submission_patterns.py
    ... --days 30
"""

import argparse
import sys
from datetime import UTC, datetime, timedelta

from supabase import create_client

from api.config import Settings
from api.services.supply_chain import submission_pattern_outliers


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=0,
                    help="only consider documents ingested in the last N days (0 = all time)")
    args = ap.parse_args()

    settings = Settings()
    sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

    q = sb.table("documents").select("document_id, ingested_by, ingested_at, source_system")
    if args.days:
        q = q.gte("ingested_at", (datetime.now(UTC) - timedelta(days=args.days)).isoformat())
    rows = q.execute().data or []

    scope = f"last {args.days} days" if args.days else "all time"
    print(f"\nDOCUMENT SUBMISSION PATTERN AUDIT — {scope}")
    print(f"  documents considered: {len(rows)}")

    report = submission_pattern_outliers([r.get("ingested_by") or "" for r in rows])
    print(f"  submitting accounts : {report['accounts']}")
    print(f"  verdict             : {report['verdict']}")

    if report["verdict"] == "insufficient_accounts":
        print(f"\n  {report['note']}")
        return 0

    print(f"  median per account  : {report['median_per_account']}")
    print(f"  flag threshold      : {report['threshold']}")

    if not report["flagged"]:
        print("\n  No account submits at an unusual rate relative to its peers.")
        return 0

    print("\n  FLAGGED — ask why, do not assume:")
    for f in report["flagged"]:
        print(f"    {f['submitted_by']:44} {f['count']:>5} documents "
              f"(median {f['median']}, threshold {f['threshold']})")
    print("\n  A bulk import, a connector service account and an attack are indistinguishable")
    print("  from this signal alone. Correlate with `source_system` and the audit log before acting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
