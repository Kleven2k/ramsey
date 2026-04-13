`timescale 1ns/1ps
`default_nettype none

module shot_accumulator_tb_wrapper #(
    parameter DEPTH = 16
) (
    input  logic        clk,
    input  logic        rst,

    input  logic        gate,
    input  logic        ref_gate,
    input  logic        sweep_point_done,
    input  logic        sweep_start,

    input  logic [31:0] sig_count,
    input  logic [31:0] ref_count,

    input  logic [3:0]  rd_addr,
    output logic [31:0] rd_sig,
    output logic [31:0] rd_ref,

    output logic [3:0]  freq_index
);

    shot_accumulator #(.DEPTH(DEPTH)) dut (
        .clk              (clk),
        .rst              (rst),
        .gate             (gate),
        .ref_gate         (ref_gate),
        .sweep_point_done (sweep_point_done),
        .sweep_start      (sweep_start),
        .sig_count        (sig_count),
        .ref_count        (ref_count),
        .rd_addr          (rd_addr),
        .rd_sig           (rd_sig),
        .rd_ref           (rd_ref),
        .freq_index       (freq_index)
    );

    initial begin
        $dumpfile("sim_build_accumulator/dump.vcd");
        $dumpvars(0, shot_accumulator_tb_wrapper);
    end

endmodule
