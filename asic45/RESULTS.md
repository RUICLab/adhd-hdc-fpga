# 45-nm HDC backend: final audited estimates

| K | MHz | Latency us | Std dynamic nJ | Std leakage nJ | SRAM total nJ | Total nJ |
|---|---|---|---|---|---|---|
| 10 | 100.00 | 82.070 | 152.559 | 22.395 | 75.182 | 250.136 |
| 10 | 335.13 | 24.489 | 152.559 | 6.683 | 75.155 | 234.396 |
| 26 | 100.00 | 82.230 | 172.931 | 27.426 | 96.624 | 296.981 |
| 26 | 299.44 | 27.461 | 172.931 | 9.159 | 96.573 | 278.663 |

Standard-cell dynamic includes the modeled local net switching at the SRAM output interface. SRAM total is exactly 8192 reads * CACTI read energy + CACTI leakage * inference time.

| K | Std cells | FFs | Std area um2 | SRAM mm2 | Total footprint mm2 | Worst data arrival ns | Setup slack ns | Hold slack ns |
|---|---|---|---|---|---|---|---|---|
| 10 | 7244 | 1400 | 13193.068 | 0.0508127 | 0.0640058 | 2.858316 | 7.017052 | 0.000846 |
| 26 | 8639 | 1704 | 15873.018 | 0.1060300 | 0.1219030 | 3.213913 | 6.661455 | 0.000862 |

Worst data arrival includes the fixed 1-ns external input delay when the critical startpoint is an input port. Full path reports identify every cell/net. Register-only timing is recorded separately.

## K=10: 100-MHz power and SRAM
Internal 1.422132 mW; switching 0.436756 mW; standard-cell leakage 0.272880 mW.
SRAM read 0.00917274 nJ/access; total leakage 0.476711 uW (subthreshold + gate); area 0.0508127 mm2.

| Block | Cells | Area um2 | Internal mW | Switching mW | Leakage mW | Dynamic nJ/inference |
|---|---|---|---|---|---|---|
| lanes | 4294 | 7341.334 | 0.437839 | 0.298021 | 0.155781 | 60.392 |
| classes | 1081 | 2009.630 | 0.047925 | 0.021810 | 0.041560 | 5.723 |
| control | 401 | 880.992 | 0.011686 | 0.005572 | 0.016952 | 1.416 |
| popcount | 1468 | 2961.112 | 0.193024 | 0.110506 | 0.058588 | 24.911 |
| register_clock_pins | 0 | 0.000 | 0.731658 | 0.000000 | 0.000000 | 60.047 |
| sram_interface_nets | 0 | 0.000 | 0.000000 | 0.000847 | 0.000000 | 0.069 |

## K=26: 100-MHz power and SRAM
Internal 1.625220 mW; switching 0.477797 mW; standard-cell leakage 0.333528 mW.
SRAM read 0.01178550 nJ/access; total leakage 0.942371 uW (subthreshold + gate); area 0.1060300 mm2.

| Block | Cells | Area um2 | Internal mW | Switching mW | Leakage mW | Dynamic nJ/inference |
|---|---|---|---|---|---|---|
| control | 454 | 913.178 | 0.011733 | 0.005595 | 0.017646 | 1.425 |
| classes | 2358 | 4585.308 | 0.121965 | 0.055430 | 0.094098 | 14.587 |
| popcount | 1482 | 2972.284 | 0.191449 | 0.109113 | 0.058896 | 24.715 |
| lanes | 4345 | 7402.248 | 0.441818 | 0.305847 | 0.162888 | 61.481 |
| register_clock_pins | 0 | 0.000 | 0.858256 | 0.000000 | 0.000000 | 70.574 |
| sram_interface_nets | 0 | 0.000 | 0.000000 | 0.001813 | 0.000000 | 0.149 |

## Assumptions and limits
- **standard_cells:** Nangate45 typical, 1.1 V, 25 C
- **sram:** 45 nm ITRS-LSTP cell/periphery; 1.1 V; 300 K; single bank/one RW port; byte-rounded 16/32-bit words; no ECC/tags/gating; ED^2 optimization
- **activity:** zero-delay mapped-netlist simulation, exact original board fixture case 2; every query/winner/score/cycle checked; input loading excluded
- **clock:** ideal clock distribution: no CTS buffers/wire parasitics. Library-modeled FF clock-pin internal power IS included and separately itemized.
- **interconnect:** Nangate 5K_hvratio_1_1 top wire-load; no physical placement/routing/SPEF
- **io:** 1 ns max / 0 min input and output delays, 2 fF output loads, 50 ps input/clock transition
- **uncertainty:** 100 ps setup and hold; hold-fix mapping enabled
- **sram_interface:** CACTI read delay; assumed 2 fF input capacitance, 50 ps output slew, 50 ps write setup, zero hold; integration abstract, not characterized IP
- **fmax:** all-path setup bound with stated I/O/uncertainty and modeled SRAM; 1 ps positive margin; rechecked; not post-layout signoff
- **fmax_energy:** fixed-workload dynamic energy; dynamic power scales linearly with frequency; leakage fixed at same voltage/temperature; no high-frequency timing-aware activity rerun
- **excluded:** CTS distribution, routing extraction/glitches, scan/tie/filler/power-grid/margin area, model/feature transfer and writes, host, sensor and digital frontend

Block attribution is an approximate disjoint capture-register cone partition. Shared combinational logic is assigned in lanes/popcount/classes/control order. Register clock-pin internal power is moved out of those blocks into its own row; no clock power is counted twice. Clock-distribution energy/area is not estimated.

All final Design Compiler and PrimeTime logs are error-free. The mapped array remains one SRAM black box per K. Final mapped netlist checks and the activity case pass. This is a pre-layout estimate with an analytical SRAM, not silicon measurement or a signoff Fmax.

## Optional digital frontend baseline
Not run in this backend study. No regional/convolutional frontend area, energy or latency is inferred from CPU timings or from the backend results.

