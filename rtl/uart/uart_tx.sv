`timescale 1ns/1ps

module uart_tx #(
    parameter CLK_FREQ = 100_000_000,
    parameter BAUD     = 115200
)(
    input  wire logic clk,
    input  wire logic rst,
    input  wire logic tx_start,
    input  wire logic [7:0] data_in,

    output logic tx,
    output logic tx_busy
);

    localparam integer CLKS_PER_BIT = CLK_FREQ / BAUD;

    typedef enum logic [1:0] {
        IDLE,
        START,
        DATA,
        STOP
    } state_t;

    state_t state = IDLE;

    logic [$clog2(CLKS_PER_BIT):0] clk_count = 0;
    logic [2:0] bit_index = 0;
    logic [7:0] tx_shift;

    always_ff @(posedge clk or posedge rst) begin
        if (rst) begin
            state     <= IDLE;
            tx        <= 1'b1;
            tx_busy   <= 0;
            clk_count <= 0;
            bit_index <= 0;
        end else begin
            case (state)

                IDLE: begin
                    tx        <= 1'b1;
                    tx_busy   <= 1'b0;
                    clk_count <= 0;
                    bit_index <= 0;

                    if (tx_start) begin
                        tx_shift <= data_in;
                        tx_busy  <= 1'b1;
                        state <= START;
                    end
                end

                START: begin
                    tx <= 1'b0;

                    if (clk_count == CLKS_PER_BIT-1) begin
                        clk_count <= 0;
                        state <= DATA;
                    end else begin
                        clk_count <= clk_count + 1;
                    end
                end

                DATA: begin
                    tx <= tx_shift[bit_index];

                    if (clk_count == CLKS_PER_BIT-1) begin
                        clk_count <= 0;

                        if (bit_index == 3'd7)
                            state <= STOP;
                        else
                            bit_index <= bit_index + 1;
                    end else begin
                        clk_count <= clk_count + 1;
                    end
                end

                STOP: begin
                    tx <= 1'b1;

                    if (clk_count == CLKS_PER_BIT-1) begin
                        state <= IDLE;
                        clk_count <= 0;
                    end else begin
                        clk_count <= clk_count + 1;
                    end
                end

            endcase
        end
    end

endmodule
`default_nettype wire
