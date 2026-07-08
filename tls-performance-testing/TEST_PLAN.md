# TLS Performance Test Plan — Classical & Post-Quantum Ciphers

**Traffic generator:** Keysight CyPerf (VM agents on VMware ESXi)
**Devices under test (DUT):** Palo Alto Networks Gen4 and Gen5 hardware firewalls
**Scope:** TLS 1.2 / TLS 1.3 classical (RSA & ECDSA certificates, ECDHE key exchange) and TLS 1.3 post-quantum key exchange (ML-KEM, FrodoKEM, BIKE)
**Primary metrics:** maximum TLS connections per second (CPS) and maximum HTTPS throughput per test case
**Output:** normalized CSV results feeding the comparison tool in `tools/compare_results.py`

---

## 1. Objectives

1. Measure, per DUT model, the maximum sustainable **TLS connection setup rate (CPS)** and **HTTPS throughput** for each TLS version / key-exchange / cipher / certificate combination.
2. Quantify the **cost of SSL decryption** on the firewall by comparing decryption-enabled results against a pass-through (no-decrypt) baseline.
3. Quantify the **overhead of post-quantum key exchange** (ML-KEM, FrodoKEM, BIKE) relative to classical X25519/ECDHE under otherwise identical conditions.
4. Produce comparable, machine-readable results across Gen4 and Gen5 platforms so hardware generations can be ranked per workload via the comparison tool.

## 2. Non-goals

- Long-duration soak/stability testing (separate plan).
- IPsec/IKEv2 PQC testing (PAN-OS quantum-resistant VPN is a separate effort).
- Threat-prevention efficacy testing; security profiles are held constant, not evaluated.

---

## 3. Test Bed

### 3.1 Topology

```
 ┌────────────────────┐        ┌─────────────────────┐        ┌────────────────────┐
 │  ESXi host A       │        │  DUT                │        │  ESXi host B       │
 │  CyPerf client     │  L2/L3 │  Palo Alto NGFW     │  L2/L3 │  CyPerf server     │
 │  agent VM(s)       ├────────┤  (Gen4 / Gen5)      ├────────┤  agent VM(s)       │
 │                    │        │  decrypt / allow    │        │                    │
 └─────────┬──────────┘        └──────────┬──────────┘        └─────────┬──────────┘
           │                              │                             │
           └───────────────  Management network  ───────────────────────┘
                        CyPerf Controller (MDW) + Panorama/console
```

- Client agents and server agents must sit on **opposite sides of the DUT** (client zone → server zone) so every session traverses the firewall.
- Use a dedicated test VLAN pair per DUT port pair; no other traffic on the test path.
- Management traffic (CyPerf controller ↔ agents, firewall management) stays on a separate network and never crosses the DUT test ports.

### 3.2 CyPerf sizing on ESXi (avoid generator-side bottlenecks)

The generator must always have more capacity than the DUT. PQC handshakes are CPU-heavy on the generator side too — size for the worst case.

| Item | Recommendation |
|---|---|
| CyPerf agent vCPU | 16+ vCPU per agent VM, CPU reservation set, no oversubscription on the host |
| Memory | 32 GB per agent VM (minimum per CyPerf release notes for high CPS) |
| vNIC | **SR-IOV or PCI passthrough** on the test interfaces (VMXNET3 acceptable only for low-rate DUTs); dedicated 25/100G NICs for Gen5 throughput targets |
| ESXi | Disable power management (High Performance), pin NUMA locality of NIC + VM, MTU consistent end-to-end |
| Scale-out | Add agent VMs (CyPerf supports multi-agent scale-out per test) until the back-to-back calibration (§7.1) exceeds ~150% of the highest expected DUT number |
| Version | CyPerf release with PQC cipher support — **verify that your installed release exposes ML-KEM (hybrid X25519MLKEM768 and pure ML-KEM), FrodoKEM, and BIKE groups** in the TLS settings of the application/attack profile. Record the exact CyPerf version in every result row. |

### 3.3 DUT inventory (fill in per lab)

| DUT ID | Model | Generation | PAN-OS version | Test interfaces | Notes |
|---|---|---|---|---|---|
| DUT-1 | e.g. PA-3440 | Gen4 | e.g. 11.2.x | ethernet1/1–1/2 (25G) | |
| DUT-2 | e.g. PA-5440 | Gen4 | | | |
| DUT-3 | e.g. PA-5450 / PA-7500 | Gen5 | | | |

Rules:

- All DUTs run the **same PAN-OS major release** wherever the hardware supports it; otherwise record the difference — the comparison tool keys results by model *and* PAN-OS version.
- Identical rulebase across DUTs: one allow rule (client zone → server zone, application ssl/web-browsing), one decryption rule per scenario, logging at session end only, **no threat/URL profiles** (constant policy; see non-goals).
- Content/app version pinned and identical across DUTs.

---

## 4. DUT Scenarios

Every test case in §6 is executed under the applicable scenarios below. Scenario is a column in the results CSV.

| Scenario | Name | Firewall behavior | Purpose |
|---|---|---|---|
| **S0** | Pass-through baseline | Allow rule only, **no decryption** | Isolates the cost of decryption; measures raw session/NAT/inspection capacity for TLS flows |
| **S1** | SSL Inbound Inspection | Decryption rule with the CyPerf **server certificate + key** imported on the firewall | Primary scenario. Deterministic: the exact cipher/kex offered by CyPerf is what the firewall must handle |
| **S2** (optional) | SSL Forward Proxy | Resign with firewall subordinate CA; CyPerf clients trust the proxy CA | Representative of outbound enterprise traffic; note the firewall renegotiates its own cipher toward the server, so client-side and server-side ciphers can differ — record both |

### 4.1 Decryption profile requirements (S1/S2)

- SSL Protocol Settings: min/max version pinned to the version under test (e.g., min = max = TLS 1.3 for TLS 1.3 cases) so no downgrade masks a failure.
- Enable only the key-exchange, encryption, and authentication algorithms of the test case under test.
- **Unsupported-mode handling: set to *block*, not allow.** This is critical for the PQC cases — if the platform/release cannot decrypt a PQC handshake, the sessions must fail visibly rather than silently bypassing decryption and inflating results.
- Verify decryption is actually occurring during each run: `show session all filter ssl-decrypt yes count yes` must track the active session count.

### 4.2 PQC support caveats (verify before executing Group C)

- **ML-KEM:** FIPS 203. The deployed web standard is the **hybrid group X25519MLKEM768**; pure ML-KEM-768/1024 groups also exist. Confirm the PAN-OS release on the DUT supports these groups **in TLS decryption** (quantum-resistant IKEv2 support in PAN-OS 11.2 does *not* imply TLS decryption support — check the release notes/decryption profile options of your target release, e.g. PAN-OS 11.2+/12.x).
- **FrodoKEM / BIKE:** not NIST-standardized (BIKE was a round-4 candidate; FrodoKEM is pursued in ISO). Support exists mainly via liboqs-based stacks. Expect these to be **pass-through-only (S0)** cases unless both CyPerf and PAN-OS explicitly support them in decryption; record `not-supported` outcomes as results — "cannot decrypt" is a finding, not a test error.
- PQC handshakes have large key shares (ClientHello for ML-KEM hybrids exceeds one TCP MSS and will span multiple segments; FrodoKEM public keys are ~9–15 KB). Verify DUT behavior with fragmented ClientHellos in S0 before blaming decryption performance.

---

## 5. Certificates & Crypto Material

| ID | Type | Details | Used by |
|---|---|---|---|
| CERT-RSA | RSA 2048, SHA-256 | CN=perf.test.local, 1-year validity | TLS 1.2/1.3 RSA cases |
| CERT-RSA-3K (optional) | RSA 3072 | Sensitivity run for cert-size impact | Optional repeats |
| CERT-EC | ECDSA P-256, SHA-256 | Same CN/SAN as CERT-RSA | TLS 1.2/1.3 ECDSA cases |

- Same issuing chain (single intermediate) for both certs so chain length is constant.
- For S1, import the leaf + key on the firewall. For S2, deploy the firewall's forward-trust CA into the CyPerf client profile.
- Session resumption/tickets **disabled** for CPS tests (every connection must do a full handshake); a separate optional resumption case can be added later.

---

## 6. Test Case Matrix

Certificate authentication is the server's signature algorithm; key exchange is the (EC)DHE/KEM group. In TLS 1.3 the certificate type is independent of the cipher suite; in TLS 1.2 it is bound into the suite name.

### Group A — TLS 1.2, classical

| TC | TLS | Key exchange | Cipher suite | Certificate | Priority |
|---|---|---|---|---|---|
| A1 | 1.2 | ECDHE P-256 | ECDHE-RSA-AES128-GCM-SHA256 | RSA-2048 | P1 |
| A2 | 1.2 | ECDHE P-256 | ECDHE-RSA-AES256-GCM-SHA384 | RSA-2048 | P1 |
| A3 | 1.2 | ECDHE P-256 | ECDHE-ECDSA-AES128-GCM-SHA256 | ECDSA P-256 | P1 |
| A4 | 1.2 | ECDHE P-256 | ECDHE-ECDSA-AES256-GCM-SHA384 | ECDSA P-256 | P1 |
| A5 | 1.2 | RSA (static, no PFS) | AES256-GCM-SHA384 | RSA-2048 | P3 (legacy reference) |

### Group B — TLS 1.3, classical

| TC | TLS | Key-exchange group | Cipher suite | Certificate | Priority |
|---|---|---|---|---|---|
| B1 | 1.3 | x25519 | TLS_AES_128_GCM_SHA256 | RSA-2048 | P1 |
| B2 | 1.3 | x25519 | TLS_AES_256_GCM_SHA384 | RSA-2048 | P1 |
| B3 | 1.3 | x25519 | TLS_AES_128_GCM_SHA256 | ECDSA P-256 | P1 |
| B4 | 1.3 | x25519 | TLS_AES_256_GCM_SHA384 | ECDSA P-256 | P1 |
| B5 | 1.3 | secp256r1 | TLS_AES_256_GCM_SHA384 | ECDSA P-256 | P2 |
| B6 | 1.3 | x25519 | TLS_CHACHA20_POLY1305_SHA256 | ECDSA P-256 | P3 |

### Group C — TLS 1.3, post-quantum key exchange

Cipher suite fixed at TLS_AES_256_GCM_SHA384, certificate fixed at ECDSA P-256 (repeat C1 with RSA-2048 as C1r if cert sensitivity is wanted). Only the key-exchange group varies — this isolates the PQC cost.

| TC | Key-exchange group | Type | Priority | Support gate |
|---|---|---|---|---|
| C1 | X25519MLKEM768 | Hybrid ML-KEM (deployed standard) | P1 | CyPerf + PAN-OS release check |
| C2 | ML-KEM-768 (pure) | FIPS 203 | P1 | CyPerf + PAN-OS release check |
| C3 | ML-KEM-1024 (pure) | FIPS 203 | P2 | CyPerf + PAN-OS release check |
| C4 | FrodoKEM-640 | Non-standardized, conservative | P2 | Likely S0 only |
| C5 | FrodoKEM-976 | Non-standardized | P3 | Likely S0 only |
| C6 | BIKE-L1 | Round-4 candidate | P2 | Likely S0 only |
| C7 | BIKE-L3 | Round-4 candidate | P3 | Likely S0 only |

**Baseline pairing:** B4 (x25519, same cipher, same cert) is the classical reference for all Group C cases. The comparison tool computes PQC overhead against it automatically.

### Execution grid

Each TC runs as: `TC × scenario (S0, S1[, S2]) × test type (CPS, THROUGHPUT)`.

Priority order for lab time: **P1 × S1**, then **P1 × S0**, then P2, then P3/S2.

---

## 7. Test Types & Procedure

### 7.1 Back-to-back calibration (mandatory, once per test type)

Cable/vSwitch the client agents directly to the server agents (bypass DUT) and run the heaviest cases (e.g., B4 and C1 CPS; B2 throughput). The generator ceiling must exceed the best expected DUT result by ≥ 50%. Record these numbers in the CSV with `dut_model=B2B`. If the margin is not met, add agent VMs before testing any DUT.

### 7.2 T-CPS — maximum TLS connections per second

- Traffic: HTTPS GET of a **1 KB** object, **1 transaction per connection**, connection closed after the response, **session resumption and TLS tickets disabled**, HTTP keep-alive off.
- Method: CyPerf objective = simulated users/CPS ramp. Find the plateau with a step ramp (or CyPerf's goal-seeking): increase offered CPS until the failure criterion trips, then binary-search between last-good and first-bad at ~5% steps.
- **Sustain:** hold the candidate rate for **300 s** steady state.
- **Pass criteria** during steady state: TCP/TLS failure rate < 0.01%, no CyPerf agent CPU > 85%, DUT within §7.4 health limits.
- Record: achieved CPS (the reported value), failure %, TLS handshake latency (avg/p95), DUT dataplane CPU %.
- Repeat **3 runs**; report the **median**; flag > 5% spread between runs as invalid → investigate and rerun.

### 7.3 T-TPUT — maximum HTTPS throughput

- Traffic: HTTPS GET of a **512 KB** object, persistent connections (many transactions per connection) so bulk crypto dominates rather than handshakes; concurrent connections sized to fill the pipe (start at 2× BDP).
- Method: throughput objective ramp to the plateau, same binary-search refinement.
- Sustain 300 s; pass criteria: failure rate < 0.01%, retransmissions < 0.1%, agent CPU < 85%, DUT within health limits.
- Record: L7 goodput (Gbps) as the value; also capture L2 throughput if you need datasheet-style numbers, but the CSV value is L7 goodput — be consistent across all DUTs.
- 3 runs, median, same spread rule.

### 7.4 DUT health limits & monitoring (during every run)

Poll every 10 s (or use SNMP/API):

```
show running resource-monitor                # dataplane CPU per core group
show session info                            # CPS, active sessions, table utilization
show session all filter ssl-decrypt yes count yes   # confirms decryption is active (S1/S2)
show counter global filter delta yes | match ssl    # proxy/decrypt error counters
debug dataplane pool statistics              # packet buffer/descriptor depletion
```

A run is invalid (regardless of CyPerf pass criteria) if: packet-buffer depletion occurs, session table > 80% during a CPS test, or decrypt-bypass counters increment in S1/S2 (means traffic sneaked past decryption).

### 7.5 Run hygiene

- `clear session all` and clear counters between runs; 60 s idle gap.
- One variable changes at a time; config commits verified before the run starts.
- Fresh CyPerf test session per TC (no reused stats windows).
- Reboot DUT between scenario changes if buffer/decrypt pools have been exhausted.

---

## 8. Data Collection — CSV Schema

One row per (run-median) result. File: `results/<dut>_<date>.csv`. Template in `results/results_template.csv`.

| Column | Meaning | Example |
|---|---|---|
| `test_id` | TC identifier from §6 | `C1` |
| `date` | ISO date of run | `2026-07-15` |
| `dut_model` | Model or `B2B` for calibration | `PA-5450` |
| `generation` | `Gen4` / `Gen5` / `-` | `Gen5` |
| `panos_version` | Exact version | `11.2.4-h2` |
| `cyperf_version` | Exact version | `6.1.0` |
| `scenario` | `S0` / `S1` / `S2` | `S1` |
| `tls_version` | `1.2` / `1.3` | `1.3` |
| `key_exchange` | Group name as configured | `X25519MLKEM768` |
| `cipher` | Cipher suite | `TLS_AES_256_GCM_SHA384` |
| `certificate` | `RSA-2048` / `ECDSA-P256` | `ECDSA-P256` |
| `test_type` | `CPS` / `THROUGHPUT` | `CPS` |
| `value` | Median of 3 runs | `18500` |
| `unit` | `cps` / `gbps` | `cps` |
| `fail_rate_pct` | Steady-state failure % | `0.004` |
| `dut_cpu_pct` | Peak dataplane CPU % | `92` |
| `notes` | Free text (e.g. `not-supported: decrypt bypass blocked`) | |

Unsupported combinations get a row with `value=0`, `unit` as normal, and a `not-supported` note — the comparison report shows these explicitly instead of leaving holes.

---

## 9. Reporting & Comparison

`tools/compare_results.py` (Python 3.8+, stdlib only) ingests every CSV under `results/` and produces:

1. **Per-metric comparison charts** (HTML report): for each test type, every test case as a grouped horizontal bar chart with one bar per DUT — direct value labels, light/dark aware, plus the full data table.
2. **Decryption cost:** S1 value as % of S0 value per DUT/test case (where both exist).
3. **PQC overhead:** each Group C result as % delta vs its B4 classical reference (same DUT, scenario, cipher, cert, test type).
4. **Generation ranking:** per test type, DUTs ordered by value with Gen4/Gen5 tagging.

```
python3 tools/compare_results.py results/ -o comparison_report.html
```

See `README.md` for options (baseline DUT selection, filtering).

---

## 10. Risks & Caveats

| Risk | Mitigation |
|---|---|
| CyPerf VM is the bottleneck, DUT numbers understated | §7.1 mandatory B2B calibration with ≥ 50% headroom; SR-IOV NICs |
| PQC groups unsupported by CyPerf release or PAN-OS release | §4.2 support gate before scheduling lab time; record `not-supported` rows |
| Decryption silently bypassed for unsupported ciphers → inflated "PQC" numbers | Unsupported-mode = block in decryption profile; §7.4 decrypt-session count check every run |
| Fragmented ClientHello (ML-KEM hybrid, FrodoKEM) handled differently than small hellos | Run S0 first for Group C to establish pass-through behavior |
| TLS 1.3 inbound inspection is a full proxy on modern PAN-OS — results are proxy performance, not passive decrypt | Expected and desired; note it in the report narrative |
| Thermal/power differences across runs | Same rack conditions; 3-run median; spread rule in §7.2 |
| PAN-OS version skew across DUTs | Record exact versions; comparison tool displays them next to each DUT |

---

## 11. Deliverables

1. Completed `results/*.csv` per DUT (this schema).
2. `comparison_report.html` generated by the tool.
3. Summary narrative: decryption cost, PQC overhead, Gen4 vs Gen5 verdict per workload.
