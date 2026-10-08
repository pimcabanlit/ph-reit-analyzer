# PH REIT Analyst

A Claude skill that reads a Philippine REIT's quarterly report (SEC Form 17-Q)
or annual report (SEC Form 17-A) and answers one question in plain language:
**is the dividend backed by real cash, and what should an investor know?**

Instead of digging through a 50-page 17-Q or a 700-page 17-A, you get a
one-page report that tells you whether the dividend is covered by cash
earnings (green / yellow / red), what's unusual in the filing, and where every
number came from.

It extracts the key numbers with page citations, computes FFO, AFFO, dividend
coverage and NAV per share with scripts (never mental math), runs validation
checks, and flags issues worth a closer look. For annual reports it also checks
the REIT rule's 90% payout minimum and shows a three-year trend. It never gives
buy/sell advice.

## Status

Version 0.10: quarterly (17-Q) and annual (17-A) review workflows.

- **Quarterly:** Q1 filings are analyzed for the quarter; Q2 and Q3 filings
  year-to-date, because the 17-Q only reports cash flows year-to-date. The
  latest quarter alone is also derived when the earlier period's facts file is
  available, and labeled "derived".
- **Annual:** full-year figures from the audited statements, the four
  quarterly dividends declared for the year, the 90% payout rule, retained
  earnings available for dividends, fair-value-adjusted NAV, a three-year
  trend, and checks against the quarterly reports. Large filings are indexed
  page by page so only the relevant pages are read.

Test cases: AREIT Q1 2026 (hand-verified), AREIT 1H 2026 from the Q2 17-Q, and
AREIT FY2025 from the 699-page 17-A (both extracted by the skill, pending owner
verification), plus three cases with deliberately broken inputs.

## Install

**Claude Code:** clone this repo and open it; the skill in
`.claude/skills/ph-reit-analyst/` loads automatically. To use it in other
projects, copy that folder to `~/.claude/skills/`.

**Claude.ai:** zip the `.claude/skills/ph-reit-analyst/` folder itself (so
`SKILL.md` sits at the top of the zip) and upload it under Settings >
Capabilities > Skills. Code execution must be enabled. GitHub's "Download ZIP"
gives the whole repo, which Claude.ai rejects.

**Python packages** (for reading PDFs):

```bash
pip install -r .claude/skills/ph-reit-analyst/requirements.txt
```

## Use

Put the filing in `data/raw/<ticker>/` (for example the included
`data/raw/areit/2026-Q2-17Q.pdf` or `data/raw/areit/2025-FY-17A.pdf`) and ask
Claude:

- "Run a quarterly review on data/raw/areit/2026-Q2-17Q.pdf"
- "Review AREIT's 2025 annual report: data/raw/areit/2025-FY-17A.pdf"
- "Did AREIT pay out at least 90% of its distributable income last year?"
- "Is AREIT's dividend safe this quarter?"
- "Safe ba ang dividend ng AREIT ngayong quarter?"

See [`evals/gold/areit-2026-q1/report.md`](evals/gold/areit-2026-q1/report.md),
[`evals/gold/areit-2026-h1/report.md`](evals/gold/areit-2026-h1/report.md) and
the annual [`evals/gold/areit-2025-fy/report.md`](evals/gold/areit-2025-fy/report.md)
for examples of the report it produces, each with its earnings bridge chart
(`bridge.png`). The chart design follows
[`docs/reference-bridge.png`](docs/reference-bridge.png).

## Develop and test

```bash
SKILL=.claude/skills/ph-reit-analyst

# Compute metrics and draw the earnings bridge for 1H 2026
python $SKILL/scripts/compute_metrics.py data/facts/areit/2026-H1.facts.json -o outputs/areit/2026-H1/metrics.json
python $SKILL/scripts/bridge_chart.py outputs/areit/2026-H1/metrics.json

# Functional eval: facts validation, metrics, checks, flags and the example report
python evals/run_eval.py evals/areit-2026-q1.json
python evals/run_eval.py evals/areit-2026-h1.json            # also derives standalone Q2
python evals/run_eval.py evals/areit-2026-h1-restated.json   # restated Q1 must block the derivation
python evals/run_eval.py evals/areit-2025-fy.json            # annual: 699-page 17-A, three-year trend
python evals/run_eval.py evals/areit-2025-fy-fv-sign.json    # fair value sign from the wrong label must be caught
python evals/run_eval.py evals/areit-2025-fy-shares.json     # wrong mid-year share count must be caught

# Test a facts file or report produced by the skill against the gold answers
python evals/run_eval.py evals/areit-2026-h1.json \
  --facts data/facts/areit/2026-H1.facts.json --report outputs/areit/2026-H1/report.md

# Intake eval: does page indexing find the right pages in the 17-Q and the 699-page 17-A?
python evals/run_intake_eval.py

# Trigger eval: does the skill load for relevant requests and stay off otherwise?
# Needs the claude CLI; makes one model call per prompt.
python evals/run_trigger_eval.py
```

The Q1 2026 filing PDF isn't in the repo, so only its analysis is tested.
AREIT's FY2025 17-A (`data/raw/areit/2025-FY-17A.pdf`) tests large-filing
intake and the annual workflow. How annual support was planned and built, and
the design decisions behind it, are in
[`docs/plans/annual-17a.md`](docs/plans/annual-17a.md).

## Disclaimer

For learning and research only. Not investment advice.
