# Red flags catalog

Each flag has an id (used in `metrics.json` and evals), a severity, a detection
rule implemented in `scripts/compute_metrics.py`, and plain wording for reports.

Severities:
- `needs_review` — numbers don't line up; could be an accounting convention or an extraction error. Check the source before concluding anything.
- `worth_knowing` — numbers are consistent, but the reader should understand the risk.

Thresholds below are starting assumptions. Tune them as more REITs are tested.

## straight_line_equals_fair_value_change (needs_review)

- **Detect:** the straight-line rent adjustment equals the absolute fair value
  change to within ₱1, AND the increase in accrued rent receivable differs from
  that adjustment by more than 10%.
- **Why it matters:** the two are separate concepts. An exact match suggests a
  presentation convention (offsetting the two) rather than a measured amount,
  so the true non-cash rent may be different.
- **Plain wording:** "The report's adjustment for rent not yet collected equals
  another figure to the peso, and doesn't match the change in uncollected rent
  on the balance sheet. This may be an accounting convention, but it's worth
  checking in the annual report."

## sponsor_finance_lease_income (worth_knowing)

- **Detect:** finance lease interest income is more than 10% of total revenue.
- **Why it matters:** this income comes from buildings leased to sponsor
  entities and is often accrued before cash is received. The dividend's safety
  partly depends on the sponsor paying on schedule.
- **Plain wording:** "About X of every 10 pesos of revenue is owed by companies
  related to the sponsor and is often collected later."

## related_party_lending (worth_knowing)

- **Detect:** cash outflow for amounts due from related parties (investing
  activities) exceeds 10% of net income for the period.
- **Why it matters:** cash lent to the sponsor group is cash not held by the
  REIT; it ties the REIT's liquidity to the sponsor.
- **Plain wording:** "During the quarter the REIT lent ₱X to companies in its
  sponsor's group."

## shares_issued_in_period (worth_knowing)

- **Detect:** shares outstanding at period end are more than 5% higher than
  at the start (`shares_outstanding` vs `shares_outstanding_prior`).
- **Why it matters:** PH REITs often buy properties from the sponsor by issuing
  new shares (property-for-share swaps). Dividends declared after the issue are
  paid on the larger share count, but the new properties may have contributed
  only part of the period's income. Coverage can look weaker or stronger than
  the run-rate until a full period has passed.
- **Plain wording:** "The REIT issued X new shares (Y% more) during the period,
  mostly to the sponsor in exchange for properties. Later dividends are shared
  across more shares, while the new properties have only just started earning."

## prior_period_mismatch (needs_review)

- **Detect:** when deriving the latest quarter of a year-to-date filing, the
  earlier period's facts file differs in ticker, year, period type or
  accounting model; a flow item is in only one file; derived capex is
  negative; or derived net income or fair value change differs from the
  quarter column the filing prints (`net_income_quarter`,
  `fair_value_change_quarter`). No quarter is derived.
- **Why it matters:** subtracting figures that were later restated produces a
  quarter that never happened.
- **Plain wording:** "The latest quarter on its own couldn't be worked out
  reliably because the earlier figures don't line up with this report, so
  this review uses the year-to-date numbers only."

## dividend_not_covered (needs_review)

- **Detect:** AFFO coverage below 1.00x.
- **Plain wording:** "The REIT paid out more than its buildings generated in
  cash earnings this period. Check whether this is temporary."

## Safety light (from AFFO coverage)

| Coverage | Light | Plain wording |
|---|---|---|
| ≥ 1.05x | green | "The dividend is covered by cash earnings." |
| 1.00x – 1.05x | yellow | "The dividend is covered, but with very little room to spare." |
| < 1.00x | red | "The dividend is larger than cash earnings this period." |

A single quarter is a snapshot. Prefer trends across several quarters when available.
