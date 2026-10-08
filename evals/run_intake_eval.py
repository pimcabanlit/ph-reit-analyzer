#!/usr/bin/env python3
"""Check the large-filing intake (index_pages.py + find_pages.py) against known pages.

For each filing in evals/intake.json:
  - the cover is read correctly (form type, period, citation basis, scanned pages);
  - each fact group's preset lookup includes the page it actually lives on;
  - optionally, every page cited by a known-good facts file is among the pages
    the preset points to (so reading only those pages is enough);
  - the pages to read are a small share of the whole filing.

Usage:
    python evals/run_intake_eval.py

Exit code is 1 if anything fails.
"""
import json
import re
import sys
from pathlib import Path

SKILL_SCRIPTS = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "ph-reit-analyst" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
from check_citations import iter_facts  # noqa: E402
from find_pages import PRESETS, search  # noqa: E402
from index_pages import index  # noqa: E402

CASES = Path(__file__).resolve().parent / "intake.json"
LIMIT = 4  # pages per lookup, as an agent would read them


def preset_pages(ix, preset):
    """Pages each lookup points to, with note pages followed to where the note ends."""
    by_group, every = {}, set()
    for name, heading, text in PRESETS[preset]:
        hits, _ = search(ix, heading, text, False, LIMIT)
        pages = set()
        for _, page, context in hits:
            pages.add(page)
            if m := re.search(r"continues to p\.(\d+)", context):
                pages.update(range(page, int(m.group(1)) + 1))
        by_group[name] = pages
        every |= pages
    return by_group, every


def run_case(case):
    rows = []
    ix = index(case["pdf"])
    for key in ("form_type", "period_end_text", "page_basis_hint"):
        ok = ix[key] == case[key]
        rows.append(("PASS" if ok else "FAIL", key, f"{ix[key]} (expected {case[key]})"))
    scanned = sum(p["quality"] == "none" for p in ix["pages"])
    rows.append(("PASS" if scanned == case["scanned_pages"] else "FAIL", "scanned pages", f"{scanned} (expected {case['scanned_pages']})"))

    by_group, every = preset_pages(ix, case["preset"])
    for group, page in case["expected_pages"].items():
        found = by_group.get(group, set())
        rows.append(("PASS" if page in found else "FAIL", f"find {group}", f"p.{page} {'found' if page in found else 'missing'} in {sorted(found)}"))

    if case.get("facts_covered"):
        doc = json.loads(Path(case["facts_covered"]).read_text())
        cited = {item["page"] for _, item in iter_facts(doc)}
        missed = sorted(cited - every)
        rows.append(("FAIL" if missed else "PASS", "every cited page is found",
                     f"missed p.{missed}" if missed else f"all {len(cited)} cited pages among the {len(every)} to read"))

    tokens = sum(ix["pages"][p - 1]["tokens_est"] for p in every)
    share = tokens / ix["tokens_est"]
    rows.append(("PASS" if share <= case["max_share_of_tokens"] else "FAIL", "pages to read",
                 f"{len(every)} pages, ~{tokens:,} of ~{ix['tokens_est']:,} tokens ({share:.0%}, limit {case['max_share_of_tokens']:.0%})"))
    return rows


def main():
    cases = json.loads(CASES.read_text())["cases"]
    fails = passes = 0
    for case in cases:
        print(f"\n{case['pdf']}")
        for status, name, detail in run_case(case):
            print(f"  {status:<5} {name:<62} {detail}")
            fails += status == "FAIL"
            passes += status == "PASS"
    print(f"\n{passes} passed, {fails} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
