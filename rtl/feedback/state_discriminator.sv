// state_discriminator.sv
// Compares gated photon count to a threshold and outputs a 1-bit spin state.
// Latches the decision on the falling edge of gate_in (readout window closed).
//
// Integration: driven by u_sig_ctr.count and pulse_sequencer.gate.
// spin_state = 1 → bright (|0⟩, above threshold)
// spin_state = 0 → dark  (|1⟩, below threshold, correction needed)

module state_discriminator (
    input  logic        clk,
    input  logic        rst,

    input  logic [31:0] count,          // from photon_counter u_sig_ctr
    input  logic [31:0] threshold,      // configurable via UART register
    input  logic        gate_in,        // pulse_sequencer.gate (readout window)

    output logic        spin_state,     // 1 = bright, 0 = dark
    output logic        valid           // pulses high for 1 cycle when decision latched
);

    logic gate_prev;

    always_ff @(posedge clk) begin
        if (rst) begin
            gate_prev  <= 1'b0;
            spin_state <= 1'b1;
            valid      <= 1'b0;
        end else begin
            gate_prev <= gate_in;
            valid     <= 1'b0;

            // Latch decision on falling edge of gate (readout window just closed)
            if (gate_prev && !gate_in) begin
                spin_state <= (count > threshold) ? 1'b1 : 1'b0;
                valid      <= 1'b1;
            end
        end
    end

endmodule