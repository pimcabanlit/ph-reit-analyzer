# PH REIT Analyst

Analyzes Philippine REIT filings to answer one question in plain language:
**is the dividend backed by real cash, and what should an investor know?**

It reads a quarterly report (SEC Form 17-Q), extracts the key numbers with page
citations, computes FFO, AFFO, dividend coverage and NAV per share, runs
validation checks, and flags issues worth a closer look.

## Status

First version: quarterly review workflow only, tested on AREIT Q1 2026.

## Quick start

```bash
pip install -r requirements.txt

# Compute metrics from the hand-verified AREIT facts
python scripts/compute_metrics.py evals/gold/areit-2026-q1.facts.json

# Run the eval (checks metrics, checks and flags against known answers)
python scripts/run_eval.py evals/areit-2026-q1.json

# Once extraction produces its own facts file, test it against the gold one
python scripts/run_eval.py evals/areit-2026-q1.json --facts data/facts/areit/2026-Q1.facts.json
```

In Claude Code, put the filing at `data/raw/areit/2026-Q1-17Q.pdf` and ask:
"Run a quarterly review on data/raw/areit/2026-Q1-17Q.pdf".

## Disclaimer

For learning and research only. Not investment advice.
