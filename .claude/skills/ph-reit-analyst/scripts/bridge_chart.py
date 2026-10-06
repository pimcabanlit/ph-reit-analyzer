#!/usr/bin/env python3
"""Draw the earnings-to-dividend bridge (waterfall) from metrics.json.

Reads only metrics.json and draws what it contains: the bridge rows, the
dividend breakdown, coverage, payout and the derived quarter if present. It
never recomputes a metric; the only arithmetic is placing each floating bar
on top of the running total so the waterfall connects.

Saves bridge.png next to metrics.json (or to -o).

Usage:
    python <skill-dir>/scripts/bridge_chart.py outputs/<ticker>/<period>/metrics.json [-o bridge.png]
"""
import argparse
import json
import math
import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

# Dark theme, validated with the dataviz palette checks against SURFACE:
# categorical set passes all-pairs (red/aqua CVD 6.5 is legal with the +/- labels),
# the two dividend shades pass as an ordinal one-hue pair.
SURFACE = "#1a1a19"
TEXT = "#ffffff"
TEXT_2 = "#c3c2b7"
GRID = "#33332f"
SUBTOTAL = "#3987e5"
ADDED = "#199e70"
SUBTRACTED = "#e66767"
DIVIDEND = ["#b08600", "#7a5a00"]
STATUS = {"green": ("#0ca30c", "✓", "Dividend covered by AFFO"),
          "yellow": ("#fab219", "!", "Covered, with little room to spare"),
          "red": ("#d03b3b", "✕", "Dividend larger than AFFO")}

PERIOD_MONTHS = {"quarter": 3, "half": 6, "nine_months": 9, "year": 12}
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
AXIS_STEP = 50e6
AXIS_PAD = 100e6

STEP_NAMES = {
    "Remove fair value change": ("+ Fair value loss", "− Fair value gain"),
    "Add back real estate depreciation": ("+ Real estate depreciation", "− Real estate depreciation"),
    "Less straight-line rent": ("+ Straight-line rent", "− Straight-line rent"),
    "Less capex": ("+ Capex", "− Capex"),
}


def millions(value, signed=False):
    text = f"{value / 1e6:+,.1f}" if signed else f"{value / 1e6:,.1f}"
    return text.replace("-", "−")


def period_title(meta):
    """'Q1 2026 (January to March)', '1H 2026 (January to June)', ..."""
    year, month = meta["period_end"][:4], int(meta["period_end"][5:7])
    span = PERIOD_MONTHS.get(meta.get("period_type"), 3)
    first = MONTHS[month - span]
    last = MONTHS[month - 1]
    name = {"quarter": f"Q{(month - 1) // 3 + 1}", "half": "1H", "nine_months": "9M", "year": "FY"}.get(meta.get("period_type"), "")
    return f"{name} {year} ({first} to {last})"


def long_date(iso):
    """'2026-06-30' -> 'June 30, 2026'."""
    return f"{MONTHS[int(iso[5:7]) - 1]} {int(iso[8:10])}, {iso[:4]}"


def quarter_name(for_period):
    """'2026-Q1' -> 'Q1 2026'."""
    year, _, q = for_period.partition("-")
    return f"{q} {year}" if q else for_period


def layout(bridge, breakdown):
    """Turn bridge rows into bars: (label, bottom, top, kind, value_text)."""
    bars, running = [], None
    stacked = len(breakdown) > 1
    for row in bridge:
        if row.get("detail"):
            continue  # drawn as segments of the stacked dividend bar
        value = row["value"]
        if row.get("comparison"):
            bars.append({"label": "Dividends declared" if stacked else "Dividend declared",
                         "bottom": 0, "top": value, "kind": "dividend", "text": millions(value)})
        elif running is None or row.get("subtotal"):
            bars.append({"label": row["step"], "bottom": 0, "top": value, "kind": "subtotal", "text": millions(value)})
            running = value
        else:
            names = STEP_NAMES.get(row["step"], (f"+ {row['step']}", f"− {row['step']}"))
            bars.append({"label": names[0] if value >= 0 else names[1],
                         "bottom": min(running, running + value), "top": max(running, running + value),
                         "kind": "added" if value >= 0 else "subtracted", "text": millions(value, signed=True)})
            running += value
    return bars


def axis_floor(bars, stacked):
    """Start just below the smallest bar, rounded down to 50M; at zero if the dividend is stacked."""
    if stacked:
        return 0, "Y-axis starts at ₱0 because the dividend bar is stacked by quarter; a cut-off axis would hide the lower segment."
    lowest = min(b["top"] if b["bottom"] == 0 else b["bottom"] for b in bars)
    floor = math.floor((lowest - AXIS_PAD) / AXIS_STEP) * AXIS_STEP
    if floor <= 0:
        return 0, None
    return floor, f"Y-axis starts at ₱{floor / 1e6:,.0f}M so the small adjustments are visible; bar heights are not proportional to the full amounts."


def draw(result, out_path):
    meta, m = result["meta"], result["metrics"]
    breakdown = m.get("dividend_breakdown") or []
    stacked = len(breakdown) > 1
    bars = layout(result["bridge"], breakdown)
    floor, note = axis_floor(bars, stacked)

    fig = plt.figure(figsize=(12, 7.6), dpi=150, facecolor=SURFACE)
    plt.rcParams["font.family"] = "DejaVu Sans"

    fig.text(0.06, 0.955, f"{meta['ticker']} – {period_title(meta)}", color=TEXT, fontsize=17, weight="bold")
    fig.text(0.06, 0.925, "Earnings bridge: from net income to cash earnings (AFFO) and the dividend, in ₱ millions",
             color=TEXT_2, fontsize=10.5)

    # Tiles: coverage, payout, dividend per share for each quarter, and the derived quarter if any
    tiles = []
    light = STATUS.get(m.get("safety_light"))
    tiles.append(("AFFO dividend coverage", f"{m['affo_coverage']:.2f}x",
                  (f"{light[1]} {light[2]}", light[0]) if light else ("", TEXT_2)))
    if m.get("payout_of_distributable_income") is not None:
        tiles.append(("Payout of distributable income", f"{m['payout_of_distributable_income']:.1%}",
                      ("REIT rules: at least 90% over the year", TEXT_2)))
    dps_text = " · ".join(f"₱{b['dividend_per_share']:.2f}" for b in breakdown)
    dps_sub = " · ".join(quarter_name(b["for_period"]) for b in breakdown) if stacked else \
        f"× {breakdown[0]['shares'] / 1e9:.2f}B shares = ₱{millions(breakdown[0]['total'])}M"
    tiles.append(("Dividend per share" + (" by quarter" if stacked else ""), dps_text, (dps_sub, TEXT_2)))
    dq = m.get("derived_quarter")
    if dq and dq.get("affo_coverage") is not None:
        dl = STATUS.get(dq.get("safety_light"))
        tiles.append((f"{quarter_name(dq['period'])} alone (derived)", f"{dq['affo_coverage']:.2f}x",
                      (f"{dl[1]} {dl[2]}", dl[0]) if dl else ("", TEXT_2)))
    width = 0.88 / len(tiles)
    for i, (title, value, (sub, sub_color)) in enumerate(tiles):
        x = 0.06 + i * width
        fig.text(x, 0.875, title, color=TEXT_2, fontsize=10)
        fig.text(x, 0.83, value, color=TEXT, fontsize=21, weight="bold")
        fig.text(x, 0.805, sub, color=sub_color, fontsize=9)

    ax = fig.add_axes([0.08, 0.19, 0.9, 0.54], facecolor=SURFACE)
    colors = {"subtotal": SUBTOTAL, "added": ADDED, "subtracted": SUBTRACTED}
    xs = range(len(bars))
    top_all = max(b["top"] for b in bars)
    lift = (top_all - floor) * 0.012
    for x, b in zip(xs, bars):
        if b["kind"] == "dividend" and stacked:
            base = 0
            for i, seg in enumerate(breakdown):
                ax.bar(x, seg["total"], bottom=base, width=0.62, color=DIVIDEND[i % 2], edgecolor=SURFACE, linewidth=2)
                ax.text(x, base + seg["total"] / 2, f"{quarter_name(seg['for_period']).split()[0]}\n{millions(seg['total'])}",
                        ha="center", va="center", color=TEXT, fontsize=9.5, weight="bold")
                base += seg["total"]
        else:
            color = DIVIDEND[0] if b["kind"] == "dividend" else colors[b["kind"]]
            bottom = max(b["bottom"], floor)
            ax.bar(x, b["top"] - bottom, bottom=bottom, width=0.62, color=color, edgecolor=SURFACE, linewidth=2)
        ax.text(x, b["top"] + lift, b["text"], ha="center", va="bottom", color=TEXT, fontsize=10.5, weight="bold")

    ax.set_ylim(floor, top_all + (top_all - floor) * 0.1)
    ax.set_xlim(-0.6, len(bars) - 0.4)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([textwrap.fill(b["label"], 14) for b in bars], color=TEXT_2, fontsize=10, linespacing=1.3)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"₱{v / 1e6:,.0f}M"))
    ax.tick_params(axis="y", colors=TEXT_2, labelsize=9, length=0)
    ax.tick_params(axis="x", length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)

    legend = [Patch(color=SUBTOTAL, label="Subtotal"), Patch(color=ADDED, label="Added back (+)"),
              Patch(color=SUBTRACTED, label="Subtracted (−)")]
    legend += [Patch(color=DIVIDEND[i % 2], label=f"Dividend {quarter_name(b['for_period']).split()[0]}")
               for i, b in enumerate(breakdown)] if stacked else [Patch(color=DIVIDEND[0], label="Dividend declared")]
    ax.legend(handles=legend, loc="lower left", bbox_to_anchor=(0, 1.01), ncol=len(legend), frameon=False,
              labelcolor=TEXT, fontsize=9.5, handlelength=1.1, handleheight=1.1, columnspacing=1.6)

    footer = [note] if note else []
    if dq:
        footer.append(f"{quarter_name(dq['period'])} alone is derived: {dq['derived_from'][0]} minus {dq['derived_from'][1]} "
                      f"for net income, fair value change, straight-line rent and capex.")
    filed = f", filed {long_date(meta['filing_date'])}" if meta.get("filing_date") else ""
    footer.append(f"Source: {meta['ticker']} SEC Form {meta['form_type']}, period ended {long_date(meta['period_end'])}{filed}. "
                  "For learning and research only. Not investment advice.")
    for i, line in enumerate(footer):
        fig.text(0.06, 0.07 - i * 0.025, line, color=TEXT_2, fontsize=8.8)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, facecolor=SURFACE)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("metrics", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="Where to save the PNG (default: bridge.png next to metrics.json)")
    args = parser.parse_args()
    out = args.output or args.metrics.parent / "bridge.png"
    draw(json.loads(args.metrics.read_text()), out)
    print(f"Saved {out}")


if __name__ == "__main__":
    sys.exit(main())
