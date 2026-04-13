`timescale 1ns/1ps
`default_nettype none

module pulse_sequencer_tb_wrapper (
    input  logic        clk,
    input  logic        rst,
    input  logic        run,
    input  logic [31:0] n_shots,
    input  logic        spi_ready,
    input  logic [31:0] init_dur,
    input  logic [31:0] mw_dur,
    input  logic [31:0] dead_time,
    input  logic [31:0] readout_dur,
    input  logic [31:0] ref_dur,

    output logic        laser_gate,
    output logic        mw_gate,
    output logic        gate,
    output logic        ref_gate,
    output logic        counter_clear,
    output logic        sweep_point_done,
    output logic        next_freq,
    output logic        busy
);

    pulse_sequencer dut (
        .clk(clk),
        .rst(rst),
        .run(run),
        .n_shots(n_shots),
        .spi_ready(spi_ready),
        .init_dur(init_dur),
        .mw_dur(mw_dur),
        .dead_time(dead_time),
        .readout_dur(readout_dur),
        .ref_dur(ref_dur),
        .laser_gate(laser_gate),
        .mw_gate(mw_gate),
        .gate(gate),
        .ref_gate(ref_gate),
        .counter_clear(counter_clear),
        .sweep_point_done(sweep_point_done),
        .next_freq(next_freq),
        .busy(busy)
    );

    initial begin
        $dumpfile("sim_build_pulse_sequencer/dump.vcd");
        $dumpvars(0, pulse_sequencer_tb_wrapper);
    end

endmodule