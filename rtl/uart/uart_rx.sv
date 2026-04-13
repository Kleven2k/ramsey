`timescale 1ns / 1ps

module uart_rx #(
    parameter int CLK_FREQ  = 100_000_000,
    parameter int BAUD = 115200
)(
    input  wire logic clk,
    input  wire logic rst,
    input  wire logic rx,

    output logic [7:0] data_out,
    output logic       data_valid
);

    localparam integer CLKS_PER_BIT = CLK_FREQ / BAUD;
    localparam integer HALF_BIT     = CLKS_PER_BIT / 2;

    typedef enum logic [2:0] {
        IDLE,
        START,
        DATA,
        STOP,
        CLEANUP
    } state_t;

    state_t state = IDLE;

    logic [$clog2(CLKS_PER_BIT):0] clk_count = 0;
    logic [2:0] bit_index = 0;
    logic [7:0] rx_shift = 0;

    // 2-Flip-Flop Synchronizer
    logic rx_sync_0, rx_sync_1;

    always_ff @(posedge clk) begin 
        rx_sync_0 <= rx;
        rx_sync_1 <= rx_sync_0;
    end

    // UART RX FSM
    always_ff @(posedge clk or posedge rst) begin 
        if (rst) begin 
            state       <= IDLE;
            clk_count   <= 0;
            bit_index   <= 0;
            data_valid  <= 0;
            data_out    <= 8'd0;
        end else begin 
            data_valid <= 0;

            case (state)

                IDLE: begin
                    clk_count <= 0;
                    bit_index <= 0;
                    if (rx_sync_1 == 1'b0) begin  // start bit detected
                        state     <= START;
                    end 
                end 

                START: begin
                    if (clk_count == HALF_BIT-1) begin
                        clk_count <= 0;
                        if (rx_sync_1 == 1'b0)
                            state     <= DATA;  // valid start bit
                        else  
                            state <= IDLE;      // false start
                    end else begin 
                        clk_count <= clk_count + 1;
                    end 
                end 

                DATA: begin
                    if (clk_count == CLKS_PER_BIT-1) begin
                        clk_count <= 0;
                        rx_shift[bit_index] <= rx_sync_1;

                        if (bit_index == 3'd7)
                            state <= STOP;
                        else
                            bit_index <= bit_index + 1;
                    end else begin 
                        clk_count <= clk_count + 1;
                    end 
                end

                STOP: begin
                    if (clk_count == CLKS_PER_BIT-1) begin
                        data_out   <= rx_shift;
                        data_valid <= 1'b1;
                        clk_count  <= 0;
                        state      <= CLEANUP;
                    end else begin
                        clk_count <= clk_count + 1;
                    end
                end

                CLEANUP: begin 
                    state <= IDLE;
                end 
            
            endcase 
        end 
    end 

endmodule
`default_nettype wire
