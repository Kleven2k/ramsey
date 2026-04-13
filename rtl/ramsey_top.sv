`timescale 1ns/1ps

// ramsey_top.sv
//
// Top-level module for the Ramsey ODMR system.
// Targets the Nexys Video Artix-7 (XC7A200T-1SBG484C, 100 MHz clock).
//
// Data flow:
//   PC → CONFIG (timing params + frequency table in kHz) → stored in registers
//   PC → START  → sweep loop:
//     for each freq point:
//       freq_calc → adf4351_ctrl (SPI) → pulse_sequencer → shot_accumulator
//   DONE → DATA packet (sig + ref counts per point) → PC
//
// CONFIG payload byte layout (big-endian throughout):
//   [0:1]   n_points     uint16   number of frequency points (max 1024)
//   [2:5]   n_shots      uint32   shots averaged per point
//   [6:9]   init_dur     uint32   laser init pulse, clock cycles
//   [10:13] mw_dur       uint32   MW pulse, clock cycles
//   [14:17] readout_dur  uint32   readout window, clock cycles
//   [18:21] ref_dur      uint32   reference window, clock cycles
//   [22:25] dead_time    uint32   dead time between MW pulses, clock cycles
//   [26]    lock_in_en   uint8    1 = lock-in (FSK) mode, 0 = standard sweep
//   [27:30] delta_f_khz  uint32   FSK half-step in kHz (ignored if lock_in_en=0)
//   [31+]   freq_table   uint32[] target output frequency in kHz, one per point
//                                 (interleaved f+df/f-df pairs when lock_in_en=1)
//
// DATA payload: for each point, 4 bytes sig (MSB first) then 4 bytes ref.
// tx_msg_len = 8 × n_points.  Max n_points = 1024 → max 8192 bytes.

module ramsey_top (
    input  logic        clk,            // 100 MHz system clock (Nexys Video R4)
    input  logic        rst_n,          // Active-low reset (mapped to a button)

    // UART — USB-UART bridge on Nexys Video
    input  logic        uart_rx_pin,
    output logic        uart_tx_pin,

    // Photon counting — single APD for both signal and reference windows
    input  logic        apd_in,         // TTL pulses from APD (async)

    // Pulse sequencer hardware outputs
    output logic        laser_gate,     // to AOM driver
    output logic        mw_gate,        // to RF switch (low-power side)

    // ADF4351 SPI
    output logic        spi_clk,
    output logic        spi_mosi,
    output logic        spi_le,         // latch enable (active-high)
    input  logic        lock_detect     // ADF4351 LD pin (may be noisy)
);

    // ── Reset ────────────────────────────────────────────────────────────────
    logic rst;
    assign rst = ~rst_n;

    // ── Message type constants ────────────────────────────────────────────────
    localparam logic [7:0] MSG_INIT   = 8'h01;
    localparam logic [7:0] MSG_CONFIG = 8'h02;
    localparam logic [7:0] MSG_START  = 8'h03;
    localparam logic [7:0] MSG_ACK    = 8'h04;
    localparam logic [7:0] MSG_DATA   = 8'h05;

    // CONFIG payload: header fields occupy bytes 0–30; freq table starts at 31
    localparam int CFG_FREQ_BASE = 31;

    // ── UART interface ────────────────────────────────────────────────────────
    logic [7:0]  rx_msg_type;
    logic [15:0] rx_msg_len;
    logic [7:0]  rx_payload_byte;
    logic        rx_payload_valid;
    logic        rx_msg_done;
    logic        rx_crc_ok;

    logic [7:0]  tx_msg_type;
    logic [15:0] tx_msg_len;
    logic [7:0]  tx_payload_byte;
    logic        tx_payload_req;
    logic        tx_send;
    logic        tx_busy;

    uart_interface #(
        .CLK_FREQ(100_000_000),
        .BAUD    (115_200)
    ) u_uart (
        .clk             (clk),
        .rst             (rst),
        .rx_pin          (uart_rx_pin),
        .tx_pin          (uart_tx_pin),
        .rx_msg_type     (rx_msg_type),
        .rx_msg_len      (rx_msg_len),
        .rx_payload_byte (rx_payload_byte),
        .rx_payload_valid(rx_payload_valid),
        .rx_msg_done     (rx_msg_done),
        .rx_crc_ok       (rx_crc_ok),
        .tx_msg_type     (tx_msg_type),
        .tx_msg_len      (tx_msg_len),
        .tx_payload_byte (tx_payload_byte),
        .tx_payload_req  (tx_payload_req),
        .tx_send         (tx_send),
        .tx_busy         (tx_busy)
    );

    // ── Pulse sequencer ───────────────────────────────────────────────────────
    logic [31:0] n_shots_r;
    logic [31:0] init_dur_r, mw_dur_r, dead_time_r, readout_dur_r, ref_dur_r;
    logic        gate, ref_gate;
    logic        counter_clear;
    logic        sweep_point_done;
    logic        spi_ready;
    logic        seq_run;

    pulse_sequencer u_seq (
        .clk             (clk),
        .rst             (rst),
        .run             (seq_run),
        .n_shots         (n_shots_r),
        .spi_ready       (spi_ready),
        .init_dur        (init_dur_r),
        .mw_dur          (mw_dur_r),
        .dead_time       (dead_time_r),
        .readout_dur     (readout_dur_r),
        .ref_dur         (ref_dur_r),
        .laser_gate      (laser_gate),
        .mw_gate         (mw_gate),
        .gate            (gate),
        .ref_gate        (ref_gate),
        .counter_clear   (counter_clear),
        .sweep_point_done(sweep_point_done),
        .next_freq       (),             // handled by main FSM
        .busy            ()              // not used at top level
    );

    // ── Photon counters (signal + reference, shared APD input) ────────────────
    // Both counters receive the same APD pulses but count during different
    // windows: u_sig_ctr during READOUT (gate), u_ref_ctr during REFERENCE (ref_gate).
    logic [31:0] sig_count, ref_count;

    photon_counter u_sig_ctr (
        .clk   (clk),
        .rst   (rst),
        .apd_in(apd_in),
        .gate  (gate),
        .clear (counter_clear),
        .count (sig_count)
    );

    photon_counter u_ref_ctr (
        .clk   (clk),
        .rst   (rst),
        .apd_in(apd_in),
        .gate  (ref_gate),
        .clear (counter_clear),
        .count (ref_count)
    );

    // ── Shot accumulator ──────────────────────────────────────────────────────
    logic [9:0]  rd_addr;
    logic [31:0] rd_sig, rd_ref;
    logic        sweep_start;

    shot_accumulator #(.DEPTH(1024)) u_accum (
        .clk             (clk),
        .rst             (rst),
        .gate            (gate),
        .ref_gate        (ref_gate),
        .sweep_point_done(sweep_point_done),
        .sweep_start     (sweep_start),
        .sig_count       (sig_count),
        .ref_count       (ref_count),
        .rd_addr         (rd_addr),
        .rd_sig          (rd_sig),
        .rd_ref          (rd_ref),
        .freq_index      ()              // not used at top level
    );

    // ── freq_calc ─────────────────────────────────────────────────────────────
    logic [31:0] fc_r0, fc_r1, fc_r2, fc_r3, fc_r4, fc_r5;
    logic        fc_start, fc_done;
    logic [31:0] fc_freq_khz;

    freq_calc u_freq_calc (
        .clk     (clk),
        .rst     (rst),
        .freq_khz(fc_freq_khz),
        .start   (fc_start),
        .done    (fc_done),
        .r0      (fc_r0),
        .r1      (fc_r1),
        .r2      (fc_r2),
        .r3      (fc_r3),
        .r4      (fc_r4),
        .r5      (fc_r5)
    );

    // ── ADF4351 controller ────────────────────────────────────────────────────
    logic adf_load;

    adf4351_ctrl #(
        .DEBOUNCE_CYCLES(1000),   // ~10 µs at 100 MHz
        .SPI_CLK_DIV    (5),      // 10 MHz SCLK
        .SPI_LE_CYCLES  (4)
    ) u_adf (
        .clk        (clk),
        .rst        (rst),
        .r0         (fc_r0),
        .r1         (fc_r1),
        .r2         (fc_r2),
        .r3         (fc_r3),
        .r4         (fc_r4),
        .r5         (fc_r5),
        .load       (adf_load),
        .lock_detect(lock_detect),
        .spi_ready  (spi_ready),
        .busy       (),           // not used; spi_ready is the handshake signal
        .sclk       (spi_clk),
        .sdata      (spi_mosi),
        .le         (spi_le)
    );

    // ── Configuration registers ───────────────────────────────────────────────
    logic [15:0] n_points_r;
    logic        lock_in_en_r;
    logic [31:0] delta_f_khz_r;
    // freq_table: read combinationally by freq_calc; written by CONFIG parser.
    // Infers as distributed RAM on Artix-7 (~512 LUTs for 1024 × 32-bit entries).
    logic [31:0] freq_table [0:1023];

    // Feed current sweep frequency to freq_calc combinationally.
    // freq_idx is stable by the time CTRL_FREQ_CALC asserts fc_start.
    logic [15:0] freq_idx;
    assign fc_freq_khz = freq_table[freq_idx[9:0]];

    // ── CONFIG byte parser ────────────────────────────────────────────────────
    // Parses the incoming CONFIG payload byte-stream into registers + freq_table.
    // cfg_byte_ptr resets on every rx_msg_done (end of any packet).
    logic [15:0] cfg_byte_ptr;
    logic [31:0] freq_shift;    // shift register for assembling 32-bit freq words

    always_ff @(posedge clk) begin
        if (rst) begin
            cfg_byte_ptr  <= 16'd0;
            n_points_r    <= 16'd0;
            n_shots_r     <= 32'd1;
            init_dur_r    <= 32'd1000;   // 10 µs laser init (@ 100 MHz)
            mw_dur_r      <= 32'd40;     // 400 ns MW pulse
            readout_dur_r <= 32'd600;    // 6 µs readout
            ref_dur_r     <= 32'd600;    // 6 µs reference
            dead_time_r   <= 32'd0;      // CW ODMR default
            lock_in_en_r  <= 1'b0;
            delta_f_khz_r <= 32'd0;
            freq_shift    <= 32'd0;
        end else begin
            if (rx_msg_done) begin
                cfg_byte_ptr <= 16'd0;
            end else if (rx_payload_valid && rx_msg_type == MSG_CONFIG) begin
                cfg_byte_ptr <= cfg_byte_ptr + 1'b1;
                // case uses the PRE-INCREMENT value of cfg_byte_ptr
                case (cfg_byte_ptr)
                    16'd0:  n_points_r[15:8]    <= rx_payload_byte;
                    16'd1:  n_points_r[7:0]      <= rx_payload_byte;
                    16'd2:  n_shots_r[31:24]     <= rx_payload_byte;
                    16'd3:  n_shots_r[23:16]     <= rx_payload_byte;
                    16'd4:  n_shots_r[15:8]      <= rx_payload_byte;
                    16'd5:  n_shots_r[7:0]       <= rx_payload_byte;
                    16'd6:  init_dur_r[31:24]    <= rx_payload_byte;
                    16'd7:  init_dur_r[23:16]    <= rx_payload_byte;
                    16'd8:  init_dur_r[15:8]     <= rx_payload_byte;
                    16'd9:  init_dur_r[7:0]      <= rx_payload_byte;
                    16'd10: mw_dur_r[31:24]      <= rx_payload_byte;
                    16'd11: mw_dur_r[23:16]      <= rx_payload_byte;
                    16'd12: mw_dur_r[15:8]       <= rx_payload_byte;
                    16'd13: mw_dur_r[7:0]        <= rx_payload_byte;
                    16'd14: readout_dur_r[31:24] <= rx_payload_byte;
                    16'd15: readout_dur_r[23:16] <= rx_payload_byte;
                    16'd16: readout_dur_r[15:8]  <= rx_payload_byte;
                    16'd17: readout_dur_r[7:0]   <= rx_payload_byte;
                    16'd18: ref_dur_r[31:24]     <= rx_payload_byte;
                    16'd19: ref_dur_r[23:16]     <= rx_payload_byte;
                    16'd20: ref_dur_r[15:8]      <= rx_payload_byte;
                    16'd21: ref_dur_r[7:0]       <= rx_payload_byte;
                    16'd22: dead_time_r[31:24]   <= rx_payload_byte;
                    16'd23: dead_time_r[23:16]   <= rx_payload_byte;
                    16'd24: dead_time_r[15:8]    <= rx_payload_byte;
                    16'd25: dead_time_r[7:0]     <= rx_payload_byte;
                    16'd26: lock_in_en_r         <= rx_payload_byte[0];
                    16'd27: delta_f_khz_r[31:24] <= rx_payload_byte;
                    16'd28: delta_f_khz_r[23:16] <= rx_payload_byte;
                    16'd29: delta_f_khz_r[15:8]  <= rx_payload_byte;
                    16'd30: delta_f_khz_r[7:0]   <= rx_payload_byte;
                    default: begin
                        // Frequency table entries — 4 bytes big-endian per word.
                        // Accumulate into freq_shift; write on the 4th byte of each word.
                        // CFG_FREQ_BASE=31 (≡ 3 mod 4), so last bytes of words fall at
                        // ptr 34, 38, 42, ... which all have bits[1:0] == 2'b10.
                        freq_shift <= {freq_shift[23:0], rx_payload_byte};
                        if (cfg_byte_ptr[1:0] == 2'b10 && cfg_byte_ptr >= 16'd34) begin
                            freq_table[(cfg_byte_ptr - 16'd31) >> 2] <=
                                {freq_shift[23:0], rx_payload_byte};
                        end
                    end
                endcase
            end
        end
    end

    // ── Main control FSM ──────────────────────────────────────────────────────
    typedef enum logic [3:0] {
        CTRL_IDLE,          // waiting for command from PC
        CTRL_ACK_SEND,      // assert tx_send for ACK (after INIT or CONFIG)
        CTRL_ACK_WAIT,      // wait for tx_busy to rise then fall
        CTRL_SWEEP_INIT,    // assert sweep_start, zero freq_idx
        CTRL_FREQ_CALC,     // assert fc_start (one cycle)
        CTRL_FREQ_WAIT,     // wait for fc_done
        CTRL_SPI_LOAD,      // assert adf_load (one cycle)
        CTRL_SPI_WAIT,      // wait for spi_ready
        CTRL_SEQ_RUN,       // assert seq_run (one cycle)
        CTRL_SEQ_WAIT,      // wait for sweep_point_done
        CTRL_NEXT_FREQ,     // advance freq_idx; done → DATA, else → FREQ_CALC
        CTRL_DATA_SEND,     // assert tx_send for DATA packet, reset TX counters
        CTRL_DATA_TX        // stream payload bytes; wait for tx_busy to fall
    } ctrl_t;

    ctrl_t ctrl_state;

    logic        configured;        // true after first valid CONFIG received
    logic        busy_seen_r;       // tx_busy has risen since last tx_send
    logic [9:0]  tx_point_ptr;      // which freq point is being streamed (0..n_points-1)
    logic [2:0]  tx_byte_in_pt;     // byte within point (0–3 = sig MSB..LSB, 4–7 = ref)

    // Accumulator read: always points at the point currently being streamed.
    // rd_sig/rd_ref update one cycle after rd_addr changes; since tx_payload_req
    // fires every ~868 cycles this latency is harmless.
    assign rd_addr = tx_point_ptr;

    always_ff @(posedge clk) begin
        if (rst) begin
            ctrl_state    <= CTRL_IDLE;
            freq_idx      <= 16'd0;
            configured    <= 1'b0;
            busy_seen_r   <= 1'b0;
            tx_point_ptr  <= 10'd0;
            tx_byte_in_pt <= 3'd0;
            tx_send       <= 1'b0;
            tx_msg_type   <= MSG_ACK;
            tx_msg_len    <= 16'd0;
            seq_run       <= 1'b0;
            sweep_start   <= 1'b0;
            fc_start      <= 1'b0;
            adf_load      <= 1'b0;
        end else begin
            // Default: de-assert all single-cycle pulses
            tx_send     <= 1'b0;
            seq_run     <= 1'b0;
            sweep_start <= 1'b0;
            fc_start    <= 1'b0;
            adf_load    <= 1'b0;

            case (ctrl_state)

                // ── Wait for a valid command from the PC ─────────────────────
                CTRL_IDLE: begin
                    if (rx_crc_ok) begin
                        case (rx_msg_type)
                            MSG_CONFIG: begin
                                configured <= 1'b1;
                                ctrl_state <= CTRL_ACK_SEND;
                            end
                            MSG_INIT: begin
                                // freq_calc computes all registers; INIT is a no-op
                                ctrl_state <= CTRL_ACK_SEND;
                            end
                            MSG_START: begin
                                if (configured)
                                    ctrl_state <= CTRL_SWEEP_INIT;
                                else
                                    ctrl_state <= CTRL_ACK_SEND;
                            end
                            default:;
                        endcase
                    end
                end

                // ── Send ACK (no payload) ────────────────────────────────────
                CTRL_ACK_SEND: begin
                    tx_msg_type <= MSG_ACK;
                    tx_msg_len  <= 16'd0;
                    tx_send     <= 1'b1;
                    busy_seen_r <= 1'b0;
                    ctrl_state  <= CTRL_ACK_WAIT;
                end

                CTRL_ACK_WAIT: begin
                    if (tx_busy) busy_seen_r <= 1'b1;
                    if (busy_seen_r && !tx_busy)
                        ctrl_state <= CTRL_IDLE;
                end

                // ── Begin sweep: reset accumulator, start at point 0 ─────────
                CTRL_SWEEP_INIT: begin
                    sweep_start <= 1'b1;   // resets shot_accumulator wr_ptr to 0
                    freq_idx    <= 16'd0;
                    ctrl_state  <= CTRL_FREQ_CALC;
                end

                // ── Compute ADF4351 registers for current freq point ──────────
                // fc_freq_khz = freq_table[freq_idx] is combinational and stable
                // by the time we reach this state (freq_idx set one state earlier).
                CTRL_FREQ_CALC: begin
                    fc_start   <= 1'b1;
                    ctrl_state <= CTRL_FREQ_WAIT;
                end

                CTRL_FREQ_WAIT: begin
                    if (fc_done)
                        ctrl_state <= CTRL_SPI_LOAD;
                end

                // ── Program ADF4351 with computed register values ─────────────
                CTRL_SPI_LOAD: begin
                    adf_load   <= 1'b1;
                    ctrl_state <= CTRL_SPI_WAIT;
                end

                CTRL_SPI_WAIT: begin
                    if (spi_ready)
                        ctrl_state <= CTRL_SEQ_RUN;
                end

                // ── Run n_shots shots at this frequency point ─────────────────
                CTRL_SEQ_RUN: begin
                    seq_run    <= 1'b1;
                    ctrl_state <= CTRL_SEQ_WAIT;
                end

                CTRL_SEQ_WAIT: begin
                    if (sweep_point_done)
                        ctrl_state <= CTRL_NEXT_FREQ;
                end

                // ── Advance to next point, or finish sweep ────────────────────
                CTRL_NEXT_FREQ: begin
                    if (freq_idx + 16'd1 < {16'(n_points_r)}) begin
                        freq_idx   <= freq_idx + 16'd1;
                        ctrl_state <= CTRL_FREQ_CALC;
                    end else begin
                        ctrl_state <= CTRL_DATA_SEND;
                    end
                end

                // ── Transmit DATA packet (sig + ref counts per point) ─────────
                // Payload: for each of n_points points: rd_sig[31:0] then rd_ref[31:0],
                // both big-endian.  tx_msg_len = n_points × 8 (max 1024×8 = 8192 bytes).
                CTRL_DATA_SEND: begin
                    tx_msg_type  <= MSG_DATA;
                    tx_msg_len   <= {n_points_r[12:0], 3'b000}; // × 8
                    tx_send      <= 1'b1;
                    tx_point_ptr <= 10'd0;
                    tx_byte_in_pt<= 3'd0;
                    busy_seen_r  <= 1'b0;
                    ctrl_state   <= CTRL_DATA_TX;
                end

                CTRL_DATA_TX: begin
                    if (tx_busy) busy_seen_r <= 1'b1;
                    if (tx_payload_req) begin
                        if (tx_byte_in_pt == 3'd7) begin
                            tx_byte_in_pt <= 3'd0;
                            tx_point_ptr  <= tx_point_ptr + 10'd1;
                        end else begin
                            tx_byte_in_pt <= tx_byte_in_pt + 3'd1;
                        end
                    end
                    if (busy_seen_r && !tx_busy)
                        ctrl_state <= CTRL_IDLE;
                end

                default: ctrl_state <= CTRL_IDLE;

            endcase
        end
    end

    // ── TX payload byte mux ───────────────────────────────────────────────────
    // rd_sig and rd_ref are the registered BRAM outputs for the current tx_point_ptr.
    always_comb begin
        case (tx_byte_in_pt)
            3'd0: tx_payload_byte = rd_sig[31:24];
            3'd1: tx_payload_byte = rd_sig[23:16];
            3'd2: tx_payload_byte = rd_sig[15:8];
            3'd3: tx_payload_byte = rd_sig[7:0];
            3'd4: tx_payload_byte = rd_ref[31:24];
            3'd5: tx_payload_byte = rd_ref[23:16];
            3'd6: tx_payload_byte = rd_ref[15:8];
            3'd7: tx_payload_byte = rd_ref[7:0];
            default: tx_payload_byte = 8'h00;
        endcase
    end

endmodule

`default_nettype wire
