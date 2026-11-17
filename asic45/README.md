# Gray-code HDC backend: 45-nm ASIC estimates

This study uses the same D=8192, K=10/26 HDC backend as the FPGA validation.
It contains no sensor implementation or digital feature-extraction frontend.
Inputs are 196 two-bit features. Fixtures are synthetic functional data;
these results establish implementation correctness, not classification accuracy.

- [Results and assumptions](RESULTS.md): energy, latency, area, timing and block power.
- [Change inventory](CHANGES.md): RTL extraction, flow changes and public packaging.
- [Machine-readable results](reports/results.json).
- `build/k10/` and `build/k26/`: mapped netlists, reports and verification fixtures.
- `rtl/`: unchanged original core/testbench, simulation SRAMs and timing abstracts.
- `scripts/`: synthesis, timing, power, gate simulation and result audit.

The only RTL adaptation extracts the level/prototype array into one SRAM black
box and retains the original registered read. Logic and cycle latency are
preserved. SRAM behavioral models are never synthesized into flip-flops.

## Inspect existing results

From this directory, with Python 3.9+ (standard library only):

```bash
python3 scripts/summarize.py
```

This audits logs, mapped cell counts/areas, power sums, activity windows,
SRAM paths and timing metrics, then regenerates the result tables.
`MANIFEST.sha256` records the public files. Numerical evidence is unchanged.

## Reproduce synthesis and power

Tools used:

| Tool | Version |
|---|---|
| Design Compiler | X-2025.06-SP3 |
| PrimeTime / PrimePower | X-2025.06-SP2 |
| VCS | X-2025.06-SP1-1 |
| CACTI | 7; commit `1ffd8dfb10303d306ecd8d215320aea07651e878` |

With these tools available on PATH, plus Python 3.9+, Git, GNU make and C++:

```bash
# Run from asic45/.
bash scripts/run_flow.sh
```

The driver fetches and verifies third-party inputs, builds CACTI, runs SRAM
configs, generates adapters, compiles Liberty, synthesizes, checks four original
fixtures per K, collects one inference of gate activity, and runs timing/power
and the result audit. Third-party inputs are not redistributed:

- Nangate typical Liberty: pinned OpenROAD-flow-scripts URL and SHA256.
- Functional Nangate Verilog: source URL plus SHA256. These models supply only
  zero-delay logic simulation; the requested Liberty supplies timing/power.
- CACTI 7: HewlettPackard/cacti commit
  `1ffd8dfb10303d306ecd8d215320aea07651e878`.

Inputs retain their original licenses. Large VCDs are regenerated;
original hashes and durations are in `build/k*/sim/activity_window.json`.

## Interpretation

These are **pre-layout estimates**, not measured ASIC energy or routed signoff.
Nangate45 uses typical 1.1 V/25 C. CACTI uses 45-nm ITRS-LSTP at 1.1 V/300 K,
with 14/30-bit logical words padded to 16/32 bits, no ECC and one bank.
The SRAM Liberty is an analytical integration abstract, not characterized IP.

Zero-delay activity uses original fixture case 2, with every query bit, winning
class/score, SRAM read count and D+5+K cycles checked. Four gate fixtures also
exercise reset/restart, busy-write guards and output backpressure. The original
netlist-mode PASS wording mentions all scores; the netlist check verifies the
winning score rather than every internal class counter.

No CTS or extracted routing is available. FF clock-pin internal power is
included; clock-distribution buffers/wires and glitches are excluded.
Interconnect uses the Nangate wire-load model. Maximum frequency includes SRAM,
uncertainty and stated I/O budgets. Its energy scales fixed inference activity;
it is not a timing-aware simulation. Area is cell footprint plus CACTI SRAM,
excluding physical-design overhead. Full assumptions are in RESULTS.md.

Study scripts and HDC source use the repository MIT license. Optional regional
and convolutional digital frontends were not synthesized.
