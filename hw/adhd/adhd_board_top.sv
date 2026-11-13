`timescale 1ns/1ps
module adhd_board_top #(parameter integer CLASSES=10)(input wire sysclk);
    wire clk,locked,restart;
    reg [7:0] powerup=0;
    always @(posedge clk) if(!locked) powerup<=0;
        else if(!(&powerup)) powerup<=powerup+1;
    wire resetn=(&powerup) && !restart && locked;
    wire [31:0] status,errors,checked,result0,result1,result2,result3,core_cycles;
    board_clk clocks(.clk_in1(sysclk),.clk_out1(clk),.locked(locked));
    adhd_board_test #(.CLASSES(CLASSES)) test(.*);
    board_vio monitor(.clk(clk),.probe_out0(restart),
        .probe_in0(status),.probe_in1(errors),.probe_in2(checked),
        .probe_in3(result0),.probe_in4(result1),.probe_in5(result2),
        .probe_in6(result3),.probe_in7(core_cycles));
endmodule
