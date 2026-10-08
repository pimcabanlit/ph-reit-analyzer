# Workflow: annual review (SEC Form 17-A)

Goal: answer "Was this year's dividend backed by real cash earnings, and what
should an investor know?" with page-cited numbers, using the audited annual
report. Read `quarterly-review.md` first: the facts, scripts, report and
checks are the same. This file covers what is different in a 17-A.

Page numbers below are PDF page positions in AREIT's FY2025 17-A (699 pages)
and are examples only; other REITs' 17-As are laid out the same way but not
on the same pages.

## 1. Intake

A 17-A is large: AREIT's runs to 699 pages and ~340,000 tokens, of which the
facts come from about 30 pages. Never read it whole.

```bash
python <skill-dir>/scripts/index_pages.py data/raw/<ticker>/<YYYY>-FY-17A.pdf
python <skill-dir>/scripts/find_pages.py data/raw/<ticker>/<YYYY>-FY-17A.index.json --preset annual
```

What a 17-A bundles, in order (AREIT FY2025):

| Part | AREIT pages | Use |
|---|---|---|
| 17-A body: business, properties, market prices, dividends and distributable income, MD&A for three years, directors, governance, exhibits | 1–44 | Market price, dividends, MD&A cross-checks, subsequent events (Item 14(d)) |
| Audited financial statements: auditor's report, statements, notes | 45–98 | Most facts. Prefer these over the body when both give a figure |
| Supplementary schedules: retained earnings available for dividends, financial soundness indicators | 99–120 | Cross-checks |
| Independent appraisal reports, one per property | 121–597 | Don't read; spot-check one property at most |
| Sponsor reinvestment reports and agreed-upon procedures (partly scanned) | 598–684 | Qualitative only |
| Sustainability report | 685–699 | Out of scope |

Rules from the intake:
- Identify the form from "SEC FORM 17-A" and "For the fiscal year ended". The
  cover's heading can be wrong: AREIT's 17-A cover says "QUARTERLY REPORT".
- Set `meta.page_basis` to `pdf_index` and cite PDF positions. Printed page
  numbers restart in each part (17-A body, financial statements "pages 1 to
  40", each appraisal's "Page x of 17"), so a printed number alone doesn't
  identify a page.
- `meta.period_type` is `year`, `meta.period_label` is `<YYYY>-FY`, and the
  facts file is `data/facts/<ticker>/<YYYY>-FY.facts.json`.

## 2. Which columns and which figure

- **Current-year column.** The income statement and cash flow statement show
  three years (AREIT: 2025, 2024, 2023, p.56 and p.58); the balance sheet two
  (p.55). Take every flow item from the current-year column. `*_prior` facts
  come from the prior year-end balance sheet column.
- **Audited first.** When the 17-A body and the audited notes both give a
  figure, cite the audited one and use the other as a cross-check. They can
  disagree: AREIT's 2023 distributable income is 4,931,289,156 in the
  dividends section (p.14) but 4,844,725,435 in the audited note (p.85); the
  difference is exactly that year's straight-line adjustment. Report a
  disagreement as a likely inconsistency in the filing, citing both pages.
- **Take signs from the statements, never from labels.** AREIT's FY2025
  fair value change is a gain of +108,679,768 (income statement, p.56); the
  dividends section lists the same amount as "Net fair value loss on
  investment properties (108,679,768)" (p.13), because it is being deducted.
  `fair_value_change` is signed as in the income statement.
- **Don't back into figures the 17-A doesn't split.** AREIT's 17-A shows
  "Trade receivables - billed" of 1,968,028,194 (p.60) with no accrued
  receivables line; the quarterly reports split the same amount into billed
  (1,245,751,587) and accrued (722,276,607). Leave
  `accrued_rent_receivable` out rather than estimating it. The straight-line
  flag then has nothing to compare, which is expected.
- **Cover share counts are dated after year-end.** AREIT's cover gives shares
  "as of February 28, 2026" (p.2). Take `shares_outstanding` and
  `shares_outstanding_prior` from the equity note's "Outstanding shares at
  December 31" (p.67).

## 3. Dividends for the year

The year's dividends are the four quarterly dividends declared **for** Q1 to
Q4, including Q4, which is declared and paid after year-end. REIT rules
count dividends paid within five months after year-end toward that year's
90% distribution (the dividends section explains this, AREIT p.13).

Record all four in the `dividends` list, each with the share count on its
record date:

| Quarter | Where | AREIT FY2025 |
|---|---|---|
| Q1–Q3 | Equity note's cash dividends table (per share, record date, total), p.69 | 0.58, 0.59, 0.62 |
| Q4 | Events after the reporting period note, p.87 (also the dividends section, p.13) | 0.62, declared February 19, 2026 |
| Share counts | Equity note's outstanding shares; confirm each with the reported peso total | 3,209,865,985 for Q1–Q2 (shares at December 31, 2024); 3,715,756,162 for Q3–Q4 (after the September 2025 swap) |

Two totals that are **not** the year's dividends:
- Cash dividends **paid** in the cash flow statement (7,921,034,294, p.58):
  that is the prior year's Q4 plus this year's Q1–Q3. It goes in
  `dividends_paid`.
- The equity note's "declared during the year" table (p.69): same basis as
  cash paid.

The company's own payout figure (AREIT: dividends of 8,363,080,842 = 91.05% of
distributable income, p.13) should equal `payout_of_distributable_income`;
compare them and mention any difference. `trailing_dividends` are the same
four quarters.

## 4. Where each fact lives in a 17-A

| Fact | Where (AREIT FY2025 page) |
|---|---|
| net_income, total_revenue, rental_income, finance_lease_interest_income, fair_value_change | Statement of comprehensive income, current-year column (p.56) |
| capex_investment_property | Cash flow statement, "Additions to: Investment properties" (p.58) |
| operating_cash_flow, dividends_paid, change_due_from_related_parties, depreciation_amortization | Cash flow statement (p.58) |
| total_assets, total_liabilities, total_equity, total_debt, cash | Balance sheet (p.55) |
| finance_lease_receivable (and _prior) | Receivables note (p.60); also the lease note's maturity analysis (p.73) |
| accounting_model | Investment properties note: "carried at fair value" (p.62–63) |
| straight_line_rent_adjustment, reported_distributable_income | Distributable income computation in the capital management note (p.85); cross-check the dividends section (p.13) |
| mdna_net_income_before_fv_change | MD&A first paragraph (p.15) |
| shares_outstanding, shares_outstanding_prior | Equity note, "Outstanding shares at December 31" (p.67) |
| sponsor_ownership_pct | Corporate information note (p.59); also Item 1 (p.5) |
| market_price_close | Item 5 market information, "Fourth Quarter" close (p.12) |
| available_credit_line | MD&A financial condition (p.16) |
| `share_issuances` | Equity note, property-for-share swap table (p.68–69) |
| `subsequent_events` | Item 14(d) (p.40) and the events after the reporting period note (p.87) |

Context worth a sentence in the report, from the same pages:
- **Fair value change breakdown** (investment properties note, p.63): the
  appraisal gain, minus the straight-line offset, minus lease commissions.
  AREIT FY2025: +432.8M − 245.9M − 78.3M = +108.7M. This also explains the
  quarterly pattern: between appraisals the fair value change is mostly the
  straight-line offset, so it can equal the straight-line adjustment to the
  peso. Say so instead of treating that as an anomaly.
- **Appraisal context** (investment properties and fair value notes, p.63
  and p.80): appraised by an independent appraiser at year-end, income
  approach, discount rate range (AREIT: 8.28%–9.42%).
- **Property table** (p.18): the valuation column ties to the appraisal
  reports (e.g. Vertis 16,698 = its three tower appraisals). Unlike a 17-Q's
  property table, it is appraisal-based. Don't scrape the appraisal reports.

## 5. Compute, chart, report, check

Same commands as the quarterly review, with `<YYYY>-FY` as the period:

```bash
python <skill-dir>/scripts/check_citations.py data/facts/<ticker>/<YYYY>-FY.facts.json
python <skill-dir>/scripts/compute_metrics.py data/facts/<ticker>/<YYYY>-FY.facts.json -o outputs/<ticker>/<YYYY>-FY/metrics.json
python <skill-dir>/scripts/bridge_chart.py outputs/<ticker>/<YYYY>-FY/metrics.json
python <skill-dir>/scripts/check_report.py outputs/<ticker>/<YYYY>-FY/report.md --metrics outputs/<ticker>/<YYYY>-FY/metrics.json --facts data/facts/<ticker>/<YYYY>-FY.facts.json
```

Report differences from the quarterly template:
- Title "FY <YYYY> (January to December)"; the one-sentence answer covers the
  full year and the four quarterly dividends.
- Under "Other figures", the year's payout of distributable income against
  the REIT rule's 90% minimum (no longer "watch at year end"), and the
  company's own payout figure.
- Say the figures are audited.

## 6. Not automated yet

These are planned (see the repo's plan) and must not be computed in prose
meanwhile:
- Adding back gains and losses on property disposals in FFO (AREIT FY2025
  had a 6,195,989 loss, p.58). Mention it as a known limitation if material.
- Fair-value-adjusted NAV from the disclosed fair value of finance lease
  receivables (AREIT: 41,001,398,588 vs carrying 35,086,452,638, p.85).
- Automatic checks for figures that disagree within the filing, the 90% rule
  and retained earnings available for dividends.
- A three-year trend from the comparative columns, and Q4 derived as full
  year minus nine months.
- Price ÷ NAV when the 17-A reports no NAV per share (AREIT's doesn't);
  `valuation` then shows only the yields.
