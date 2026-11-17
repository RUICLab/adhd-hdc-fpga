`timescale 1ns/1ps
// Binary ADHD backend. Single clock; one dimension issued per cycle.
// Memory word j: bits [3:0] = L_0..L_3[j]; bits [4+k] = P_k[j].
// Writes allowed only while idle. Load ALL model words/features before start.
// No early exit: deterministic full-D timing. Lowest class index wins ties.
module adhd_hdc #(
    parameter integer DIM_BITS=13,
    parameter integer FEATURES=196,
    parameter integer CLASSES=10,
    parameter integer STRIDE=1597,
    parameter integer THRESHOLD=96
) (
    input wire clk, input wire resetn,
    input wire model_we, input wire [DIM_BITS-1:0] model_addr,
    input wire [31:0] model_data,
    input wire feature_we, input wire [7:0] feature_addr,
    input wire [1:0] feature_data,
    input wire start, output wire ready, output wire busy,
    output wire result_valid, input wire result_ready,
    output reg [4:0] result_class,
    output reg [DIM_BITS:0] result_score,
    output reg [31:0] cycles,
    output wire query_valid, output wire [DIM_BITS-1:0] query_addr,
    output wire query_bit
);
    localparam integer D=1<<DIM_BITS;
    localparam [2:0] IDLE=0, RUN=1, DRAIN=2, SCAN=3, OUT=4;
    reg [2:0] state;
    reg [1:0] features [0:FEATURES-1];
    // ASIC array storage is a black-box SRAM; word0 remains the original read register.
    reg [DIM_BITS-1:0] t;
    reg [FEATURES-1:0] hstate, h0;
    reg [CLASSES+3:0] word0;
    reg [2:0] sum1 [0:63];
    reg [4:0] sum2 [0:15];
    reg [6:0] sum3 [0:3];
    reg q4;
    reg [4:0] valid_pipe, last_pipe;
    reg [DIM_BITS-1:0] addr_pipe [0:4];
    reg [CLASSES-1:0] proto1,proto2,proto3,proto4;
    reg [DIM_BITS:0] scores [0:CLASSES-1];
    reg [4:0] scan_index;
    reg [DIM_BITS:0] best_score;
    reg [4:0] best_class;
    wire [DIM_BITS-1:0] j=t^(t>>1);
    wire [DIM_BITS-1:0] next_t=t+1'b1;
    reg [DIM_BITS-1:0] flip_index;
    integer b;
    reg found;
    always @* begin
        flip_index=0; found=0;
        for (integer x=0;x<DIM_BITS;x=x+1)
            if (!found && next_t[x]) begin flip_index=x; found=1; end
    end
    wire [FEATURES-1:0] next_mask;
    genvar g;
    generate for(g=0;g<FEATURES;g=g+1) begin: lanes
        localparam [DIM_BITS-1:0] ROW=STRIDE*(g+1);
        assign next_mask[g]=ROW[flip_index];
    end endgenerate
    wire [255:0] bound;
    generate for(g=0;g<256;g=g+1) begin: bind_bits
        if(g<FEATURES) assign bound[g]=h0[g]^word0[features[g]];
        else assign bound[g]=1'b0;
    end endgenerate
    wire [8:0] total={2'b0,sum3[0]}+{2'b0,sum3[1]}+
                     {2'b0,sum3[2]}+{2'b0,sum3[3]};
    assign ready=(state==IDLE);
    assign busy=(state!=IDLE);
    assign result_valid=(state==OUT);
    assign query_valid=valid_pipe[4];
    assign query_addr=addr_pipe[4];
    assign query_bit=q4;

    // SRAM extraction: same writes and synchronous read behavior, no extra cycle.
    wire sram_write=resetn && ready && !start && model_we;
    wire sram_read=resetn && state==RUN;
    wire [CLASSES+3:0] sram_q;
    adhd_sram_8192x30 model_sram(.CLK(clk),.CE(sram_write || sram_read),
        .WE(sram_write),.A(sram_read ? j : model_addr),
        .D(model_data[CLASSES+3:0]),.Q(sram_q));
    always @(posedge clk) begin
        if(sram_read) word0<=sram_q;
    end
    always @(posedge clk) begin
        if(!resetn) begin
            state<=IDLE; t<=0; hstate<=0; h0<=0;
            valid_pipe<=0;last_pipe<=0; cycles<=0;
            result_class<=0;result_score<=0;
            best_score<=0;best_class<=0;scan_index<=0;
            for(integer k=0;k<CLASSES;k=k+1) scores[k]<=0;
        end else begin
            if(ready && !start && feature_we && feature_addr<FEATURES)
                features[feature_addr]<=feature_data;
            valid_pipe<={valid_pipe[3:0],state==RUN};
            last_pipe<={last_pipe[3:0],(state==RUN && t==D-1)};
            for(integer p=1;p<5;p=p+1) addr_pipe[p]<=addr_pipe[p-1];
            if(state==RUN) begin
                h0<=hstate;addr_pipe[0]<=j;
                hstate<=hstate^next_mask;
                t<=t+1'b1;
                if(t==D-1) state<=DRAIN;
            end
            if(valid_pipe[0]) begin
                for(integer n=0;n<64;n=n+1)
                    sum1[n]<={2'b0,bound[4*n]}+{2'b0,bound[4*n+1]}+
                             {2'b0,bound[4*n+2]}+{2'b0,bound[4*n+3]};
                proto1<=word0[CLASSES+3:4];
            end
            if(valid_pipe[1]) begin
                for(integer n=0;n<16;n=n+1)
                    sum2[n]<={2'b0,sum1[4*n]}+{2'b0,sum1[4*n+1]}+
                             {2'b0,sum1[4*n+2]}+{2'b0,sum1[4*n+3]};
                proto2<=proto1;
            end
            if(valid_pipe[2]) begin
                for(integer n=0;n<4;n=n+1)
                    sum3[n]<={2'b0,sum2[4*n]}+{2'b0,sum2[4*n+1]}+
                             {2'b0,sum2[4*n+2]}+{2'b0,sum2[4*n+3]};
                proto3<=proto2;
            end
            if(valid_pipe[3]) begin
                q4<=(total>=THRESHOLD);proto4<=proto3;
            end
            if(valid_pipe[4]) begin
                for(integer k=0;k<CLASSES;k=k+1)
                    scores[k]<=scores[k]+(q4==proto4[k]);
                if(last_pipe[4]) begin
                    state<=SCAN;scan_index<=0;best_score<=0;best_class<=0;
                end
            end
            if(state==RUN || state==DRAIN || state==SCAN) cycles<=cycles+1'b1;
            if(state==IDLE && start) begin
                state<=RUN;t<=0;hstate<=0;valid_pipe<=0;last_pipe<=0;
                cycles<=0;
                for(integer k=0;k<CLASSES;k=k+1) scores[k]<=0;
            end
            if(state==SCAN) begin
                if(scores[scan_index]>best_score) begin
                    best_score<=scores[scan_index];best_class<=scan_index;
                end
                if(scan_index==CLASSES-1) begin
                    result_class<=(scores[scan_index]>best_score)?scan_index:best_class;
                    result_score<=(scores[scan_index]>best_score)?scores[scan_index]:best_score;
                    state<=OUT;
                end else scan_index<=scan_index+1'b1;
            end
            if(state==OUT && result_ready) state<=IDLE;
        end
    end
endmodule
