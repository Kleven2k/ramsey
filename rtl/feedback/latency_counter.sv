// latency_counter.sv
// Measures the feedback loop latency: time from readout window closing
// to mw_correction rising edge. Resolution = 1 clock cycle = 10 ns at 100 MHz.
//
// Latches the last measured latency so it can be read via UART STATUS packet.
// Saturates at 32'hFFFFFFFF if correction never fires.

module latency_counter (
    input  logic        clk,
    input  logic        rst,

    input  logic        gate_in,        // pulse_sequencer.gate (start timing on falling edge)
    input  logic        mw_correction,  // feedback_ctrl output (stop timing on rising edge)

    output logic [31:0] latency_cycles, // last measured latency (readable via UART)
    output logic        latency_valid   // pulses 1 cycle when new measurement latched
);

    typedef enum logic [1:0] {
        IDLE,
        COUNTING,
        DONE
    } lc_state_t;

    lc_state_t state;
    logic [31:0] counter;
    logic gate_prev;
    logic mw_prev;

    always_ff @(posedge clk) begin
        if (rst) begin
            state          <= IDLE;
            counter        <= '0;
            gate_prev      <= 1'b0;
            mw_prev        <= 1'b0;
            latency_cycles <= '0;
            latency_valid  <= 1'b0;
        end else begin
            gate_prev     <= gate_in;
            mw_prev       <= mw_correction;
            latency_valid <= 1'b0;

            case (state)
                IDLE: begin
                    // Start counting on falling edge of gate (readout window closed)
                    if (gate_prev && !gate_in) begin
                        counter <= '0;
                        state   <= COUNTING;
                    end
                end

                COUNTING: begin
                    // Stop on rising edge of mw_correction
                    if (!mw_prev && mw_correction) begin
                        latency_cycles <= counter;
                        latency_valid  <= 1'b1;
                        state          <= DONE;
                    end else if (&counter) begin
                        // Saturate — no correction fired
                        state <= IDLE;
                    end else begin
                        counter <= counter + 1;
                    end
                end

                DONE: begin
                    state <= IDLE;
                end

                default: state <= IDLE;
            endcase
        end
    end

endmodule