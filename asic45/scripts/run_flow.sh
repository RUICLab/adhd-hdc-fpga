#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p reports vendor tools build/k10/sim build/k26/sim
python3 scripts/bootstrap.py
make -C tools/cacti -j4 opt >reports/cacti_build.log 2>&1
for k in 10 26; do
  (cd tools/cacti; ./cacti -infile "../../constraints/sram_k$k.cfg") >"reports/cacti_k$k.txt" 2>&1
done
python3 scripts/prepare.py
lc_shell -f scripts/compile_library.tcl >reports/library_compile_lc.log 2>&1 </dev/null
lc_shell -f scripts/compile_srams.tcl >reports/sram_library_compile.log 2>&1 </dev/null
for k in 10 26; do
  CLASSES=$k dc_shell -f scripts/synth_dc.tcl >"reports/synth_k$k.log" 2>&1 </dev/null
  if grep -q '^Error:' "reports/synth_k$k.log"; then exit 1; fi
  bash scripts/simulate.sh "$k" >"reports/gls_k$k.log" 2>&1
  python3 scripts/rebase_vcd.py "$k" >"build/k$k/sim/rebase.log"
  CLASSES=$k pt_shell -f scripts/analyze_pt.tcl >"reports/pt_k$k.log" 2>&1 </dev/null
  if grep -q '^Error:' "reports/pt_k$k.log"; then exit 1; fi
  grep -q "ASIC PT ANALYSIS COMPLETE K=$k" "reports/pt_k$k.log"
  gzip -c "build/k$k/sim/activity.vcd" >"build/k$k/sim/activity.vcd.gz"
done
python3 scripts/summarize.py
