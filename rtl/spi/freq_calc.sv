`timescale 1ns/1ps

// freq_calc.sv
//
// Computes ADF4351 register values (r0..r5) from a target output frequency.
//
// Formula:  fout = fref × (INT + FRAC/MOD) / OUTDIV
// With fixed MOD (default 1000) this gives 25 kHz resolution at 25 MHz fref.
//
// Algorithm (sequential, ~70 clock cycles):
//   1. Select output divider D so that fvco = fout × D falls in [2.2, 4.4] GHz
//   2. Divide fvco by fref (32-bit restoring divider) → INT, remainder
//   3. Multiply remainder by MOD, divide by fref → FRAC
//   4. Pack INT, FRAC, MOD, OUTDIV into r0/r1/r4; r2/r3/r5 are parameters
//
// Inputs are in kHz to avoid floating point.
// At 100 MHz system clock total latency ≈ 700 ns — negligible vs PLL lock time.
//
// R4 note: only bits [22:20] (RF divider select) are computed by this module.
// All other R4 bits come from R4_BASE so the user can set output power,
// band-select divider, and RF enable without touching this module.

module freq_calc #(
    parameter [31:0] FREF_KHZ  = 32'd25000,        // reference clock in kHz — UPDATE if using ext ref via MCLK
    parameter [31:0] FIXED_MOD = 32'd1000,         // fixed ADF4351 MOD value
    parameter [31:0] R2_CFG    = 32'h18004062,     // MUXOUT=digital LD, PD_POL=+, CP=0.31mA, R=1
    parameter [31:0] R3_CFG    = 32'h00000003,     // R3 defaults: clock divider off
    parameter [31:0] R4_BASE   = 32'h008FA03C,     // BSCD=250 (100kHz margin), fundamental feedback, RF enabled
    parameter [31:0] R5_CFG    = 32'h00200005      // LD pin mode = digital lock detect
) (
    input  logic        clk,
    input  logic        rst,

    input  logic [31:0] freq_khz, // target output frequency in kHz (stable on start)
    input  logic        start,    // single-cycle: begin calculation
    output logic        done,     // single-cycle: r0..r5 are valid

    output logic [31:0] r0, r1, r2, r3, r4, r5
);

    // ── Output divider selection (combinational) ──────────────────────────────
    // ADF4351 VCO range: 2200–4400 MHz. Select smallest D such that fout×D
    // falls in that range. D ∈ {1, 2, 4, 8, 16, 32, 64}.
    logic [2:0]  outdiv_comb;
    logic [31:0] fvco_comb;

    always_comb begin
        if      (freq_khz >= 32'd2200000) begin outdiv_comb = 3'd0; fvco_comb = freq_khz;       end
        else if (freq_khz >= 32'd1100000) begin outdiv_comb = 3'd1; fvco_comb = freq_khz << 1;  end
        else if (freq_khz >= 32'd550000)  begin outdiv_comb = 3'd2; fvco_comb = freq_khz << 2;  end
        else if (freq_khz >= 32'd275000)  begin outdiv_comb = 3'd3; fvco_comb = freq_khz << 3;  end
        else if (freq_khz >= 32'd137500)  begin outdiv_comb = 3'd4; fvco_comb = freq_khz << 4;  end
        else if (freq_khz >= 32'd68750)   begin outdiv_comb = 3'd5; fvco_comb = freq_khz << 5;  end
        else                              begin outdiv_comb = 3'd6; fvco_comb = freq_khz << 6;  end
    end

    // ── FSM ──────────────────────────────────────────────────────────────────
    typedef enum logic [2:0] {
        IDLE,
        DIV_INT,   // restoring division: fvco / fref → INT + remainder
        MUL_REM,   // multiply remainder by MOD, set up FRAC division
        DIV_FRAC,  // restoring division: (remainder×MOD) / fref → FRAC
        PACK,      // latch FRAC, assemble registers
        DONE_ST
    } state_t;

    state_t state;

    // ── Shared restoring divider ──────────────────────────────────────────────
    logic [4:0]  bit_idx;       // counts 31 down to 0
    logic [31:0] dividend_r;    // original dividend (indexed by bit_idx)
    logic [31:0] divisor_r;     // = FREF_KHZ
    logic [31:0] quotient_r;    // accumulates result bits
    logic [31:0] remainder_r;   // partial remainder

    // Combinational: one divider step
    // Shift remainder left, bring in current dividend bit
    logic [31:0] div_partial;
    assign div_partial = {remainder_r[30:0], dividend_r[bit_idx]};

    // ── Latched results ───────────────────────────────────────────────────────
    logic [15:0] int_r;
    logic [11:0] frac_r;
    logic [2:0]  outdiv_r;

    always_ff @(posedge clk) begin
        if (rst) begin
            state       <= IDLE;
            done        <= 1'b0;
            int_r       <= '0;
            frac_r      <= '0;
            outdiv_r    <= '0;
            dividend_r  <= '0;
            divisor_r   <= '0;
            quotient_r  <= '0;
            remainder_r <= '0;
            bit_idx     <= '0;
        end else begin
            done <= 1'b0;

            case (state)

                // ── Wait for start ────────────────────────────────────────────
                IDLE: begin
                    if (start) begin
                        dividend_r  <= fvco_comb;
                        divisor_r   <= FREF_KHZ;
                        quotient_r  <= '0;
                        remainder_r <= '0;
                        bit_idx     <= 5'd31;
                        outdiv_r    <= outdiv_comb;
                        state       <= DIV_INT;
                    end
                end

                // ── fvco / fref → INT ─────────────────────────────────────────
                // Each cycle processes one bit of the dividend, MSB first.
                // quotient_r[i] ← 1 if partial remainder ≥ divisor.
                DIV_INT: begin
                    if (div_partial >= divisor_r) begin
                        remainder_r        <= div_partial - divisor_r;
                        quotient_r[bit_idx] <= 1'b1;
                    end else begin
                        remainder_r        <= div_partial;
                        quotient_r[bit_idx] <= 1'b0;
                    end

                    if (bit_idx == 5'd0) begin
                        state <= MUL_REM;
                    end else begin
                        bit_idx <= bit_idx - 1'b1;
                    end
                end

                // ── Set up FRAC division ───────────────────────────────────────
                // quotient_r and remainder_r now hold final INT division results.
                // remainder_r < FREF_KHZ (25000), FIXED_MOD = 1000 → product < 2^25 (no overflow).
                MUL_REM: begin
                    int_r       <= quotient_r[15:0];
                    dividend_r  <= remainder_r * FIXED_MOD;
                    divisor_r   <= FREF_KHZ;
                    quotient_r  <= '0;
                    remainder_r <= '0;
                    bit_idx     <= 5'd31;
                    state       <= DIV_FRAC;
                end

                // ── (remainder × MOD) / fref → FRAC ──────────────────────────
                DIV_FRAC: begin
                    if (div_partial >= divisor_r) begin
                        remainder_r        <= div_partial - divisor_r;
                        quotient_r[bit_idx] <= 1'b1;
                    end else begin
                        remainder_r        <= div_partial;
                        quotient_r[bit_idx] <= 1'b0;
                    end

                    if (bit_idx == 5'd0) begin
                        state <= PACK;
                    end else begin
                        bit_idx <= bit_idx - 1'b1;
                    end
                end

                // ── Latch FRAC and assemble registers ─────────────────────────
                PACK: begin
                    frac_r <= quotient_r[11:0];
                    state  <= DONE_ST;
                end

                DONE_ST: begin
                    done  <= 1'b1;
                    state <= IDLE;
                end

            endcase
        end
    end

    // ── Register packing ──────────────────────────────────────────────────────
    // R0: [30:15]=INT, [14:3]=FRAC, [2:0]=3'b000
    assign r0 = {1'b0, int_r, frac_r, 3'b000};

    // R1: [26:15]=PHASE(=1, fixed), [14:3]=MOD, [2:0]=3'b001
    assign r1 = {5'b0, 12'h001, FIXED_MOD[11:0], 3'b001};

    // R2, R3, R5: fixed hardware configuration
    assign r2 = R2_CFG;
    assign r3 = R3_CFG;
    assign r5 = R5_CFG;

    // R4: insert computed outdiv into bits [22:20] of R4_BASE
    assign r4 = (R4_BASE & 32'hFF8FFFFF) | ({29'b0, outdiv_r} << 20);

endmodule

`default_nettype wire
