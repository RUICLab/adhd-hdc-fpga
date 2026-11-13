# Reuse routed core with RTL simulation switching. These are FPGA tool estimates.
set root [file normalize [file join [file dirname [info script]] ..]]
set k [lindex $argv 0]
if {$k ni {10 26}} {error "Use -tclargs 10 or 26"}
set out [file join $root build adhd-k$k]
open_checkpoint [file join $out adhd_route.dcp]
write_verilog -force -mode funcsim [file join $out adhd_funcsim.v]
set mode [lindex $argv 1]
if {$mode eq "export"} {exit}
if {$mode eq "gate"} {
    set simdir adhd-gate-k$k-d8192
    set rpt power_gate_saif.rpt
} else {
    set simdir adhd-sim-k$k-d8192
    set rpt power_saif.rpt
}
read_saif -strip_path tb_config/test/dut -file [file join $root build $simdir inference.saif]
report_power -file [file join $out $rpt]
