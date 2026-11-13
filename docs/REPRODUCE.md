# Reproducing the implementation

Run from the repository root in PowerShell, with Python 3.10+ and Vivado/XSim
installed. Set `$vivadoRoot` to your installation. Vendor tools/IP are not
redistributed. These launchers use Windows `.bat` files; Linux launching has
not been tested. The public release uses the same numerical RTL as the
recorded board run.

## Core RTL and routed-netlist checks

```powershell
$vivadoRoot = 'C:/AMDDesignTools/2025.2/Vivado'
foreach ($k in 10,26) {
    python scripts/adhd_verify.py --vivado $vivadoRoot --classes $k --saif
    & "$vivadoRoot/bin/vivado.bat" -mode batch -source scripts/adhd_synth.tcl -tclargs $k
    python scripts/adhd_verify.py --vivado $vivadoRoot --classes $k --netlist --saif
    & "$vivadoRoot/bin/vivado.bat" -mode batch -source scripts/adhd_power.tcl -tclargs $k gate
}
python scripts/adhd_report.py
```

Expected simulation marker: `ADHD PASS`. Each run tests four deterministic
cases using the independent direct-parity Python reference. RTL simulation
checks every query bit, all class scores, winner, and cycle count. Routed
functional-netlist simulation checks query bits, winner and winning score;
it does not perform SDF/glitch simulation. Model words and feature/query/score
fixtures are emitted as hexadecimal text under `build/adhd-sim-k*-d8192/`.

OOC implementation reports go to `build/adhd-k*/`. Power capture uses the
random case only. Keep power annotation coverage and tool/process/thermal
assumptions with any estimates. Raw archived results used Vivado 2026.1;
different tools and machines can produce different placement/timing/power.
Fresh results do not automatically replace the archived evidence.

## CPU reference and benchmark

Generate the K=10 simulation fixtures first. Use GCC with C++17 support:

```powershell
# Set a GCC directory; the Vivado-bundled compiler was used for archived runs.
$compiler = "$vivadoRoot/tps/mingw/10.0.0/win64.o/nt/bin"
$env:PATH = $compiler + ';' + $env:PATH
& "$compiler/g++.exe" -O3 -march=native -std=c++17 -static-libgcc -static-libstdc++ bench/hdc_cpu.cpp -o build/hdc_cpu.exe
& ./build/hdc_cpu.exe ./build/adhd-sim-k10-d8192
```

Expected checks: three CPU algorithms agree with the four RTL fixtures,
64 extra random inputs agree, and convolution/pooling agrees with its
independent direct-loop reference. Timings use 64 resident synthetic inputs,
warm caches, nine batches of 256 inferences and median batch-average time.
Windows code attempts to pin to logical CPU 0; inspect the printed affinity
success flag. CPU frequency/turbo is OS-managed. Results will vary by CPU,
compiler, OS and system load.

The stored-HV baseline uses 1.53125 MiB of extra byte-vector storage. FWHT
is the fastest tested reference and is mathematically exact for this encoder.
The printed `fpga_core_speedup` value divides CPU time by a fixed 82.07 us
cycle-derived reference. It is a compute-only ratio, not measured full-system
speedup. The regional and convolutional frontend examples are synthetic CPU
kernels; their sensor circuits and FPGA implementations are not provided.

See [board instructions](BOARD.md) for physical execution, and
[results/provenance](RESULTS.md) for the archived measurements.
