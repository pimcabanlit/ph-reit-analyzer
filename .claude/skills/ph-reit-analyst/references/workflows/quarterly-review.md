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

## 2. Extract facts

Create `data/facts/<ticker>/<YYYY>-Q<n>.facts.json` following
`schemas/reit_facts.schema.json` (in this skill's folder). Where to find each value in a typical 17-Q:

| Fact | Usual location |
|---|---|
| net_income, total_revenue, rental_income, finance_lease_interest_income, fair_value_change | Statement of comprehensive income |
| capex_investment_property, operating_cash_flow, dividends_paid, change_due_from_related_parties, depreciation_amortization | Statement of cash flows |
| total_assets, total_liabilities, total_equity, total_debt, cash | Statement of financial position |
| accrued_rent_receivable (current and prior), finance_lease_receivable (current and prior) | Receivables note |
| accounting_model | Investment properties note ("carried at fair value" vs "cost less accumulated depreciation") |
| straight_line_rent_adjustment, reported_distributable_income | Distributable income computation in the equity note |
| dividend_per_share_declared | Events after the reporting period, or dividend table — use the dividend declared FOR this quarter, which is often declared after quarter end |
| shares_outstanding | Cover page item 10 or equity note |
| mdna_net_income_before_fv_change | MD&A first paragraph (used only as a cross-check) |
| sponsor_ownership_pct | Corporate information note |

Rules:
- Store values in whole pesos, signed as in the statements (fair value loss is negative).
- Values reported in millions: convert to pesos, keep the note, set `"rounded": true`.
- The same figure often appears in several places; extract from the primary
  statement and use the others as cross-checks.

## 3. Validate and compute

```bash
python <skill-dir>/scripts/compute_metrics.py data/facts/<ticker>/<YYYY>-Q<n>.facts.json \
  -o outputs/<ticker>/<YYYY>-Q<n>/metrics.json
```

The script first runs `scripts/validate_facts.py`. If it prints `[error]`
lines, nothing is calculated: fix the facts file and run it again.
`[warning]` lines (low or medium confidence values) must be mentioned in the
report.

Read the printed checks and flags. If a check fails, re-inspect the source
page before assuming the filing is wrong. Extraction errors are more common
than filing errors.

## 4. Report

Write `outputs/<ticker>/<YYYY>-Q<n>/report.md` following
`references/report-template.md`. Explain each flag in one or two plain
sentences using `references/red-flags.md`.

## 5. Check the report

```bash
python <skill-dir>/scripts/check_report.py outputs/<ticker>/<YYYY>-Q<n>/report.md \
  --metrics outputs/<ticker>/<YYYY>-Q<n>/metrics.json \
  --facts data/facts/<ticker>/<YYYY>-Q<n>.facts.json
```

Fix every FAIL and run it again. Stop when everything passes; don't hand over
a report with a FAIL. The script checks required sections, the disclaimer, no
buy/sell/hold wording, that every number traces to `metrics.json` or the
facts file, and that every flag and check has its own line.
