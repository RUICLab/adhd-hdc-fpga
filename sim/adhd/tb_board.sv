`timescale 1ns/1ps
module tb_board;
    parameter integer CLASSES=10;
    reg clk=0;always #5 clk=~clk;
    reg resetn=0;
    wire [31:0] status,errors,checked,result0,result1,result2,result3,core_cycles;
    adhd_board_test #(.CLASSES(CLASSES)) dut(.*);
    initial begin
        repeat(8) @(negedge clk);resetn=1;
        repeat(2) begin
            wait(status[3]);@(negedge clk);
            if(errors!==0 || checked!==32768 || status[7:4]!==4'hf ||
               core_cycles!==8192+5+CLASSES)
                $fatal(1,"Board controller failed status=%h errors=%d checked=%d cycles=%d",
                    status,errors,checked,core_cycles);
            $display("BOARD CONTROLLER PASS K=%0d status=%h checked=%0d cycles=%0d results=%h,%h,%h,%h",
                CLASSES,status,checked,core_cycles,result0,result1,result2,result3);
            resetn=0;repeat(8) @(negedge clk);resetn=1;
        end
        $finish;
    end
    initial begin #5000000;$fatal(1,"Board controller timeout");end
endmodule
