#!/usr/bin/env bash
set -euo pipefail
k=${1:?Pass class count}
root=$(pwd)
out="$root/build/k$k"
mkdir -p "$out/sim"
cd "$out/fixtures"
vcs -full64 -sverilog -timescale=1ns/1ps +nospecify +notimingcheck \
  +define+ADHD_NETLIST+CLASSES="$k" \
  "$root/vendor/NangateOpenCellLibrary.v" "$root/rtl/sram_models.sv" \
  "$out/core_mapped.v" "$root/rtl/tb_adhd_original.sv" "$root/rtl/tb_gate_config.sv" \
  -top tb_config -Mdir="$out/sim/csrc_check" -o "$out/sim/check" \
  > "$out/sim/compile_check.log" 2>&1
"$out/sim/check" -no_save > "$out/sim/check.log" 2>&1
grep 'ADHD PASS' "$out/sim/check.log"
vcs -full64 -sverilog -timescale=1ns/1ps +nospecify +notimingcheck \
  +define+CLASSES="$k" \
  "$root/vendor/NangateOpenCellLibrary.v" "$root/rtl/sram_models.sv" \
  "$out/core_mapped.v" "$root/rtl/tb_activity.sv" \
  -top tb_activity -Mdir="$out/sim/csrc_activity" -o "$out/sim/activity" \
  > "$out/sim/compile_activity.log" 2>&1
"$out/sim/activity" -no_save > "$out/sim/activity.log" 2>&1
grep 'ASIC ACTIVITY PASS' "$out/sim/activity.log"
mv inference.vcd "$out/sim/inference.vcd"
