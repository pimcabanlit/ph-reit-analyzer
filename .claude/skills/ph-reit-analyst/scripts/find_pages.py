#!/usr/bin/env python3
"""Find the pages to read, using the index made by index_pages.py.

Two ways to use it:

  1. Search for terms (regular expressions, case-insensitive). Pages whose
     section heading matches come first, then pages whose text matches,
     with one line of context each.
  2. --preset quarterly | annual: look up every standard fact group at once
     (statements, distributable income, dividends, notes, ...) and print a
     short "where to look" list.

Appraisal reports, reinvestment progress reports, agreed-upon procedures and
sustainability sections are skipped unless --all is given, so their hundreds
of pages don't drown the financial statements.

Usage:
    python <skill-dir>/scripts/find_pages.py <index.json> "Distributable income" "Cash dividends"
    python <skill-dir>/scripts/find_pages.py <index.json> --preset annual
"""
import argparse
import json
import re
import sys
from pathlib import Path

SKIPPED_SECTIONS = {"appraisal", "procedures", "reinvestment", "sustainability"}
SECTION_START_LINES = 8

# Fact group -> (heading pattern, text pattern); either may be None
PRESETS = {
    "quarterly": [
        ("Balance sheet", r"Statements? of Financial Position", None),
        ("Income statement", r"Statements? of Comprehensive Income", None),
        ("Cash flow statement", r"Statements? of Cash Flows", None),
        ("Notes: receivables (accrued rent, finance leases)", r"\d+\.? Receivables", None),
        ("Notes: investment properties (accounting model)", r"\d+\.? Investment Propert", None),
        ("Notes: equity (shares, swaps, dividends)", r"\d+\.? Equity", None),
        ("Distributable income", r"Distributable Income", r"Distributable income"),
        ("Dividends declared", r"(?:Cash )?Dividends?", r"per (?:outstanding )?(?:common )?share"),
        ("Events after the reporting date", r"(?:\d+\.? )?Events? After", None),
        ("MD&A (net income before fair value change)", r"Management[’']?s Discussion", r"before the net fair value change"),
        ("NAV per share and market price", r"Key Performance Indicators|Market Information", r"Net asset value"),
        ("Cover (shares outstanding, period)", r"SEC FORM 17-[AQ]", None),
        ("Corporate information (sponsor ownership)", r"\d*\.? ?Corporate Information", r"owned by"),
        ("Material subsequent events (Part II / Item 14)", None, r"Material events subsequent|events? subsequent to the end"),
    ],
}
PRESETS["annual"] = PRESETS["quarterly"] + [
    ("Fair value change breakdown (appraisal, straight-line, lease commissions)", None, r"Lease commissions"),
    ("Fair values of financial instruments (finance lease receivables)", None, r"Carrying value\s+Fair value"),
    ("Appraisal method and discount rates", None, r"Discount rate"),
    ("Retained earnings available for dividends", r"Reconciliation of Retained Earnings", None),
    ("Financial soundness indicators (interest coverage)", r"Financial Soundness Indicators", None),
    ("Property table (valuation, occupancy)", r"Property Performance", None),
]


def sections(index):
    """The section kind each page belongs to: the last section start seen so far.

    Only headings near the top of a page start a section; a list that mentions
    "Reinvestment Plan" halfway down a page doesn't.
    """
    current, out = None, {}
    for p in index["pages"]:
        kinds = [lm["kind"] for lm in p["landmarks"]
                 if lm["kind"] not in ("note", "dividends", "distributable", "item", "part") and lm.get("line", 0) < SECTION_START_LINES]
        if kinds:
            current = kinds[-1]
        out[p["page"]] = current
    return out


def note_end(index, page):
    """Last page that can hold the note starting on `page`: the page where the next note starts.

    Notes often end mid-page, so that page is included.
    """
    for p in index["pages"][page:]:
        if any(lm["kind"] in ("note", "schedule", "appraisal") for lm in p["landmarks"]):
            return p["page"]
    return page


def search(index, heading=None, text=None, include_all=False, limit=6):
    section_of = sections(index)
    heading_rx = re.compile(heading, re.I) if heading else None
    text_rx = re.compile(text, re.I) if text else None
    hits = []
    for p in index["pages"]:
        if not include_all and section_of[p["page"]] in SKIPPED_SECTIONS:
            continue
        if heading_rx:
            for lm in p["landmarks"]:
                if heading_rx.search(lm["text"]):
                    span = ""
                    if lm["kind"] == "note" and (end := note_end(index, p["page"])) > p["page"]:
                        span = f" (continues to p.{end})"
                    hits.append((0, p["page"], f"[{lm['kind']}] {lm['text']}{span}"))
                    break
        is_listing = any(lm["kind"] == "contents" for lm in p["landmarks"])  # tables of contents just repeat headings
        if text_rx and not is_listing and not any(h[1] == p["page"] for h in hits):
            for line in p["text"].splitlines():
                if text_rx.search(line):
                    hits.append((1, p["page"], line.strip()[:110]))
                    break
            else:
                joined = re.sub(r"\s+", " ", p["text"])
                if m := text_rx.search(joined):
                    hits.append((1, p["page"], joined[max(0, m.start() - 40):m.end() + 60]))
    hits.sort()
    return hits[:limit], len(hits)


def page_note(index, page):
    p = index["pages"][page - 1]
    return {"none": " (no text layer: read visually)", "garbled": " (unreadable text)"}.get(p["quality"], "")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("index", type=Path)
    parser.add_argument("terms", nargs="*", help="Regular expressions to search for")
    parser.add_argument("--preset", choices=sorted(PRESETS))
    parser.add_argument("--all", action="store_true", help="Also search appraisal, reinvestment and similar sections")
    parser.add_argument("--limit", type=int, default=6, help="Pages to show per search")
    args = parser.parse_args()
    if not args.terms and not args.preset:
        parser.error("give search terms or --preset")

    index = json.loads(args.index.read_text())
    searches = [(name, h, t) for name, h, t in PRESETS[args.preset]] if args.preset else []
    searches += [(term, term, term) for term in args.terms]
    for name, heading, text in searches:
        hits, total = search(index, heading, text, args.all, args.limit)
        more = f" (+{total - len(hits)} more)" if total > len(hits) else ""
        print(f"\n{name}:{more}")
        if not hits:
            print("  not found")
        for rank, page, context in hits:
            kind = "heading" if rank == 0 else "text"
            print(f"  p.{page:<4} {kind:<7} {context}{page_note(index, page)}")
    pages = sorted({page for name, h, t in searches for _, page, _ in search(index, h, t, args.all, args.limit)[0]})
    tokens = sum(index["pages"][p - 1]["tokens_est"] for p in pages)
    print(f"\nReading all {len(pages)} pages listed above: ~{tokens:,} tokens "
          f"(the whole filing is ~{index['tokens_est']:,}).")


if __name__ == "__main__":
    sys.exit(main())
