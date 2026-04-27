`timescale 1ns/1ps
`default_nettype none

module freq_calc_tb_wrapper (
    input  logic        clk,
    input  logic        rst,
    input  logic [31:0] freq_khz,
    input  logic        start,
    output logic        done,
    output logic [31:0] r0, r1, r2, r3, r4, r5
);

    freq_calc #(
        .FREF_KHZ  (32'd25000),
        .FIXED_MOD (32'd1000),
        .R2_CFG    (32'h18004E42),
        .R3_CFG    (32'h008004B3),
        .R4_BASE   (32'h008FA03C),
        .R5_CFG    (32'h00580005)
    ) dut (
        .clk      (clk),
        .rst      (rst),
        .freq_khz (freq_khz),
        .start    (start),
        .done     (done),
        .r0       (r0),
        .r1       (r1),
        .r2       (r2),
        .r3       (r3),
        .r4       (r4),
        .r5       (r5)
    );

    initial begin
        $dumpfile("sim_build_spi/dump_freq_calc.vcd");
        $dumpvars(0, freq_calc_tb_wrapper);
    end

endmodule
