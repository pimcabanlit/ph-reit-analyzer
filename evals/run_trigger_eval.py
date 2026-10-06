#!/usr/bin/env python3
"""Check that the skill loads for the right requests and stays off for others.

Sends each prompt in evals/triggers.json to Claude Code in headless mode and
records whether Claude invoked the skill. Needs the `claude` CLI, logged in,
run from the repo root (so the project skill is visible). Each prompt costs a
short model call, so this isn't part of run_eval.py.

Usage:
    python evals/run_trigger_eval.py                    # all prompts once
    python evals/run_trigger_eval.py --runs 3           # repeat to see consistency
    python evals/run_trigger_eval.py --only should_not_trigger

Exit code is 1 if the trigger rate is below target or any should-not prompt
triggered.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

CASES = Path(__file__).resolve().parent / "triggers.json"


def triggered(prompt, skill, max_turns, timeout):
    """Return True if Claude invoked the skill while handling the prompt."""
    cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose", "--max-turns", str(max_turns)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except subprocess.TimeoutExpired:
        return None
    for line in out.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "assistant":
            continue
        for block in event["message"].get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == "Skill" \
                    and block.get("input", {}).get("skill", "").endswith(skill):
                return True
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--only", choices=["should_trigger", "should_not_trigger"])
    parser.add_argument("--max-turns", type=int, default=2, help="Turns allowed per prompt (skill is usually called in the first)")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    cases = json.loads(CASES.read_text())
    skill = cases["skill"]
    groups = [args.only] if args.only else ["should_trigger", "should_not_trigger"]
    results = {g: [] for g in groups}

    for group in groups:
        print(f"\n{group}:")
        for prompt in cases[group]:
            hits = [triggered(prompt, skill, args.max_turns, args.timeout) for _ in range(args.runs)]
            n = sum(h is True for h in hits)
            expected = group == "should_trigger"
            ok = (n == args.runs) if expected else (n == 0)
            timeouts = sum(h is None for h in hits)
            note = f" ({timeouts} timed out)" if timeouts else ""
            print(f"  {'PASS' if ok else 'FAIL'}  {n}/{args.runs} triggered{note}  {prompt}")
            results[group].append(n / args.runs)

    failed = False
    if "should_trigger" in results:
        rate = sum(results["should_trigger"]) / len(results["should_trigger"])
        target = cases.get("target_trigger_rate", 0.9)
        print(f"\nTrigger rate on relevant prompts: {rate:.0%} (target {target:.0%})")
        failed |= rate < target
    if "should_not_trigger" in results:
        false_hits = sum(r > 0 for r in results["should_not_trigger"])
        print(f"Unrelated prompts that triggered: {false_hits} of {len(results['should_not_trigger'])}")
        failed |= false_hits > 0
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
