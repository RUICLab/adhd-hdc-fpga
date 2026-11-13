# ADHD HDC FPGA

SystemVerilog implementation of a binary hyperdimensional computing (HDC)
classifier, independent Python verification, C++ reference implementations,
and reproducible FPGA results for the Xilinx Zynq-7020 / PYNQ-Z2.

The repository supports reproducing the digital classifier and its synthetic
validation. It includes physical-board results for 10 and 26 classes. Trained
ADHD models, EEG datasets, sensor hardware, and a training pipeline are not
included; the recorded tests establish implementation correctness rather than
diagnostic or classification accuracy.

## Implementation

The default configuration uses 196 four-level input features, 8192-dimensional
binary hypervectors, and either 10 or 26 class prototypes. For feature index
`i` and dimension `j`, the encoder uses Hadamard bit
`parity(((1597 * (i + 1)) mod 8192) & j)`, XOR-bound to the selected level bit.
The query bit is one when the 196 bound bits sum to **at least 96**. This
threshold is intentional. Class scores count matching query/prototype bits;
the lowest class index wins ties.

The RTL generates dimensions in Gray-code order and pipelines the popcount.
It evaluates every dimension, then scans all classes; no early exit is used.
Start-to-result latency is `8192 + 5 + classes` core cycles.

| Path | Purpose |
|---|---|
| `hw/adhd/adhd_hdc.sv` | Synthesizable classifier with writable model/feature memory |
| `hw/adhd/adhd_board_test.sv` | Synthesizable fixture loader and result checker |
| `hw/adhd/adhd_board_top.sv` | PYNQ-Z2 clocking and JTAG VIO integration |
| `sim/adhd/` | Core and board-controller testbenches |
| `scripts/` | Golden vectors, simulation, implementation, power estimates, board tests |
| `bench/hdc_cpu.cpp` | Direct-parity, stored-HV, and exact FWHT CPU references |
| `docs/INTERFACE.md` | Core ports and model format |
| `docs/REPRODUCE.md` | Simulation, FPGA, power, and CPU commands |
| `docs/BOARD.md` | Building, programming, and checking the PYNQ-Z2 |
| `docs/RESULTS.md` | Results, evidence provenance, and measurement boundaries |
| `docs/adhd/` | Tool reports, simulation transcripts, and JTAG results |

## Quick start

Requirements: Python 3.10+ (standard library only) and an installed
Vivado/XSim with Zynq-7000 support. The supplied launchers are tested on Windows
with Vivado 2025.2. Archived core-only results used Vivado 2026.1. A physical
board is only needed for the board test; GCC with C++17 support is optional
for the CPU benchmark. No Python packages, model downloads, or datasets are
needed for the deterministic checks.

```powershell
git clone https://github.com/RUICLab/adhd-hdc-fpga.git
cd adhd-hdc-fpga
# Set this to your installed Vivado root.
$vivadoRoot = 'C:/AMDDesignTools/2025.2/Vivado'
python scripts/adhd_verify.py --vivado $vivadoRoot --classes 10
python scripts/adhd_verify.py --vivado $vivadoRoot --classes 26
```

Each run must print `ADHD PASS`. Tests compare every query bit, all class
scores, winner and cycle count against a direct-parity reference. They also
exercise reset/abort/restart, ignored writes while busy, ties, last-class
selection and result backpressure. Generated vectors and builds stay under
ignored `build/`.

## Validated results

Core-only implementation, Vivado 2026.1, `xc7z020clg400-1`:

| Classes | LUTs | FFs | BRAM36 equivalent | DSPs | Cycles | Core time at 100 MHz |
|---|---:|---:|---:|---:|---:|---:|
| 10 | 1387 | 1317 | 3.5 | 0 | 8207 | 82.07 us |
| 26 | 1491 | 1589 | 7.5 | 0 | 8223 | 82.23 us |

Physical PYNQ-Z2 validation, Vivado 2025.2: **40 checked inferences,
327,680 query-bit comparisons, zero errors** across the two configurations.
Each configuration passed five reset/load/infer batches. JTAG readback
confirmed every final winner, winning score, query count and core cycle count.
Both complete test harnesses met setup and hold timing at the requested
100 MHz clock. Their ROM/debug resources are additional to the core above.

CPU results on one Intel Core i7-13700F thread: median HDC compute times were
913.621 us (direct parity), 331.668 us (stored-HV), and 88.368 us (exact FWHT).
The fastest tested CPU baseline is about 1.08 times the cycle-derived FPGA
core time. This excludes model transfer, launch, host overhead and sensor
work; it is not a measured end-to-end speedup. FPGA power figures in the
archived reports are tool estimates, not measured rail power or energy.

See [results and limitations](docs/RESULTS.md) before using these numbers.
The repository contains technical documentation and results, with no
manuscript files or generated vendor IP/binaries. Code is released under the
[MIT license](LICENSE).
