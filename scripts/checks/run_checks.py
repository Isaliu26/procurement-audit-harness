#!/usr/bin/env python3
"""Run the four QA checks and print one table and a verdict.

  run_checks.py [--root DIR] [--final]

Without --final the challenge rows of check_trace are PENDING (the challenger may still be
working) and the verdict is INTERIM. With --final, challenges.md must exist, cite evidence and
have no open row, and the verdict is READY FOR SIGN-OFF or BLOCKED.
Exit code: 0 all four pass, 1 any failure."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_numbers, check_quotes, check_samples, check_trace  # noqa: E402
from _util import REPO, safe_run  # noqa: E402

CHECKS = [("quotes", check_quotes.run), ("numbers", check_numbers.run), ("trace", check_trace.run),
          ("samples", check_samples.run)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--final", action="store_true")
    a = ap.parse_args(argv)
    results = [safe_run(n, f, Path(a.root), a.final) for n, f in CHECKS]

    w = 10
    print(f"{'Check':<{w}}| {'Result':<7}| {'Checked':>8} | {'Failures':>8} | {'Pending':>7}")
    print(f"{'-' * w}|{'-' * 8}|{'-' * 10}|{'-' * 10}|{'-' * 8}")
    for r in results:
        print(f"{r['name']:<{w}}| {'FAIL' if r['failures'] else 'PASS':<7}| {r['checked']:>8} | "
              f"{len(r['failures']):>8} | {len(r['pending']):>7}")
    for r in results:
        for x in r["failures"]:
            print(f"FAIL {r['name']}: {x}")
    for r in results:
        for x in r["pending"]:
            print(f"PENDING {r['name']}: {x}")
    for r in results:
        for x in r["notes"]:
            print(f"note {r['name']}: {x}")
    failed = [r["name"] for r in results if r["failures"]]
    if a.final:
        verdict = "READY FOR SIGN-OFF" if not failed else "BLOCKED"
    else:
        verdict = "INTERIM: ALL CHECKS PASS (challenge rows not yet required)" if not failed \
            else "INTERIM: FAIL"
    print(f"VERDICT: {verdict}" + (f" ({', '.join(failed)})" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
