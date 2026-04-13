`timescale 1ns/1ps
`default_nettype none

module spi_master_tb_wrapper (
    input  logic        clk,
    input  logic        rst,
    input  logic [31:0] data,
    input  logic        start,
    output logic        busy,
    output logic        done,
    output logic        sclk,
    output logic        sdata,
    output logic        le
);

    spi_master #(
        .CLK_DIV  (2),   // fast for simulation: SCLK = clk/4
        .LE_CYCLES(2)
    ) dut (
        .clk  (clk),
        .rst  (rst),
        .data (data),
        .start(start),
        .busy (busy),
        .done (done),
        .sclk (sclk),
        .sdata(sdata),
        .le   (le)
    );

    initial begin
        $dumpfile("sim_build_spi/dump.vcd");
        $dumpvars(0, spi_master_tb_wrapper);
    end

endmodule
