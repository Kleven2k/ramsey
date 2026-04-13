`timescale 1ns/1ps

// adf4351_ctrl.sv
//
// Programs the ADF4351 PLL synthesizer with a new set of register values.
// The ADF4351 requires its 6 registers written in order R5→R4→R3→R2→R1→R0
// (R0 last — writing R0 triggers the VCO to lock to the new frequency).
//
// After R0 is written the controller waits for the lock-detect pin to assert
// and debounces it for DEBOUNCE_CYCLES before asserting spi_ready.
//
// Usage:
//   1. Load r0..r5 with pre-computed ADF4351 register values.
//   2. Assert load for one cycle.
//   3. Wait for spi_ready to go high.
//
// Register values are computed by the host (Python) from the target frequency
// using: fout = fref * (INT + FRAC/MOD), then packed per the ADF4351 datasheet.
// The bottom 3 bits of each register encode the register address (0–5).

module adf4351_ctrl #(
    parameter DEBOUNCE_CYCLES  = 1000, // ~10 µs at 100 MHz — LD settling time
    parameter SPI_CLK_DIV      = 5,    // SCLK = clk / (2*SPI_CLK_DIV)
    parameter SPI_LE_CYCLES    = 4     // LE pulse width in system clock cycles
) (
    input  logic        clk,
    input  logic        rst,

    // Register values (pre-computed by host, loaded before asserting load)
    input  logic [31:0] r0, r1, r2, r3, r4, r5,

    // Control
    input  logic        load,       // single-cycle: start programming sequence
    input  logic        lock_detect,// ADF4351 LD pin (may be noisy)
    output logic        spi_ready,  // high when PLL is locked and stable
    output logic        busy,       // high while programming or waiting for lock

    // SPI pins
    output logic        sclk,
    output logic        sdata,
    output logic        le
);

    // ── SPI master instance ───────────────────────────────────────────────────
    logic [31:0] spi_data;
    logic        spi_start;
    logic        spi_done;
    logic        spi_busy;

    spi_master #(
        .CLK_DIV  (SPI_CLK_DIV),
        .LE_CYCLES(SPI_LE_CYCLES)
    ) u_spi (
        .clk   (clk),
        .rst   (rst),
        .data  (spi_data),
        .start (spi_start),
        .busy  (spi_busy),
        .done  (spi_done),
        .sclk  (sclk),
        .sdata (sdata),
        .le    (le)
    );

    // ── FSM ──────────────────────────────────────────────────────────────────
    typedef enum logic [2:0] {
        IDLE,
        SEND,       // wait for current spi_master transfer to complete
        DEBOUNCE,   // wait for lock_detect to assert and stay stable
        LOCKED
    } adf_state_t;

    adf_state_t state;

    // Register sequence: R5 first, R0 last
    logic [31:0] reg_seq [0:5];
    logic [2:0]  reg_idx;   // index into reg_seq

    logic [$clog2(DEBOUNCE_CYCLES)-1:0] debounce_cnt;

    always_ff @(posedge clk) begin
        if (rst) begin
            state       <= IDLE;
            reg_idx     <= '0;
            spi_data    <= '0;
            spi_start   <= 1'b0;
            spi_ready   <= 1'b0;
            busy        <= 1'b0;
            debounce_cnt<= '0;
        end else begin
            spi_start <= 1'b0;  // single-cycle default

            case (state)

                IDLE: begin
                    busy      <= 1'b0;
                    spi_ready <= 1'b0;
                    if (load) begin
                        // Latch register values and start sequence R5→R0
                        reg_seq[0] <= r5;
                        reg_seq[1] <= r4;
                        reg_seq[2] <= r3;
                        reg_seq[3] <= r2;
                        reg_seq[4] <= r1;
                        reg_seq[5] <= r0;
                        reg_idx    <= 3'd0;
                        busy       <= 1'b1;
                        spi_data   <= r5;
                        spi_start  <= 1'b1;
                        state      <= SEND;
                    end
                end

                SEND: begin
                    if (spi_done) begin
                        if (reg_idx == 3'd5) begin
                            // All registers sent — wait for lock
                            debounce_cnt <= '0;
                            state        <= DEBOUNCE;
                        end else begin
                            reg_idx   <= reg_idx + 1'b1;
                            spi_data  <= reg_seq[reg_idx + 1'b1];
                            spi_start <= 1'b1;
                        end
                    end
                end

                // Count consecutive cycles where lock_detect is high.
                // Any glitch resets the counter.
                DEBOUNCE: begin
                    if (!lock_detect) begin
                        debounce_cnt <= '0;
                    end else if (debounce_cnt == DEBOUNCE_CYCLES - 1) begin
                        state <= LOCKED;
                    end else begin
                        debounce_cnt <= debounce_cnt + 1'b1;
                    end
                end

                LOCKED: begin
                    spi_ready <= 1'b1;
                    busy      <= 1'b0;
                    state     <= IDLE;
                end

            endcase
        end
    end

endmodule

`default_nettype wire
