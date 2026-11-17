`timescale 1ns/1ps
// Exactly board fixture case 2; recording excludes input loading and idle time.
module tb_activity;
    localparam integer D=8192,K=`CLASSES;
    reg clk=0;always #5 clk=~clk;
    reg resetn=0,model_we=0,feature_we=0,start=0,result_ready=0;
    reg [12:0] model_addr=0;
    reg [31:0] model_data=0;
    reg [7:0] feature_addr=0;
    reg [1:0] feature_data=0;
    wire ready,busy,result_valid,query_valid,query_bit;
    wire [12:0] query_addr;
    wire [4:0] result_class;
    wire [13:0] result_score;
    wire [31:0] cycles;
    adhd_hdc dut(.*);
    reg [31:0] words[0:D-1];
    reg [1:0] features[0:195];
    reg queries[0:D-1];
    reg [13:0] scores[0:K-1];
    integer count=0,read_count=0,best=0,winner=0;
    reg checking=0;
    real started;
    always @(negedge clk) if(checking && query_valid) begin
        if(query_addr!==(count^(count>>1)) || query_bit!==queries[query_addr])
            $fatal(1,"Activity query mismatch dimension=%d",count);
        count=count+1;
    end
    always @(posedge clk) if(checking && dut.model_sram.CE && !dut.model_sram.WE)
        read_count=read_count+1;
    initial begin
        $readmemh("model2.hex",words);$readmemh("features2.hex",features);
        $readmemh("query2.hex",queries);$readmemh("scores2.hex",scores);
        for(integer k=0;k<K;k=k+1)if(scores[k]>best)begin best=scores[k];winner=k;end
        repeat(25)@(negedge clk);resetn=1;
        for(integer j=0;j<D;j=j+1)begin
            @(negedge clk);model_we=1;model_addr=j;model_data=words[j];
        end
        @(negedge clk);model_we=0;
        for(integer i=0;i<196;i=i+1)begin
            @(negedge clk);feature_we=1;feature_addr=i;feature_data=features[i];
        end
        @(negedge clk);feature_we=0;start=1;
        @(posedge clk);#0.001;
        started=$realtime;checking=1;
        $dumpfile("inference.vcd");$dumpvars(0,dut);
        @(negedge clk);start=0;
        wait(result_valid);#0.001;
        $dumpoff;
        if(cycles!==D+5+K || count!=D || read_count!=D || result_class!==winner || result_score!==best)
            $fatal(1,"Activity result mismatch cycles=%d queries=%d reads=%d winner=%d score=%d",cycles,count,read_count,result_class,result_score);
        if($realtime-started<(D+5+K)*10.0-0.0005 || $realtime-started>(D+5+K)*10.0+0.0005)
            $fatal(1,"Activity window mismatch observed=%0.9f expected=%0.3f",$realtime-started,(D+5+K)*10.0);
        $display("ASIC ACTIVITY PASS K=%0d queries=%0d reads=%0d cycles=%0d winner=%0d score=%0d duration_ns=%0.3f",K,count,read_count,cycles,result_class,result_score,$realtime-started);
        $finish;
    end
    initial begin #2000000;$fatal(1,"Activity timeout");end
endmodule
