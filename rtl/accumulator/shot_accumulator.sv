`timescale 1ns/1ps

// shot_accumulator.sv
//
// Accumulates signal and reference photon counts into dual-port BRAM.
// One entry per frequency point; each entry is two 32-bit words:
//   addr 2*N   → signal_counts[N]   (counts during READOUT window)
//   addr 2*N+1 → reference_counts[N](counts during REFERENCE window)
//
// On every sweep_point_done the write pointer advances to the next
// frequency point. The host reads out accumulated data via the rd_* port.
//
// Read-modify-write sequencing (3-cycle pipeline):
//   Cycle 0: issue read address, latch new_count
//   Cycle 1: BRAM dout valid, present sum to write port
//   Cycle 2: write completes

module shot_accumulator #(
    parameter DEPTH = 1024  // max frequency points (power of two)
) (
    input  logic        clk,
    input  logic        rst,

    // From pulse_sequencer
    input  logic        gate,             // high during signal readout window
    input  logic        ref_gate,         // high during reference window
    input  logic        sweep_point_done, // single-cycle: advance to next freq point
    input  logic        sweep_start,      // single-cycle: new sweep — reset ptr to 0

    // From photon_counter — stable count captured at end of each window
    input  logic [31:0] sig_count,        // photon count from signal window
    input  logic [31:0] ref_count,        // photon count from reference window

    // Host read port (UART / PC)
    input  logic [$clog2(DEPTH)-1:0] rd_addr,
    output logic [31:0]              rd_sig,
    output logic [31:0]              rd_ref,

    // Status
    output logic [$clog2(DEPTH)-1:0] freq_index  // current write pointer
);

    localparam AW = $clog2(DEPTH);

    // ── BRAM arrays (inferred) ────────────────────────────────────────────────
    // Separate arrays for signal and reference keeps addressing simple.
    logic [31:0] sig_mem [0:DEPTH-1];
    logic [31:0] ref_mem [0:DEPTH-1];

    // ── Write-side state ──────────────────────────────────────────────────────
    logic [AW-1:0] wr_ptr;    // current frequency point index

    // Capture counts on the falling edge of gate / ref_gate
    // (use the single-cycle negedge — detect high→low transition)
    logic gate_prev;
    logic ref_gate_prev;
    logic gate_fall;
    logic ref_gate_fall;

    always_ff @(posedge clk) begin
        gate_prev     <= gate;
        ref_gate_prev <= ref_gate;
    end

    assign gate_fall     = gate_prev     & ~gate;
    assign ref_gate_fall = ref_gate_prev & ~ref_gate;

    // Read-modify-write pipeline
    // Stage 0 registers: latch count and address when window closes
    logic [31:0] sig_add_d, ref_add_d;
    logic        sig_wen_d, ref_wen_d;
    logic [AW-1:0] sig_waddr_d, ref_waddr_d;

    // Stage 1: BRAM read data available
    logic [31:0] sig_rdata, ref_rdata;
    logic [31:0] sig_add_q, ref_add_q;
    logic        sig_wen_q, ref_wen_q;
    logic [AW-1:0] sig_waddr_q, ref_waddr_q;

    // Stage 0 — capture on window fall
    always_ff @(posedge clk) begin
        if (rst) begin
            sig_wen_d <= 1'b0;
            ref_wen_d <= 1'b0;
        end else begin
            sig_wen_d   <= gate_fall;
            sig_add_d   <= sig_count;
            sig_waddr_d <= wr_ptr;

            ref_wen_d   <= ref_gate_fall;
            ref_add_d   <= ref_count;
            ref_waddr_d <= wr_ptr;
        end
    end

    // Stage 1 — BRAM read (registered output)
    always_ff @(posedge clk) begin
        if (sig_wen_d)
            sig_rdata <= sig_mem[sig_waddr_d];
        if (ref_wen_d)
            ref_rdata <= ref_mem[ref_waddr_d];

        sig_wen_q   <= sig_wen_d;
        sig_add_q   <= sig_add_d;
        sig_waddr_q <= sig_waddr_d;

        ref_wen_q   <= ref_wen_d;
        ref_add_q   <= ref_add_d;
        ref_waddr_q <= ref_waddr_d;
    end

    // Stage 2 — write back sum
    always_ff @(posedge clk) begin
        if (sig_wen_q)
            sig_mem[sig_waddr_q] <= sig_rdata + sig_add_q;
        if (ref_wen_q)
            ref_mem[ref_waddr_q] <= ref_rdata + ref_add_q;
    end

    // ── Write pointer + clear ─────────────────────────────────────────────────
    always_ff @(posedge clk) begin
        if (rst) begin
            wr_ptr <= '0;
        end else if (sweep_start) begin
            wr_ptr <= '0;
        end else if (sweep_point_done) begin
            wr_ptr <= wr_ptr + 1'b1;
        end
    end

    assign freq_index = wr_ptr;

    // ── Host read port ────────────────────────────────────────────────────────
    always_ff @(posedge clk) begin
        rd_sig <= sig_mem[rd_addr];
        rd_ref <= ref_mem[rd_addr];
    end

    // ── Initialise memory to zero on reset ───────────────────────────────────
    integer i;
    always_ff @(posedge clk) begin
        if (rst) begin
            for (i = 0; i < DEPTH; i = i + 1) begin
                sig_mem[i] <= 32'd0;
                ref_mem[i] <= 32'd0;
            end
        end
    end

endmodule

`default_nettype wire
