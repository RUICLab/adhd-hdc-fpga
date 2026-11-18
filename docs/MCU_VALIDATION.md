# MCU comparison status and reproduction

Two deliberately separate targets are being prepared:

1. **PicoRV32 RV32IMC reference MCU**: compiled firmware runs on CPU RTL in
   XSim. The native SRAM bus uses a registered one-cycle response. Actual
   simulated core cycles are divided by a modeled 100 MHz clock. This is not
   an ESP32 CPU or a physical-board measurement.
2. **ESP32-C3, one core at 160 MHz**: ESP-IDF firmware plus Espressif QEMU
   functional simulation, followed by an explicitly assumed instruction/CPI
   timing model. ESP-IDF v6.1.1, GCC 15.2.0 and Espressif QEMU 9.2.2 are
   installed. Both class configurations build and pass all four full-query
   checks and nine query-free calls. Dynamic instruction counts are recorded
   below; no measured ESP32 hardware runtime is claimed.

The shared kernel is `bench/mcu/hdc_packed.c`: 196 feature lanes packed into
seven 32-bit words, Gray-code Hadamard generation, SWAR population counts and
bit-plane class counters. It uses no desktop SIMD or stored feature-HV table.
Models have the same dimension-major 32-bit word format as the RTL loader.
Physical model allocation is 32 KiB for either class count (distinct from the
14/30 KiB logical packed-HV capacity). The row masks take 364 bytes. Query
storage is omitted in timed calls; an optional 1 KiB query buffer is used for
untimed verification only. Input grouping and score extraction are included
in timing; model loading, mask initialization, reference checks and printing
are outside the measured kernel. It is one optimized baseline, not a claim
that all MCU algorithms or implementations are slower.

## RISC-V RTL results actually obtained

| Classes | Raw cycles | Empty-window cycles | Corrected cycles | Retired instructions | Time at modeled 100 MHz (us) | MCU/FPGA ratio |
|---|---:|---:|---:|---:|---:|---:|
| 10 | 10,694,808 | 18 | 10,694,790 | 2,280,328 | 106,947.90 | 1303.13 |
| 26 | 11,036,303 | 18 | 11,036,285 | 2,344,922 | 110,362.85 | 1342.12 |

Simulation completed with four full-query golden checks (tie and random for
both K), both query-free timed score checks, and PASS MCU RTL. Across the four
full-query MCU checks, all 32,768 query bits and all class scores match.
K=10 random winner/score: 8/4188; K=26: 16/4170. Each timed case is a single
deterministic synthetic random fixture. These are not average dataset timings.

Raw evidence and source hashes are archived in docs/adhd/mcu-riscv/. Binary
SHA256 is c5a9c408512e6347a7f234922bb279973a6c71b6ac6ba23141bcde0b060b6a68.
A current-source recompilation produced exactly the executed image. No RTL
cycle count from this MCU is substituted for an ESP32 cycle count.

## Host validation already executed

`scripts/prepare_mcu_vectors.py` independently evaluates natural-index parity
for K=10/26, D=8192, four deterministic cases per K. Cases include exact tie,
all-three/random features and last-class winner. `bench/mcu/test_host.c`
compares every query bit, class score and winner, and repeats each inference
without query storage. All eight cases / 65,536 query bits pass with GCC 9.5.0
at -O3. This is C algorithm validation, not ESP32 timing validation.

## Run the RISC-V RTL reference

```powershell
python scripts/run_mcu_rtl.py
```

Options `--gcc PATH` and `--vivado PATH` override the original compiler and
Vivado installations. Original compiler is the Vivado-bundled RISC-V GCC 13.4.0
at `C:/vivado/2026.1/Vivado/gnu/riscv/linux_toolchain/nt32/bin/riscv32-amd-linux-gcc.exe`.
The firmware is bare metal: no Linux runtime or libraries are linked.
Flags include -O3, -march=rv32imc_zicsr_zicntr, -mabi=ilp32, -ffreestanding,
-nostdlib, -static, no PIE, no stack protector, no linker relaxation and no
GNU build-ID note. The initial startup smoke test exposed the Linux linker's
default build-ID at address zero; this was disabled before valid execution.

Vendor CPU source is fetched by `scripts/fetch_picorv32.py` from upstream
YosysHQ/picorv32 at commit `ef203c2b0a3fb793280f5114941416c425c5b461`.
Source/ISC license hashes are recorded in `build/vendor/picorv32/source.json`.
The unmodified CPU RTL hash is
`0836050971b3c6cdd28ac3b1e5719a67fb645161912bef1e472e63995ceb0622`.
The simulator's CPU parameters include dual-port registers, barrel shifter,
compressed ISA, fast multiplier, divider, enabled counters and no interrupts.
There are 512 KiB of uniform initialized SRAM, no caches or flash wait states.
This clock/memory configuration is a model, not signed-off target silicon.

Firmware verifies complete query bits/scores/winners for a tie and a random
case at each K, then times the query-free random inference. Hardware `rdcycle`
and `rdinstret` counters count actual simulated clocks/instructions. An empty
counter-read window is measured and subtracted; raw counts are retained.
The timed window includes the function call/return. Do not treat simulator
wall-clock duration as modeled MCU execution time.

Outputs: `build/mcu-rtl/results.json`, `simulate.txt`, `compiler.txt`,
`disassembly.txt`, `firmware.map`, and firmware ELF/bin/hex. Success requires
four MCU_VERIFY messages, both MCU_RESULT lines and a final PASS MCU RTL.
Traps, mismatches, missing results and timeout are failures.

## Install the tools for ESP32-C3

Use Espressif Installation Manager (EIM), selecting a stable ESP-IDF release
with ESP32-C3 and its RISC-V compiler. No Arduino IDE is necessary.
Open the installed ESP-IDF PowerShell environment and install QEMU:

```powershell
python "$env:IDF_PATH/tools/idf_tools.py" install qemu-riscv32
```

Reopen the ESP-IDF terminal so tools are exported, then confirm:

```powershell
idf.py --version
qemu-system-riscv32 --version
```

Run from the repository root to generate the fixtures, then build both variants:

```powershell
python scripts/prepare_mcu_vectors.py
cd bench/esp32
idf.py set-target esp32c3
idf.py -B build/k10 -D HDC_CLASSES=10 build
idf.py -B build/k10 qemu monitor
# Stop QEMU after the final ESP32_HDC PASS marker.
idf.py -B build/k26 -D HDC_CLASSES=26 build
idf.py -B build/k26 qemu monitor
```

Both target configurations were built and run on November 18, 2026.
It requests a fixed 160 MHz configuration, disables dynamic power management,
does not initialize Wi-Fi/Bluetooth, puts the kernel in IRAM and the working
model in internal RAM. It checks all four golden cases before nine query-free
samples. The printed guest cycle-counter delta is diagnostic only when run
under QEMU. It MUST NOT be entered directly as real ESP32 timing in a table.

## Analytical ESP32 timing after functional validation

QEMU explicitly does not model real instruction cycle timing. Obtain dynamic
executed instruction counts per kernel invocation (not static disassembly
line counts), preserving the trace/counting method and compiler flags. Verify
that helper functions, calls and loop iterations are included. The prepared
firmware has four verification calls followed by nine timed calls; do not mix
query-capturing verification and query-free benchmark counts.

For an explicitly assumed mean CPI, estimate

    time_us = executed_instructions * assumed_CPI / frequency_MHz.

`scripts/estimate_esp32_time.py` accepts counts and the evidence file, then
reports CPI=1/2/3 sensitivity points by default. These are assumptions, NOT
calibrated predictions, confidence intervals or guaranteed hardware bounds.
No MCU energy follows from them. A result derived from another RV32 execution
model must identify that model rather than claim ESP32 SoC simulation.
The helper deliberately has no default instruction count, so it cannot invent
a numerical runtime before an execution/counting run is available.

## ESP32-C3 execution evidence (November 18, 2026)

ESP-IDF v6.1.1; riscv32-esp-elf GCC 15.2.0 (esp-15.2.0_20251204);
Espressif QEMU 9.2.2 (esp_develop_9.2.2_20260417). Both K=10 and K=26 pass
all four independent golden queries (65,536 checked query bits in total),
all class scores and the tie/forced-winner checks. Each then passes nine
query-free calls on deterministic random case 2. The following counts include
feature grouping, counter initialization, encoding, class-score extraction,
function prologue/epilogue and return. Model/feature copies, mask initialization,
checking, printing, RTOS and peripheral overhead are excluded.

| Classes | Instructions per query-free call | Assumed CPI=1, us | Assumed CPI=2, us | Assumed CPI=3, us |
|---|---:|---:|---:|---:|
| 10 | 2,181,879 | 13,636.74 | 27,273.49 | 40,910.23 |
| 26 | 2,233,890 | 13,961.81 | 27,923.63 | 41,885.44 |

The clock assumption is 160 MHz. At CPI=2, modeled time divided by FPGA core
time (82.07/82.23 us) is 332.32x/339.58x. These are analytical ratios, not
measured speedups. CPI=1/2/3 is a sensitivity study, not an empirically
calibrated estimate or a guaranteed range. No hardware measurements, cache
timing, bus stalls, branch penalties, MCU energy or MCU area are established
by QEMU. A physical ESP32-C3 run is still required for publishable measured
runtime. These are single-input kernel counts, not dataset-average latency.

`scripts/run_esp32_qemu.py` launches the target's merged flash image with the
ESP-IDF default C3 eFuse configuration and a 4 MiB emulated flash. It uses
`-accel tcg,one-insn-per-tb=on -d exec,nochain` with `-dfilter` restricted
to the complete `hdc_packed32` symbol. The disassembly is checked for outgoing
calls/indirect jumps; helpers are inline. Thus each executed trace record is
one kernel instruction, including compressed instructions. Four verification
calls and nine query-free calls are separated by entry PC; the latter counts
are identical within each K. All 13 calls finish at the kernel return PC.
The kernel is in IRAM; working model and features are in internal SRAM.

UART output, full-kernel disassembly, compile commands, source/ELF/trace hashes
and per-call counts are in `docs/adhd/esp32-k10/` and `esp32-k26/`.
Combined counts and CPI sensitivity results are in `docs/adhd/esp32/`.
Raw 2.1 GB traces remain in ignored build folders; rerun to regenerate them.
QEMU's printed guest-counter deltas and host execution time are not used.

For an exported ESP-IDF terminal, build and count from the repository root:

```powershell
$repo = (Get-Location).Path
python scripts/prepare_mcu_vectors.py
$qemu = 'C:/Espressif/tools/tools/qemu-riscv32/esp_develop_9.2.2_20260417/qemu/bin/qemu-system-riscv32.exe'
$tc = 'C:/Espressif/tools/riscv32-esp-elf/esp-15.2.0_20251204/riscv32-esp-elf/bin'
foreach ($k in 10,26) {
  $targetBuild = "$repo/build/esp32-k$k"
  python "$env:IDF_PATH/tools/idf.py" -C bench/esp32 -B $targetBuild -D IDF_TARGET=esp32c3 -D HDC_CLASSES=$k build
  python scripts/run_esp32_qemu.py --idf $env:IDF_PATH --qemu $qemu --toolchain-bin $tc --build $targetBuild --classes $k --out "docs/adhd/esp32-k$k"
}
python scripts/estimate_esp32_time.py --instructions10 2181879 --instructions26 2233890 --source 'QEMU dynamic kernel instruction trace' --evidence docs/adhd/esp32/instruction_counts.json --out build/esp32-analytical-timing.json
```

Adapt SDK/tool paths for another installation. On this host, the first K=10
build is at `<BUILD_K10>`; K=26 is under this
repository's `build/esp32-k26`. The SDK install has a separate EIM tools
layout, so the current process explicitly exports the venv, compiler and
CMake paths; no global PATH or Windows configuration was changed. Initial
`idf.py` execution needed `ESP_IDF_VERSION=6.1.1` and `PYTHONUTF8=1`; a
nonfatal missing-ROM-GDB-helper warning in K=10 was avoided by setting
`ESP_ROM_ELF_DIR` for K=26. Both final build logs report success.

Official references:
- ESP32-C3 CPU/memory: https://documentation.espressif.com/esp32-c3_datasheet_en.html
- Windows installation: https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/windows-setup.html
- Espressif QEMU: https://docs.espressif.com/projects/esp-idf/en/stable/esp32c3/api-guides/tools/qemu.html
- QEMU timing limitation: https://qemu-project.gitlab.io/qemu/devel/tcg-icount.html
- PicoRV32 core and parameters: https://github.com/YosysHQ/picorv32

No manuscript files belong in the code repository. Add numerical comparison
rows locally only after corresponding execution evidence exists, with the
model assumptions named explicitly.
