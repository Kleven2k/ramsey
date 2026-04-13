`timescale 1ns/1ps
`default_nettype none

module adf4351_tb_wrapper (
    input  logic        clk,
    input  logic        rst,

    input  logic [31:0] r0, r1, r2, r3, r4, r5,
    input  logic        load,
    input  logic        lock_detect,
    output logic        spi_ready,
    output logic        busy,

    output logic        sclk,
    output logic        sdata,
    output logic        le
);

    adf4351_ctrl #(
        .DEBOUNCE_CYCLES(8),  // short for simulation
        .SPI_CLK_DIV    (2),  // fast SCLK: period = 4 system cycles
        .SPI_LE_CYCLES  (2)
    ) dut (
        .clk         (clk),
        .rst         (rst),
        .r0          (r0),
        .r1          (r1),
        .r2          (r2),
        .r3          (r3),
        .r4          (r4),
        .r5          (r5),
        .load        (load),
        .lock_detect (lock_detect),
        .spi_ready   (spi_ready),
        .busy        (busy),
        .sclk        (sclk),
        .sdata       (sdata),
        .le          (le)
    );

    initial begin
        $dumpfile("sim_build_spi/dump_adf4351.vcd");
        $dumpvars(0, adf4351_tb_wrapper);
    end

endmodule
