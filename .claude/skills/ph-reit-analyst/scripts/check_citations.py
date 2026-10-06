#!/usr/bin/env python3
"""Confirm every fact can be found in the filing where the facts file says.

For each fact (and each entry in the dividends list), opens the cited page of
the PDF and checks two things:
  1. The label appears on the page, so a reader can search the PDF for it.
  2. The value appears on the page (as printed: with commas, in millions for
     rounded figures, or with two decimals for per-share amounts and percents).

Whitespace and capitalization are ignored when matching. Uses meta.source_file
unless a PDF is given.

Usage:
    python <skill-dir>/scripts/check_citations.py <facts.json> [--pdf <filing.pdf>]

Exit code is 1 if any label or value is not found on its page.
"""
import argparse
import json
import re
import sys
from pathlib import Path


def normalize(text):
    return re.sub(r"\s+", " ", text.replace("₱", "P")).strip().lower()


def printed_forms(value, rounded, unit="million"):
    """Ways the filing may print this value."""
    forms = set()
    if rounded:
        scale = 1e9 if unit == "billion" else 1e6
        forms.update({f"{abs(value) / scale:,.2f}", f"{abs(value) / scale:,.1f}"})
    if float(value).is_integer() and abs(value) >= 1000:
        forms.add(f"{abs(value):,.0f}")
    elif abs(value) >= 1000:
        forms.add(f"{abs(value):,.2f}")
    else:
        forms.add(f"{value:.2f}")
    return forms


def iter_facts(doc):
    for key, item in doc.get("facts", {}).items():
        yield key, item
    for section, name_key in (("dividends", "for_period"), ("trailing_dividends", "for_period"),
                              ("share_issuances", "property"), ("share_issuance_totals", "year"),
                              ("subsequent_events", "date")):
        for entry in doc.get(section, []):
            for key, item in entry.items():
                if isinstance(item, dict) and "value" in item:
                    yield f"{section} {entry.get(name_key, '?')} {key}", item


def check(doc, page_text):
    """page_text: function taking a 1-based PDF page index, returning its text."""
    rows = []
    for key, item in iter_facts(doc):
        index = item.get("pdf_page") or item.get("page")
        try:
            text = normalize(page_text(index))
        except IndexError:
            rows.append(("FAIL", key, f"page {index} is not in the PDF"))
            continue
        label = item.get("label")
        if not label:
            rows.append(("FAIL", key, f"no label to search for on p.{item.get('page')}"))
        elif normalize(label) not in text:
            rows.append(("FAIL", key, f"label not found on p.{item.get('page')}: \"{label}\""))
        else:
            rows.append(("PASS", key, f"p.{item.get('page')} \"{label}\""))
        forms = printed_forms(item["value"], item.get("rounded"), item.get("unit", "million"))
        if not any(normalize(form) in text for form in forms):
            rows.append(("FAIL", f"{key} value", f"{' or '.join(sorted(forms))} not found on p.{item.get('page')}"))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("facts", type=Path)
    parser.add_argument("--pdf", type=Path, help="Filing PDF (default: meta.source_file)")
    args = parser.parse_args()

    import pdfplumber  # only this script needs the PDF library

    doc = json.loads(args.facts.read_text())
    pdf_path = args.pdf or Path(doc["meta"]["source_file"])
    with pdfplumber.open(pdf_path) as pdf:
        cache = {}

        def page_text(index):
            if index < 1 or index > len(pdf.pages):
                raise IndexError(index)
            if index not in cache:
                cache[index] = pdf.pages[index - 1].extract_text() or ""
            return cache[index]

        rows = check(doc, page_text)

    for status, name, detail in rows:
        print(f"  {status:<5} {name:<45} {detail}")
    fails = sum(r[0] == "FAIL" for r in rows)
    print(f"\n{pdf_path}: {len(rows) - fails} passed, {fails} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
