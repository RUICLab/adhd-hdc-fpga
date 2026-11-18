`timescale 1ns/1ps
// Standalone, deterministic MCU reference: RV32IMC CPU + registered SRAM bus.
// Clock period is a MODEL configuration, not a measured ESP32 frequency.
module tb_mcu;
    reg clk=0;always #5 clk=~clk;
    reg resetn=0;
    wire trap,mem_valid,mem_instr;
    reg mem_ready=0;
    wire [31:0] mem_addr,mem_wdata;
    wire [3:0] mem_wstrb;
    reg [31:0] mem_rdata=0;
    wire [31:0] pcpi_insn,pcpi_rs1,pcpi_rs2;
    wire pcpi_valid;
    wire [31:0] eoi;
    wire trace_valid;wire [35:0] trace_data;
    picorv32 #(.ENABLE_COUNTERS(1),.ENABLE_COUNTERS64(1),
      .ENABLE_REGS_DUALPORT(1),.COMPRESSED_ISA(1),.BARREL_SHIFTER(1),
      .ENABLE_FAST_MUL(1),.ENABLE_DIV(1),.ENABLE_IRQ(0),
      .PROGADDR_RESET(0),.STACKADDR(32'h0007fff0)) cpu(
      .clk(clk),.resetn(resetn),.trap(trap),.mem_valid(mem_valid),.mem_instr(mem_instr),
      .mem_ready(mem_ready),.mem_addr(mem_addr),.mem_wdata(mem_wdata),.mem_wstrb(mem_wstrb),
      .mem_rdata(mem_rdata),.pcpi_valid(pcpi_valid),.pcpi_insn(pcpi_insn),
      .pcpi_rs1(pcpi_rs1),.pcpi_rs2(pcpi_rs2),.pcpi_wr(1'b0),.pcpi_rd(32'b0),
      .pcpi_wait(1'b0),.pcpi_ready(1'b0),.irq(32'b0),.eoi(eoi),
      .trace_valid(trace_valid),.trace_data(trace_data));
    reg [31:0] memory [0:131071];
    reg [31:0] report [0:15];
    reg [63:0] total_cycles=0;
    integer results=0,verified=0;
    initial begin
        $readmemh("firmware.hex",memory);
        repeat(10)@(negedge clk);resetn=1;
    end
    always @(posedge clk)begin
        if(resetn)total_cycles<=total_cycles+1;
        mem_ready<=0;
        if(resetn && mem_valid && !mem_ready)begin
            mem_ready<=1;
            if(mem_addr<32'h00080000)begin
                mem_rdata<=memory[mem_addr>>2];
                for(integer b=0;b<4;b=b+1)
                    if(mem_wstrb[b])memory[mem_addr>>2][8*b+:8]<=mem_wdata[8*b+:8];
            end else if(mem_addr>=32'h10000000 && mem_addr<32'h10000040 && |mem_wstrb)begin
                report[(mem_addr-32'h10000000)>>2]<=mem_wdata;
                if(mem_addr==32'h10000020)begin
                    if(mem_wdata==1)begin
                        verified=verified+1;
                        $display("MCU_VERIFY PASS K=%0d count=%0d total_cycles=%0d",report[0],verified,total_cycles);
                    end else if(mem_wdata==2)begin
                        results=results+1;
                        $display("MCU_RESULT K=%0d raw_cycles=%0d overhead=%0d cycles=%0d instructions=%0d winner=%0d score=%0d",
                          report[0],report[1],report[2],report[1]-report[2],report[3],report[4],report[5]);
                    end else $fatal(1,"Unknown report command");
                end
                if(mem_addr==32'h1000003c)begin
                    if(mem_wdata!=32'h600d600d)$fatal(1,"MCU firmware check failed code=%h",mem_wdata);
                    if(results!=2 || verified!=4)$fatal(1,"Missing MCU results");
                    $display("PASS MCU RTL: K=10/26; tie/random golden query bits, all scores and winners; query-free timing checks");
                    $finish;
                end
            end else $fatal(1,"Out-of-range MCU access %h",mem_addr);
        end
        if(resetn && trap)$fatal(1,"MCU trap at cycle %0d",total_cycles);
        if(total_cycles>200000000)$fatal(1,"MCU timeout");
        if(resetn && total_cycles%5000000==0)$display("MCU_PROGRESS cycles=%0d",total_cycles);
    end
endmodule
