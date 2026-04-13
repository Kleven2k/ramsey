`timescale 1ns/1ps

module photon_counter_tb_wrapper (
    input  logic        clk,
    input  logic        rst,
    input  logic        apd_in,
    input  logic        gate,
    input  logic        clear,
    output logic [31:0] count
);

    photon_counter dut (
        .clk   (clk),
        .rst   (rst),
        .apd_in(apd_in),
        .gate  (gate),
        .clear (clear),
        .count (count)
    );

    initial begin
        $dumpfile("sim_build_photon_counter/dump.vcd");
        $dumpvars(0, photon_counter_tb_wrapper);
    end

endmodule
