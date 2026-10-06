# Workflow: quarterly review (SEC Form 17-Q)

Goal: answer "Is this quarter's dividend backed by real cash earnings, and what
should an investor know?" with page-cited numbers.

## 1. Intake

1. Confirm the cover page: company, form type (17-Q), quarter end date.
2. Map the pages. PSE uploads often bundle several documents in one PDF. A
   typical AREIT 17-Q file contains the 17-Q itself (statements, notes, MD&A,
   property table) followed by sponsor reinvestment progress reports, auditor
   agreed-upon procedures reports, and notary pages. Record which page ranges
   belong to which document. Use only the 17-Q pages for the facts file; note
   the reinvestment reports for later sponsor analysis.
3. Check which pages have a text layer (pdfplumber `extract_text()` returns
   text) and which are scanned images. Scanned pages that matter can be read
   visually; mark values from them `"confidence": "medium"`.

## Which period to analyze

The 17-Q income statement shows the quarter and year-to-date, but the cash
flow statement and the distributable income computation are **year-to-date
only**. Never subtract an earlier quarter to get a single quarter; analyze on
the basis the filing supports:

| Filing | `period_type` | `period_label` | Dividends to include |
|---|---|---|---|
| Q1 17-Q | `quarter` | `2026-Q1` | Q1 dividend: `dividend_per_share_declared` |
| Q2 17-Q | `half` | `2026-H1` | Q1 and Q2 dividends: `dividends` list |
| Q3 17-Q | `nine_months` | `2026-9M` | Q1, Q2 and Q3 dividends: `dividends` list |

Use the year-to-date column for every income statement value. In the
`dividends` list, give each declaration the share count on its record date;
shares often change mid-year through property-for-share swaps. The reported
peso total of each declaration confirms the share count. Fill
`shares_outstanding_prior` from the prior year-end column so new share
issuances are flagged, and `reported_nav_per_share` from the KPI table as a
cross-check.

## 2. Extract facts

Create `data/facts/<ticker>/<period_label>.facts.json` following
`schemas/reit_facts.schema.json` (in this skill's folder). Where to find each value in a typical 17-Q:

| Fact | Usual location |
|---|---|
| net_income, total_revenue, rental_income, finance_lease_interest_income, fair_value_change | Statement of comprehensive income |
| capex_investment_property, operating_cash_flow, dividends_paid, change_due_from_related_parties, depreciation_amortization | Statement of cash flows |
| total_assets, total_liabilities, total_equity, total_debt, cash | Statement of financial position |
| accrued_rent_receivable (current and prior), finance_lease_receivable (current and prior) | Receivables note |
| accounting_model | Investment properties note ("carried at fair value" vs "cost less accumulated depreciation") |
| straight_line_rent_adjustment, reported_distributable_income | Distributable income computation in the equity note |
| dividend_per_share_declared, or the `dividends` list | Events after the reporting period, or dividend table. Use the dividend declared FOR the period, which is often declared after period end |
| shares_outstanding, shares_outstanding_prior | Cover page item 10 or equity note |
| reported_nav_per_share | Key performance indicators table in the MD&A |
| mdna_net_income_before_fv_change | MD&A first paragraph (used only as a cross-check) |
| sponsor_ownership_pct | Corporate information note |

Rules:
- Store values in whole pesos, signed as in the statements (fair value loss is negative).
- Values reported in millions: convert to pesos, keep the note, set `"rounded": true`.
- The same figure often appears in several places; extract from the primary
  statement and use the others as cross-checks.

Each fact's `label` must be exact text from its page (the line item name, or
a short phrase printed next to the value) so a reader can search the PDF for
it; put the column header in `column` and any explanation in `note`. Then
confirm every label and value is really on its cited page:

```bash
python <skill-dir>/scripts/check_citations.py data/facts/<ticker>/<period_label>.facts.json
```

Fix every FAIL (usually a paraphrased label or a wrong page) and run it again.

## 3. Validate and compute

```bash
python <skill-dir>/scripts/compute_metrics.py data/facts/<ticker>/<period_label>.facts.json \
  -o outputs/<ticker>/<period_label>/metrics.json
```

The script first runs `scripts/validate_facts.py`. If it prints `[error]`
lines, nothing is calculated: fix the facts file and run it again.
`[warning]` lines (low or medium confidence values) must be mentioned in the
report.

Read the printed checks and flags. If a check fails, re-inspect the source
page before assuming the filing is wrong. Extraction errors are more common
than filing errors.

## 4. Report

Write `outputs/<ticker>/<period_label>/report.md` following
`references/report-template.md`. Explain each flag in one or two plain
sentences using `references/red-flags.md`.

## 5. Check the report

```bash
python <skill-dir>/scripts/check_report.py outputs/<ticker>/<period_label>/report.md \
  --metrics outputs/<ticker>/<period_label>/metrics.json \
  --facts data/facts/<ticker>/<period_label>.facts.json
```

Fix every FAIL and run it again. Stop when everything passes; don't hand over
a report with a FAIL. The script checks required sections, the disclaimer, no
buy/sell/hold wording, that every number traces to `metrics.json` or the
facts file, and that every flag and check has its own line.
