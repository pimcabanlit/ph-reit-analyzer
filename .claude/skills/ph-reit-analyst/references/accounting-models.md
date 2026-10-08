# Accounting models and how they change FFO

Philippine standards (PAS 40) let a REIT carry investment property at either
fair value or cost. Detect the model first; it decides the FFO formula.

## How to detect

Look in the investment properties note (and the accounting policies note):
- "carried at fair value" / "fair value model" → `fair_value`
- "cost less accumulated depreciation" / "cost model" → `cost`

Record the page in `accounting_model_citation`. If the filing is unclear, set
confidence to low and ask before computing.

## Fair value model (e.g. AREIT)

- No depreciation on investment property. Instead, appraisal gains and losses
  run through net income as "net fair value change in investment properties".
- These are paper gains/losses, so FFO removes them:
  `FFO = net income − fair value change` (a loss is negative, so it is added back).
- NAV shortcut: because buildings are already at appraised value, total equity
  ÷ shares outstanding is a reasonable NAV-per-share estimate. Note it as an
  estimate; finance lease receivables are at amortized cost, not market value.

## Cost model

- Buildings are depreciated, so the Investopedia-style adjustment applies:
  `FFO = net income + real estate depreciation − gains on property sales`.
- Only add back depreciation of real estate, not of office equipment.
- NAV cannot be read from equity; it needs the fair value of investment
  property disclosed in the annual report (see the adjusted NAV below). In a
  17-Q, leave `nav_per_share` empty and say why.

## NAV is secondary, and book-based

- Report the company's NAV per share (equity ÷ shares) as "book NAV" and
  price ÷ NAV from the filing's own closing price. NAV supports the dividend
  answer; it never leads the report.
- Fair value model: finance lease receivables are at amortized cost, not
  market value. Show their share of total assets under "Other figures" as
  context. Never estimate their market value: it needs a discount rate
  assumption. A 17-A discloses their fair value; `compute_metrics.py` then
  adds a fair-value-adjusted NAV (book equity with the receivables at
  disclosed fair value). AREIT FY2025: book NAV 36.57, adjusted 38.17.
- Interim fair value changes are often just the offset of the straight-line
  adjustment, so interim book NAV mostly reflects the last year-end
  appraisal.
- Cost model: `compute_metrics.py` computes an adjusted NAV (equity +
  disclosed fair value − carrying amount of investment property) from the
  fair value disclosure PAS 40 requires in the 17-A
  (`investment_property_fair_value`, `investment_property_carrying`). Without
  that disclosure, leave NAV empty. Not yet tested on a real cost-model
  filing.

## Gains and losses on disposal

Selling a property isn't an operating result, so FFO removes any gain (and
adds back any loss) on disposal under both models (`gain_on_property_sale`,
signed: loss negative). AREIT FY2025 had a 6,195,989 loss on disposal.

## Adjustments common to both

- **Straight-line rent:** rent recognized evenly over a lease even when actual
  payments step up, creating income before cash. AFFO subtracts it. PH REITs
  often show it in their distributable income computation.
- **Capex:** "payments for additions to investment properties" in the cash
  flow. Filings rarely split maintenance from growth capex; subtract it, except
  cash purchases of whole buildings that the filing identifies
  (`capex_acquisitions`, e.g. AREIT's SEDA Lio, P1,192.00 million in 2024):
  buying a building isn't upkeep, and counting it would make a purchase look
  like a dividend shortfall. Only exclude what the filing names; if the
  amount has to be reconciled rather than read off a line, mark it medium
  confidence and show the reconciliation in the note.
- **Finance leases:** some REITs (AREIT) lease whole buildings to sponsor
  entities under finance leases. The building leaves investment property, a
  receivable appears, and income is booked as interest. That interest can be
  largely non-cash in a given quarter. It stays in FFO/AFFO but is flagged.

## Formulas used by `scripts/compute_metrics.py`

- `AFFO = FFO − straight-line rent adjustment − capex`
- `Dividend declared = dividend per share × shares outstanding`
- `AFFO coverage = AFFO ÷ dividend declared`
- `Payout of distributable income = dividend declared ÷ reported distributable income`
