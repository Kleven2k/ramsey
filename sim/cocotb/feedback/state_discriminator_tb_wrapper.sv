`timescale 1ns/1ps
`default_nettype none

module state_discriminator_tb_wrapper (
    input  logic        clk,
    input  logic        rst,
    input  logic [31:0] count,
    input  logic [31:0] threshold,
    input  logic        gate_in,
    output logic        spin_state,
    output logic        valid
);

    state_discriminator dut (
        .clk(clk),
        .rst(rst),
        .count(count),
        .threshold(threshold),
        .gate_in(gate_in),
        .spin_state(spin_state),
        .valid(valid)
    );

    initial begin
        $dumpfile("sim_build_feedback/dump_disc.vcd");
        $dumpvars(0, state_discriminator_tb_wrapper);
    end

endmodule