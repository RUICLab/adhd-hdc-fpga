# Build the fixture runner as a real PYNQ-Z2 bitstream (no PS/software needed).
set root [file normalize [file join [file dirname [info script]] ..]]
set k [lindex $argv 0]
if {$k ni {10 26}} {error "Use -tclargs 10 or 26"}
set out [file join $root build adhd-board-k$k]
file mkdir [file join $out ip]
cd $out
create_project -in_memory -part xc7z020clg400-1
set_param general.maxThreads 4
create_ip -name clk_wiz -vendor xilinx.com -library ip -module_name board_clk -dir [file join $out ip] -force
set_property -dict [list CONFIG.PRIM_IN_FREQ {125.000} CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {100.000} CONFIG.USE_RESET {false}] [get_ips board_clk]
create_ip -name vio -vendor xilinx.com -library ip -module_name board_vio -dir [file join $out ip] -force
set_property -dict [list CONFIG.C_NUM_PROBE_IN {8} CONFIG.C_NUM_PROBE_OUT {1} CONFIG.C_PROBE_OUT0_WIDTH {1} CONFIG.C_PROBE_OUT0_INIT_VAL {0x0}] [get_ips board_vio]
for {set i 0} {$i<8} {incr i} {set_property CONFIG.C_PROBE_IN${i}_WIDTH 32 [get_ips board_vio]}
generate_target all [get_ips]
synth_ip [get_ips]
read_verilog -sv [file join $root hw adhd adhd_hdc.sv]
read_verilog -sv [file join $root hw adhd adhd_board_test.sv]
read_verilog -sv [file join $root hw adhd adhd_board_top.sv]
read_xdc [file join $root hw adhd pynq_z2_board.xdc]
synth_design -top adhd_board_top -part xc7z020clg400-1 -generic CLASSES=$k
set query_rams [get_cells -hier -filter {NAME =~ *golden_q_reg* && REF_NAME =~ RAMB*}]
if {[llength $query_rams]==0} {error "Golden query ROM was not inferred as initialized BRAM"}
puts "BOARD_GOLDEN_QUERY_BRAM=$query_rams"
opt_design
place_design
phys_opt_design
route_design
report_utilization -file utilization_route.rpt
report_timing_summary -report_unconstrained -file timing_route.rpt
report_drc -file drc_route.rpt
set setup [get_property SLACK [get_timing_paths -max_paths 1]]
set hold [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
if {$setup<0 || $hold<0} {error "Board timing failed setup=$setup hold=$hold"}
write_checkpoint -force board_route.dcp
write_debug_probes -force board.ltx
write_bitstream -force board.bit
set fp [open build_metrics.txt w]
puts $fp "classes=$k\npart=xc7z020clg400-1\nclock_mhz=100\nsetup_slack_ns=$setup\nhold_slack_ns=$hold"
close $fp
exit
