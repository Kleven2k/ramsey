`timescale 1ns/1ps

// uart_interface.sv
//
// Packet framing layer on top of uart_top.
// Implements the ODMR packet protocol:
//   [0xAA] [TYPE: 1B] [LENGTH: 2B] [PAYLOAD: N B] [CRC: 1B]
// CRC = XOR of all payload bytes.
//
// RX: streams payload bytes out as they arrive, asserts rx_msg_done
//     on the last byte, rx_crc_ok indicates whether CRC matched.
//
// TX: accepts a message type, payload length, and a byte-at-a-time
//     payload stream. Frames and sends the full packet. Caller must
//     hold tx_payload_byte valid until the next tx_payload_req pulse.
//
// Note: no RX timeout — a truncated packet will stall the RX FSM.
//       Add a watchdog counter if needed for robustness.

module uart_interface #(
    parameter int CLK_FREQ = 100_000_000,
    parameter int BAUD     = 115_200
)(
    input  logic clk,
    input  logic rst,

    // Physical UART pins
    input  logic        rx_pin,
    output logic        tx_pin,

    // ── RX (PC → FPGA) ──────────────────────────────────────────
    output logic [7:0]  rx_msg_type,      // message type of current packet
    output logic [15:0] rx_msg_len,       // payload length in bytes
    output logic [7:0]  rx_payload_byte,  // current payload byte (streamed)
    output logic        rx_payload_valid, // rx_payload_byte is valid this cycle
    output logic        rx_msg_done,      // pulses on last payload byte
    output logic        rx_crc_ok,        // CRC result, valid when rx_msg_done

    // ── TX (FPGA → PC) ──────────────────────────────────────────
    input  logic [7:0]  tx_msg_type,      // message type to send
    input  logic [15:0] tx_msg_len,       // payload length (0 = no payload)
    input  logic [7:0]  tx_payload_byte,  // next payload byte from caller
    output logic        tx_payload_req,   // pulse: advance to next byte
    input  logic        tx_send,          // pulse to start sending a packet
    output logic        tx_busy           // high while transmission in progress
);

    // ── Low-level UART ───────────────────────────────────────────
    logic [7:0] raw_rx_data;
    logic       raw_rx_valid;
    logic [7:0] raw_tx_data;
    logic       raw_tx_start;
    logic       raw_tx_busy;

    uart_top #(
        .CLK_FREQ(CLK_FREQ),
        .BAUD    (BAUD)
    ) u_uart (
        .clk     (clk),
        .rst     (rst),
        .rx      (rx_pin),
        .tx      (tx_pin),
        .rx_data (raw_rx_data),
        .rx_valid(raw_rx_valid),
        .tx_data (raw_tx_data),
        .tx_start(raw_tx_start),
        .tx_busy (raw_tx_busy)
    );

    // ── RX FSM ───────────────────────────────────────────────────
    typedef enum logic [2:0] {
        RX_WAIT_HEADER,
        RX_GET_TYPE,
        RX_GET_LEN_HI,
        RX_GET_LEN_LO,
        RX_GET_PAYLOAD,
        RX_GET_CRC
    } rx_state_t;

    rx_state_t   rx_state;
    logic [15:0] rx_byte_count;
    logic [7:0]  rx_crc_accum;

    always_ff @(posedge clk) begin
        if (rst) begin
            rx_state         <= RX_WAIT_HEADER;
            rx_msg_type      <= 8'd0;
            rx_msg_len       <= 16'd0;
            rx_payload_byte  <= 8'd0;
            rx_payload_valid <= 1'b0;
            rx_msg_done      <= 1'b0;
            rx_crc_ok        <= 1'b0;
            rx_byte_count    <= 16'd0;
            rx_crc_accum     <= 8'd0;
        end else begin
            rx_payload_valid <= 1'b0;
            rx_msg_done      <= 1'b0;
            rx_crc_ok        <= 1'b0;

            if (raw_rx_valid) begin
                case (rx_state)

                    RX_WAIT_HEADER:
                        if (raw_rx_data == 8'hAA)
                            rx_state <= RX_GET_TYPE;

                    RX_GET_TYPE: begin
                        rx_msg_type  <= raw_rx_data;
                        rx_crc_accum <= 8'd0;
                        rx_state     <= RX_GET_LEN_HI;
                    end

                    RX_GET_LEN_HI: begin
                        rx_msg_len[15:8] <= raw_rx_data;
                        rx_state         <= RX_GET_LEN_LO;
                    end

                    // rx_msg_len[15:8] is already registered from previous cycle
                    RX_GET_LEN_LO: begin
                        rx_msg_len[7:0] <= raw_rx_data;
                        rx_byte_count   <= 16'd0;
                        if (rx_msg_len[15:8] == 8'd0 && raw_rx_data == 8'd0)
                            rx_state <= RX_GET_CRC;  // zero-length payload
                        else
                            rx_state <= RX_GET_PAYLOAD;
                    end

                    RX_GET_PAYLOAD: begin
                        rx_payload_byte  <= raw_rx_data;
                        rx_payload_valid <= 1'b1;
                        rx_crc_accum     <= rx_crc_accum ^ raw_rx_data;
                        rx_byte_count    <= rx_byte_count + 1;
                        if (rx_byte_count == rx_msg_len - 1) begin
                            rx_msg_done <= 1'b1;
                            rx_state    <= RX_GET_CRC;
                        end
                    end

                    RX_GET_CRC: begin
                        rx_crc_ok <= (raw_rx_data == rx_crc_accum);
                        rx_state  <= RX_WAIT_HEADER;
                    end

                endcase
            end
        end
    end

    // ── TX FSM ───────────────────────────────────────────────────
    typedef enum logic [2:0] {
        TX_IDLE,
        TX_HEADER,
        TX_TYPE,
        TX_LEN_HI,
        TX_LEN_LO,
        TX_PAYLOAD,
        TX_CRC
    } tx_state_t;

    tx_state_t   tx_state;
    logic [7:0]  tx_type_reg;
    logic [15:0] tx_len_reg;
    logic [15:0] tx_byte_count;
    logic [7:0]  tx_crc_accum;

    // Safe to send when uart_tx is idle and no start pulse is already in flight.
    // Checking raw_tx_start (the registered output) prevents double-triggering
    // on the cycle between asserting start and uart_tx raising tx_busy.
    logic tx_can_send;
    assign tx_can_send = !raw_tx_busy && !raw_tx_start;

    always_ff @(posedge clk) begin
        if (rst) begin
            tx_state       <= TX_IDLE;
            tx_busy        <= 1'b0;
            raw_tx_start   <= 1'b0;
            raw_tx_data    <= 8'd0;
            tx_payload_req <= 1'b0;
            tx_byte_count  <= 16'd0;
            tx_crc_accum   <= 8'd0;
            tx_type_reg    <= 8'd0;
            tx_len_reg     <= 16'd0;
        end else begin
            raw_tx_start   <= 1'b0;  // default: no start pulse
            tx_payload_req <= 1'b0;  // default: no advance request

            case (tx_state)

                TX_IDLE: begin
                    tx_busy <= 1'b0;
                    if (tx_send) begin
                        tx_type_reg   <= tx_msg_type;
                        tx_len_reg    <= tx_msg_len;
                        tx_byte_count <= 16'd0;
                        tx_crc_accum  <= 8'd0;
                        tx_busy       <= 1'b1;
                        tx_state      <= TX_HEADER;
                    end
                end

                TX_HEADER:
                    if (tx_can_send) begin
                        raw_tx_data  <= 8'hAA;
                        raw_tx_start <= 1'b1;
                        tx_state     <= TX_TYPE;
                    end

                TX_TYPE:
                    if (tx_can_send) begin
                        raw_tx_data  <= tx_type_reg;
                        raw_tx_start <= 1'b1;
                        tx_state     <= TX_LEN_HI;
                    end

                TX_LEN_HI:
                    if (tx_can_send) begin
                        raw_tx_data  <= tx_len_reg[15:8];
                        raw_tx_start <= 1'b1;
                        tx_state     <= TX_LEN_LO;
                    end

                TX_LEN_LO:
                    if (tx_can_send) begin
                        raw_tx_data  <= tx_len_reg[7:0];
                        raw_tx_start <= 1'b1;
                        if (tx_len_reg == 16'd0)
                            tx_state <= TX_CRC;
                        else
                            tx_state <= TX_PAYLOAD;
                    end

                TX_PAYLOAD:
                    if (tx_can_send) begin
                        raw_tx_data   <= tx_payload_byte;
                        raw_tx_start  <= 1'b1;
                        tx_crc_accum  <= tx_crc_accum ^ tx_payload_byte;
                        tx_byte_count <= tx_byte_count + 1;
                        if (tx_byte_count == tx_len_reg - 1)
                            tx_state <= TX_CRC;
                        else
                            tx_payload_req <= 1'b1;  // advance to next byte
                    end

                TX_CRC:
                    if (tx_can_send) begin
                        raw_tx_data  <= tx_crc_accum;
                        raw_tx_start <= 1'b1;
                        tx_state     <= TX_IDLE;
                    end

            endcase
        end
    end

endmodule

`default_nettype wire
