#!/usr/bin/env python3
"""Check results against a known-correct eval case.

Two levels:
  1. Analysis: metrics, checks and flags computed from facts vs expected answers.
  2. Extraction (only with --facts): each extracted fact vs the gold facts file.

Usage:
    python scripts/run_eval.py evals/areit-2026-q1.json                  # uses gold facts
    python scripts/run_eval.py evals/areit-2026-q1.json --facts data/facts/areit/2026-Q1.facts.json

Exit code is 1 if anything fails, so this can run in CI.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from compute_metrics import compute  # noqa: E402


def compare_extraction(facts_doc, gold_doc):
    rows = []
    gold, got = gold_doc["facts"], facts_doc["facts"]
    for key, g in gold.items():
        x = got.get(key)
        if x is None:
            rows.append(("FAIL", f"fact {key}", "missing"))
            continue
        value_ok = abs(x["value"] - g["value"]) <= (1 if isinstance(g["value"], int) else 1e-6)
        page_ok = x.get("page") == g.get("page")
        if value_ok and page_ok:
            rows.append(("PASS", f"fact {key}", f"{x['value']:,} p.{x.get('page')}"))
        elif value_ok:
            rows.append(("WARN", f"fact {key}", f"value ok, page {x.get('page')} vs gold {g.get('page')}"))
        else:
            rows.append(("FAIL", f"fact {key}", f"{x['value']:,} vs gold {g['value']:,}"))
    if facts_doc["meta"].get("accounting_model") != gold_doc["meta"].get("accounting_model"):
        rows.append(("FAIL", "meta accounting_model", f"{facts_doc['meta'].get('accounting_model')} vs gold {gold_doc['meta'].get('accounting_model')}"))
    else:
        rows.append(("PASS", "meta accounting_model", gold_doc["meta"]["accounting_model"]))
    return rows


def compare_analysis(result, case):
    rows = []
    m = result["metrics"]
    for key, exp in case["expected_metrics"].items():
        got = m.get(key)
        if got is None:
            rows.append(("FAIL", f"metric {key}", "missing"))
        elif isinstance(exp["value"], str):
            ok = got == exp["value"]
            rows.append(("PASS" if ok else "FAIL", f"metric {key}", f"{got} (expected {exp['value']})"))
        else:
            ok = abs(got - exp["value"]) <= exp.get("tolerance", 0)
            shown = f"{got:,.0f}" if isinstance(exp["value"], int) else f"{got:,.4f}"
            rows.append(("PASS" if ok else "FAIL", f"metric {key}", f"{shown} (expected {exp['value']:,} ± {exp.get('tolerance', 0)})"))

    status = {c["id"]: c["status"] for c in result["checks"]}
    for cid in case.get("expected_checks_pass", []):
        ok = status.get(cid) == "pass"
        rows.append(("PASS" if ok else "FAIL", f"check {cid}", status.get(cid, "missing")))

    flagged = {fl["id"] for fl in result["flags"]}
    expected = set(case.get("expected_flags", []))
    for fid in sorted(expected):
        rows.append(("PASS" if fid in flagged else "FAIL", f"flag {fid}", "raised" if fid in flagged else "not raised"))
    for fid in sorted(flagged - expected):
        rows.append(("WARN", f"flag {fid}", "raised but not expected"))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("case", type=Path)
    parser.add_argument("--facts", type=Path, help="Extracted facts to test (default: the gold facts)")
    args = parser.parse_args()

    case = json.loads(args.case.read_text())
    gold_doc = json.loads(Path(case["gold_facts"]).read_text())
    facts_doc = json.loads(args.facts.read_text()) if args.facts else gold_doc

    rows = []
    if args.facts:
        rows += compare_extraction(facts_doc, gold_doc)
    rows += compare_analysis(compute(facts_doc), case)

    print(f"\nEval: {case['id']}  (facts: {args.facts or case['gold_facts']})\n")
    for status, name, detail in rows:
        print(f"  {status:<5} {name:<48} {detail}")
    fails = sum(r[0] == "FAIL" for r in rows)
    warns = sum(r[0] == "WARN" for r in rows)
    passes = sum(r[0] == "PASS" for r in rows)
    print(f"\n{passes} passed, {fails} failed, {warns} warnings")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
