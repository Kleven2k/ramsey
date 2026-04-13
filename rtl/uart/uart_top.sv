`timescale 1ns/1ps

module uart_top #(
    parameter CLK_FREQ = 100_000_000,
    parameter BAUD     = 115200
)(
    input  wire logic clk,
    input  wire logic rst,

    input  wire logic rx,
    output wire logic tx,

    output wire logic [7:0] rx_data,
    output wire logic       rx_valid,

    input  wire logic [7:0] tx_data,
    input  wire logic       tx_start,
    output wire logic       tx_busy
);

    uart_rx #(
        .CLK_FREQ(CLK_FREQ),
        .BAUD(BAUD)
    ) u_rx (
        .clk(clk),
        .rst(rst),
        .rx(rx),
        .data_out(rx_data),
        .data_valid(rx_valid)
    );

    uart_tx #(
        .CLK_FREQ(CLK_FREQ),
        .BAUD(BAUD)
    ) u_tx (
        .clk(clk),
        .rst(rst),
        .tx_start(tx_start),
        .data_in(tx_data),
        .tx(tx),
        .tx_busy(tx_busy)
    );

endmodule
`default_nettype wire
