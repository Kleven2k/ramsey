`timescale 1ns/1ps
`default_nettype none

// Integration testbench wrapper.
// Connects pulse_sequencer → photon_counter (×2) → shot_accumulator.
// Two independent APD inputs: apd_sig (signal window) and apd_ref (reference window).
// Both share counter_clear from the sequencer so they are zeroed before each shot.

module integration_tb_wrapper #(
    parameter DEPTH = 16
) (
    input  logic       clk,
    input  logic       rst,

    // Sequencer configuration
    input  logic [31:0] n_shots,
    input  logic [31:0] init_dur,
    input  logic [31:0] mw_dur,
    input  logic [31:0] dead_time,
    input  logic [31:0] readout_dur,
    input  logic [31:0] ref_dur,
    input  logic        run,          // pulse_sequencer trigger (each freq point)
    input  logic        sweep_start,  // shot_accumulator reset (once per full sweep)

    // Fake APD inputs
    input  logic        apd_sig,   // drives signal-window photon counter
    input  logic        apd_ref,   // drives reference-window photon counter

    // Readout port
    input  logic [3:0]  rd_addr,
    output logic [31:0] rd_sig,
    output logic [31:0] rd_ref,

    // Observable signals for test assertions
    output logic        gate,
    output logic        ref_gate,
    output logic        sweep_point_done,
    output logic        busy,
    output logic [3:0]  freq_index
);

    // ── Internal wires ────────────────────────────────────────────────────────
    logic        laser_gate, mw_gate;
    logic        counter_clear, next_freq;

    logic [31:0] sig_count, ref_count;

    // ── pulse_sequencer ───────────────────────────────────────────────────────
    pulse_sequencer u_seq (
        .clk              (clk),
        .rst              (rst),
        .run              (run),
        .n_shots          (n_shots),
        .init_dur         (init_dur),
        .mw_dur           (mw_dur),
        .dead_time        (dead_time),
        .readout_dur      (readout_dur),
        .ref_dur          (ref_dur),
        .spi_ready        (1'b1),        // synthesizer always ready in sim
        .laser_gate       (laser_gate),
        .mw_gate          (mw_gate),
        .gate             (gate),
        .ref_gate         (ref_gate),
        .counter_clear    (counter_clear),
        .sweep_point_done (sweep_point_done),
        .next_freq        (next_freq),
        .busy             (busy)
    );

    // ── photon_counter — signal window ────────────────────────────────────────
    photon_counter u_sig_ctr (
        .clk    (clk),
        .rst    (rst),
        .apd_in (apd_sig),
        .gate   (gate),
        .clear  (counter_clear),
        .count  (sig_count)
    );

    // ── photon_counter — reference window ─────────────────────────────────────
    photon_counter u_ref_ctr (
        .clk    (clk),
        .rst    (rst),
        .apd_in (apd_ref),
        .gate   (ref_gate),
        .clear  (counter_clear),
        .count  (ref_count)
    );

    // ── shot_accumulator ──────────────────────────────────────────────────────
    shot_accumulator #(.DEPTH(DEPTH)) u_accum (
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
        $dumpfile("sim_build_integration/dump.vcd");
        $dumpvars(0, integration_tb_wrapper);
    end

endmodule
