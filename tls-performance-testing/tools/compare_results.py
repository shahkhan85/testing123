#!/usr/bin/env python3
"""Compare TLS performance results across Palo Alto hardware platforms.

Ingests result CSVs (schema in TEST_PLAN.md section 8), prints a console
summary, and writes a self-contained HTML comparison report with:

  1. Per test-type bar charts: one bar per DUT for every test case.
  2. Decryption cost: S1 (decrypt) as a percentage of S0 (pass-through).
  3. PQC overhead: each TLS 1.3 key-exchange group vs the x25519 baseline.
  4. Relative performance index per DUT (Gen4 vs Gen5 ranking).

Stdlib only (Python 3.8+). Usage:

  python3 tools/compare_results.py results/ -o comparison_report.html
"""

import argparse
import csv
import statistics
import sys
from datetime import date
from html import escape
from pathlib import Path

REQUIRED_COLUMNS = [
    "test_id", "dut_model", "generation", "panos_version", "scenario",
    "tls_version", "key_exchange", "cipher", "certificate", "test_type",
    "value", "unit",
]
OPTIONAL_COLUMNS = ["date", "cyperf_version", "fail_rate_pct", "dut_cpu_pct", "notes"]

# Validated categorical palette (dataviz reference instance): slots assigned
# to DUTs in fixed sorted order, never cycled past 8 series.
SERIES_LIGHT = ["#2a78d6", "#1baf7a", "#eda100", "#008300",
                "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"]
SERIES_DARK = ["#3987e5", "#199e70", "#c98500", "#008300",
               "#9085e9", "#e66767", "#d55181", "#d95926"]
MAX_SERIES = len(SERIES_LIGHT)

CLASSICAL_BASELINE_KEX = "x25519"


def load_rows(paths):
    """Load and validate all CSV rows from the given files/directories."""
    files = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            files.extend(sorted(p.rglob("*.csv")))
        elif p.is_file():
            files.append(p)
        else:
            sys.exit(f"error: no such file or directory: {p}")
    if not files:
        sys.exit("error: no CSV files found in the given paths")

    rows = []
    for f in files:
        with open(f, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
            if missing:
                sys.exit(f"error: {f}: missing required columns: {', '.join(missing)}")
            for lineno, row in enumerate(reader, start=2):
                row = {k: (v or "").strip() for k, v in row.items() if k}
                if not row.get("dut_model"):
                    continue
                try:
                    row["value"] = float(row["value"])
                except ValueError:
                    sys.exit(f"error: {f}:{lineno}: non-numeric value {row['value']!r}")
                row["_source"] = f.name
                rows.append(row)
    return rows, files


def case_key(row):
    """Identity of a test case, independent of which DUT ran it."""
    return (row["test_type"], row["scenario"], row["tls_version"],
            row["key_exchange"], row["cipher"], row["certificate"])


def case_label(key):
    test_type, scenario, tls, kex, cipher, cert = key
    return f"TLS {tls} · {kex} · {cipher} · {cert} ({scenario})"


def aggregate(rows):
    """Collapse duplicate (case, dut) rows to their median value.

    Returns {case_key: {dut: {"value", "unit", "supported", "meta"}}}.
    """
    buckets = {}
    for row in rows:
        buckets.setdefault(case_key(row), {}).setdefault(row["dut_model"], []).append(row)

    cases = {}
    for key, per_dut in buckets.items():
        cases[key] = {}
        for dut, samples in per_dut.items():
            values = [s["value"] for s in samples]
            first = samples[0]
            supported = any(v > 0 for v in values) and \
                not any("not-supported" in s.get("notes", "").lower() for s in samples)
            cases[key][dut] = {
                "value": statistics.median(values),
                "unit": first["unit"],
                "supported": supported,
                "fail": first.get("fail_rate_pct", ""),
                "cpu": first.get("dut_cpu_pct", ""),
                "notes": first.get("notes", ""),
                "n": len(values),
            }
    return cases


def dut_info(rows, include_b2b):
    """Sorted DUT list with generation/PAN-OS metadata."""
    info = {}
    for row in rows:
        dut = row["dut_model"]
        if dut == "B2B" and not include_b2b:
            continue
        entry = info.setdefault(dut, {"generation": set(), "panos": set()})
        if row.get("generation"):
            entry["generation"].add(row["generation"])
        if row.get("panos_version"):
            entry["panos"].add(row["panos_version"])
    duts = sorted(info)
    if len(duts) > MAX_SERIES:
        sys.exit(f"error: {len(duts)} DUTs exceeds the {MAX_SERIES}-series palette; "
                 "split the comparison into multiple reports")
    return duts, info


def fmt_value(value, unit):
    if unit.lower() == "gbps":
        return f"{value:,.2f}"
    return f"{value:,.0f}"


def decryption_cost(cases, duts):
    """S1 value as % of S0 for cases that exist in both scenarios."""
    out = []
    for key in sorted(cases):
        test_type, scenario, tls, kex, cipher, cert = key
        if scenario != "S1":
            continue
        s0_key = (test_type, "S0", tls, kex, cipher, cert)
        if s0_key not in cases:
            continue
        row = {"label": f"TLS {tls} · {kex} · {cipher} · {cert}",
               "test_type": test_type, "cells": {}}
        for dut in duts:
            s1 = cases[key].get(dut)
            s0 = cases[s0_key].get(dut)
            if s1 and s0 and s1["supported"] and s0["supported"] and s0["value"]:
                row["cells"][dut] = 100.0 * s1["value"] / s0["value"]
        if row["cells"]:
            out.append(row)
    return out


def pqc_overhead(cases, duts):
    """Each TLS 1.3 key exchange vs the x25519 baseline (same everything else)."""
    out = []
    for key in sorted(cases):
        test_type, scenario, tls, kex, cipher, cert = key
        if tls != "1.3" or kex.lower() == CLASSICAL_BASELINE_KEX:
            continue
        ref_key = (test_type, scenario, tls, CLASSICAL_BASELINE_KEX, cipher, cert)
        if ref_key not in cases:
            continue
        row = {"label": f"{kex} vs {CLASSICAL_BASELINE_KEX} · {cipher} · {cert} ({scenario})",
               "test_type": test_type, "cells": {}}
        for dut in duts:
            cur = cases[key].get(dut)
            ref = cases[ref_key].get(dut)
            if cur and ref and ref["supported"] and ref["value"]:
                row["cells"][dut] = (None if not cur["supported"]
                                     else 100.0 * (cur["value"] / ref["value"] - 1.0))
        if row["cells"]:
            out.append(row)
    return out


def performance_index(cases, duts):
    """Mean of (value / best value for that case) over cases the DUT ran.

    Returns {test_type: [(dut, index_pct, n_cases)]} sorted best-first.
    """
    out = {}
    test_types = sorted({key[0] for key in cases})
    for tt in test_types:
        scores = {dut: [] for dut in duts}
        for key, per_dut in cases.items():
            if key[0] != tt:
                continue
            vals = [d["value"] for dut, d in per_dut.items()
                    if dut in duts and d["supported"]]
            if not vals:
                continue
            best = max(vals)
            for dut in duts:
                d = per_dut.get(dut)
                if d and d["supported"] and best:
                    scores[dut].append(d["value"] / best)
        ranked = [(dut, 100.0 * statistics.mean(s), len(s))
                  for dut, s in scores.items() if s]
        ranked.sort(key=lambda r: -r[1])
        out[tt] = ranked
    return out


# ---------------------------------------------------------------- console ---

def print_console(cases, duts, info, index):
    width = max([len(case_label(k)) for k in cases] + [10])
    for tt in sorted({k[0] for k in cases}):
        print(f"\n=== {tt} ===")
        header = "case".ljust(width) + "".join(d.rjust(14) for d in duts)
        print(header)
        print("-" * len(header))
        for key in sorted(cases):
            if key[0] != tt:
                continue
            line = case_label(key).ljust(width)
            for dut in duts:
                d = cases[key].get(dut)
                if d is None:
                    cell = "-"
                elif not d["supported"]:
                    cell = "n/s"
                else:
                    cell = fmt_value(d["value"], d["unit"])
                line += cell.rjust(14)
            print(line)
        if tt in index:
            ranking = ", ".join(f"{dut} {pct:.0f}%" for dut, pct, _ in index[tt])
            print(f"relative index (100% = best per case): {ranking}")


# ------------------------------------------------------------------- html ---

CSS = """
:root { color-scheme: light dark; }
.viz-root {
  --surface-1: #fcfcfb; --page: #f9f9f7;
  --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #898781;
  --grid: #e1e0d9; --baseline: #c3c2b7; --border: rgba(11,11,11,0.10);
  __SERIES_LIGHT__
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  background: var(--page); color: var(--text-primary);
  margin: 0; padding: 24px; line-height: 1.45;
}
@media (prefers-color-scheme: dark) {
  .viz-root {
    --surface-1: #1a1a19; --page: #0d0d0d;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
    --grid: #2c2c2a; --baseline: #383835; --border: rgba(255,255,255,0.10);
    __SERIES_DARK__
  }
}
.viz-root h1 { font-size: 22px; margin: 0 0 4px; }
.viz-root h2 { font-size: 17px; margin: 32px 0 8px; }
.viz-root .meta { color: var(--text-secondary); font-size: 13px; margin-bottom: 16px; }
.card { background: var(--surface-1); border: 1px solid var(--border);
        border-radius: 8px; padding: 16px 20px; margin: 12px 0; overflow-x: auto; }
.legend { display: flex; flex-wrap: wrap; gap: 16px; margin: 8px 0 4px; font-size: 13px; }
.legend .item { display: flex; align-items: center; gap: 6px; color: var(--text-secondary); }
.legend .chip { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
.group { margin: 14px 0 18px; }
.group-label { font-size: 13px; color: var(--text-secondary); margin-bottom: 6px; }
.row { display: grid; grid-template-columns: 110px 1fr 110px; align-items: center;
       gap: 10px; margin: 2px 0; }
.row .dut { font-size: 12px; color: var(--text-secondary); text-align: right;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.track { position: relative; height: 14px; background: transparent;
         border-left: 1px solid var(--baseline); }
.bar { height: 14px; border-radius: 0 4px 4px 0; min-width: 1px; }
.bar:hover { filter: brightness(1.12); }
.row .val { font-size: 12px; color: var(--text-primary);
            font-variant-numeric: tabular-nums; white-space: nowrap; }
.row .val.ns { color: var(--text-muted); }
table { border-collapse: collapse; font-size: 13px; width: 100%; }
th, td { text-align: right; padding: 5px 10px; border-bottom: 1px solid var(--grid);
         font-variant-numeric: tabular-nums; white-space: nowrap; }
th { color: var(--text-secondary); font-weight: 600; }
th:first-child, td:first-child { text-align: left; }
td.ns { color: var(--text-muted); }
.note { color: var(--text-muted); font-size: 12px; margin-top: 6px; }
details summary { cursor: pointer; color: var(--text-secondary); font-size: 13px;
                  margin-top: 10px; }
"""


def series_css(prefix, colors):
    return "\n  ".join(f"--{prefix}{i + 1}: {c};" for i, c in enumerate(colors))


def html_report(cases, duts, info, files, index):
    color_of = {dut: f"var(--series-{i + 1})" for i, dut in enumerate(duts)}
    out = []
    w = out.append

    css = CSS.replace("__SERIES_LIGHT__", series_css("series-", SERIES_LIGHT)) \
             .replace("__SERIES_DARK__", series_css("series-", SERIES_DARK))
    w(f"<title>TLS Performance Comparison</title>\n<style>{css}</style>")
    w('<div class="viz-root">')
    w("<h1>TLS Performance Comparison — Palo Alto Networks Hardware</h1>")
    w(f'<div class="meta">Generated {date.today().isoformat()} · '
      f'sources: {escape(", ".join(f.name for f in files))}</div>')

    # DUT legend (identity is also direct-labeled on every bar row).
    w('<div class="legend">')
    for dut in duts:
        gen = "/".join(sorted(info[dut]["generation"])) or "?"
        panos = "/".join(sorted(info[dut]["panos"])) or "?"
        w(f'<span class="item"><span class="chip" style="background:{color_of[dut]}">'
          f'</span>{escape(dut)} · {escape(gen)} · PAN-OS {escape(panos)}</span>')
    w("</div>")

    # 1. Charts per test type
    for tt in sorted({k[0] for k in cases}):
        tt_keys = [k for k in sorted(cases) if k[0] == tt]
        unit = next((d["unit"] for k in tt_keys for d in cases[k].values()), "")
        max_val = max((d["value"] for k in tt_keys for dut, d in cases[k].items()
                       if dut in duts and d["supported"]), default=0) or 1
        w(f"<h2>{escape(tt)} — maximum sustained ({escape(unit)})</h2>")
        w('<div class="card">')
        for key in tt_keys:
            w('<div class="group">')
            w(f'<div class="group-label">{escape(case_label(key))}</div>')
            for dut in duts:
                d = cases[key].get(dut)
                if d is None:
                    continue
                if d["supported"]:
                    pct = 100.0 * d["value"] / max_val
                    val = fmt_value(d["value"], d["unit"])
                    tip = (f"{dut} — {val} {d['unit']}"
                           + (f" · fail {d['fail']}%" if d["fail"] else "")
                           + (f" · DUT CPU {d['cpu']}%" if d["cpu"] else "")
                           + (f" · median of {d['n']} runs" if d["n"] > 1 else ""))
                    bar = (f'<div class="bar" style="width:{pct:.2f}%;'
                           f'background:{color_of[dut]}" title="{escape(tip)}"></div>')
                    val_html = f'<span class="val">{val}</span>'
                else:
                    note = d["notes"] or "not supported"
                    bar = f'<div class="bar" style="width:0" title="{escape(note)}"></div>'
                    val_html = f'<span class="val ns" title="{escape(note)}">not supported</span>'
                w(f'<div class="row"><span class="dut">{escape(dut)}</span>'
                  f'<div class="track">{bar}</div>{val_html}</div>')
            w("</div>")

        # Table view (accessibility channel for the chart above)
        w("<details><summary>Table view</summary><table>")
        w("<tr><th>Test case</th>" + "".join(f"<th>{escape(d)}</th>" for d in duts) + "</tr>")
        for key in tt_keys:
            w(f"<tr><td>{escape(case_label(key))}</td>")
            for dut in duts:
                d = cases[key].get(dut)
                if d is None:
                    w("<td>—</td>")
                elif not d["supported"]:
                    w('<td class="ns">n/s</td>')
                else:
                    w(f"<td>{fmt_value(d['value'], d['unit'])}</td>")
            w("</tr>")
        w("</table></details></div>")

    # 2. Decryption cost
    cost = decryption_cost(cases, duts)
    if cost:
        w("<h2>Decryption cost — S1 (decrypt) as % of S0 (pass-through)</h2>")
        w('<div class="card"><table>')
        w("<tr><th>Test case</th><th>Type</th>"
          + "".join(f"<th>{escape(d)}</th>" for d in duts) + "</tr>")
        for row in cost:
            w(f"<tr><td>{escape(row['label'])}</td><td>{escape(row['test_type'])}</td>")
            for dut in duts:
                v = row["cells"].get(dut)
                w("<td>—</td>" if v is None else f"<td>{v:.1f}%</td>")
            w("</tr>")
        w('</table><div class="note">Lower % = decryption costs more relative to '
          "pass-through on that platform.</div></div>")

    # 3. PQC / key-exchange overhead
    overhead = pqc_overhead(cases, duts)
    if overhead:
        w(f"<h2>Key-exchange overhead vs {CLASSICAL_BASELINE_KEX} (TLS 1.3)</h2>")
        w('<div class="card"><table>')
        w("<tr><th>Comparison</th><th>Type</th>"
          + "".join(f"<th>{escape(d)}</th>" for d in duts) + "</tr>")
        for row in overhead:
            w(f"<tr><td>{escape(row['label'])}</td><td>{escape(row['test_type'])}</td>")
            for dut in duts:
                if dut not in row["cells"]:
                    w("<td>—</td>")
                elif row["cells"][dut] is None:
                    w('<td class="ns">n/s</td>')
                else:
                    w(f"<td>{row['cells'][dut]:+.1f}%</td>")
            w("</tr>")
        w('</table><div class="note">Negative = slower than the classical baseline; '
          '"n/s" = combination not supported on that platform.</div></div>')

    # 4. Relative performance index
    if index:
        w("<h2>Relative performance index (100% = best result per test case)</h2>")
        w('<div class="card"><table>')
        w("<tr><th>Test type</th><th>Rank</th><th>DUT</th><th>Generation</th>"
          "<th>Index</th><th>Cases</th></tr>")
        for tt, ranked in index.items():
            for rank, (dut, pct, n) in enumerate(ranked, start=1):
                gen = "/".join(sorted(info[dut]["generation"])) or "?"
                w(f"<tr><td>{escape(tt)}</td><td>{rank}</td><td>{escape(dut)}</td>"
                  f"<td>{escape(gen)}</td><td>{pct:.1f}%</td><td>{n}</td></tr>")
        w('</table><div class="note">Mean of per-case scores over the cases each DUT '
          "ran; only comparable when DUTs share the same case coverage.</div></div>")

    w("</div>")
    return "<!doctype html>\n" + "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="+", help="result CSV files and/or directories")
    ap.add_argument("-o", "--output", default="comparison_report.html",
                    help="HTML report path (default: comparison_report.html)")
    ap.add_argument("--include-b2b", action="store_true",
                    help="include generator back-to-back calibration rows as a series")
    ap.add_argument("--test-type", action="append",
                    help="only include this test_type (repeatable), e.g. CPS")
    args = ap.parse_args()

    rows, files = load_rows(args.paths)
    if args.test_type:
        wanted = {t.upper() for t in args.test_type}
        rows = [r for r in rows if r["test_type"].upper() in wanted]
    if not args.include_b2b:
        rows = [r for r in rows if r["dut_model"] != "B2B"]
    if not rows:
        sys.exit("error: no data rows after filtering")

    duts, info = dut_info(rows, args.include_b2b)
    cases = aggregate(rows)
    index = performance_index(cases, duts)

    print_console(cases, duts, info, index)
    report = html_report(cases, duts, info, files, index)
    Path(args.output).write_text(report, encoding="utf-8")
    print(f"\nwrote {args.output} ({len(cases)} test cases, {len(duts)} DUTs, "
          f"{len(rows)} rows)")


if __name__ == "__main__":
    main()
