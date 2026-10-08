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
from check_citations import iter_facts  # noqa: E402
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
PRIOR_PERIOD = {"half": ("quarter", "Q1"), "nine_months": ("half", "H1"), "year": ("nine_months", "9M")}
# Prior year-end figures in a quarterly filing -> the same figure in last year's annual report
PRIOR_YEAR_END = {"shares_outstanding_prior": "shares_outstanding",
                  "finance_lease_receivable_prior": "finance_lease_receivable",
                  "accrued_rent_receivable_prior": "accrued_rent_receivable"}
# Flow items subtracted to derive a standalone quarter
DERIVED_FLOWS = ["net_income", "fair_value_change", "real_estate_depreciation", "gain_on_property_sale",
                 "straight_line_rent_adjustment", "capex_investment_property", "capex_acquisitions"]
NAV_ROUNDING_TOLERANCE = 0.01


class Facts:
    def __init__(self, doc):
        self.meta = doc["meta"]
        self.items = doc["facts"]
        self.dividends = doc.get("dividends")
        self.doc = doc

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
    gain = v.get("gain_on_property_sale") or 0  # gains and losses on selling property aren't operating earnings
    if model == "fair_value":
        ffo = v["net_income"] - v["fair_value_change"] - gain
    elif model == "cost":
        ffo = v["net_income"] + v["real_estate_depreciation"] - gain
    else:
        raise ValueError(f"Unknown accounting model: {model}")
    # Upkeep capex only: cash purchases of whole buildings the filing identifies aren't spending on the buildings held
    upkeep = v["capex_investment_property"] - (v.get("capex_acquisitions") or 0)
    affo = ffo - (v.get("straight_line_rent_adjustment") or 0) - upkeep
    return ffo, affo


def safety_light(coverage):
    if coverage is None:
        return None
    if coverage >= SAFETY_GREEN_MIN:
        return "green"
    if coverage >= SAFETY_YELLOW_MIN:
        return "yellow"
    return "red"


def compute(doc, prior_doc=None, annual_doc=None):
    f = Facts(doc)
    model = f.meta["accounting_model"]
    period_type = f.meta.get("period_type", "quarter")

    net_income = f.get("net_income")
    flows = {k: f.get(k, required=False) for k in DERIVED_FLOWS}
    ffo, affo = ffo_affo(model, flows)
    ffo_method = {"fair_value": "net income minus fair value change and gains / losses on disposal (fair value model)",
                  "cost": "net income plus real estate depreciation minus gains / losses on disposal (cost model)"}[model]
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
    metrics["nav_fair_value_adjusted"] = fair_value_adjusted_nav(f, model, equity, shares)
    metrics["interest_coverage"] = interest_coverage(f)
    metrics["valuation"] = valuation(f, breakdown, nav_per_share)
    fl_receivable = f.get("finance_lease_receivable", required=False)
    metrics["assets_not_at_fair_value_share"] = (
        {"value": fl_receivable / assets, "basis": "finance lease receivables / total assets",
         "finance_lease_receivable": fl_receivable, "total_assets": assets}
        if model == "fair_value" and fl_receivable is not None else None)
    metrics["trend"], trend_checks = trend(f, model, metrics)
    metrics["share_issuances"], issuance_checks = share_issuances(f)
    metrics["subsequent_events"], event_flags = subsequent_events(f, metrics["share_issuances"])

    bridge = [
        {"step": "Net income", "value": net_income, **f.source("net_income")},
    ]
    if model == "fair_value":
        bridge.append({"step": "Remove fair value change", "value": -f.get("fair_value_change"), **f.source("fair_value_change")})
    else:
        bridge.append({"step": "Add back real estate depreciation", "value": f.get("real_estate_depreciation"), **f.source("real_estate_depreciation")})
    if flows["gain_on_property_sale"]:
        bridge.append({"step": "Remove gain or loss on disposal", "value": -flows["gain_on_property_sale"],
                       **f.source("gain_on_property_sale")})
    bridge += [
        {"step": "FFO", "value": ffo, "page": None, "subtotal": True},
        {"step": "Less straight-line rent", "value": -straight_line, **f.source("straight_line_rent_adjustment")},
    ]
    if di is not None and model == "fair_value":
        # Reported figure; the distributable_income_reconciles check confirms it equals the running total
        row = {"step": "Distributable income (reported)", "value": di, **f.source("reported_distributable_income")}
        if flows["gain_on_property_sale"]:
            # REIT rules don't remove disposal gains / losses, so this figure is off the FFO-to-AFFO path: show it, don't reset the total
            row["reference"] = True
        else:
            row["subtotal"] = True
        bridge.append(row)
    bridge += [
        {"step": "Less capex", "value": -capex, **f.source("capex_investment_property")},
    ]
    if flows["capex_acquisitions"]:
        bridge.append({"step": "Exclude acquisitions in capex", "value": flows["capex_acquisitions"], **f.source("capex_acquisitions")})
    bridge += [
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
        "meta": {k: f.meta.get(k) for k in ("ticker", "form_type", "period_label", "period_type", "period_end", "filing_date", "accounting_model", "source_file")},
        "metrics": metrics,
        "bridge": bridge,
        "checks": run_checks(f, ffo, nav_per_share) + annual_checks(f, breakdown, dividend_total, payout_di)
                  + [consistency_check(doc)] + derived_checks + issuance_checks + trend_checks
                  + [prior_annual_check(f, annual_doc)],
        "flags": detect_flags(f, coverage, fl_share, metrics["share_issuances"]) + derived_flags + event_flags,
    }


def quarter_index(label):
    """'2026-Q2' -> 2026 * 4 + 1, so consecutive quarters differ by 1."""
    year, _, q = label.partition("-Q")
    return int(year) * 4 + int(q) - 1


def fair_value_adjusted_nav(f, model, equity, shares):
    """Book NAV with assets not carried at fair value moved to their disclosed fair value.

    Fair value model: finance lease receivables (at amortized cost in the books).
    Cost model: investment property. Uses disclosed figures only, never estimates.
    """
    if model == "fair_value":
        fair, carrying = f.get("finance_lease_receivable_fair_value", required=False), f.get("finance_lease_receivable", required=False)
        what = "finance lease receivables"
    else:
        fair, carrying = f.get("investment_property_fair_value", required=False), f.get("investment_property_carrying", required=False)
        what = "investment property"
    if fair is None or carrying is None:
        return None
    return {"value": (equity + fair - carrying) / shares,
            "basis": f"book equity with {what} at disclosed fair value instead of carrying amount, per share",
            "adjustment": fair - carrying, "fair_value": fair, "carrying": carrying,
            "fair_value_source": cite(f.items.get("finance_lease_receivable_fair_value" if model == "fair_value" else "investment_property_fair_value"))}


def interest_coverage(f):
    """EBITDA / interest expense, EBITDA as PH REITs define it in their financial soundness indicators:
    before interest expense, tax and depreciation, excluding the fair value change, interest income and other income.
    Follows the company's definition exactly (no disposal adjustment) so it can be checked against the reported ratio."""
    keys = ("interest_expense", "interest_income")
    if any(f.get(k, required=False) is None for k in keys):
        return None
    get = lambda k: f.get(k, required=False) or 0  # noqa: E731
    ebitda = (f.get("net_income") + get("income_tax_expense") + get("interest_expense") + get("depreciation_amortization")
              - get("fair_value_change") - get("interest_income") - get("other_income"))
    return {"value": ebitda / f.get("interest_expense"), "ebitda": ebitda, "interest_expense": f.get("interest_expense")}


def valuation(f, breakdown, book_nav=None):
    """Price / NAV and dividend yield on two labeled bases, from the filing's own price."""
    price = f.get("market_price_close", required=False)
    if price is None:
        return None
    nav = f.get("reported_nav_per_share", required=False)
    nav_basis = "reported"
    if nav is None and book_nav is not None:
        nav, nav_basis = book_nav, "computed: total equity / shares outstanding (the filing reports no NAV per share)"
    latest = max(breakdown, key=lambda b: quarter_index(b["for_period"]))
    run_rate = latest["dividend_per_share"] * 4
    result = {
        "price": price,
        "price_source": f.source("market_price_close"),
        "nav_per_share_reported": nav,
        "nav_basis": nav_basis,
        "nav_source": f.source("reported_nav_per_share") if nav_basis == "reported" else None,
        "price_to_nav": price / nav if nav else None,
        "yield_latest_quarter_x4": {"basis": f"latest quarter ({latest['for_period']}) x 4",
                                    "dividend_per_share": latest["dividend_per_share"],
                                    "annualized_dividend_per_share": run_rate, "yield": run_rate / price},
        "yield_trailing_four_quarters": None,
    }
    trailing = f.doc.get("trailing_dividends") or []
    quarters = sorted(trailing, key=lambda d: quarter_index(d["for_period"]))
    idx = [quarter_index(d["for_period"]) for d in quarters]
    if len(quarters) == 4 and idx == list(range(idx[0], idx[0] + 4)) and quarters[-1]["for_period"] == latest["for_period"]:
        total = sum(d["dividend_per_share"]["value"] for d in quarters)
        result["yield_trailing_four_quarters"] = {
            "basis": f"dividends declared for {quarters[0]['for_period']} to {quarters[-1]['for_period']}",
            "quarters": [{"for_period": d["for_period"], "dividend_per_share": d["dividend_per_share"]["value"],
                          **cite(d["dividend_per_share"])} for d in quarters],
            "dividend_per_share": total, "yield": total / price}
    elif trailing:
        result["trailing_note"] = "trailing_dividends must be four consecutive quarters ending with the latest quarter"
    return result


def share_issuances(f):
    """Check each row of the issuance table and compare issue prices with the NAV before the issuance."""
    rows = f.doc.get("share_issuances") or []
    if not rows:
        return [], []
    out, problems = [], []
    totals = {t["year"]: t for t in f.doc.get("share_issuance_totals") or []}
    for r in rows:
        value, paid, apic = r["transaction_value"]["value"], r["paid_up_capital"]["value"], r["apic"]["value"]
        nav_before = r["nav_before"]["value"] if r.get("nav_before") else None
        row = {"property": r["property"], "year": r["year"], "transaction_value": value, "shares": r["shares"]["value"],
               "issue_price": r["issue_price"]["value"], "paid_up_capital": paid, "apic": apic,
               "adds_up": abs(paid + apic - value) <= 1, "apic_implied": value - paid,
               "nav_before": nav_before, "nav_before_source": cite(r.get("nav_before")) if nav_before else None,
               "issue_price_vs_nav_before": r["issue_price"]["value"] / nav_before - 1 if nav_before else None}
        out.append(row)
        if not row["adds_up"]:
            problems.append(f"{r['property']} ({r['year']}): paid-up capital {paid:,} + APIC {apic:,} = {paid + apic:,} "
                            f"vs transaction value {value:,}; transaction value - paid-up capital = {value - paid:,}")
    if not problems:
        return out, [_check("share_issuance_table_adds_up", True, f"paid-up capital + APIC = transaction value in all {len(rows)} rows")]
    notes = []
    for year in sorted({r["year"] for r in out if not r["adds_up"]}):
        tot = totals.get(year)
        if tot is None:
            continue
        implied = sum(r["apic_implied"] for r in out if r["year"] == year)
        if abs(implied - tot["apic"]["value"]) <= len(out):
            notes.append(f"the printed {year} APIC total {tot['apic']['value']:,} matches the rows' implied APIC, "
                         f"so the printed row is likely a typo in the filing")
    detail = "; ".join(problems + notes)
    return out, [_check("share_issuance_table_adds_up", False, detail, review=True)]


def subsequent_events(f, issuances):
    """Summarize events after the reporting date; the implied swap price is derived, not disclosed."""
    events, flags = [], []
    nav = f.get("reported_nav_per_share", required=False)
    for e in f.doc.get("subsequent_events") or []:
        out = {"date": e["date"], "type": e["type"], "description": e["description"]}
        if e["type"] == "share_issuance" and e.get("shares") and e.get("transaction_value"):
            shares, value = e["shares"]["value"], e["transaction_value"]["value"]
            implied = value / shares
            out.update(shares=shares, transaction_value=value, implied_price_derived=implied,
                       implied_price_vs_nav=implied / nav - 1 if nav else None)
            earlier = sorted({r["issue_price"] for r in issuances})
            vs_nav = f", {implied / nav - 1:+.1%} vs reported NAV per share {nav:.2f}" if nav else ""
            flags.append({"id": "subsequent_share_issuance", "severity": "worth_knowing",
                          "detail": f"{e['date']}: {shares:,} new shares for a transaction value of {value:,.2f}; implied price "
                                    f"{implied:.2f} per share (derived: value / shares; not stated in the filing){vs_nav}. "
                                    f"Earlier swaps in this filing: {', '.join(f'{p:.2f}' for p in earlier)}.",
                          "pages": [e["shares"]["page"], e["transaction_value"]["page"]]})
        elif e["type"] == "cash_acquisition" and e.get("amount"):
            amount, cash = e["amount"]["value"], f.get("cash", required=False)
            credit = f.get("available_credit_line", required=False)
            out.update(amount=amount, cash_at_period_end=cash, available_credit_line=credit,
                       amount_to_cash=amount / cash if cash else None)
            extra = f" ({amount / cash:.1f}x)" if cash else ""
            extra += f"; available credit line {credit:,}" if credit else ""
            flags.append({"id": "subsequent_cash_acquisition", "severity": "worth_knowing",
                          "detail": f"{e['date']}: cash purchase of {amount:,} vs cash of {cash:,} at period end{extra}.",
                          "pages": [e["amount"]["page"], f.page("cash")]})
        else:
            flags.append({"id": "subsequent_event", "severity": "worth_knowing",
                          "detail": f"{e['date']}: {e['description']}", "pages": []})
        events.append(out)
    return events, flags


def trend(f, model, metrics):
    """Year-by-year FFO, AFFO, coverage, payout and book NAV from the history list plus the current year."""
    history = f.doc.get("history") or []
    if not history or f.meta.get("period_type") != "year":
        return None, []
    rows, problems = [], []
    for entry in sorted(history, key=lambda e: e["year"]):
        v = {k: item["value"] for k, item in entry["facts"].items()}
        row = {"year": entry["year"], "ffo": None, "affo": None, "coverage": None, "payout": None, "nav_book": None,
               "dividends": v.get("dividend_declared_total_reported"),
               "distributable_income": v.get("reported_distributable_income")}
        try:
            row["ffo"], row["affo"] = ffo_affo(model, v)
        except KeyError:
            pass  # not enough items for that year
        if row["affo"] is not None and row["dividends"]:
            row["coverage"] = row["affo"] / row["dividends"]
        if row["dividends"] and row["distributable_income"]:
            row["payout"] = row["dividends"] / row["distributable_income"]
        if v.get("total_equity") and v.get("shares_outstanding") and model == "fair_value":
            row["nav_book"] = v["total_equity"] / v["shares_outstanding"]
        reported = v.get("reported_payout_pct")
        if reported is not None and row["payout"] is not None and abs(row["payout"] * 100 - reported) > 0.005:
            problems.append(f"{entry['year']}: computed payout {row['payout']:.2%} vs reported {reported:.2f}%")
        rows.append(row)
    m = metrics
    rows.append({"year": int(f.meta["period_end"][:4]), "ffo": m["ffo"], "affo": m["affo"], "coverage": m["affo_coverage"],
                 "payout": m["payout_of_distributable_income"], "nav_book": m["nav_per_share"],
                 "dividends": m["dividend_declared_total"], "distributable_income": f.get("reported_distributable_income", required=False)})
    if problems:
        check = _check("history_payout_matches_reported", False, "; ".join(problems), review=True)
    else:
        check = _check("history_payout_matches_reported", True, f"reported payouts agree for {len(history)} earlier years")
    return rows, [check]


def annual_checks(f, breakdown, dividend_total, payout):
    """Checks that only make sense for a full year: the REIT rule's 90% payout and dividend capacity."""
    if f.meta.get("period_type") != "year":
        return []
    checks = []
    if payout is not None:
        checks.append(_check("annual_distribution_rule", payout >= 0.90,
                             f"dividends declared for the year are {payout:.2%} of distributable income (REIT rules: at least 90%)",
                             review=True))
    reported = f.get("reported_payout_pct", required=False)
    if reported is not None and payout is not None:
        checks.append(_check("payout_matches_reported", abs(payout * 100 - reported) <= 0.005,
                             f"computed {payout:.2%} vs company's {reported:.2f}%", review=True))
    available = f.get("retained_earnings_available_for_dividends", required=False)
    last_quarter = f"{f.meta['period_end'][:4]}-Q4"
    after_year_end = sum(b["total"] for b in breakdown if b["for_period"] == last_quarter)
    if available is not None and after_year_end:
        checks.append(_check("dividends_within_retained_earnings", after_year_end <= available,
                             f"{last_quarter} dividend declared after year-end {after_year_end:,} vs retained earnings "
                             f"available for dividends {available:,}", review=True))
    return checks


def prior_annual_check(f, annual_doc):
    """A quarterly filing's prior year-end column must match last year's annual report."""
    check_id = "matches_prior_annual_report"
    if f.meta.get("period_type") == "year":
        return {"id": check_id, "status": "skipped", "detail": "Annual report"}
    if annual_doc is None:
        return {"id": check_id, "status": "skipped", "detail": "No facts file for last year's annual report"}
    a = Facts(annual_doc)
    pairs = [(mine, f.get(mine, required=False), theirs, a.get(theirs, required=False)) for mine, theirs in PRIOR_YEAR_END.items()]
    nav_prior = f.get("reported_nav_per_share_prior", required=False)
    annual_nav = a.get("reported_nav_per_share", required=False)
    if annual_nav is None and a.get("total_equity", required=False) and a.get("shares_outstanding", required=False):
        annual_nav = a.get("total_equity") / a.get("shares_outstanding")
    pairs.append(("reported_nav_per_share_prior", nav_prior, "NAV per share", annual_nav))
    compared, mismatches = [], []
    for mine, x, theirs, y in pairs:
        if x is None or y is None:
            continue
        tolerance = 0.01 if abs(y) < 1000 else 1
        show = (lambda v: f"{v:,.2f}") if abs(y) < 1000 else (lambda v: f"{v:,}")
        (mismatches if abs(x - y) > tolerance else compared).append(f"{mine} {show(x)} vs annual {theirs} {show(y)}")
    if not compared and not mismatches:
        return {"id": check_id, "status": "skipped", "detail": "No prior year-end figures to compare"}
    if mismatches:
        return _check(check_id, False, "differs from last year's annual report (restated or misread?): " + "; ".join(mismatches), review=True)
    return _check(check_id, True, f"{len(compared)} prior year-end figures match {a.meta.get('period_label')}: " + "; ".join(compared))


def consistency_check(doc):
    """Figures the filing prints in more than one place must agree; a mismatch is likely the filing's, not ours."""
    mismatches, compared = [], 0
    for name, item in iter_facts(doc):
        for other in item.get("also_reported", []):
            compared += 1
            if other.get("rounded"):
                tolerance = 0.005 * (1e9 if other.get("unit") == "billion" else 1e6)
            else:
                tolerance = 1 if abs(item["value"]) >= 1000 else 0.005
            if abs(other["value"] - item["value"]) > tolerance:
                mismatches.append(f"{name}: {item['value']:,} on p.{item['page']} vs {other['value']:,} on p.{other['page']} "
                                  f"(difference {other['value'] - item['value']:,})")
    if not compared:
        return {"id": "figures_consistent_within_filing", "status": "skipped", "detail": "No figures reported in more than one place"}
    if mismatches:
        return _check("figures_consistent_within_filing", False,
                      "likely inconsistency in the filing: " + "; ".join(mismatches), review=True)
    return _check("figures_consistent_within_filing", True, f"{compared} figures printed in more than one place agree")


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
    # Annual reports print no Q4 column, so nothing in the filing can confirm a derived Q4
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
        "unverified": not verified,
    }
    if verified:
        check = {"id": "derived_quarter_matches_filing", "status": "pass",
                 "detail": f"Derived {quarter} " + ", ".join(f"{k} {values[k]:,}" for k in verified)
                           + " match the filing's quarter column"}
    else:
        check = skipped("No quarter column to compare against (annual reports print none), so the derived quarter is unverified")[0]
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
        # The MD&A's figure is net income before the fair value change only, so compare like with like
        # (FFO also removes disposal gains / losses)
        before_fv = f.get("net_income") - f.get("fair_value_change")
        diff = before_fv - mdna
        checks.append(_check("ffo_matches_mdna", abs(diff) <= ROUNDED_MILLIONS_TOLERANCE,
                             f"net income before fair value change {before_fv:,} vs MD&A {mdna:,} (diff {diff:,})", review=True))
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
        period_total = f.get("dividend_declared_total_reported", required=False)
        if period_total is not None:
            pairs.append((f"{f.meta.get('period_label')} total",
                          sum(round(d["dividend_per_share"]["value"] * d["shares"]["value"]) for d in f.dividends), period_total))
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

    parts = [f.get(k, required=False) for k in ("fair_value_appraisal_gain", "fair_value_straight_line_offset", "fair_value_lease_commissions")]
    fv = f.get("fair_value_change", required=False)
    if all(p is not None for p in parts) and fv is not None:
        diff = sum(parts) - fv
        checks.append(_check("fair_value_breakdown_adds_up", abs(diff) <= 1,
                             f"appraisal {parts[0]:,} + straight-line offset {parts[1]:,} + lease commissions {parts[2]:,} "
                             f"= {sum(parts):,} vs fair value change {fv:,}", review=True))
    else:
        checks.append({"id": "fair_value_breakdown_adds_up", "status": "skipped", "detail": "No fair value breakdown (annual reports only)"})

    reported_ic = f.get("reported_interest_coverage", required=False)
    ic = interest_coverage(f)
    if reported_ic is not None and ic is not None:
        checks.append(_check("interest_coverage_matches_reported", abs(ic["value"] - reported_ic) <= 0.005,
                             f"EBITDA {ic['ebitda']:,} / interest {ic['interest_expense']:,} = {ic['value']:.2f}x vs reported {reported_ic:.2f}x",
                             review=True))
    else:
        checks.append({"id": "interest_coverage_matches_reported", "status": "skipped", "detail": "No reported interest coverage"})

    reported_nav = f.get("reported_nav_per_share", required=False)
    if reported_nav is not None and nav_per_share is not None:
        diff = nav_per_share - reported_nav
        checks.append(_check("nav_matches_reported", abs(diff) <= NAV_ROUNDING_TOLERANCE,
                             f"equity / shares = {nav_per_share:.4f} vs reported {reported_nav:.2f}", review=True))
    else:
        checks.append({"id": "nav_matches_reported", "status": "skipped", "detail": "No reported NAV or cost model"})

    return checks


def detect_flags(f, coverage, fl_share, issuances=()):
    flags = []

    sl = f.get("straight_line_rent_adjustment", required=False)
    fv = f.get("fair_value_change", required=False)
    ar, ar_prior = f.get("accrued_rent_receivable", required=False), f.get("accrued_rent_receivable_prior", required=False)
    if sl and fv is not None and ar is not None and ar_prior is not None:
        ar_increase = ar - ar_prior
        if abs(sl - abs(fv)) <= 1 and abs(ar_increase - sl) > STRAIGHT_LINE_MISMATCH * sl:
            # Between appraisals the fair value change mostly offsets straight-line rent (see red-flags.md)
            flags.append({
                "id": "straight_line_equals_fair_value_change",
                "severity": "worth_knowing",
                "detail": f"Straight-line adjustment {sl:,} equals |fair value change| {abs(fv):,}, consistent with the fair value "
                          f"change offsetting straight-line rent between appraisals; accrued rent receivable rose {ar_increase:,}.",
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
            "detail": f"Shares outstanding rose {shares - shares_prior:,} ({(shares - shares_prior) / shares_prior:.1%}) during the period."
                      + "".join(f" Issued at {price:.2f} per share vs NAV per share {nav:.2f} before the issuance ({price / nav - 1:+.1%})."
                                for price, nav in sorted({(r["issue_price"], r["nav_before"]) for r in issuances
                                                          if r["nav_before"] and str(r["year"]) == f.meta["period_end"][:4]})),
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
    v = m.get("valuation")
    if v:
        trailing = v["yield_trailing_four_quarters"]
        to_nav = (f"Price {v['price']:.2f} / NAV {v['nav_per_share_reported']:.2f} ({v['nav_basis'].split(':')[0]}) = {v['price_to_nav']:.2f}x; "
                  if v["price_to_nav"] is not None else f"Price {v['price']:.2f} (no reported NAV per share); ")
        print(to_nav + f"yield {v['yield_latest_quarter_x4']['yield']:.2%} ({v['yield_latest_quarter_x4']['basis']})"
              + (f", {trailing['yield']:.2%} (trailing four quarters)" if trailing else ""))
    if m.get("nav_fair_value_adjusted"):
        print(f"NAV per share, fair-value-adjusted: {m['nav_fair_value_adjusted']['value']:.2f} "
              f"(adjustment {m['nav_fair_value_adjusted']['adjustment']:,})")
    if m.get("interest_coverage"):
        print(f"Interest coverage: {m['interest_coverage']['value']:.2f}x")
    if m.get("assets_not_at_fair_value_share"):
        print(f"Assets not at fair value: {m['assets_not_at_fair_value_share']['value']:.1%} "
              f"({m['assets_not_at_fair_value_share']['basis']})")
    if m.get("trend"):
        print("Trend:   year   coverage   payout   book NAV")
        for row in m["trend"]:
            fmt = lambda v, spec: format(v, spec) if v is not None else "-"  # noqa: E731
            print(f"         {row['year']}   {fmt(row['coverage'], '.2f'):>7}x  {fmt(row['payout'], '.1%'):>7}   {fmt(row['nav_book'], '.2f'):>7}")
    dq = m.get("derived_quarter")
    if dq and dq["affo_coverage"] is not None:
        label = "derived, unverified" if dq.get("unverified") else "derived"
        print(f"Standalone {dq['period']} ({label}): AFFO {dq['affo'] / 1e6:,.1f}M, "
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


def find_prior_annual(facts_path, meta):
    """Last year's annual facts file, if it sits next to this one."""
    if meta.get("period_type") == "year":
        return None
    candidate = facts_path.parent / f"{int(meta['period_end'][:4]) - 1}-FY.facts.json"
    return candidate if candidate.exists() else None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("facts", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="Where to write metrics.json")
    parser.add_argument("--prior", type=Path, help="Facts file for the earlier period of the same year")
    parser.add_argument("--annual", type=Path, help="Facts file for last year's annual report (17-A)")
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

    annual_path = args.annual or find_prior_annual(args.facts, doc["meta"])
    annual_doc = json.loads(annual_path.read_text()) if annual_path else None
    if annual_doc:
        print(f"  Comparing prior year-end figures with {annual_path}")

    result = compute(doc, prior_doc, annual_doc)
    result["validation_warnings"] = warnings
    print_summary(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2))
        print(f"\nSaved {args.output}")


if __name__ == "__main__":
    sys.exit(main())
