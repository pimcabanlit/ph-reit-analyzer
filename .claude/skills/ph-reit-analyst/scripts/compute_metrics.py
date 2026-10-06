#!/usr/bin/env python3
"""Compute REIT metrics, validation checks and flags from a facts JSON file.

Every calculation in this project lives here, so numbers are reproducible and
testable. The AI extracts facts; this script does the math.

Usage:
    python <skill-dir>/scripts/compute_metrics.py <facts.json> [-o outputs/<ticker>/<period>/metrics.json]
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


def compute(doc):
    f = Facts(doc)
    model = f.meta["accounting_model"]
    period_type = f.meta.get("period_type", "quarter")

    net_income = f.get("net_income")

    # FFO depends on the accounting model (references/accounting-models.md)
    if model == "fair_value":
        fv_change = f.get("fair_value_change")
        ffo = net_income - fv_change
        ffo_method = "net income minus fair value change (fair value model)"
    elif model == "cost":
        dep = f.get("real_estate_depreciation")
        gain = f.get("gain_on_property_sale", required=False) or 0
        ffo = net_income + dep - gain
        ffo_method = "net income plus real estate depreciation minus gains on sale (cost model)"
    else:
        raise ValueError(f"Unknown accounting model: {model}")

    straight_line = f.get("straight_line_rent_adjustment", required=False) or 0
    capex = f.get("capex_investment_property")
    affo = ffo - straight_line - capex

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

    if coverage is None:
        light = None
    elif coverage >= SAFETY_GREEN_MIN:
        light = "green"
    elif coverage >= SAFETY_YELLOW_MIN:
        light = "yellow"
    else:
        light = "red"
    metrics["safety_light"] = light

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
        "checks": run_checks(f, ffo, nav_per_share),
        "flags": detect_flags(f, coverage, fl_share),
    }


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
    print("\nChecks:")
    for c in result["checks"]:
        print(f"  [{c['status']}] {c['id']}: {c['detail']}")
    print("\nFlags:")
    for fl in result["flags"] or [{"severity": "-", "id": "none", "detail": "Nothing unusual detected"}]:
        print(f"  [{fl['severity']}] {fl['id']}: {fl['detail']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("facts", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="Where to write metrics.json")
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

    result = compute(doc)
    result["validation_warnings"] = warnings
    print_summary(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2))
        print(f"\nSaved {args.output}")


if __name__ == "__main__":
    sys.exit(main())
