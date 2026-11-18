# Results and evidence provenance

Results cover deterministic synthetic consistency, physical classifier
execution, CPU compute benchmarks, and FPGA tool characterization. They do
not establish trained ADHD accuracy, clinical validity, sensor operation,
measured FPGA power/energy, or complete application latency.

## Physical board: Vivado 2025.2

PYNQ-Z2, XC7Z020CLG400-1, requested 100 MHz core clock. Recorded November 13,
2026. Each class configuration passed five reset/load/infer batches with
20 checked inferences and 163,840 query-bit comparisons, zero errors.

| Classes | Core cycles | Core us at requested clock | Setup slack ns | Hold slack ns |
|---|---:|---:|---:|---:|
| 10 | 8207 | 82.07 | +1.566 | +0.045 |
| 26 | 8223 | 82.23 | +1.421 | +0.032 |

`adhd/board-2025.2-k*/hardware_results.txt` contains JTAG readback. The same
folders include full-harness timing/utilization/DRC, simulation transcripts,
and ROM audits. Both harnesses met setup/hold constraints with zero unclocked
registers or unconstrained internal endpoints. Core cycle counts exclude ROM
loading, host interaction and result hold time. Clock frequency was configured
through the MMCM, not externally measured. Resources include fixture ROM/VIO;
use the separate core-only resource figures for classifier area.

## Core-only characterization: Vivado 2026.1

`adhd/evidence-k10/`, `adhd/evidence-k26/` and `adhd/metrics.json` contain
the original OOC implementation, functional-netlist/RTL checks and power
reports. Target clock is 100 MHz with 0.2 ns uncertainty.

| Classes | LUTs | FFs | BRAM36 equivalent | DSPs | Setup ns | Hold ns |
|---|---:|---:|---:|---:|---:|---:|
| 10 | 1387 | 1317 | 3.5 | 0 | +1.378 | +0.016 |
| 26 | 1491 | 1589 | 7.5 | 0 | +1.372 | +0.012 |

The mapped functional-netlist SAIF estimates are approximately 40/51 mW
dynamic for K=10/26 (about 3.28/4.19 uJ dynamic core energy per inference).
Only 63%/60% of nets have direct annotation; other activity is estimated.
Stimulus is one random synthetic case, with default typical process/thermal
assumptions and no SDF/glitch simulation. Device-static estimates are about
103/104 mW. These are estimates, not physical power measurements. Rounded
power values do not justify precise energy claims. Static/idle, sensor,
data-transfer and host costs must be included separately for a system claim.

The OOC design has no physical system IO/partition timing closure and has a
PS7-absent warning. Its reports do not establish complete application timing
or achieved Fmax. The later board harness is a separate implementation.

## CPU measurements

`adhd/cpu_environment.json` and `adhd/cpu_benchmark.txt` record Intel Core
i7-13700F, GCC 9.5.0, one thread pinned to logical CPU 0, warm caches and a
resident model. Frequency/turbo is OS-managed. Median of nine batches, each
256 inferences across 64 synthetic inputs:

| Operation | Median us |
|---|---:|
| Direct-parity HDC | 913.6207 |
| Stored-HV HDC | 331.6680 |
| Exact FWHT HDC | 88.3680 |
| Regional frontend | 0.1141 |
| Convolution/pooling frontend | 3.4598 |
| Regional frontend + FWHT | 91.5238 |
| Convolutional frontend + FWHT | 92.7148 |

All three HDC algorithms match query bits/scores for the four fixtures and
64 additional random inputs. Convolution/pooling matches an independent
reference for 64 synthetic images. Combined paths were measured independently,
not formed by summing medians. Stored-HV uses 1.53125 MiB extra storage.

The strongest tested CPU comparison is `88.368 / 82.07 = 1.0767` relative to
cycle-derived core time, rather than 11.13 against direct parity. Neither is
a measured full-system speedup. CPU energy was not measured; CPU TDP/base
power is not substituted for workload power. Frontend CPU examples do not
establish the energy or latency of a physical sensor frontend.

## Public release provenance

The release starts with a clean Git history. Raw report numeric values are
preserved. Local hostnames, absolute workspace roots and the JTAG adapter
identifier are replaced with neutral placeholders in public evidence;
sanitization is recorded in `publication_manifest.json` with file hashes.

Archived 2026.1 RTL hash `2237ee4d...` predates the explicit
`timescale 1ns/1ps` header needed by XSim 2025.2. The numerical RTL is
unchanged. `adhd/board_metrics.json` retains capture-time hashes and separately
records release-source hashes. Public-release edits to scripts make JTAG
target selection portable and remove local paths; the original physical
bitstream's numerical core and fixture controller are retained unchanged.

No trained model, dataset, generated vendor IP, bitstream, executable,
manuscript, bibliography or private Git history is distributed. Rebuild with
an installed vendor toolchain using [reproduction commands](REPRODUCE.md).

## MCU reference results

The separate [MCU study](MCU_VALIDATION.md) adds historical PicoRV32 RTL
execution results and ESP32-C3 functional QEMU validation with an explicit
instruction/CPI sensitivity model. These MCU runs do not use physical boards
and do not alter the FPGA/board or ASIC results above. The portable C kernel
also passes all eight independent fixtures in this repository after import:
65,536 query-bit comparisons, all class scores and winners, and query-free
outputs match. Public evidence path substitutions and original hashes are
recorded in `adhd/mcu_publication_manifest.json`.
