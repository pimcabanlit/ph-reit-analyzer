---
name: ph-reit-analyst
description: Analyzes Philippine REITs listed on the PSE (AREIT, RCR, MREIT, CREIT, FILRT, DDMPR, PREIT, VREIT) from their filings — SEC Form 17-Q quarterly reports, 17-A annual reports, dividend declarations and asset disclosures. Computes FFO, AFFO, dividend coverage, distributable income payout and NAV per share, runs validation checks, and flags red flags such as sponsor-related income or unusual adjustments. Use this skill whenever the user uploads or points to a PH REIT filing, asks whether a PH REIT's dividend is safe or sustainable, asks about a PH REIT's earnings quality, valuation or sponsor dependence, or wants a plain-language explanation of a REIT report — even if they don't use terms like FFO or AFFO.
---

# PH REIT Analyst

Turns a Philippine REIT filing into a plain-language answer backed by
page-cited numbers. Read `CLAUDE.md` at the repo root first; its rules apply
to everything here.

## Why this skill works the way it does

Retail investors want to know whether a REIT's dividend is real and safe.
Net income is a poor guide for REITs: under the fair value model it swings with
appraisal gains and losses, and some income (straight-line rent, finance lease
interest) is booked before cash arrives. So the skill rebuilds cash-based
earnings (FFO, then AFFO) and compares them with the dividend. Accuracy matters
more than speed, which is why extraction and calculation are separated and
every number carries a page citation.

## Pick the workflow

| The user gives or asks for | Workflow |
|---|---|
| A 17-Q quarterly report, or "is the dividend safe" for a quarter | `references/workflows/quarterly-review.md` |
| A 17-A annual report | Not built yet. Say so, then offer a quarterly-style review of the annual figures, clearly labeled as partial. |
| Comparisons, total return, asset infusions | Not built yet. Say so and offer what the quarterly review can answer. |

If the document type is unclear, read the cover page (company name, form type,
period end) before choosing. Ask the user only if the cover page doesn't settle it.

## Shared references

- `references/accounting-models.md` — read before computing FFO; decides the formula
- `references/red-flags.md` — what to look for and how each flag is detected
- `references/ph-reit-rules.md` — regulatory context (verify before citing specifics)
- `references/report-template.md` — required report structure and tone

## Output locations

- Facts: `data/facts/<ticker>/<YYYY>-<period>.facts.json` (must follow `schemas/reit_facts.schema.json`)
- Metrics: `outputs/<ticker>/<YYYY>-<period>/metrics.json` (from `scripts/compute_metrics.py`)
- Report: `outputs/<ticker>/<YYYY>-<period>/report.md`

## Before finishing

- Every number in the report appears in `metrics.json` or the facts file.
- Every check that failed or needs review is mentioned in the report.
- The report never recommends buying, selling, or holding.
