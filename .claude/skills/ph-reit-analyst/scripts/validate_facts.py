#!/usr/bin/env python3
"""Check a facts JSON file before any metric is computed.

Enforces the rules in schemas/reit_facts.schema.json plus the ones a schema
can't express: every fact cites a page, the facts the chosen accounting model
needs are present, and low-confidence values are listed so the report can
mention them. Uses only the standard library so it runs anywhere.

Usage:
    python <skill-dir>/scripts/validate_facts.py <facts.json>

Exit code is 1 if there are errors. compute_metrics.py runs this first.
"""
import json
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "reit_facts.schema.json"

# Facts each accounting model needs on top of the schema's required list
MODEL_REQUIRED = {
    "fair_value": ["fair_value_change"],
    "cost": ["real_estate_depreciation"],
}


def validate(doc, schema=None):
    """Return (errors, warnings) as lists of plain-language strings."""
    schema = schema or json.loads(SCHEMA_PATH.read_text())
    errors, warnings = [], []

    for key in schema["required"]:
        if key not in doc:
            errors.append(f"Missing top-level section: {key}")
    if errors:
        return errors, warnings

    meta, facts = doc["meta"], doc["facts"]
    meta_schema = schema["properties"]["meta"]
    facts_schema = schema["properties"]["facts"]
    fact_schema = schema["$defs"]["fact"]

    for key in meta_schema["required"]:
        if meta.get(key) in (None, ""):
            errors.append(f"meta.{key} is missing")
    for key, spec in meta_schema["properties"].items():
        if key in meta and "enum" in spec and meta[key] not in spec["enum"]:
            errors.append(f"meta.{key} = {meta[key]!r}; must be one of {spec['enum']}")
    basis = str(meta.get("page_basis", ""))
    if basis and not basis.startswith(("printed", "pdf_index")):
        warnings.append(f"meta.page_basis {basis!r} should start with 'printed' or 'pdf_index'")
    if meta.get("form_type") == "17-A" and basis.startswith("printed"):
        warnings.append("17-A filings restart their page numbering; cite PDF positions (page_basis 'pdf_index')")
    if "accounting_model_page" in meta and not isinstance(meta["accounting_model_page"], int):
        errors.append("meta.accounting_model_page must be a whole page number")

    required = list(facts_schema["required"]) + MODEL_REQUIRED.get(meta.get("accounting_model"), [])
    for key in required:
        if key not in facts:
            errors.append(f"Required fact missing: {key}")

    known = set(facts_schema["properties"])
    confidence_values = fact_schema["properties"]["confidence"]["enum"]

    def check_fact(key, item):
        if not isinstance(item, dict):
            errors.append(f"{key}: must be an object with value and page")
            return
        value, page = item.get("value"), item.get("page")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"{key}: value must be a number, got {value!r}")
        if isinstance(page, bool) or not isinstance(page, int):
            errors.append(f"{key}: needs a page citation (whole printed page number)")
        conf = item.get("confidence", "high")
        if item.get("citation") == "visual" and conf == "high":
            errors.append(f"{key}: read visually from a scanned page, so confidence must be medium or low")
        if conf not in confidence_values:
            errors.append(f"{key}: confidence {conf!r} must be one of {confidence_values}")
        elif conf == "low":
            warnings.append(f"{key}: low confidence — mention in the report ({item.get('note', 'no note given')})")
        elif conf == "medium":
            warnings.append(f"{key}: medium confidence ({item.get('note', 'no note given')})")

    for key, item in facts.items():
        check_fact(key, item)
        if key not in known:
            warnings.append(f"{key}: not a known fact name; check spelling (it will be ignored by the metrics)")

    dividends = doc.get("dividends")
    if dividends is not None:
        if not isinstance(dividends, list) or not dividends:
            errors.append("dividends must be a non-empty list")
        else:
            item_spec = schema["properties"]["dividends"]["items"]
            for i, d in enumerate(dividends, 1):
                label = f"dividends[{i}] ({d.get('for_period', '?')})"
                for key in item_spec["required"]:
                    if key not in d:
                        errors.append(f"{label}: missing {key}")
                for key in ("dividend_per_share", "shares", "reported_total"):
                    if key in d:
                        check_fact(f"{label}.{key}", d[key])
    if dividends is None and "dividend_per_share_declared" not in facts:
        errors.append("No dividend: add facts.dividend_per_share_declared, or a dividends list for multi-quarter periods")

    for section in ("trailing_dividends", "share_issuances", "share_issuance_totals", "subsequent_events"):
        entries = doc.get(section, [])
        spec = schema["properties"][section]["items"]
        for i, entry in enumerate(entries, 1):
            label = f"{section}[{i}]"
            for key in spec["required"]:
                if key not in entry:
                    errors.append(f"{label}: missing {key}")
            for key, item in entry.items():
                if spec["properties"].get(key, {}).get("$ref"):
                    check_fact(f"{label}.{key}", item)
            enum = spec["properties"].get("type", {}).get("enum")
            if enum and entry.get("type") not in enum:
                errors.append(f"{label}: type {entry.get('type')!r} must be one of {enum}")

    for key in ("capex_investment_property", "straight_line_rent_adjustment", "shares_outstanding"):
        value = facts.get(key, {}).get("value")
        if isinstance(value, (int, float)) and value < 0:
            errors.append(f"{key}: should be a positive amount, got {value:,}")

    return errors, warnings


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    path = Path(sys.argv[1])
    errors, warnings = validate(json.loads(path.read_text()))
    for w in warnings:
        print(f"  [warning] {w}")
    for e in errors:
        print(f"  [error] {e}")
    print(f"\n{path}: {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
