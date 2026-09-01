`timescale 1ns/1ps
`default_nettype none

module latency_counter_tb_wrapper (
    input  logic        clk,
    input  logic        rst,
    input  logic        gate_in,
    input  logic        mw_correction,
    output logic [31:0] latency_cycles,
    output logic        latency_valid
);

    latency_counter dut (
        .clk(clk),
        .rst(rst),
        .gate_in(gate_in),
        .mw_correction(mw_correction),
        .latency_cycles(latency_cycles),
        .latency_valid(latency_valid)
    );

    initial begin
        $dumpfile("sim_build_feedback/dump_lc.vcd");
        $dumpvars(0, latency_counter_tb_wrapper);
    end

endmodule