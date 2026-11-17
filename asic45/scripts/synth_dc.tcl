set k $env(CLASSES)
if {$k ni {10 26}} {error "CLASSES must be 10 or 26"}
set out build/k$k
file mkdir $out
define_design_lib WORK -path $out/WORK
set_app_var search_path [concat $search_path [list . vendor]]
set_app_var target_library [list vendor/NangateOpenCellLibrary_typical.db]
set_app_var link_library [concat [list *] $target_library [list vendor/sram_k${k}.db]]
set_app_var auto_wire_load_selection false
analyze -format sverilog $out/adhd_hdc_asic.sv
elaborate adhd_hdc -parameters "DIM_BITS=13,CLASSES=$k"
rename_design [get_object_name [current_design]] adhd_hdc
current_design adhd_hdc
link
set_dont_touch [get_cells model_sram] true
set_operating_conditions typical -library NangateOpenCellLibrary
source constraints/core_100mhz.sdc
set_fix_hold [all_clocks]
set_fix_multiple_port_nets -all -buffer_constants
redirect $out/check_before.rpt {check_design}
compile -map_effort high -area_effort high
compile -incremental_mapping -only_hold_time
change_names -rules verilog -hierarchy
redirect $out/area.rpt {report_area -hierarchy}
redirect $out/references.rpt {report_reference -hierarchy}
redirect $out/timing_dc.rpt {report_timing -max_paths 10 -transition_time -capacitance -nets}
redirect $out/constraints.rpt {report_constraint -all_violators}
redirect $out/check_after.rpt {check_design}
write -format ddc -hierarchy -output $out/core.ddc
write -format verilog -hierarchy -output $out/core_mapped.v
write_sdc $out/core_mapped.sdc
set leaves [get_cells -hierarchical -filter "is_hierarchical == false"]
set macros [get_cells model_sram]
if {[sizeof_collection $macros]!=1} {error "SRAM macro missing"}
set std [remove_from_collection $leaves $macros]
set area 0.0
set mapped_count 0
set ff_count 0
set constant_pseudo_count 0
array set hist {}
foreach_in_collection cell $std {
    set ref [get_attribute $cell ref_name]
    if {$ref eq "**logic_0**" || $ref eq "**logic_1**"} {incr constant_pseudo_count; continue}
    set libcell [get_lib_cells NangateOpenCellLibrary/$ref]
    if {[sizeof_collection $libcell]!=1} {error "Unexpected unmapped/nonstandard cell $ref"}
    set area [expr {$area+[get_attribute $libcell area]}]
    incr mapped_count
    if {[string match DFF* $ref]} {incr ff_count}
    if {![info exists hist($ref)]} {set hist($ref) 0}
    incr hist($ref)
}
set fp [open $out/cell_metrics.txt w]
puts $fp "classes=$k"
puts $fp "standard_cell_count=$mapped_count"
puts $fp "standard_cell_area_um2=$area"
puts $fp "ff_count=$ff_count"
puts $fp "ideal_constant_pseudo_cells=$constant_pseudo_count"
puts $fp "sram_macro_count=[sizeof_collection $macros]"
puts $fp "sram_macro_ref=[get_attribute $macros ref_name]"
foreach ref [lsort [array names hist]] {puts $fp "cell:$ref=$hist($ref)"}
close $fp
exit
