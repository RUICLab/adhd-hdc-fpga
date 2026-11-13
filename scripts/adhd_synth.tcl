# Core-only OOC characterization, NOT a deployed PYNQ overlay.
set root [file normalize [file join [file dirname [info script]] ..]]
set classes [lindex $argv 0]
if {$classes ni {10 26}} {error "Use -tclargs 10 or 26"}
set out [file join $root build adhd-k$classes]
file mkdir $out
cd $out
create_project -in_memory -part xc7z020clg400-1
set_param general.maxThreads 4
read_verilog -sv [file join $root hw adhd adhd_hdc.sv]
synth_design -top adhd_hdc -part xc7z020clg400-1 -mode out_of_context -generic CLASSES=$classes
create_clock -name core_clk -period 10.000 [get_ports clk]
set_clock_uncertainty 0.200 [get_clocks core_clk]
report_utilization -file utilization_synth.rpt
opt_design
place_design
phys_opt_design
route_design
report_utilization -file utilization_route.rpt
report_timing_summary -report_unconstrained -file timing_route.rpt
report_drc -file drc_route.rpt
report_power -file power_vectorless.rpt
write_checkpoint -force adhd_route.dcp
write_verilog -force -mode funcsim adhd_funcsim.v
set fp [open metrics.txt w]
puts $fp "classes=$classes"
puts $fp "part=xc7z020clg400-1"
puts $fp "period_ns=10.0"
puts $fp "setup_slack_ns=[get_property SLACK [get_timing_paths -max_paths 1]]"
puts $fp "hold_slack_ns=[get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]"
puts $fp "cycles=[expr {8192+5+$classes}]"
close $fp
