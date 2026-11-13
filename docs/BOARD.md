# PYNQ-Z2 board test

The harness uses the PYNQ-Z2 125 MHz PL clock on H16 and a Clocking Wizard
MMCM requesting 100 MHz. Pin reference:
[Xilinx PYNQ-Z2 constraints](https://github.com/Xilinx/xup_fpga_vivado_flow/blob/main/source/pynq-z2/lab5/uart_led_pins_pynq.xdc).
JTAG VIO provides reset and result readback. No PS software or network
configuration is needed. This is a PYNQ-Z2-specific pin/clock design, not a
universal Zynq-7020 board bitstream.

## Build and run

Connect and power a PYNQ-Z2 with a working JTAG driver. The final command
below replaces the current volatile FPGA configuration. It does not write
boot flash or SD storage. By default the runner requires exactly one JTAG
target containing exactly one XC7Z020; an optional second Tcl argument can
select a target by its full path/glob.

```powershell
$vivadoRoot = 'C:/AMDDesignTools/2025.2/Vivado'
foreach ($k in 10,26) {
    python scripts/adhd_verify.py --vivado $vivadoRoot --classes $k
    python scripts/adhd_board_prepare.py --classes $k
    python scripts/adhd_board_verify.py --vivado $vivadoRoot --classes $k
    & "$vivadoRoot/bin/vivado.bat" -mode batch -source scripts/adhd_board_build.tcl -tclargs $k
    & "$vivadoRoot/bin/vivado.bat" -mode batch -source scripts/adhd_board_run.tcl -tclargs $k
}
& "$vivadoRoot/bin/vivado.bat" -mode batch -source scripts/adhd_board_audit.tcl
python scripts/adhd_board_collect.py
```

Expected markers: `BOARD CONTROLLER PASS` twice per simulated configuration,
`BOARD PASS` five times per hardware configuration, `ADHD HARDWARE PASS`,
and a post-route `BOARD ROM AUDIT PASS` for each configuration. Scripts fail
on mismatches. Results and generated IP/bitstreams stay under ignored `build/`.
The collector can archive new results into `docs/adhd/`; save archived evidence
separately before intentionally replacing it.

## Hardware checks

The fixture ROMs hold the four independent Python-reference cases. The
controller loads every model word and feature, runs inference, compares all
8192 query bits and Gray addresses, and checks the final winner/score and
`8192 + 5 + K` cycles. Cases include an all-class tie and a last-class winner.
Case zero also aborts an inference using reset, then attempts ignored busy
writes/start during the restarted inference. Results are held under
backpressure for eight controller checks before acceptance.

VIO inputs 0..7 expose status, errors, checked bits, results 0..3, and core
cycles. Output 0 restarts the fixture runner. Expected completed status is
`adcd03f9`; packed results are `(class << 16) | score`. The host verifies that
restart clears the query counter, then checks status and all results after
each of five reset/load/infer batches (20 inferences per configuration).

## Boundaries

This test uses ROM fixture loading, with JTAG restart/readback. It does not
implement a general host model-transfer interface, AXI overlay, EEG input,
trained model, or application frontend. The recorded 82.07/82.23 us values
divide observed core cycle counts by the requested MMCM clock rate; no
external frequency measurement or host-inclusive latency measurement is
claimed. ROMs, VIO and debug logic add resources beyond the classifier core.

The full test designs have zero DRC errors; retained warnings concern vendor
debug-hub logic and absent PS7 in this PL-only design. Warnings are not
suppressed. A one-bit packed ROM declaration is required for Vivado 2025.2
to retain the golden reference; the build guard and post-route audit verify
that the initialized golden-query BRAM exists.
