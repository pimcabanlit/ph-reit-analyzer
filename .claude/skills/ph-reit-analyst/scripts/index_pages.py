#!/usr/bin/env python3
"""Index a filing PDF page by page so only the pages that matter get read.

Big filings (a 17-A can run to 700 pages and 300,000+ tokens) must never be
read whole. This script extracts every page's text once, saves it to an index
file, and prints a short map of the document:

- landmarks: pages that start a known section (statements, notes, MD&A,
  dividends, appraisal reports, ...);
- runs of pages sharing a running header (e.g. 39 appraisal reports);
- pages with no text layer (scanned) or unreadable text;
- the form type and period from the cover.

Then use find_pages.py to look up where each fact lives, and read only those
pages. Uses pymupdf (fast); falls back to pdfplumber.

Usage:
    python <skill-dir>/scripts/index_pages.py <filing.pdf> [-o <index.json>]

Writes <filing>.index.json next to the PDF unless -o is given.
"""
import argparse
import json
import re
import sys
from pathlib import Path

LARGE_FILING_PAGES = 150

# Section starts found at the beginning of a line (case-insensitive)
LANDMARKS = [
    ("cover", r"SEC FORM 17-[AQ]\b"),
    ("cover", r"C\s*O\s*V\s*E\s*R\s+S\s*H\s*E\s*E\s*T"),
    ("contents", r"TABLE OF CONTENTS"),
    ("contents", r"INDEX TO (?:EXHIBITS|SUPPLEMENTARY SCHEDULES|FINANCIAL STATEMENTS)"),
    ("part", r"PART\s+[IVX]+\s*[-–—]"),
    ("item", r"Item\s+\d+\.\s+[A-Z]"),
    ("auditor", r"Independent Auditor[’']?s Report"),
    ("statement", r"(?:Unaudited\s+)?(?:Interim\s+)?(?:Condensed\s+)?Statements? of Financial Position"),
    ("statement", r"(?:Unaudited\s+)?(?:Interim\s+)?(?:Condensed\s+)?Statements? of Comprehensive Income"),
    ("statement", r"(?:Unaudited\s+)?(?:Interim\s+)?(?:Condensed\s+)?Statements? of Changes in Equity"),
    ("statement", r"(?:Unaudited\s+)?(?:Interim\s+)?(?:Condensed\s+)?Statements? of Cash Flows"),
    ("notes", r"Notes to (?:the )?(?:Unaudited )?(?:Interim )?(?:Condensed )?Financial Statements"),
    ("mdna", r"(?:Item \d+\.\s*)?Management[’']?s Discussion and Analysis"),
    ("dividends", r"(?:\(\w\)\s*)?(?:Cash )?Dividends?(?: policy)?$"),
    ("distributable", r"Distributable Income"),
    ("events", r"(?:\d+\.?\s*)?Events? After"),
    ("market", r"Market Information"),
    ("kpi", r"(?:III\.\s*)?Key Performance Indicators"),
    ("kpi", r"Financial Soundness Indicators"),
    ("schedule", r"Schedule [A-H]\b"),
    ("schedule", r"Reconciliation of Retained Earnings"),
    ("property", r"Property Performance"),
    ("appraisal", r"MARKET VALUE APPRAISAL"),
    ("procedures", r"Agreed-Upon Procedures Report"),
    ("reinvestment", r"(?:Summary of )?(?:Quarterly |Final )?(?:Progress Report|Reinvestment Plan)\b"),
    ("sustainability", r"Sustainability Report"),
]
LANDMARK_RES = [(kind, re.compile(r"^\s*" + pattern, re.I)) for kind, pattern in LANDMARKS]
MAX_HEADING_LENGTH = 110
# Numbered note headings, e.g. "5 Investment properties" or "12. Equity"; only looked for inside the notes
NOTE_HEADING = re.compile(r"^\s*(\d{1,2})\.?\s+([A-Z][A-Za-z ,\-&()’']{3,70})$")
NOTES_END_KINDS = {"schedule", "appraisal", "mdna", "procedures", "sustainability"}
PRINTED_PAGE = re.compile(r"^\s*(?:Page\s+)?(\d{1,3})(?:\s+of\s+\d+)?\s*$", re.I)


def extract(pdf_path):
    """Text of every page, using pymupdf when available."""
    try:
        import pymupdf
        with pymupdf.open(pdf_path) as doc:
            return [page.get_text() for page in doc], "pymupdf"
    except ImportError:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            return [page.extract_text() or "" for page in pdf.pages], "pdfplumber"


def text_quality(text):
    stripped = text.strip()
    if len(stripped) < 20:
        return "none"
    odd = sum(1 for ch in stripped if not (ch.isalnum() or ch.isspace() or ch in ".,;:()[]%/-–—&'’\"“”₱$#*•@!?+=_<>"))
    return "garbled" if "(cid:" in stripped or odd / len(stripped) > 0.08 else "text"


def header_key(lines):
    """Running header with digits removed, so 'Page 3 of 17' and 'Page 4 of 17' match."""
    for line in lines[:2]:
        key = re.sub(r"\d+", "#", line.strip())
        if len(key) >= 8:
            return key
    return None


def index(pdf_path):
    texts, engine = extract(pdf_path)
    pages, in_notes, last_note = [], False, None
    for number, text in enumerate(texts, 1):
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        # The printed page number: pdfplumber puts it last, pymupdf often right after the running header
        candidates = [i for i in range(len(lines) - 1, max(len(lines) - 4, -1), -1)] + list(range(min(3, len(lines))))
        printed_at = next((i for i in candidates if PRINTED_PAGE.match(lines[i])), None)
        printed = int(PRINTED_PAGE.match(lines[printed_at]).group(1)) if printed_at is not None else None
        landmarks = []
        for i, line in enumerate(lines):
            if i == printed_at:
                continue
            if in_notes and re.fullmatch(r"\d{1,2}\.?", line):
                # pymupdf may put a note's number and title on separate lines ("4" / "Other assets")
                title = next((l for l in lines[i + 1:i + 3] if not re.fullmatch(r"\d{1,2}\.?", l)), "")
                line = f"{line} {title}"
            if len(line) > MAX_HEADING_LENGTH or line[0].islower():
                continue  # prose, not a heading
            for kind, rx in LANDMARK_RES:
                if rx.match(line) and not any(lm[:2] == (kind, line[:90]) for lm in landmarks):
                    landmarks.append((kind, line[:90], i))
            m = NOTE_HEADING.match(line) if in_notes else None
            if m and not re.search(r"\d{3}", line):
                n = int(m.group(1))
                # Real notes are numbered in sequence; table rows and cross-references are not
                if last_note is None or n == last_note + 1:
                    landmarks.append(("note", re.sub(r"\s+", " ", line)[:90], i))
                    last_note = n
        kinds = {lm[0] for lm in landmarks}
        if "contents" in kinds:
            landmarks = [lm for lm in landmarks if lm[0] in ("contents", "cover")]  # a listing, not section starts
        elif "notes" in kinds:
            in_notes, last_note = True, None
        elif kinds & NOTES_END_KINDS:
            in_notes = False
        pages.append({
            "page": number,
            "printed_page": printed,
            "quality": text_quality(text),
            "tokens_est": len(text) // 4,
            "header": header_key(lines),
            "first_lines": lines[:3],
            "landmarks": [{"kind": k, "text": t, "line": n} for k, t, n in landmarks],
            "text": text,
        })

    # Runs of 3+ consecutive pages sharing a running header (appraisal reports, bundled attachments)
    runs, start = [], 0
    for i in range(1, len(pages) + 1):
        if i == len(pages) or pages[i]["header"] != pages[start]["header"] or pages[start]["header"] is None:
            if pages[start]["header"] and i - start >= 3:
                raw = [pages[j]["first_lines"][0] for j in range(start, i)]
                documents = 1 + sum(1 for a, b in zip(raw, raw[1:]) if a != b)
                runs.append({"first": start + 1, "last": i, "header": raw[0][:90], "documents": documents})
            start = i

    cover = " ".join(texts[i] for i in range(min(5, len(texts))))
    form = re.search(r"SEC FORM (17-[AQ])", cover, re.I)
    period = re.search(r"(?:fiscal year|quarterly period) ended:?\s*([A-Z][a-z]+ \d{1,2}, \d{4})", cover, re.I)
    return {
        "source_file": str(pdf_path),
        "engine": engine,
        "page_count": len(pages),
        "tokens_est": sum(p["tokens_est"] for p in pages),
        "form_type": form.group(1).upper() if form else None,
        "period_end_text": period.group(1) if period else None,
        "page_basis_hint": printed_basis(pages),
        "runs": runs,
        "pages": pages,
    }


def printed_basis(pages):
    """'printed' when printed page numbers equal their PDF positions, else 'pdf_index'.

    A 17-A restarts its numbering (body, financial statements, each attachment), so
    printed numbers are ambiguous there and citations must use PDF positions.
    """
    numbered = [p for p in pages if p["printed_page"] is not None]
    matching = sum(p["printed_page"] == p["page"] for p in numbered)
    # A few stray numbers (last line of a table, an attachment's own page numbers) don't count against it
    if len(numbered) >= 5 and matching >= 0.8 * len(numbered):
        return "printed"
    return "pdf_index"


def ranges(numbers):
    out, start = [], None
    for i, n in enumerate(numbers):
        if start is None:
            start = n
        if i == len(numbers) - 1 or numbers[i + 1] != n + 1:
            out.append(f"{start}" if start == n else f"{start}-{n}")
            start = None
    return ", ".join(out)


def summary(ix):
    lines = [f"{ix['source_file']}: {ix['page_count']} pages, ~{ix['tokens_est']:,} tokens of text ({ix['engine']})",
             f"Form: {ix['form_type'] or 'not found on cover'}; period ended: {ix['period_end_text'] or 'not found'}; "
             f"cite pages as: {ix['page_basis_hint']}"]
    if ix["page_count"] > LARGE_FILING_PAGES:
        lines.append(f"LARGE FILING (> {LARGE_FILING_PAGES} pages): do not read it whole. Use find_pages.py and read only matched pages.")
    for quality in ("none", "garbled"):
        bad = [p["page"] for p in ix["pages"] if p["quality"] == quality]
        if bad:
            label = "No text layer (scanned)" if quality == "none" else "Unreadable text"
            lines.append(f"{label}: {len(bad)} pages: {ranges(bad)}")
    lines.append("\nRuns of pages with the same running header:")
    for r in ix["runs"]:
        docs = f", {r['documents']} documents" if r["documents"] > 1 else ""
        lines.append(f"  {r['first']}-{r['last']} ({r['last'] - r['first'] + 1} pages{docs}): {r['header']}")
    if not ix["runs"]:
        lines.append("  none")
    lines.append("\nLandmarks (page: section start):")
    seen = {}
    for p in ix["pages"]:
        for lm in p["landmarks"]:
            key = (lm["kind"], re.sub(r"\d+", "#", lm["text"]))
            if lm["kind"] in ("appraisal", "procedures", "auditor") and key in seen:
                seen[key][1] += 1  # repeated document starts: count them instead of listing each
                continue
            seen[key] = [p["page"], 1]
            lines.append(f"  {p['page']:>4}: [{lm['kind']}] {lm['text']}")
    repeats = [(page, n, kind, text) for (kind, text), (page, n) in seen.items() if n > 1]
    for page, n, kind, text in repeats:
        lines.append(f"  (from p.{page}: {n} pages start with [{kind}] {text})")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="Index file (default: <pdf>.index.json)")
    args = parser.parse_args()
    ix = index(args.pdf)
    out = args.output or args.pdf.with_suffix(".index.json")
    out.write_text(json.dumps(ix, ensure_ascii=False))
    print(summary(ix))
    print(f"\nSaved {out}")


if __name__ == "__main__":
    sys.exit(main())
