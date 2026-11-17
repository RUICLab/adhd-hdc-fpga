`timescale 1ns/1ps
module adhd_sram_8192x14(input CLK,CE,WE,input [12:0] A,input [13:0] D,output [13:0] Q);
    reg [13:0] mem[0:8191];
    always @(posedge CLK) if(CE && WE) mem[A]<=D;
    assign Q=(CE && !WE) ? mem[A] : 14'b0;
endmodule
module adhd_sram_8192x30(input CLK,CE,WE,input [12:0] A,input [29:0] D,output [29:0] Q);
    reg [29:0] mem[0:8191];
    always @(posedge CLK) if(CE && WE) mem[A]<=D;
    assign Q=(CE && !WE) ? mem[A] : 30'b0;
endmodule
