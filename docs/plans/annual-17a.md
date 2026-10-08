# Plan: annual reports (SEC Form 17-A)

Status: Phases 1–4 done; Phase 5 (tests) next. Based on AREIT's 17-A for FY2025 (filed April 14,
2026), `data/raw/areit/2025-FY-17A.pdf`. Page numbers below are PDF page
positions.

## 1. What a 17-A contains (AREIT FY2025)

699 pages, about 308,000 tokens of text, 44 pages without a text layer.

| PDF pages | Part | Use |
|---|---|---|
| 1–44 | 17-A body: business, properties, market prices, dividends and distributable income (p.12–14), three years of MD&A, directors, governance, exhibits | High |
| 45–98 | Audited financial statements: auditor's report, statements (p.55–58), notes (p.59–98) | Highest |
| 99–120 | Supplementary schedules: retained earnings available for dividends (p.107–109), financial soundness indicators (p.110) | Medium |
| 121–597 | 39 independent appraisal reports (Dec 2025), about 12 pages each | Spot checks |
| 598–684 | Sponsor reinvestment reports and agreed-upon procedures; garbled text, 44 scanned pages | Qualitative |
| 685–699 | Sustainability report | Out of scope |

About 15 pages (roughly 10,000 tokens, 3% of the file) feed the numbers.

## 2. How it differs from a 17-Q

1. Printed page numbers restart three times (17-A body; financial statements
   "pages 1 to 40"; each appraisal's "Page x of 17"). Cite PDF page positions.
2. The cover says "QUARTERLY REPORT" on a 17-A (p.2). Identify the form from
   "SEC FORM 17-A" and "fiscal year ended".
3. The FY2025 fair value change is a gain of +108,679,768 (income statement,
   p.56) but the dividend section labels it "Net fair value loss
   (108,679,768)" (p.13). Take the sign from the income statement.
4. The fair value change has three parts (Note 5, p.63): appraisal gain
   +432.8M, straight-line offset −245.9M, lease commissions −78.3M. In
   quarters without a new appraisal it is mostly the straight-line offset,
   which is why it equaled the straight-line adjustment in Q1 and 1H 2026.
5. Dividends for the year include Q4, declared and paid after year-end
   (8,363,080,842 = 91.05% of distributable income, p.13). The audited note
   lists dividends declared during the calendar year instead (p.69). Use
   "for the period". Share counts change mid-year.
6. Three years of history: income statement and cash flows 2025–2023
   (p.56, 58); distributable income three years (p.85); dividends since 2023
   (p.13).
7. Internal inconsistencies: 2023 distributable income 4,931,289,156 (p.14)
   vs 4,844,725,435 (audited note, p.85), a difference equal to the 2023
   straight-line adjustment; dividend table headings on p.69 seem to carry the
   prior year's totals; net income off by 1 peso on p.107.
8. Fair values disclosed for finance lease receivables (41,001,398,588 vs
   carrying 35,086,452,638), lease liabilities and security deposits (p.85).
9. The property table's valuation ties to the appraisals (Vertis 16,698 =
   three tower appraisals; Abreeza 5,389 = mall + BPO). Appraisal reports are
   not reliably machine-readable.
10. New items: loss on disposal 6,195,989; interest coverage 34.73x (p.110);
    retained earnings available for dividends (p.107–109); appraisal discount
    rates 8.28–9.42% (p.80).

Preview with the current formulas (not yet extracted facts): FFO
9,430,540,059 (matches MD&A 9,430.54M); AFFO 8,949,323,055; coverage 1.07x;
payout 91.05%; book NAV 36.57; fair-value-adjusted NAV about 38.17; price /
NAV 1.19x at the 43.50 year-end close.

## 3. Phases

### Phase 0: housekeeping
- [x] Merge `main` (the 17-A commit) into the working branch
- [x] Move the PDF to `data/raw/areit/2025-FY-17A.pdf`
- [x] Install pymupdf (already in requirements.txt)

### Phase 1: large-filing intake (helps 17-Qs too)
- [x] `index_pages.py`: one line per PDF page (first lines, text layer,
      token estimate), consecutive pages grouped into documents; saved to a
      file, never read whole
- [x] `find_pages.py`: keyword search over the index for statement and note
      headings
- [x] Citations by PDF page position for 17-As (`page_basis: "pdf_index"`);
      `visual` citation type for scanned pages, accepted with a warning
- [x] Workflow rule: index first, read only matched pages; warn above ~150
      pages
- [x] Tests: the index finds the pages the AREIT 1H 2026 review used, and the
      17-A's statements, dividend and fair value pages

### Phase 2: annual workflow
- [x] `references/workflows/annual-review.md`: where each fact sits; period
      rules (full year; dividends declared for Q1–Q4; five-month tax timing
      rule); sign rule; using 2- and 3-year columns
- [x] `SKILL.md` routing for 17-A; version bump

Phase 2 findings, from a dry run of the guide's page table against the PDF
(40 of 40 citations found; coverage 1.07x, payout 91.05% as the company
reports):
- The 17-A doesn't split accrued receivables out of trade receivables
  (1,968,028,194 = the 17-Q's billed 1,245,751,587 + accrued 722,276,607);
  the guide says to leave `accrued_rent_receivable` out.
- Year-end share counts are in the equity note (p.67); the cover's are dated
  February 28, 2026.
- Fixed: compute_metrics.py crashed when a filing has a price but no
  reported NAV per share; the chart's dividend tile overflowed with four
  quarters.

### Phase 3: schema and metrics
- [x] Fair value change breakdown facts and a check that the parts add up;
      reword the straight-line flag as context
- [x] Remove gains / losses on disposal in FFO under both models
- [x] Fair-value-adjusted NAV from disclosed fair values (cost model: the
      investment property fair value disclosure)
- [x] Checks: annual payout ≥ 90% and equal to the company's stated figure;
      dividends declared after year-end ≤ retained earnings available;
      interest coverage vs the company's figure
- [x] Consistency check for figures reported in several places
      (`also_reported`), reported as a likely filing inconsistency
- [x] `history` list for a 3-year trend from one filing
- [x] Cross-filing checks (17-Q prior-year-end columns vs 17-A); derived Q4 =
      FY − 9M when a 9M facts file exists, labeled unverified

### Phase 4: report and chart
- [x] Annual report template: full-year answer, 3-year table, appraisal
      context, sponsor reinvestment noted qualitatively
- [x] Bridge chart with `period_type: year`; optional 3-year trend chart

Phase 4 output: `evals/gold/areit-2025-fy/report.md` and `bridge.png`
(pending owner verification), produced from
`data/facts/areit/2025-FY.facts.json` (86 citations verified); the report
passes all 14 `check_report.py` checks, including the new trend-table check.

### Phase 5: tests
- [ ] `areit-2025-fy` eval case with expected values and citations
- [ ] Negative fixtures: fair value sign from the p.13 label; mismatched 2023
      distributable income; wrong mid-year share count on one dividend
- [ ] Trigger prompts for annual-report requests

Out of scope: scraping all appraisal reports, governance and compensation,
sustainability, numbers from scanned sponsor pages.

## 4. Decisions
1. Fair-value-adjusted NAV: finance lease receivables only (decided).
2. Trend: table only, no chart (decided).
3. 2024 and 2023 columns extracted into `history` (decided).
4. The 18.7 MB PDF stays committed (decided).
5. AFFO excludes cash acquisitions the filing identifies inside capex
   (`capex_acquisitions`) (decided). AREIT 2024 coverage: 0.87x with SEDA Lio
   (1,192.00M) counted as capex, 1.06x without.

Phase 3 results on AREIT FY2025 (data/facts/areit/2025-FY.facts.json, 81
citations verified): FFO 9,436.7M (disposal loss added back), AFFO 8,955.5M,
coverage 1.07x; payout 91.05% (matches the company; above 90%); Q4 dividend
2,303.8M within retained earnings available 8,203.1M; interest coverage
34.73x (matches); book NAV 36.57, fair-value-adjusted 38.17; price / NAV
1.19x on computed book NAV; trend coverage 1.04x / 1.06x / 1.07x for
2023–2025 (2024 excludes the SEDA Lio purchase from capex). Flagged automatically: the filing's 2023 distributable income
mismatch (p.14 vs p.85) and the stated 2023 payout built on it. The 1H 2026
facts' December 2025 figures match the annual report.
