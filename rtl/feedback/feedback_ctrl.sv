// feedback_ctrl.sv
// Fires a conditional MW correction pulse based on the spin state decision.
// When spin_state=0 (dark, |1⟩), asserts mw_correction for correction_dur cycles
// before the next INIT_PULSE begins.
//
// Timing: valid fires 1 cycle after readout window closes.
// The correction pulse must complete before pulse_sequencer re-enters INIT_PULSE.
// At 100 MHz a π pulse is typically mw_dur cycles (same as sequencer mw_dur).
//
// Integration: insert between state_discriminator and ramsey_top outputs.
// mw_correction_gate connects to the same RF switch as mw_gate (OR'd in top).

module feedback_ctrl (
    input  logic        clk,
    input  logic        rst,

    input  logic        valid,          // from state_discriminator: decision ready
    input  logic        spin_state,     // 1=bright(no action), 0=dark(correct)
    input  logic        enable,         // feedback enable (UART configurable)
    input  logic [31:0] correction_dur, // π pulse duration in clock cycles

    output logic        mw_correction,  // correction MW gate (OR with mw_gate in top)
    output logic        busy            // high while correction pulse is active
);

    logic [31:0] timer;

    always_ff @(posedge clk) begin
        if (rst) begin
            mw_correction <= 1'b0;
            busy          <= 1'b0;
            timer         <= '0;
        end else begin
            if (busy) begin
                // Counting down correction pulse
                if (timer == 32'd1) begin
                    mw_correction <= 1'b0;
                    busy          <= 1'b0;
                    timer         <= '0;
                end else begin
                    timer <= timer - 1;
                end
            end else if (valid && enable && !spin_state) begin
                // Dark state detected — fire correction π pulse
                mw_correction <= 1'b1;
                busy          <= 1'b1;
                timer         <= correction_dur;
            end
        end
    end

endmodule