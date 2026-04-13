`timescale 1ns/1ps

// pulse_sequencer.sv
//
// Timing engine for ODMR experiments.
// Sequences one shot: INIT_PULSE → MW1 → DEAD → MW2 → READOUT → REFERENCE.
// Repeats n_shots times per frequency point, then pulses sweep_point_done
// and next_freq before returning to IDLE.
//
// CW ODMR:  set dead_time = 0 — MW1 and MW2 fuse into one continuous pulse.
// Ramsey:   dead_time = τ (free precession time), mw_dur = π/2 pulse width.
//
// All duration inputs are in clock cycles (1 cycle = 10 ns at 100 MHz).

module pulse_sequencer (
    input  logic        clk,
    input  logic        rst,

    // Control
    input  logic        run,          // single-cycle pulse to start a sweep point
    input  logic [31:0] n_shots,      // shots to average per frequency point
    input  logic        spi_ready,    // ADF4351 has settled at new frequency

    // Timing parameters (in clock cycles)
    input  logic [31:0] init_dur,     // laser initialization pulse duration
    input  logic [31:0] mw_dur,       // MW pulse duration (π/2 for Ramsey)
    input  logic [31:0] dead_time,    // free precession time τ (0 for CW ODMR)
    input  logic [31:0] readout_dur,  // signal readout window duration
    input  logic [31:0] ref_dur,      // reference window duration

    // Outputs to hardware
    output logic        laser_gate,      // to AOM driver
    output logic        mw_gate,         // to RF switch
    output logic        gate,            // to photon counter enable (signal window)
    output logic        ref_gate,        // to photon counter enable (reference window)
    output logic        counter_clear,   // single-cycle: clear photon counter
    output logic        sweep_point_done,// single-cycle: n_shots complete
    output logic        next_freq,       // single-cycle: request next frequency
    output logic        busy             // high while sequencer is running
);

    // ── FSM ──────────────────────────────────────────────────────────────────
    typedef enum logic [2:0] {
        IDLE,
        INIT_PULSE,
        MW1,
        DEAD,
        MW2,
        READOUT,
        REFERENCE
    } pulse_state_t;

    pulse_state_t pulse_state;

    logic [31:0] timer;       // counts down clock cycles within each state
    logic [31:0] shot_count;  // number of completed shots this frequency point

    always_ff @(posedge clk) begin
        if (rst) begin
            pulse_state      <= IDLE;
            timer            <= 32'd0;
            shot_count       <= 32'd0;
            laser_gate       <= 1'b0;
            mw_gate          <= 1'b0;
            gate             <= 1'b0;
            ref_gate         <= 1'b0;
            counter_clear    <= 1'b0;
            sweep_point_done <= 1'b0;
            next_freq        <= 1'b0;
            busy             <= 1'b0;
        end else begin
            // Single-cycle pulses cleared every cycle by default.
            // Individual states assert them for exactly one cycle.
            counter_clear    <= 1'b0;
            sweep_point_done <= 1'b0;
            next_freq        <= 1'b0;

            case (pulse_state)

                // ── Wait for run pulse ────────────────────────────────────
                IDLE: begin
                    busy       <= 1'b0;
                    laser_gate <= 1'b0;
                    mw_gate    <= 1'b0;
                    gate       <= 1'b0;
                    ref_gate   <= 1'b0;
                    if (run) begin
                        busy        <= 1'b1;
                        shot_count  <= 32'd0;
                        timer       <= init_dur;
                        pulse_state <= INIT_PULSE;
                    end
                end

                // ── Laser on: spin initialisation into ms=0 ───────────────
                INIT_PULSE: begin
                    laser_gate <= 1'b1;
                    timer      <= timer - 1;
                    if (timer == 32'd1) begin
                        laser_gate  <= 1'b0;
                        timer       <= mw_dur;
                        pulse_state <= MW1;
                    end
                end

                // ── First MW pulse (π/2 for Ramsey, or full CW pulse) ─────
                // dead_time = 0: skip DEAD, keep mw_gate high into MW2.
                MW1: begin
                    mw_gate <= 1'b1;
                    timer   <= timer - 1;
                    if (timer == 32'd1) begin
                        if (dead_time == 32'd0) begin
                            timer       <= mw_dur;
                            pulse_state <= MW2;
                        end else begin
                            mw_gate     <= 1'b0;
                            timer       <= dead_time;
                            pulse_state <= DEAD;
                        end
                    end
                end

                // ── Free precession (τ for Ramsey, skip for CW) ───────────
                // dead_time = 0 exits immediately without decrementing.
                DEAD: begin
                    if (timer == 32'd0) begin
                        timer       <= mw_dur;
                        pulse_state <= MW2;
                    end else begin
                        timer <= timer - 1;
                        if (timer == 32'd1) begin
                            timer       <= mw_dur;
                            pulse_state <= MW2;
                        end
                    end
                end

                // ── Second MW pulse (π/2 for Ramsey, fuses with MW1 for CW)
                MW2: begin
                    mw_gate <= 1'b1;
                    timer   <= timer - 1;
                    if (timer == 32'd1) begin
                        mw_gate       <= 1'b0;
                        counter_clear <= 1'b1;  // clear before opening readout gate
                        timer         <= readout_dur;
                        pulse_state   <= READOUT;
                    end
                end

                // ── Readout: laser + counter on, accumulate signal counts ──
                READOUT: begin
                    laser_gate <= 1'b1;
                    gate       <= 1'b1;
                    timer      <= timer - 1;
                    if (timer == 32'd1) begin
                        gate        <= 1'b0;
                        timer       <= ref_dur;
                        pulse_state <= REFERENCE;
                    end
                end

                // ── Reference: laser on, ref_gate open, normalisation window ─
                REFERENCE: begin
                    laser_gate <= 1'b1;
                    ref_gate   <= 1'b1;
                    timer      <= timer - 1;
                    if (timer == 32'd1) begin
                        laser_gate <= 1'b0;
                        ref_gate   <= 1'b0;
                        if (shot_count + 1 < n_shots) begin
                            // More shots to go — start next shot
                            shot_count  <= shot_count + 1;
                            timer       <= init_dur;
                            pulse_state <= INIT_PULSE;
                        end else begin
                            // All shots done — signal accumulator and move on
                            shot_count       <= 32'd0;
                            sweep_point_done <= 1'b1;
                            next_freq        <= 1'b1;
                            pulse_state      <= IDLE;
                        end
                    end
                end

            endcase
        end
    end

endmodule

`default_nettype wire
