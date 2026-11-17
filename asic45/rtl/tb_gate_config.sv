`timescale 1ns/1ps
module tb_config;
    tb_adhd #(.CLASSES(`CLASSES),.DIM_BITS(13),.CAPTURE(0)) test();
endmodule
