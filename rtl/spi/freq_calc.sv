`timescale 1ns/1ps

// freq_calc.sv
//
// Computes ADF4351 register values (r0..r5) from a target output frequency.
//
// Formula:  fout = fref × (INT + FRAC/MOD) / OUTDIV
// With fixed MOD (default 1000) this gives 25 kHz resolution at 25 MHz fref.
//
// Algorithm (sequential, ~200 clock cycles including GCD reduction):
//   1. Select output divider D so that fvco = fout × D falls in [2.2, 4.4] GHz
//   2. Divide fvco by fref (32-bit restoring divider) → INT, remainder
//   3. Multiply remainder by MOD, divide by fref → FRAC
//   4. GCD-reduce FRAC/MOD using Stein's binary algorithm (minimises sigma-delta
//      noise so digital lock detect asserts reliably)
//   5. Pack INT, FRAC_reduced, MOD_reduced, OUTDIV into r0/r1/r4
//
// Inputs are in kHz to avoid floating point.
// At 100 MHz system clock total latency ≈ 2 µs — negligible vs PLL lock time.
//
// R4 note: only bits [22:20] (RF divider select) are computed by this module.
// All other R4 bits come from R4_BASE so the user can set output power,
// band-select divider, and RF enable without touching this module.

module freq_calc #(
    parameter [31:0] FREF_KHZ  = 32'd25000,        // reference clock in kHz — 25000 for old board (25 MHz crystal)
    parameter [31:0] FIXED_MOD = 32'd1000,         // fixed ADF4351 MOD value
    parameter [31:0] R2_CFG    = 32'h18004E42,     // MUXOUT=digital LD, PD_POL=+, CP=2.5mA, R=1, PD=0
    parameter [31:0] R3_CFG    = 32'h008004B3,     // ClkDiv=150, Band Select Clock Mode=fast
    parameter [31:0] R4_BASE   = 32'h008FA03C,     // BSCD=250, fundamental feedback, RF enabled, +5dBm
    parameter [31:0] R5_CFG    = 32'h00580005      // LD pin=digital lock detect, reserved bits correct
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
    typedef enum logic [3:0] {
        IDLE,
        DIV_INT,       // restoring division: fvco / fref → INT + remainder
        MUL_REM,       // multiply remainder by MOD, set up FRAC division
        DIV_FRAC,      // restoring division: (remainder×MOD) / fref → FRAC
        PACK,          // latch FRAC; branch to GCD or DONE
        GCD_INIT,      // load Stein's GCD operands
        GCD_STEP,      // one step of Stein's binary GCD
        REDUCE_WAIT,   // restoring division for FRAC/GCD or MOD/GCD
        REDUCE_LATCH,  // latch quotient, set up next reduction or finish
        DONE_ST
    } state_t;

    state_t state;

    // ── Shared restoring divider ──────────────────────────────────────────────
    logic [4:0]  bit_idx;
    logic [31:0] dividend_r;
    logic [31:0] divisor_r;
    logic [31:0] quotient_r;
    logic [31:0] remainder_r;

    logic [31:0] div_partial;
    assign div_partial = {remainder_r[30:0], dividend_r[bit_idx]};

    // ── Latched results ───────────────────────────────────────────────────────
    logic [15:0] int_r;
    logic [11:0] frac_r;
    logic [11:0] mod_r;     // GCD-reduced MOD (output in R1)
    logic [2:0]  outdiv_r;

    // ── GCD state (Stein's binary algorithm) ─────────────────────────────────
    logic [11:0] gcd_a, gcd_b, gcd_result;
    logic [3:0]  gcd_shift;
    logic        reducing_mod; // 0 = reducing frac_r, 1 = reducing FIXED_MOD

    always_ff @(posedge clk) begin
        if (rst) begin
            state        <= IDLE;
            done         <= 1'b0;
            int_r        <= '0;
            frac_r       <= '0;
            mod_r        <= FIXED_MOD[11:0];
            outdiv_r     <= '0;
            dividend_r   <= '0;
            divisor_r    <= '0;
            quotient_r   <= '0;
            remainder_r  <= '0;
            bit_idx      <= '0;
            gcd_a        <= '0;
            gcd_b        <= '0;
            gcd_result   <= '0;
            gcd_shift    <= '0;
            reducing_mod <= 1'b0;
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
                DIV_INT: begin
                    if (div_partial >= divisor_r) begin
                        remainder_r         <= div_partial - divisor_r;
                        quotient_r[bit_idx] <= 1'b1;
                    end else begin
                        remainder_r         <= div_partial;
                        quotient_r[bit_idx] <= 1'b0;
                    end
                    if (bit_idx == 5'd0) begin
                        state <= MUL_REM;
                    end else begin
                        bit_idx <= bit_idx - 1'b1;
                    end
                end

                // ── Set up FRAC division ──────────────────────────────────────
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
                        remainder_r         <= div_partial - divisor_r;
                        quotient_r[bit_idx] <= 1'b1;
                    end else begin
                        remainder_r         <= div_partial;
                        quotient_r[bit_idx] <= 1'b0;
                    end
                    if (bit_idx == 5'd0) begin
                        state <= PACK;
                    end else begin
                        bit_idx <= bit_idx - 1'b1;
                    end
                end

                // ── Latch FRAC; skip GCD if integer-N ────────────────────────
                PACK: begin
                    frac_r <= quotient_r[11:0];
                    mod_r  <= FIXED_MOD[11:0];
                    if (quotient_r[11:0] == 12'd0) begin
                        state <= DONE_ST;   // FRAC=0 → integer-N, no reduction needed
                    end else begin
                        state <= GCD_INIT;
                    end
                end

                // ── Stein's binary GCD: load operands ────────────────────────
                GCD_INIT: begin
                    gcd_a     <= frac_r;
                    gcd_b     <= FIXED_MOD[11:0];
                    gcd_shift <= 4'd0;
                    state     <= GCD_STEP;
                end

                // ── Stein's binary GCD: one step per cycle ────────────────────
                // Invariant: GCD(original_frac, FIXED_MOD) = GCD(gcd_a, gcd_b) × 2^gcd_shift
                GCD_STEP: begin
                    if (gcd_a == 12'd0 || gcd_b == 12'd0) begin
                        // GCD found
                        gcd_result  <= (gcd_a | gcd_b) << gcd_shift;
                        dividend_r  <= {20'b0, frac_r};
                        divisor_r   <= {20'b0, (gcd_a | gcd_b) << gcd_shift};
                        quotient_r  <= '0;
                        remainder_r <= '0;
                        bit_idx     <= 5'd31;
                        reducing_mod <= 1'b0;
                        state       <= REDUCE_WAIT;
                    end else if (gcd_a[0] == 1'b0 && gcd_b[0] == 1'b0) begin
                        // Both even: extract common factor of 2
                        gcd_a     <= gcd_a >> 1;
                        gcd_b     <= gcd_b >> 1;
                        gcd_shift <= gcd_shift + 4'd1;
                    end else if (gcd_a[0] == 1'b0) begin
                        gcd_a <= gcd_a >> 1;
                    end else if (gcd_b[0] == 1'b0) begin
                        gcd_b <= gcd_b >> 1;
                    end else if (gcd_a >= gcd_b) begin
                        // Both odd, a≥b: GCD(a,b) = GCD((a-b)/2, b)
                        gcd_a <= (gcd_a - gcd_b) >> 1;
                    end else begin
                        // Both odd, b>a: GCD(a,b) = GCD(a, (b-a)/2)
                        gcd_b <= (gcd_b - gcd_a) >> 1;
                    end
                end

                // ── Restoring division for GCD reduction ─────────────────────
                REDUCE_WAIT: begin
                    if (div_partial >= divisor_r) begin
                        remainder_r         <= div_partial - divisor_r;
                        quotient_r[bit_idx] <= 1'b1;
                    end else begin
                        remainder_r         <= div_partial;
                        quotient_r[bit_idx] <= 1'b0;
                    end
                    if (bit_idx == 5'd0) begin
                        state <= REDUCE_LATCH;
                    end else begin
                        bit_idx <= bit_idx - 1'b1;
                    end
                end

                // ── Latch result; set up next reduction or finish ─────────────
                REDUCE_LATCH: begin
                    if (!reducing_mod) begin
                        // Just finished FRAC/GCD; now compute FIXED_MOD/GCD
                        frac_r      <= quotient_r[11:0];
                        dividend_r  <= FIXED_MOD;
                        divisor_r   <= {20'b0, gcd_result};
                        quotient_r  <= '0;
                        remainder_r <= '0;
                        bit_idx     <= 5'd31;
                        reducing_mod <= 1'b1;
                        state        <= REDUCE_WAIT;
                    end else begin
                        // Just finished FIXED_MOD/GCD; done
                        mod_r <= quotient_r[11:0];
                        state <= DONE_ST;
                    end
                end

                DONE_ST: begin
                    done  <= 1'b1;
                    state <= IDLE;
                end

            endcase
        end
    end

    // ── Register packing ──────────────────────────────────────────────────────
    // R0: [30:15]=INT, [14:3]=FRAC_reduced, [2:0]=3'b000
    assign r0 = {1'b0, int_r, frac_r, 3'b000};

    // R1: bit27=1 (8/9 prescaler), [26:15]=PHASE=1, [14:3]=MOD_reduced, [2:0]=3'b001
    assign r1 = {4'b0, 1'b1, 12'h001, mod_r, 3'b001};

    assign r2 = R2_CFG;
    assign r3 = R3_CFG;
    assign r5 = R5_CFG;

    // R4: insert computed outdiv into bits [22:20] of R4_BASE
    assign r4 = (R4_BASE & 32'hFF8FFFFF) | ({29'b0, outdiv_r} << 20);

endmodule

`default_nettype wire
