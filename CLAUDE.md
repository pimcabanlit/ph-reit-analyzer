# PH REIT Analyst — project rules

This repo builds and tests the `ph-reit-analyst` skill, which analyzes
Philippine REITs from PSE/SEC filings (17-Q, 17-A, dividend and asset
disclosures). Always run commands from the repo root.

The skill is self-contained in `.claude/skills/ph-reit-analyst/`. Its rules
(numbers from scripts only, page citations, flag don't guess, no buy/sell
advice, plain language) live in its `SKILL.md` so they travel with the skill
when it's uploaded to Claude.ai or used through the API. Don't duplicate them
here; change them there.

## Repo map

- `.claude/skills/ph-reit-analyst/`: the skill (everything it needs at runtime)
  - `SKILL.md`: entry point, critical rules, examples, troubleshooting
  - `references/`: accounting models, PH REIT rules, red flags, report template, workflows
  - `schemas/reit_facts.schema.json`: the contract between extraction and analysis
  - `scripts/validate_facts.py`: checks a facts file (runs automatically before metrics)
  - `scripts/compute_metrics.py`: FFO, AFFO, coverage, NAV, checks, flags
  - `scripts/check_report.py`: checks a finished report against the rules
  - `requirements.txt`: PDF libraries
- `evals/`: development tests, not part of the skill
  - `run_eval.py` + `<case>.json`: functional tests against known answers
  - `gold/`: hand-verified facts and an example report
  - `run_trigger_eval.py` + `triggers.json`: does the skill load when it should?
- `data/raw/<ticker>/`: source PDFs, named `<YYYY>-<period>-<form>.pdf`
- `data/facts/<ticker>/`: extracted facts, named `<YYYY>-<period>.facts.json`
- `outputs/<ticker>/<YYYY>-<period>/`: metrics, report, charts (git-ignored)

## Working style

- Propose a plan before large changes and wait for approval.
- Keep changes small. After any change to extraction, metrics or report logic,
  run `python evals/run_eval.py` on every case in `evals/` (`areit-2026-q1.json`,
  `areit-2026-h1.json`) and report what passes and fails.
- After changing the skill's `description`, run
  `python evals/run_trigger_eval.py` (makes one model call per prompt).
- Keep the skill portable: no paths outside its folder, no reliance on this
  file. Bump `metadata.version` in `SKILL.md` when behavior changes.
- Explain new scripts briefly in plain language; the owner is learning too.
- Commit after each working step with a clear message.
