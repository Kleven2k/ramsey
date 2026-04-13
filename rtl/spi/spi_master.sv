`timescale 1ns/1ps

// spi_master.sv
//
// Generic SPI master — shifts 32 bits MSB-first, then pulses LE (latch enable).
// Designed for write-only peripherals such as the ADF4351 PLL synthesizer.
//
// SPI mode 0: CPOL=0, CPHA=0 — data captured on SCLK rising edge.
// SCLK frequency = clk / (2 * CLK_DIV).
// At 100 MHz system clock and CLK_DIV=5: SCLK = 10 MHz (ADF4351 max is 20 MHz).
//
// Timing:
//   start asserted (1 cycle) → SCLK begins toggling → 32 bits shifted MSB first
//   → SCLK held low → LE pulses high for LE_CYCLES → done asserted (1 cycle)

module spi_master #(
    parameter CLK_DIV  = 5,   // SCLK half-period in system clock cycles
    parameter LE_CYCLES = 4   // LE pulse width in system clock cycles
) (
    input  logic        clk,
    input  logic        rst,

    // Control
    input  logic [31:0] data,   // word to transmit (latched on start)
    input  logic        start,  // single-cycle: begin transfer
    output logic        busy,   // high while transfer is in progress
    output logic        done,   // single-cycle: transfer + LE complete

    // SPI pins
    output logic        sclk,
    output logic        sdata,
    output logic        le
);

    // ── FSM ──────────────────────────────────────────────────────────────────
    typedef enum logic [1:0] {
        IDLE,
        SHIFT,
        LE_PULSE,
        DONE_ST
    } spi_state_t;

    spi_state_t state;

    logic [31:0] shift_reg;           // data being shifted out
    logic [$clog2(32)-1:0] bit_cnt;   // bits remaining
    logic [$clog2(CLK_DIV)-1:0] clk_cnt; // clock divider counter
    logic [$clog2(LE_CYCLES)-1:0] le_cnt; // LE pulse counter
    logic sclk_r;                     // registered SCLK

    always_ff @(posedge clk) begin
        if (rst) begin
            state     <= IDLE;
            shift_reg <= '0;
            bit_cnt   <= '0;
            clk_cnt   <= '0;
            le_cnt    <= '0;
            sclk_r    <= 1'b0;
            sdata     <= 1'b0;
            le        <= 1'b0;
            busy      <= 1'b0;
            done      <= 1'b0;
        end else begin
            done <= 1'b0;  // single-cycle default

            case (state)

                IDLE: begin
                    sclk_r  <= 1'b0;
                    le      <= 1'b0;
                    busy    <= 1'b0;
                    if (start) begin
                        shift_reg <= data;
                        bit_cnt   <= 5'd31;
                        clk_cnt   <= '0;
                        busy      <= 1'b1;
                        sdata     <= data[31];  // MSB first
                        state     <= SHIFT;
                    end
                end

                // Clock out bits MSB-first.
                // Each bit takes 2*CLK_DIV system cycles (one SCLK period).
                SHIFT: begin
                    if (clk_cnt == CLK_DIV - 1) begin
                        // Toggle SCLK
                        sclk_r  <= ~sclk_r;
                        clk_cnt <= '0;

                        if (sclk_r == 1'b1) begin
                            // Falling edge — advance to next bit
                            if (bit_cnt == 0) begin
                                // All bits sent — go to LE pulse
                                sclk_r <= 1'b0;
                                le_cnt <= '0;
                                state  <= LE_PULSE;
                            end else begin
                                bit_cnt   <= bit_cnt - 1'b1;
                                shift_reg <= shift_reg << 1;
                                sdata     <= shift_reg[30]; // next bit
                            end
                        end
                        // Rising edge — data already stable on sdata, nothing extra needed
                    end else begin
                        clk_cnt <= clk_cnt + 1'b1;
                    end
                end

                // Pulse LE high for LE_CYCLES after SCLK has settled low.
                LE_PULSE: begin
                    le <= 1'b1;
                    if (le_cnt == LE_CYCLES - 1) begin
                        le    <= 1'b0;
                        state <= DONE_ST;
                    end else begin
                        le_cnt <= le_cnt + 1'b1;
                    end
                end

                DONE_ST: begin
                    done  <= 1'b1;
                    busy  <= 1'b0;
                    state <= IDLE;
                end

            endcase
        end
    end

    assign sclk = sclk_r;

endmodule

`default_nettype wire
