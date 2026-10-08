---
name: ph-reit-analyst
description: Analyzes Philippine REITs listed on the PSE (AREIT, RCR, MREIT, CREIT, FILRT, DDMPR, PREIT, VREIT or any other PSE-listed REIT) from their filings, such as SEC Form 17-Q quarterly reports (PDF), 17-A annual reports and dividend declarations. Computes FFO, AFFO, dividend coverage, distributable income payout and NAV per share with page citations, runs validation checks, and flags risks like sponsor-related income or unusual adjustments. Use when the user uploads or points to a PH REIT filing, asks if a PH REIT's dividend is safe, covered or sustainable, asks about its earnings quality, valuation or sponsor dependence, or wants a REIT report explained in plain language (including in Filipino/Taglish), even without terms like FFO or AFFO. Do NOT use for non-REIT Philippine stocks, foreign REITs, live share prices, or buy/sell/hold advice.
compatibility: Needs code execution with Python 3.9+, pymupdf (fast page indexing) and pdfplumber (citation checks) to read filing PDFs, and matplotlib for the bridge chart (pip install -r requirements.txt in this folder); the metric and check scripts use only the standard library. No network access required.
metadata:
  author: pimcabanlit
  version: 0.10.0
---

# PH REIT Analyst

Turns a Philippine REIT filing into a plain-language answer backed by
page-cited numbers: **is the dividend backed by real cash, and what should an
investor know?**

All paths below are relative to this skill's folder (the folder containing
this file), written as `<skill-dir>`. Outputs go in the user's current working
directory.

## Critical rules

1. **Numbers come from files and scripts, never mental math.** Extract raw
   values into a facts JSON, then let `scripts/compute_metrics.py` do every
   calculation. If a number is needed that the script doesn't produce, add it
   to the script rather than computing it in prose.
2. **Every extracted number cites its page and quotes the filing.** Use the
   printed page number (note the PDF page index if it differs) and an exact
   phrase from that page that readers can search for. No citation, no entry.
3. **Flag, don't guess.** Ambiguous, missing or contradictory values get
   `"confidence": "low"` and a note, and are surfaced in the report.
4. **No buy/sell/hold recommendations.** Describe dividend safety, valuation
   and risks only. Every report ends with: "For learning and research only.
   Not investment advice."
5. **Plain language first.** Lead with a one-sentence answer a non-finance
   reader understands. Explain each technical term the first time it appears.

## Why it works this way

Net income is a poor guide for REITs: under the fair value model it swings with
appraisal gains and losses, and some income (straight-line rent, finance lease
interest) is booked before cash arrives. So the skill rebuilds cash-based
earnings (FFO, then AFFO) and compares them with the dividend. Accuracy matters
more than speed, which is why extraction and calculation are separated.

## Pick the workflow

| The user gives or asks for | Do this |
|---|---|
| A 17-Q quarterly report, or "is the dividend safe" for a quarter | Follow `references/workflows/quarterly-review.md`. Q2 and Q3 filings are analyzed year-to-date (see "Which period to analyze" there). |
| A 17-A annual report, or "was the dividend covered last year" | Follow `references/workflows/annual-review.md` (on top of the quarterly workflow): full-year columns, the four quarterly dividends declared for the year, audited figures first. |
| Comparisons, total return, asset infusions | Not built yet. Say so and offer what the quarterly review can answer. |
| A REIT question with no filing | Ask for the filing (PSE EDGE or the REIT's investor relations page). Don't answer from memory. |

If the document type is unclear, read the cover page (company, form type,
period end) before choosing. Ask the user only if the cover page doesn't settle it.

## The pipeline (details in the workflow file)

1. **Index the filing and find the pages; never read it whole.**
   ```bash
   python <skill-dir>/scripts/index_pages.py data/raw/<ticker>/<file>.pdf
   python <skill-dir>/scripts/find_pages.py data/raw/<ticker>/<file>.index.json --preset quarterly   # or annual
   ```
   Read only the pages listed. A 17-A can be 700 pages; the facts come from
   about 30 of them.
2. **Extract** values into `data/facts/<ticker>/<YYYY>-<period>.facts.json`
   following `schemas/reit_facts.schema.json`.
3. **Check citations.** Each `label` must be exact text from the cited page,
   so readers can search the PDF for it. This confirms every label and value
   is on its page:
   ```bash
   python <skill-dir>/scripts/check_citations.py data/facts/<ticker>/<YYYY>-<period>.facts.json
   ```
4. **Validate and compute** in one step. The script refuses to calculate if
   the facts file breaks the schema or lacks page citations. For a Q2 or Q3
   filing it also derives the latest quarter alone when the earlier period's
   facts file of the same year sits in the same folder:
   ```bash
   python <skill-dir>/scripts/compute_metrics.py data/facts/<ticker>/<YYYY>-<period>.facts.json \
     -o outputs/<ticker>/<YYYY>-<period>/metrics.json
   ```
5. **Draw the earnings bridge** next to `metrics.json`:
   ```bash
   python <skill-dir>/scripts/bridge_chart.py outputs/<ticker>/<YYYY>-<period>/metrics.json
   ```
   It only draws what `metrics.json` contains. Look at the image before
   moving on.
6. **Write** `outputs/<ticker>/<YYYY>-<period>/report.md` using
   `references/report-template.md` and the wording in `references/red-flags.md`.
7. **Check the report** and fix every FAIL before handing it over:
   ```bash
   python <skill-dir>/scripts/check_report.py outputs/<ticker>/<YYYY>-<period>/report.md \
     --metrics outputs/<ticker>/<YYYY>-<period>/metrics.json \
     --facts data/facts/<ticker>/<YYYY>-<period>.facts.json
   ```

## Before finishing

- `check_report.py` passes with no FAIL.
- Every number in the report appears in `metrics.json` or the facts file.
- Every check that failed or needs review is mentioned in the report.
- `bridge.png` exists next to the report and is embedded under "From earnings
  to dividend".
- A derived quarter, if shown, is labeled "derived" and never replaces the
  year-to-date answer.
- Subsequent events affecting shares, debt or dividends are under "Worth
  knowing", with any derived figure labeled as derived.
- The report never recommends buying, selling, or holding.

## References (read when the step needs them)

- `references/workflows/quarterly-review.md`: step-by-step 17-Q workflow and where each fact lives
- `references/workflows/annual-review.md`: what differs in a 17-A (columns, signs, dividends for the year, where each fact lives)
- `references/accounting-models.md`: read before computing FFO; the model decides the formula
- `references/red-flags.md`: each flag's detection rule and plain wording
- `references/ph-reit-rules.md`: regulatory context (verify before citing specifics)
- `references/report-template.md`: required report structure and tone

## Examples

**Example 1: filing provided**
User says: "Run a quarterly review on data/raw/areit/2026-Q1-17Q.pdf"
Actions: map the PDF's pages, extract facts with citations, run
`compute_metrics.py`, write the report, run `check_report.py`.
Result: a report that opens with "AREIT earned ₱1.09 in cash earnings for
every ₱1 it declared in dividends this quarter", a green safety light, three
"worth knowing" flags (straight-line adjustment, sponsor finance lease income,
related-party lending) and the earnings-to-dividend table with page citations.

**Example 2: Taglish question**
User says: "Safe ba ang dividend ng AREIT ngayong quarter? Nasa data/raw/areit yung report."
Actions: same pipeline. Reply in the user's language; the report keeps its
English structure unless the user asks otherwise.

**Example 3: annual report**
User says: "Review AREIT's 2025 annual report: data/raw/areit/2025-FY-17A.pdf"
Actions: index the 699-page filing, read only the ~30 pages the annual preset
lists, extract the full-year facts (four quarterly dividends, audited figures,
signs from the statements), then the same compute, chart and check steps.
Result: a full-year report citing PDF page positions, with the year's payout
compared against the REIT rule's 90% minimum.

**Example 4: asks for a recommendation**
User says: "Should I buy MREIT?"
Actions: explain that the skill doesn't give buy/sell advice, then offer a
dividend-safety review if they share the latest 17-Q.

## Troubleshooting

**`compute_metrics.py` prints `[error]` lines and calculates nothing**
Cause: the facts file is missing a required fact, a page citation, or a fact
the accounting model needs (`fair_value_change` or `real_estate_depreciation`).
Solution: go back to the filing for each listed item. If a value truly isn't
in the filing, the workflow can't finish; tell the user which value is missing.

**A check shows `needs_review` or `fail`**
Cause: usually an extraction error (wrong line, wrong period column, millions
vs pesos), sometimes a genuine inconsistency in the filing.
Solution: re-read the cited page first. If the value is right, keep it,
mention the check in the report, and don't explain it away.

**Pages return no text (scanned images)**
Cause: some bundled pages are scans with no text layer (`index_pages.py`
lists them).
Solution: read those pages visually and mark the facts `"citation": "visual"`
and `"confidence": "medium"`; `check_citations.py` warns instead of failing.

**The filing is very large (hundreds of pages)**
Cause: 17-As bundle appraisal reports, reinvestment reports and other
attachments.
Solution: never read it whole. Use `index_pages.py` and `find_pages.py`
and read only the listed pages; cite PDF positions (`page_basis: pdf_index`).

**`prior_period_mismatch` flag, no derived quarter**
Cause: the earlier period's facts file doesn't line up with the year-to-date
one (different ticker, year or accounting model), or the derived figures
differ from the quarter column the filing prints, which usually means the
earlier figures were restated.
Solution: don't derive by hand. Report year-to-date only, mention the flag,
and re-extract the earlier period from its latest filing if needed.

**`share_issuance_table_adds_up` needs review**
Cause: a row's paid-up capital + APIC differs from its transaction value.
If the detail says the printed column total matches the other rows, the
row is likely a typo in the filing.
Solution: re-read the row once. If it's as printed, report it as a likely
filing typo with the corrected figure, not as an extraction error.

**`matches_prior_annual_report` needs review**
Cause: a quarterly report's prior year-end figure differs from last year's
annual report: a restatement, or one of the two was misread.
Solution: re-read both cited pages. If both are as printed, report it as a
possible restatement; don't pick one silently.

**`figures_consistent_within_filing` needs review**
Cause: the filing prints the same figure differently in two places (AREIT's
2023 distributable income: p.14 vs p.85).
Solution: use the audited figure, report the other as a likely inconsistency
in the filing, citing both pages.

**`nav_per_share` is empty**
Cause: the REIT uses the cost model, so equity doesn't reflect appraised values.
Solution: say NAV needs appraised values from the 17-A; don't estimate it.

**`check_citations.py` says a label is not found**
Cause: the label paraphrases the filing ("Net income for the half") instead
of quoting it, or the page is wrong.
Solution: copy the exact words from the page into `label`; move context such
as the period into `column` or `note`.

**`check_report.py` says a number is untraced**
Cause: the number was rounded differently, or computed in prose.
Solution: use the value from `metrics.json` (₱ millions with one decimal).
If the number is genuinely new, add it to `compute_metrics.py` first.

**`ModuleNotFoundError: pdfplumber`**
Solution: `pip install -r <skill-dir>/requirements.txt`. The metric scripts
don't need it; only PDF reading does.
