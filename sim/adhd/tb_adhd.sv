`timescale 1ns/1ps
module tb_adhd;
    parameter integer DIM_BITS=13,CLASSES=10,CAPTURE=0;
    localparam integer D=1<<DIM_BITS;
    reg clk=0; always #5 clk=~clk;
    reg resetn=0,model_we=0,feature_we=0,start=0,result_ready=0;
    reg [DIM_BITS-1:0] model_addr=0;
    reg [31:0] model_data=0;
    reg [7:0] feature_addr=0;
    reg [1:0] feature_data=0;
    wire ready,busy,result_valid,query_valid,query_bit;
    wire [DIM_BITS-1:0] query_addr;
    wire [4:0] result_class;
    wire [DIM_BITS:0] result_score;
    wire [31:0] cycles;
`ifdef ADHD_NETLIST
    adhd_hdc dut(.*);
`else
    adhd_hdc #(.DIM_BITS(DIM_BITS),.CLASSES(CLASSES)) dut(.*);
`endif
    reg [31:0] words [0:D-1];
    reg [1:0] features [0:195];
    reg queries [0:D-1];
    reg [DIM_BITS:0] expected_scores [0:CLASSES-1];
    integer qcount=0,errors=0,expected_class,best,case_id;
    reg checking=0;
    always @(negedge clk) if(checking && query_valid) begin
        if(query_addr !== (qcount^(qcount>>1))) $fatal(1,"Gray address mismatch %d",qcount);
        if(query_bit !== queries[query_addr]) $fatal(1,"Query mismatch case=%d j=%d",case_id,query_addr);
        qcount=qcount+1;
    end
    initial begin
        repeat(25) @(negedge clk);resetn=1;
        for(case_id=0;case_id<4;case_id=case_id+1) begin
            $readmemh($sformatf("model%0d.hex",case_id),words);
            $readmemh($sformatf("features%0d.hex",case_id),features);
            $readmemh($sformatf("query%0d.hex",case_id),queries);
            $readmemh($sformatf("scores%0d.hex",case_id),expected_scores);
            for(integer j=0;j<D;j=j+1) begin
                @(negedge clk);model_we=1;model_addr=j;model_data=words[j];
            end
            @(negedge clk);model_we=0;
            for(integer i=0;i<196;i=i+1) begin
                @(negedge clk);feature_we=1;feature_addr=i;feature_data=features[i];
            end
            @(negedge clk);feature_we=0;
            // Abort an in-flight vector and restart. Model/feature RAM survives.
            if(case_id==0) begin
                start=1;@(negedge clk);start=0;
                repeat(17) @(negedge clk);
                resetn=0;@(negedge clk);resetn=1;
            end
            if(CAPTURE && case_id==2) $stop;
            qcount=0;checking=1;start=1;
            @(negedge clk);start=0;
            // Busy writes and another start must not corrupt the active query.
            repeat(10) @(negedge clk);
            if(case_id==0) begin
            model_we=1;feature_we=1;start=1;model_data=0;feature_data=0;
            @(negedge clk);model_we=0;feature_we=0;start=0;
            end
            wait(result_valid);@(negedge clk);checking=0;
            if(CAPTURE && case_id==2) $stop;
            if(qcount!=D) $fatal(1,"Query count %d",qcount);
            best=0;expected_class=0;
            for(integer k=0;k<CLASSES;k=k+1) begin
`ifndef ADHD_NETLIST
                if(dut.scores[k] !== expected_scores[k]) $fatal(1,"Score mismatch class=%d",k);
`endif
                if(expected_scores[k]>best) begin best=expected_scores[k];expected_class=k;end
            end
            if(result_class!==expected_class || result_score!==best)
                $fatal(1,"Winner mismatch got=%d expected=%d",result_class,expected_class);
            // Pipeline drain = five cycles, serial class selection = CLASSES.
            if(cycles!=D+5+CLASSES) $fatal(1,"Cycle count %d",cycles);
            repeat(7) begin
                @(negedge clk);
                if(!result_valid || result_class!==expected_class || result_score!==best)
                    $fatal(1,"Result not stable under backpressure");
            end
            $display("CASE %0d PASS K=%0d D=%0d cycles=%0d winner=%0d",case_id,CLASSES,D,cycles,result_class);
            result_ready=1;@(negedge clk);result_ready=0;
        end
        $display("ADHD PASS: all query bits, class scores, winners, reset/restart, busy guards, output backpressure");
        $finish;
    end
    initial begin #20000000; $fatal(1,"Timeout"); end
endmodule
