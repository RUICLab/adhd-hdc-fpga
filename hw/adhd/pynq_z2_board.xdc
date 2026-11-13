# PYNQ-Z2 PL reference clock, per TUL manual and Xilinx PYNQ-Z2 XDC.
# https://github.com/Xilinx/xup_fpga_vivado_flow/blob/main/source/pynq-z2/lab5/uart_led_pins_pynq.xdc
set_property -dict {PACKAGE_PIN H16 IOSTANDARD LVCMOS33} [get_ports sysclk]
create_clock -name sysclk -period 8.000 [get_ports sysclk]
set_clock_uncertainty 0.200 [get_clocks sysclk]
