`timescale 1ns/1ps
`default_nettype none

module feedback_ctrl_tb_wrapper (
    input  logic        clk,
    input  logic        rst,
    input  logic        valid,
    input  logic        spin_state,
    input  logic        enable,
    input  logic [31:0] correction_dur,
    output logic        mw_correction,
    output logic        busy
);

    feedback_ctrl dut (
        .clk(clk),
        .rst(rst),
        .valid(valid),
        .spin_state(spin_state),
        .enable(enable),
        .correction_dur(correction_dur),
        .mw_correction(mw_correction),
        .busy(busy)
    );

    initial begin
        $dumpfile("sim_build_feedback/dump_fb.vcd");
        $dumpvars(0, feedback_ctrl_tb_wrapper);
    end

endmodule