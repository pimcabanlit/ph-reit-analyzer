#!/usr/bin/env python3
"""Compute REIT metrics, validation checks and flags from a facts JSON file.

Every calculation in this project lives here, so numbers are reproducible and
testable. The AI extracts facts; this script does the math.

Usage:
    python <skill-dir>/scripts/compute_metrics.py <facts.json> [-o outputs/<ticker>/<period>/metrics.json] [--prior <facts.json>]

For year-to-date periods (half, nine_months), the standalone latest quarter is
derived by subtracting the earlier period's facts file of the same year, if
it exists next to this one (<YYYY>-Q1.facts.json for a half,
<YYYY>-H1.facts.json for nine months) or is given with --prior.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_facts import validate  # noqa: E402

PERIODS_PER_YEAR = {"quarter": 4, "half": 2, "nine_months": 4 / 3, "year": 1}

# Tolerance for comparing against figures the filing reports in millions
# (rounded to P0.01 million = P10,000; half of that is the max rounding error).
ROUNDED_MILLIONS_TOLERANCE = 5_000

# Starting thresholds; see references/red-flags.md. Tune as more REITs are tested.
SAFETY_GREEN_MIN = 1.05
SAFETY_YELLOW_MIN = 1.00
FINANCE_LEASE_SHARE_FLAG = 0.10
RELATED_PARTY_LENDING_FLAG = 0.10
STRAIGHT_LINE_MISMATCH = 0.10
SHARES_ISSUED_FLAG = 0.05
# Year-to-date period -> (period type of the earlier file, its label suffix)
PRIOR_PERIOD = {"half": ("quarter", "Q1"), "nine_months": ("half", "H1")}
# Flow items subtracted to derive a standalone quarter
DERIVED_FLOWS = ["net_income", "fair_value_change", "real_estate_depreciation", "gain_on_property_sale",
                 "straight_line_rent_adjustment", "capex_investment_property"]
NAV_ROUNDING_TOLERANCE = 0.01


class Facts:
    def __init__(self, doc):
        self.meta = doc["meta"]
        self.items = doc["facts"]
        self.dividends = doc.get("dividends")

    def get(self, key, required=True):
        item = self.items.get(key)
        if item is None or item.get("value") is None:
            if required:
                raise KeyError(f"Missing required fact: {key}")
            return None
        return item["value"]

    def page(self, key):
        item = self.items.get(key)
        return item.get("page") if item else None

    def source(self, key):
        """Page, printed label and column, so a reader can find the value in the PDF."""
        return cite(self.items.get(key))


def cite(item):
    item = item or {}
    return {"page": item.get("page"), "label": item.get("label"), "column": item.get("column")}


def ffo_affo(model, v):
    """FFO and AFFO from flow values (references/accounting-models.md)."""
    if model == "fair_value":
        ffo = v["net_income"] - v["fair_value_change"]
    elif model == "cost":
        ffo = v["net_income"] + v["real_estate_depreciation"] - (v.get("gain_on_property_sale") or 0)
    else:
        raise ValueError(f"Unknown accounting model: {model}")
    affo = ffo - (v.get("straight_line_rent_adjustment") or 0) - v["capex_investment_property"]
    return ffo, affo


def safety_light(coverage):
    if coverage is None:
        return None
    if coverage >= SAFETY_GREEN_MIN:
        return "green"
    if coverage >= SAFETY_YELLOW_MIN:
        return "yellow"
    return "red"


def compute(doc, prior_doc=None):
    f = Facts(doc)
    model = f.meta["accounting_model"]
    period_type = f.meta.get("period_type", "quarter")

    net_income = f.get("net_income")
    flows = {k: f.get(k, required=False) for k in DERIVED_FLOWS}
    ffo, affo = ffo_affo(model, flows)
    ffo_method = {"fair_value": "net income minus fair value change (fair value model)",
                  "cost": "net income plus real estate depreciation minus gains on sale (cost model)"}[model]
    straight_line = flows["straight_line_rent_adjustment"] or 0
    capex = flows["capex_investment_property"]

    shares = f.get("shares_outstanding")
    if f.dividends:
        # One entry per declaration, each on its own record-date share count
        breakdown = [{
            "for_period": d["for_period"],
            "dividend_per_share": d["dividend_per_share"]["value"],
            "shares": d["shares"]["value"],
            "total": round(d["dividend_per_share"]["value"] * d["shares"]["value"]),
            "dividend_source": cite(d["dividend_per_share"]),
            "shares_source": cite(d["shares"]),
        } for d in f.dividends]
    else:
        breakdown = [{
            "for_period": f.meta.get("period_label"),
            "dividend_per_share": f.get("dividend_per_share_declared"),
            "shares": shares,
            "total": round(f.get("dividend_per_share_declared") * shares),
            "dividend_source": f.source("dividend_per_share_declared"),
            "shares_source": f.source("shares_outstanding"),
        }]
    dps = sum(b["dividend_per_share"] for b in breakdown)
    dividend_total = sum(b["total"] for b in breakdown)
    coverage = affo / dividend_total if dividend_total else None

    di = f.get("reported_distributable_income", required=False)
    payout_di = dividend_total / di if di else None

    equity = f.get("total_equity")
    nav_per_share = equity / shares if model == "fair_value" else None

    revenue = f.get("total_revenue")
    fl_income = f.get("finance_lease_interest_income", required=False)
    fl_share = fl_income / revenue if fl_income is not None else None

    debt = f.get("total_debt", required=False)
    assets = f.get("total_assets")

    metrics = {
        "ffo": ffo,
        "ffo_method": ffo_method,
        "affo": affo,
        "dividend_declared_total": dividend_total,
        "dividend_per_share_for_period": dps,
        "dividend_breakdown": breakdown,
        "affo_coverage": coverage,
        "payout_of_distributable_income": payout_di,
        "nav_per_share": nav_per_share,
        "annualized_dividend_per_share": dps * PERIODS_PER_YEAR.get(period_type, 1),
        "finance_lease_share_of_revenue": fl_share,
        "debt_to_equity": debt / equity if debt is not None else None,
        "debt_to_total_assets": debt / assets if debt is not None else None,
    }

    metrics["safety_light"] = safety_light(coverage)

    derived, derived_checks, derived_flags = derive_quarter(f, prior_doc, flows, breakdown)
    metrics["derived_quarter"] = derived

    bridge = [
        {"step": "Net income", "value": net_income, **f.source("net_income")},
    ]
    if model == "fair_value":
        bridge.append({"step": "Remove fair value change", "value": -f.get("fair_value_change"), **f.source("fair_value_change")})
    else:
        bridge.append({"step": "Add back real estate depreciation", "value": f.get("real_estate_depreciation"), **f.source("real_estate_depreciation")})
    bridge += [
        {"step": "FFO", "value": ffo, "page": None, "subtotal": True},
        {"step": "Less straight-line rent", "value": -straight_line, **f.source("straight_line_rent_adjustment")},
    ]
    if di is not None and model == "fair_value":
        # Reported figure; the distributable_income_reconciles check confirms it equals the running total
        bridge.append({"step": "Distributable income (reported)", "value": di, **f.source("reported_distributable_income"),
                       "subtotal": True})
    bridge += [
        {"step": "Less capex", "value": -capex, **f.source("capex_investment_property")},
        {"step": "AFFO", "value": affo, "page": None, "subtotal": True},
    ]
    if len(breakdown) == 1:
        b = breakdown[0]
        bridge.append({"step": "Dividend declared for the period", "value": dividend_total, **b["dividend_source"], "comparison": True})
    else:
        # Show how the combined dividend is built, one row per declaration
        for b in breakdown:
            bridge.append({"step": f"{b['for_period']}: {b['dividend_per_share']:.2f} x {b['shares']:,} shares",
                           "value": b["total"], **b["dividend_source"], "detail": True})
        bridge.append({"step": "Dividends declared for the period", "value": dividend_total, "page": None,
                       "subtotal": True, "comparison": True})

    return {
        "meta": {k: f.meta.get(k) for k in ("ticker", "form_type", "period_label", "period_type", "period_end", "accounting_model", "source_file")},
        "metrics": metrics,
        "bridge": bridge,
        "checks": run_checks(f, ffo, nav_per_share) + derived_checks,
        "flags": detect_flags(f, coverage, fl_share) + derived_flags,
    }


def derive_quarter(f, prior_doc, flows, breakdown):
    """Standalone latest quarter = year-to-date minus the earlier period, for flow items only.

    Returns (derived_quarter or None, checks, flags). Refuses to subtract, and
    flags prior_period_mismatch, when the two files don't line up or the result
    disagrees with the quarter column the filing prints itself.
    """
    period_type = f.meta.get("period_type")
    if period_type not in PRIOR_PERIOD:
        return None, [], []
    skipped = lambda why: [{"id": "derived_quarter_matches_filing", "status": "skipped", "detail": why}]  # noqa: E731
    if prior_doc is None:
        return None, skipped("No facts file for the earlier period"), []

    p = Facts(prior_doc)
    year, month = f.meta["period_end"][:4], int(f.meta["period_end"][5:7])
    quarter = f"{year}-Q{(month - 1) // 3 + 1}"
    problems = []
    expected_type, _ = PRIOR_PERIOD[period_type]
    if p.meta.get("period_type") != expected_type:
        problems.append(f"earlier file is a {p.meta.get('period_type')}, expected {expected_type}")
    for key in ("ticker", "accounting_model"):
        if p.meta.get(key) != f.meta.get(key):
            problems.append(f"{key} differs ({p.meta.get(key)} vs {f.meta.get(key)})")
    if p.meta.get("period_end", "")[:4] != year:
        problems.append(f"earlier file is for {p.meta.get('period_end', '')[:4]}, not {year}")

    values, inputs, verified = {}, {}, []
    if not problems:
        for key in DERIVED_FLOWS:
            cur, prev = flows[key], p.get(key, required=False)
            if cur is None and prev is None:
                continue
            if cur is None or prev is None:
                problems.append(f"{key} is in only one of the two files")
                continue
            values[key] = cur - prev
            inputs[key] = {"value": values[key], "year_to_date": f.source(key), "earlier": p.source(key)}
        if values.get("capex_investment_property", 0) < 0:
            problems.append("derived capex is negative, so the earlier capex is larger than year-to-date")
        # The filing prints its own quarter column for income statement items: the derived value must match it
        for key in ("net_income", "fair_value_change"):
            printed = f.get(f"{key}_quarter", required=False)
            if printed is None or key not in values:
                continue
            if abs(values[key] - printed) > 1:
                problems.append(f"derived {key} {values[key]:,} differs from the filing's quarter column {printed:,} "
                                f"(p.{f.page(key + '_quarter')}); the earlier figures may have been restated")
            else:
                verified.append(key)

    if problems:
        detail = "; ".join(problems)
        return None, [{"id": "derived_quarter_matches_filing", "status": "needs_review", "detail": detail}], [{
            "id": "prior_period_mismatch",
            "severity": "needs_review",
            "detail": f"Standalone {quarter} not derived: {detail}.",
            "pages": [],
        }]

    ffo, affo = ffo_affo(f.meta["accounting_model"], values)
    dividend = next((b for b in breakdown if b["for_period"] == quarter), None)
    coverage = affo / dividend["total"] if dividend and dividend["total"] else None
    derived = {
        "period": quarter,
        "basis": "derived",
        "derived_from": [f.meta.get("period_label"), p.meta.get("period_label")],
        "inputs": inputs,
        "ffo": ffo,
        "affo": affo,
        "dividend_declared": dividend["total"] if dividend else None,
        "dividend_per_share": dividend["dividend_per_share"] if dividend else None,
        "affo_coverage": coverage,
        "safety_light": safety_light(coverage),
        "verified_against_filing": verified,
    }
    if verified:
        check = {"id": "derived_quarter_matches_filing", "status": "pass",
                 "detail": f"Derived {quarter} " + ", ".join(f"{k} {values[k]:,}" for k in verified)
                           + " match the filing's quarter column"}
    else:
        check = skipped("No quarter column in the facts file to compare against")[0]
    return derived, [check], []


def _check(check_id, ok, detail, review=False):
    status = "pass" if ok else ("needs_review" if review else "fail")
    return {"id": check_id, "status": status, "detail": detail}


def run_checks(f, ffo, nav_per_share):
    checks = []

    assets, liab, equity = f.get("total_assets"), f.get("total_liabilities"), f.get("total_equity")
    diff = assets - (liab + equity)
    checks.append(_check("balance_sheet_balances", abs(diff) <= 1,
                         f"assets - (liabilities + equity) = {diff:,}"))

    mdna = f.get("mdna_net_income_before_fv_change", required=False)
    if mdna is not None and f.meta["accounting_model"] == "fair_value":
        diff = ffo - mdna
        checks.append(_check("ffo_matches_mdna", abs(diff) <= ROUNDED_MILLIONS_TOLERANCE,
                             f"FFO {ffo:,} vs MD&A {mdna:,} (diff {diff:,})", review=True))
    else:
        checks.append({"id": "ffo_matches_mdna", "status": "skipped", "detail": "No MD&A figure or not fair value model"})

    di = f.get("reported_distributable_income", required=False)
    if di is not None and f.meta["accounting_model"] == "fair_value":
        rebuilt = f.get("net_income") - f.get("fair_value_change") - (f.get("straight_line_rent_adjustment", required=False) or 0)
        diff = rebuilt - di
        checks.append(_check("distributable_income_reconciles", abs(diff) <= 1,
                             f"net income - FV change - straight-line = {rebuilt:,} vs reported {di:,}", review=True))
    else:
        checks.append({"id": "distributable_income_reconciles", "status": "skipped", "detail": "Not available"})

    if f.dividends:
        pairs = [(d["for_period"], round(d["dividend_per_share"]["value"] * d["shares"]["value"]), d["reported_total"]["value"])
                 for d in f.dividends if d.get("reported_total")]
    else:
        reported = f.get("dividend_declared_total_reported", required=False)
        pairs = [(f.meta.get("period_label"), round(f.get("dividend_per_share_declared") * f.get("shares_outstanding")), reported)] \
            if reported is not None else []
    if pairs:
        ok = all(abs(calc - rep) <= ROUNDED_MILLIONS_TOLERANCE for _, calc, rep in pairs)
        detail = "; ".join(f"{label}: DPS x shares = {calc:,} vs reported {rep:,} (diff {calc - rep:,})" for label, calc, rep in pairs)
        checks.append(_check("dividend_total_matches_reported", ok, detail, review=True))
    else:
        checks.append({"id": "dividend_total_matches_reported", "status": "skipped", "detail": "No reported total"})

    reported_nav = f.get("reported_nav_per_share", required=False)
    if reported_nav is not None and nav_per_share is not None:
        diff = nav_per_share - reported_nav
        checks.append(_check("nav_matches_reported", abs(diff) <= NAV_ROUNDING_TOLERANCE,
                             f"equity / shares = {nav_per_share:.4f} vs reported {reported_nav:.2f}", review=True))
    else:
        checks.append({"id": "nav_matches_reported", "status": "skipped", "detail": "No reported NAV or cost model"})

    return checks


def detect_flags(f, coverage, fl_share):
    flags = []

    sl = f.get("straight_line_rent_adjustment", required=False)
    fv = f.get("fair_value_change", required=False)
    ar, ar_prior = f.get("accrued_rent_receivable", required=False), f.get("accrued_rent_receivable_prior", required=False)
    if sl and fv is not None and ar is not None and ar_prior is not None:
        ar_increase = ar - ar_prior
        if abs(sl - abs(fv)) <= 1 and abs(ar_increase - sl) > STRAIGHT_LINE_MISMATCH * sl:
            flags.append({
                "id": "straight_line_equals_fair_value_change",
                "severity": "needs_review",
                "detail": f"Straight-line adjustment {sl:,} equals |fair value change| {abs(fv):,}; accrued rent receivable rose {ar_increase:,}.",
                "pages": [f.page("straight_line_rent_adjustment"), f.page("fair_value_change"), f.page("accrued_rent_receivable")],
            })

    if fl_share is not None and fl_share > FINANCE_LEASE_SHARE_FLAG:
        fl_now, fl_prior = f.get("finance_lease_receivable", required=False), f.get("finance_lease_receivable_prior", required=False)
        growth = f" Finance lease receivable grew {fl_now - fl_prior:,}." if fl_now is not None and fl_prior is not None else ""
        flags.append({
            "id": "sponsor_finance_lease_income",
            "severity": "worth_knowing",
            "detail": f"Finance lease interest is {fl_share:.1%} of revenue.{growth}",
            "pages": [f.page("finance_lease_interest_income"), f.page("finance_lease_receivable")],
        })

    rp = f.get("change_due_from_related_parties", required=False)
    ni = f.get("net_income")
    if rp is not None and rp < 0 and -rp > RELATED_PARTY_LENDING_FLAG * ni:
        flags.append({
            "id": "related_party_lending",
            "severity": "worth_knowing",
            "detail": f"Cash lent to related parties: {-rp:,} ({-rp / ni:.0%} of net income).",
            "pages": [f.page("change_due_from_related_parties")],
        })

    shares, shares_prior = f.get("shares_outstanding"), f.get("shares_outstanding_prior", required=False)
    if shares_prior and (shares - shares_prior) / shares_prior > SHARES_ISSUED_FLAG:
        flags.append({
            "id": "shares_issued_in_period",
            "severity": "worth_knowing",
            "detail": f"Shares outstanding rose {shares - shares_prior:,} ({(shares - shares_prior) / shares_prior:.1%}) during the period.",
            "pages": [f.page("shares_outstanding"), f.page("shares_outstanding_prior")],
        })

    if coverage is not None and coverage < 1.0:
        flags.append({
            "id": "dividend_not_covered",
            "severity": "needs_review",
            "detail": f"AFFO coverage {coverage:.2f}x is below 1.00x.",
            "pages": [],
        })

    return flags


def print_summary(result):
    m = result["metrics"]
    meta = result["meta"]
    print(f"\n{meta['ticker']} {meta['period_label']} ({meta['accounting_model']} model)")
    print("-" * 52)
    for row in result["bridge"]:
        source = f"p.{row['page']} \"{row.get('label') or '?'}\"" if row.get("page") else "computed"
        step = f"  {row['step']}" if row.get("detail") else row["step"]
        print(f"{step:<44}{row['value'] / 1e6:>12,.1f}M  {source}")
    print("-" * 52)
    print(f"AFFO coverage: {m['affo_coverage']:.2f}x  -> safety light: {m['safety_light']}")
    if m["payout_of_distributable_income"] is not None:
        print(f"Payout of distributable income: {m['payout_of_distributable_income']:.1%}")
    if m["nav_per_share"] is not None:
        print(f"NAV per share (estimate): {m['nav_per_share']:.2f}")
    dq = m.get("derived_quarter")
    if dq and dq["affo_coverage"] is not None:
        print(f"Standalone {dq['period']} (derived): AFFO {dq['affo'] / 1e6:,.1f}M, "
              f"coverage {dq['affo_coverage']:.2f}x -> {dq['safety_light']}")
    print("\nChecks:")
    for c in result["checks"]:
        print(f"  [{c['status']}] {c['id']}: {c['detail']}")
    print("\nFlags:")
    for fl in result["flags"] or [{"severity": "-", "id": "none", "detail": "Nothing unusual detected"}]:
        print(f"  [{fl['severity']}] {fl['id']}: {fl['detail']}")


def find_prior(facts_path, meta):
    """The earlier period's facts file, if it sits next to this one."""
    if meta.get("period_type") not in PRIOR_PERIOD:
        return None
    candidate = facts_path.parent / f"{meta['period_end'][:4]}-{PRIOR_PERIOD[meta['period_type']][1]}.facts.json"
    return candidate if candidate.exists() else None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("facts", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="Where to write metrics.json")
    parser.add_argument("--prior", type=Path, help="Facts file for the earlier period of the same year")
    args = parser.parse_args()

    doc = json.loads(args.facts.read_text())
    errors, warnings = validate(doc)
    for w in warnings:
        print(f"  [warning] {w}")
    if errors:
        for e in errors:
            print(f"  [error] {e}")
        print(f"\nFix the facts file before computing ({len(errors)} errors). Nothing was calculated.")
        return 1

    prior_path = args.prior or find_prior(args.facts, doc["meta"])
    prior_doc = None
    if prior_path:
        prior_doc = json.loads(prior_path.read_text())
        prior_errors, _ = validate(prior_doc)
        if prior_errors:
            print(f"  [warning] earlier facts file {prior_path} is invalid, so no quarter is derived: {prior_errors[0]}")
            prior_doc = None
        else:
            print(f"  Deriving the standalone quarter with {prior_path}")

    result = compute(doc, prior_doc)
    result["validation_warnings"] = warnings
    print_summary(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2))
        print(f"\nSaved {args.output}")


if __name__ == "__main__":
    sys.exit(main())
