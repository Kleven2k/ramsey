`timescale 1ns/1ps

module photon_counter (
    input  logic        clk,
    input  logic        rst,
    input  logic        apd_in,   // asynchronous TTL from APD
    input  logic        gate,     // count only while high
    input  logic        clear,    // synchronous count reset
    output logic [31:0] count
);

    // Two-stage synchronizer — brings asynchronous apd_in into clk domain
    logic apd_sync_0, apd_sync_1, apd_sync_2;

    always_ff @(posedge clk) begin
        if (rst) begin
            apd_sync_0 <= 1'b0;
            apd_sync_1 <= 1'b0;
            apd_sync_2 <= 1'b0;
        end else begin
            apd_sync_0 <= apd_in;
            apd_sync_1 <= apd_sync_0;
            apd_sync_2 <= apd_sync_1;
        end
    end

    // Rising edge detection on synchronized signal
    wire apd_rising = apd_sync_1 & ~apd_sync_2;

    // Gated counter — holds value after gate goes low
    always_ff @(posedge clk) begin
        if (rst || clear)
            count <= 32'd0;
        else if (gate && apd_rising)
            count <= count + 32'd1;
    end

endmodule
