# TLS Performance Testing — CyPerf vs Palo Alto Gen4/Gen5

Performance test plan and result-comparison tooling for TLS 1.2 / TLS 1.3
(classical RSA/ECDSA + ECDHE) and TLS 1.3 post-quantum key exchange
(ML-KEM, FrodoKEM, BIKE), generated with Keysight CyPerf VM agents on ESXi
against Palo Alto Networks Gen4 and Gen5 hardware firewalls.

## Contents

| Path | What it is |
|---|---|
| `TEST_PLAN.md` | The full test plan: topology, DUT scenarios, cipher matrix, procedures, pass criteria, CSV schema |
| `results/results_template.csv` | Empty CSV template matching the schema in TEST_PLAN.md §8 |
| `results/sample/sample_results.csv` | **Fictional** sample data (3 DUTs) to demo the tooling — not real measurements |
| `tools/compare_results.py` | Comparison tool: CSVs in → console summary + HTML report out |

## Workflow

1. Execute the test plan; record one row per median result into
   `results/<dut>_<date>.csv` using the template columns.
2. Generate the comparison report:

   ```bash
   python3 tools/compare_results.py results/ -o comparison_report.html
   ```

   No dependencies — Python 3.8+ standard library only. The report is a single
   self-contained HTML file (light/dark aware) you can mail or archive.

### Try it on the sample data

```bash
python3 tools/compare_results.py results/sample/ -o sample_report.html
```

### Options

| Flag | Effect |
|---|---|
| `-o FILE` | Output HTML path (default `comparison_report.html`) |
| `--test-type CPS` | Restrict to one test type (repeatable: `--test-type CPS --test-type THROUGHPUT`) |
| `--include-b2b` | Show generator back-to-back calibration rows (`dut_model=B2B`) as a series |

## What the report contains

1. **Per test-type charts** — every test case (TLS version / key exchange /
   cipher / certificate / scenario) as a horizontal bar group, one bar per DUT,
   with direct value labels, hover details (fail rate, DUT CPU), and a table view.
2. **Decryption cost** — S1 (decrypt) result as a percentage of the S0
   (pass-through) result, per DUT.
3. **PQC overhead** — every TLS 1.3 key-exchange group vs the x25519 classical
   baseline (same cipher/cert/scenario), per DUT. `n/s` marks combinations the
   platform could not decrypt — that's a finding, not a gap.
4. **Relative performance index** — DUTs ranked per test type (100% = best
   result per case), tagged Gen4/Gen5.

Rows with `value=0` or a `not-supported` note render as *not supported* instead
of skewing the charts. Duplicate rows for the same (case, DUT) are collapsed to
their median.
