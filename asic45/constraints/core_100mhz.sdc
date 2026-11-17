# Nangate typical: 1.1 V, 25 C; no physical clock tree or routed parasitics.
if {![info exists CORE_PERIOD_NS]} {set CORE_PERIOD_NS 10.000}
create_clock -name core_clk -period $CORE_PERIOD_NS [get_ports clk]
set_clock_uncertainty 0.100 [get_clocks core_clk]
set_clock_transition 0.050 [get_clocks core_clk]
set_input_delay -max 1.000 -clock core_clk [remove_from_collection [all_inputs] [get_ports clk]]
set_input_delay -min 0.000 -clock core_clk [remove_from_collection [all_inputs] [get_ports clk]]
set_input_transition 0.050 [remove_from_collection [all_inputs] [get_ports clk]]
set_output_delay -max 1.000 -clock core_clk [all_outputs]
set_output_delay -min 0.000 -clock core_clk [all_outputs]
set_load 2.000 [all_outputs]
set_wire_load_mode top
set_wire_load_model -name 5K_hvratio_1_1 -library NangateOpenCellLibrary [current_design]
