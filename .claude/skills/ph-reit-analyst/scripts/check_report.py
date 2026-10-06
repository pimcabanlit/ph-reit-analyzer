#!/usr/bin/env python3
"""Check a finished report against the skill's rules before handing it over.

Checks:
  1. Every section required by references/report-template.md is present.
  2. The report ends with the disclaimer.
  3. No buy / sell / hold style recommendation.
  4. Every number in the report traces back to metrics.json or the facts file
     (so no number was made up or computed in prose).
  5. Every flag and every non-skipped check has its own line in the report.
  6. Every source in the earnings-to-dividend table that cites a page also
     quotes the phrase to search for in the PDF, e.g. p.7 · "NET INCOME".
  7. The bridge chart is embedded under "From earnings to dividend" and the
     image file exists next to the report.
  8. If metrics.json has a derived quarter, the report shows its coverage and
     labels it "derived".

Usage:
    python <skill-dir>/scripts/check_report.py <report.md> --metrics <metrics.json> --facts <facts.json>

Exit code is 1 if anything fails.
"""
import argparse
import json
import re
import sys
from pathlib import Path

DISCLAIMER = "For learning and research only. Not investment advice."

REQUIRED_SECTIONS = [
    "**In one sentence:**",
    "**Dividend safety:**",
    "## Worth knowing",
    "## From earnings to dividend",
    "## Checks",
    "## Other figures",
]

RECOMMENDATION_PATTERNS = [
    r"\b(should|must|recommend(?:ed|s)?|advise[sd]?|suggest(?:ed|s)?)\s+(?:you\s+|investors\s+|to\s+)?(buy|sell|hold|accumulate|avoid)\b",
    r"\b(good|great|strong|solid|bad)\s+(buy|sell|investment|pick)\b",
    r"\b(buy|sell|hold)\s+(rating|recommendation|call|signal)\b",
    r"\b(time to|worth)\s+(buy|sell)ing\b",
    r"\b(buy|sell|hold)\s+(it|the stock|the shares|now)\b",
]

# Numbers the template and rules use as fixed reference points
ALLOWED_CONSTANTS = [1.00, 1.05, 90, 0.90]

NUMBER = re.compile(r"(?<![\w.])(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+)(?![\d])")
PAGE_REF = re.compile(r"p\.\s*$")


def collect_numbers(obj, out):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, str):
        # Flag and check details carry derived numbers, e.g. "rose 41,129,305"
        out.extend(float(t.replace(",", "")) for t in re.findall(r"\d[\d,]*(?:\.\d+)?", obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            collect_numbers(v, out)


def candidates(values):
    """Each source value as it might appear: as is, in millions, or as a percent."""
    out = set()
    for v in values + ALLOWED_CONSTANTS:
        a = abs(v)
        out.update((a, a / 1e6, a * 100))
    return out


def traces_back(token, cands):
    decimals = len(token.split(".")[1]) if "." in token else 0
    target = float(token.replace(",", ""))
    step = 10 ** -decimals
    return any(abs(round(c, decimals) - target) < step / 2 for c in cands)


def section(text, heading):
    start = text.find(heading)
    if start < 0:
        return ""
    rest = text[start + len(heading):]
    nxt = re.search(r"^## |^---", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def check(report, metrics, facts, report_dir=None):
    rows = []

    for s in REQUIRED_SECTIONS:
        rows.append(("PASS" if s in report else "FAIL", f"section {s}", "present" if s in report else "missing"))

    ends_ok = report.rstrip().endswith(DISCLAIMER)
    rows.append(("PASS" if ends_ok else "FAIL", "disclaimer", "report ends with it" if ends_ok else f"must end with: {DISCLAIMER}"))

    hits = [m.group(0) for p in RECOMMENDATION_PATTERNS for m in re.finditer(p, report, re.I)]
    rows.append(("FAIL" if hits else "PASS", "no recommendation", f"found: {hits}" if hits else "none found"))

    values = []
    collect_numbers(metrics, values)
    collect_numbers(facts.get("facts", {}), values)
    collect_numbers(facts.get("dividends", []), values)
    cands = candidates(values)
    untraced = []
    for line_no, line in enumerate(report.splitlines(), 1):
        for m in NUMBER.finditer(line):
            if PAGE_REF.search(line[: m.start()]):
                continue
            if not traces_back(m.group(0), cands):
                untraced.append(f"{m.group(0)} (line {line_no})")
    rows.append(("FAIL" if untraced else "PASS", "numbers trace to metrics/facts",
                 "untraced: " + ", ".join(untraced) if untraced else "all numbers found"))

    bullets = lambda body: len(re.findall(r"^\s*[-*] ", body, re.M))  # noqa: E731
    n_flags = len(metrics.get("flags", []))
    got = bullets(section(report, "## Worth knowing"))
    ok = got >= n_flags
    rows.append(("PASS" if ok else "FAIL", "every flag explained", f"{got} bullets for {n_flags} flags"))

    table = section(report, "## From earnings to dividend")
    unquoted = [row.split("|")[1].strip() for row in table.splitlines()
                if row.startswith("|") and re.search(r"p\.\s*\d", row) and not re.search(r"p\.\s*\d+[^|]*[\"“][^\"”|]+[\"”]", row)]
    rows.append(("FAIL" if unquoted else "PASS", "sources quote a search phrase",
                 "missing for: " + "; ".join(unquoted) if unquoted else "all page citations quoted"))

    image = re.search(r"!\[[^\]]*\]\(([^)\s]+\.png)\)", table)
    if not image:
        rows.append(("FAIL", "bridge chart embedded", "no ![...](bridge.png) under From earnings to dividend"))
    elif report_dir is not None and not (Path(report_dir) / image.group(1)).exists():
        rows.append(("FAIL", "bridge chart embedded", f"{image.group(1)} not found next to the report"))
    else:
        rows.append(("PASS", "bridge chart embedded", image.group(1)))

    dq = metrics.get("metrics", {}).get("derived_quarter")
    if dq and dq.get("affo_coverage") is not None:
        shown = f"{dq['affo_coverage']:.2f}x" in report and re.search(r"\bderived\b", report, re.I)
        rows.append(("PASS" if shown else "FAIL", "derived quarter shown",
                     f"{dq['period']} {dq['affo_coverage']:.2f}x labeled derived" if shown
                     else f"report must show {dq['period']} coverage {dq['affo_coverage']:.2f}x and call it derived"))

    n_checks = sum(c["status"] != "skipped" for c in metrics.get("checks", []))
    got = bullets(section(report, "## Checks"))
    ok = got >= n_checks
    rows.append(("PASS" if ok else "FAIL", "every check listed", f"{got} lines for {n_checks} checks"))

    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("report", type=Path)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--facts", type=Path, required=True)
    args = parser.parse_args()

    rows = check(args.report.read_text(), json.loads(args.metrics.read_text()), json.loads(args.facts.read_text()),
                 report_dir=args.report.parent)
    for status, name, detail in rows:
        print(f"  {status:<5} {name:<34} {detail}")
    fails = sum(r[0] == "FAIL" for r in rows)
    print(f"\n{len(rows) - fails} passed, {fails} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
