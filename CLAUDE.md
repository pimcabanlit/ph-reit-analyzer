# PH REIT Analyst — project rules

This repo analyzes Philippine REITs from PSE/SEC filings (17-Q, 17-A, dividend
and asset disclosures). The core skill is `.claude/skills/ph-reit-analyst/`.
Always run commands from the repo root.

## Non-negotiable rules

1. **Numbers come from files and scripts, never mental math.** Extract raw
   values into a facts JSON, then let `scripts/compute_metrics.py` do every
   calculation. If you need a number the script doesn't produce, add it to the
   script rather than computing it in prose.
2. **Every extracted number cites its page.** Use the printed page number of the
   filing and note the PDF page index if it differs. A number without a page
   citation does not go into a facts file.
3. **Flag, don't guess.** If a value is ambiguous, missing, or contradicts
   another part of the filing, record it with `"confidence": "low"` and a note,
   and surface it in the report. Never fill gaps with assumptions silently.
4. **No buy/sell recommendations.** Outputs describe dividend safety, valuation,
   and risks. They never tell the reader to buy, sell, or hold. Every report
   ends with: "For learning and research only. Not investment advice."
5. **Plain language first.** Reports lead with a one-sentence answer a
   non-finance reader understands, then details. Technical terms get a short
   plain explanation the first time they appear.

## Repo map

- `.claude/skills/ph-reit-analyst/SKILL.md` — entry point; routes to workflows
- `references/` — domain knowledge (accounting models, PH REIT rules, red flags,
  report template, workflows)
- `schemas/reit_facts.schema.json` — the contract between extraction and analysis
- `scripts/compute_metrics.py` — FFO, AFFO, coverage, NAV, checks, flags
- `scripts/run_eval.py` — compares results against known-correct answers
- `evals/` — test cases; `evals/gold/` holds hand-verified facts files
- `data/raw/<ticker>/` — source PDFs, named `<YYYY>-<period>-<form>.pdf`
- `data/facts/<ticker>/` — extracted facts, named `<YYYY>-<period>.facts.json`
- `outputs/<ticker>/<YYYY>-<period>/` — metrics, report, charts

## Working style

- Propose a plan before large changes and wait for approval.
- Keep changes small; run `python scripts/run_eval.py` after any change to
  extraction or metrics logic and report what passes and fails.
- Explain new scripts briefly in plain language — the owner is learning too.
- Commit after each working step with a clear message.
