# Volatile JTAG configuration only. Does not write QSPI/SD/boot flash or PS.
set root [file normalize [file join [file dirname [info script]] ..]]
set k [lindex $argv 0]
if {$k ni {10 26}} {error "Use -tclargs 10 or 26"}
set out [file join $root build adhd-board-k$k]
set fp [open [file join $out board_expected.hex] r]
set expected [regexp -all -inline {\S+} [read $fp]]
close $fp
open_hw_manager
connect_hw_server -allow_non_jtag
set target_pattern [lindex $argv 1]
if {$target_pattern eq ""} {set target_pattern *}
set targets [get_hw_targets $target_pattern]
if {[llength $targets]!=1} {error "Expected exactly one JTAG target; specify a target path/glob as the second Tcl argument. Got: $targets"}
current_hw_target [lindex $targets 0]
open_hw_target
set devices [get_hw_devices -filter {PART == xc7z020}]
if {[llength $devices]!=1} {error "Expected exactly one xc7z020; got $devices"}
set dev [lindex $devices 0]
current_hw_device $dev
set_property PROGRAM.FILE [file join $out board.bit] $dev
set_property PROBES.FILE [file join $out board.ltx] $dev
program_hw_devices $dev
refresh_hw_device $dev
set vios [get_hw_vios -of_objects $dev]
if {[llength $vios]!=1} {error "Expected one test VIO; got $vios"}
set vio [lindex $vios 0]
puts "BOARD_DEVICE=$dev TARGET=[current_hw_target] CLASSES=$k"
puts "BOARD_PROBES=[get_hw_probes -of_objects $vio]"
proc input_value {vio n} {
    set name [lindex {status errors checked result0 result1 result2 result3 core_cycles} $n]
    set probe [get_hw_probes -of_objects $vio -filter "NAME =~ *$name*"]
    if {[llength $probe]!=1} {error "Missing input probe $n"}
    return [expr "0x[get_property INPUT_VALUE $probe]"]
}
set restart [get_hw_probes -of_objects $vio -filter {NAME =~ *restart*}]
if {[llength $restart]!=1} {error "Missing restart probe"}
set fp [open [file join $out hardware_results.txt] w]
puts $fp "Vivado=[version -short] classes=$k device=$dev target=[current_hw_target]"
for {set run 0} {$run<5} {incr run} {
    set_property OUTPUT_VALUE 1 $restart
    commit_hw_vio $vio
    after 10
    refresh_hw_vio $vio
    if {[input_value $vio 2]!=0} {error "Restart did not clear query counter"}
    set_property OUTPUT_VALUE 0 $restart
    commit_hw_vio $vio
    set complete 0
    for {set poll 0} {$poll<100} {incr poll} {
        after 10
        refresh_hw_vio $vio
        set status [input_value $vio 0]
        if {$status & 8} {set complete 1;break}
    }
    set errors [input_value $vio 1]
    set checked [input_value $vio 2]
    set cycles [input_value $vio 7]
    if {!$complete || $status!=0xadcd03f9 || $errors!=0 || $checked!=32768 || $cycles!=8192+5+$k} {
        error "Hardware failure complete=$complete status=[format %08x $status] errors=$errors checked=$checked cycles=$cycles"
    }
    set results {}
    for {set i 0} {$i<4} {incr i} {
        set value [input_value $vio [expr {3+$i}]]
        if {$value != [expr "0x[lindex $expected $i]"]} {error "Hardware result mismatch case=$i value=$value"}
        lappend results [format %08x $value]
    }
    set line "BOARD PASS run=$run K=$k status=[format %08x $status] errors=$errors checked=$checked cycles=$cycles results=$results"
    puts $line
    puts $fp $line
    flush $fp
}
puts $fp "ADHD HARDWARE PASS: 5 reset/load/infer batches, 20 inferences, 163840 query-bit comparisons"
close $fp
puts "ADHD HARDWARE PASS K=$k"
close_hw_target
disconnect_hw_server
close_hw_manager
exit
