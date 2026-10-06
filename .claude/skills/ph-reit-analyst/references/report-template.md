# Report template (quarterly review)

Write for a smart reader with no finance background. Short sentences. Explain
each technical term once, in parentheses. Use pesos in millions with one
decimal (₱2,520.7M) except per-share figures (₱0.62).

ALWAYS use this structure:

```markdown
# <TICKER> — <period, e.g. Q1 2026 or 1H 2026 (January to June)> review

**In one sentence:** <plain answer about dividend safety, citing coverage>

**Dividend safety:** <light: green/yellow/red> — <one plain sentence>

## Worth knowing
- <one bullet per flag, plain wording from references/red-flags.md, with the number>
(If there are no flags, write "Nothing unusual stood out in this report.")

## From earnings to dividend
| Step | ₱ millions | Source (page · search phrase · column) |
|---|---|---|
| Net income | | p.<n> · "<label>" · <column> |
| ± Fair value change (paper gain/loss) | | p.<n> · "<label>" · <column> |
| = FFO (funds from operations) | | computed |
| − Straight-line rent (booked, not yet collected) | | p.<n> · "<label>" · <column> |
| − Capex (spending on the buildings) | | p.<n> · "<label>" · <column> |
| = AFFO (cash earnings after upkeep) | | computed |
| Dividend declared for the period | | p.<n> · "<label>" |
| Coverage (AFFO ÷ dividend) | x.xx | computed |

## Checks
<list each validation check: passed / needs review, one line each>

## Other figures
- Payout of distributable income: <x>%
- NAV per share (estimate): ₱<x> — <one-line caveat>
- Sponsor ownership: <x>%

---
Source: <form, period, filing date>. For learning and research only. Not investment advice.
```

Sources: copy the page, `label` and `column` from the bridge rows in
`metrics.json`. The quoted label is exact text from the filing, so the reader
can search the PDF for it. `check_report.py` fails any page citation without
a quoted phrase.

When the period has more than one dividend declaration (1H, 9M), replace the
single dividend row with one row per declaration from `dividend_breakdown`,
then the total:

```markdown
| Dividends declared: | | |
| &nbsp;&nbsp;Q1: ₱0.62 × 3,715,756,162 shares | 2,303.8 | p.18 · "for the first quarter of 2026" |
| &nbsp;&nbsp;Q2: ₱0.63 × 4,156,887,818 shares | 2,618.8 | p.21 · "for the second quarter of 2026" |
| = Total dividends for the period | 4,922.6 | computed |
```

Each declaration uses the share count on its own record date, which can
differ when new shares are issued mid-year. Say so in one line under the table.

For year-to-date periods (1H, 9M), say so in the title and the one-sentence
answer.

Tone examples:

- Good: "AREIT earned ₱1.09 in cash earnings for every ₱1 it paid in dividends."
- Avoid: "AFFO/DPS coverage of 1.09x indicates adequate distribution sustainability."
- Never: "AREIT is a good buy." / "Investors should hold."
