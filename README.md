# PH REIT Analyst

A Claude skill that reads a Philippine REIT's quarterly report and answers one
question in plain language: **is the dividend backed by real cash, and what
should an investor know?**

Instead of digging through a 50-page SEC Form 17-Q, you get a one-page report
that tells you whether the dividend is covered by cash earnings (green /
yellow / red), what's unusual in the filing, and where every number came from.

It extracts the key numbers with page citations, computes FFO, AFFO, dividend
coverage and NAV per share with scripts (never mental math), runs validation
checks, and flags issues worth a closer look. It never gives buy/sell advice.

## Status

Version 0.2: quarterly review workflow only, tested on AREIT Q1 2026.

## Install

**Claude Code:** clone this repo and open it; the skill in
`.claude/skills/ph-reit-analyst/` loads automatically. To use it in other
projects, copy that folder to `~/.claude/skills/`.

**Claude.ai:** zip the `.claude/skills/ph-reit-analyst/` folder and upload it
under Settings > Capabilities > Skills. Code execution must be enabled.

**Python packages** (for reading PDFs):

```bash
pip install -r .claude/skills/ph-reit-analyst/requirements.txt
```

## Use

Put the filing at `data/raw/areit/2026-Q1-17Q.pdf` and ask Claude:

- "Run a quarterly review on data/raw/areit/2026-Q1-17Q.pdf"
- "Is AREIT's dividend safe this quarter?"
- "Safe ba ang dividend ng AREIT ngayong quarter?"

See [`evals/gold/areit-2026-q1.report.md`](evals/gold/areit-2026-q1.report.md)
for an example of the report it produces.

## Develop and test

```bash
SKILL=.claude/skills/ph-reit-analyst

# Compute metrics from the hand-verified AREIT facts
python $SKILL/scripts/compute_metrics.py evals/gold/areit-2026-q1.facts.json

# Functional eval: facts validation, metrics, checks, flags and the example report
python evals/run_eval.py evals/areit-2026-q1.json

# Test a facts file or report produced by the skill against the gold answers
python evals/run_eval.py evals/areit-2026-q1.json \
  --facts data/facts/areit/2026-Q1.facts.json --report outputs/areit/2026-Q1/report.md

# Trigger eval: does the skill load for relevant requests and stay off otherwise?
# Needs the claude CLI; makes one model call per prompt.
python evals/run_trigger_eval.py
```

The extraction step (PDF to facts) can only be tested end to end once the
filing PDF is in `data/raw/areit/`.

## Disclaimer

For learning and research only. Not investment advice.
