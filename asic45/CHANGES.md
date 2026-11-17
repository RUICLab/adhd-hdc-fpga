# Change inventory for this ASIC estimate

The original FPGA core is unchanged. Its source is
copied verbatim to `rtl/adhd_hdc_original.sv`, SHA256
`f769365d532712f79f5fade019ac2e43c97b08afc8791159ec577caa8af4bff1`.

## Design adaptation

`scripts/prepare.py` generates `build/k10/adhd_hdc_asic.sv` and
`build/k26/adhd_hdc_asic.sv` from that snapshot. The only RTL changes are:

1. Remove the FPGA `ram_style="block"` model-array declaration.
2. Replace its write/read process with a black-box, one-read/write-port SRAM
   instance, an address mux, and the same guarded write/read enables.
3. Retain the original `word0` register and its read enable. The SRAM read is
   asynchronous into that register; the core still observes the same
   synchronous read latency. `word0` therefore remains a standard-cell
   register rather than being silently omitted from area or clock power.
4. Add comments and explicit intermediate SRAM-interface wires.

The feature registers, Hadamard/Gray recurrence, binding, threshold 96,
popcount pipeline, class counters, tie policy, control, debug outputs and
cycle counter are unchanged. Neither model array is expanded to flip-flops.
Both mapped netlists retain exactly one SRAM instance.

`rtl/sram_models.sv` is a simulation-only behavioral implementation of the
two SRAM interfaces. It is never analyzed by Design Compiler. Memory contents
are not reset; writes remain restricted to idle/non-start cycles. The
generated Liberty abstracts contain no SRAM dynamic/leakage power: CACTI
array energy and leakage are added separately to avoid double counting.

## Flow and analysis additions

- Downloaded the requested Nangate typical Liberty from a pinned
  OpenROAD-flow-scripts commit, recorded in `vendor/library_source.json`.
  The Liberty data was not edited. Library Compiler converts it to `.db`.
- Added CACTI 7 input files: 45 nm, ITRS-LSTP cells and peripherals, 1.1-V
  technology-file nominal voltage, 300 K, one bank, one RW port, scratch RAM,
  no tags/ECC/power gating. Logical 14/30-bit words are conservatively modeled
  as byte-rounded 16/32-bit physical words. Original CACTI source is unchanged.
- Added SRAM timing abstracts from CACTI access time and area. Assumed port
  capacitance is 2 fF, output slew 50 ps, write setup 50 ps, hold zero. These
  are explicitly assumed integration abstracts, not characterized SRAM IP.
  Per-bit arcs avoid unequal address/data-bus width interpretation errors.
  `interface_timing:true` is required so the tools propagate timing across
  the nonfunctional SRAM abstract. The flow explicitly rejects a netlist
  with no constrained SRAM-read path; this was audited before final results.
- Added Design Compiler scripts, top-module naming after parameter
  elaboration, and explicit exclusion of ideal constant pseudo-drivers from
  standard-cell counts. Constants have zero area/power here; physical tie
  cell insertion is not modeled. FF counts exclude the SRAM macro.
- Added a 100-MHz SDC: 100-ps clock uncertainty, 50-ps clock/input transition,
  1-ns maximum/zero minimum input and output delays, 2-fF output loads and
  the library `5K_hvratio_1_1` top-level wire-load model. No CTS, placement,
  routed RC/SPEF, extraction or SDF is performed.
- Enabled `set_fix_hold` and incremental hold-only mapping after the initial
  timing audit found a violation with the conservative 100-ps hold uncertainty.
  This inserts/changes mapped delay buffers, not RTL logic or cycle latency.
  Area, netlist checks and power are rerun after this change.
- Reused the existing fixture hex files and core testbench unchanged, in
  gate-netlist mode, with a small parameter wrapper. Added a separate case-2
  activity testbench checking every query bit/address, winner/score, exact
  cycles, SRAM read count and recording duration.
- The activity testbench uses a 0.5-ps tolerance only for floating-point
  comparison of `$realtime`; no design timing or function is changed.
- VCS runs with `+nospecify +notimingcheck` and `-no_save`: zero-delay
  functional switching, no SDF/glitch estimate and no save/restore ASLR
  re-execution. A streaming script rebases VCD timestamps to zero, appends a
  one-ps final marker if needed, and verifies exact duration and clock edges.
- Added PrimeTime/PrimePower averaged analysis, activity-annotation reports,
  explicit register-to-register and SRAM-read path reports, a minimum-period
  recheck with 1-ps positive margin, cell power export, and disjoint
  capture-register cone allocation for approximate block attribution.
  Retained `bound` nets seed the binding/level-mux lane cone. Register-clock-pin
  internal power is exported separately so the clock subtotal is not counted
  twice (`power_enable_pin_internal_power` enabled). Timing reports explicitly
  include positive-slack paths. Temporary power-export diagnostics were fixed;
  only error-free final runs are accepted.
- Added result aggregation and reproducibility documentation. At maximum
  frequency, dynamic energy is scaled as fixed activity per inference;
  leakage energy uses the shorter latency. This is not timing-aware GLS.

## Public release

- Added the HDC ASIC scripts, fixtures, mapped netlists, reports and results.
- Recorded tool versions, library provenance and scientific assumptions.
- Included pinned third-party download instructions and a cell-area table for
  auditing results without commercial tools.
- Kept the original HDC function and FPGA core unchanged.
- Normalized public text to LF and included a SHA256 manifest.
- Published tool-output excerpts with relative artifact paths and no machine
  setup information. Numerical results are unchanged.
- The generic `scripts/run_flow.sh` uses tools already available on PATH.

No sensor implementation or optional digital frontend baseline is included.
