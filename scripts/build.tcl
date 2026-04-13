# ============================================================
# build.tcl — Vivado non-project batch build for Ramsey
#
# Runs: synth → opt → place → phys_opt → route → phys_opt → bitstream
# Each invocation writes to a timestamped runs/build_YYYYMMDD_HHMMSS/
# directory so previous builds are never overwritten.
#
# Usage (from repo root):
#   vivado -mode batch -source scripts/build.tcl
# ============================================================

set PART "xc7a200tsbg484-1"
set TOP  "ramsey_top"

# ── Timestamped output directory ──────────────────────────────────────────────
set TS      [clock format [clock seconds] -format "%Y%m%d_%H%M%S"]
set RUN_DIR "runs/build_$TS"
file mkdir $RUN_DIR

puts "============================================================"
puts " RAMSEY BUILD"
puts " Part:    $PART"
puts " Top:     $TOP"
puts " Out dir: $RUN_DIR"
puts "============================================================"

# ── Sources ───────────────────────────────────────────────────────────────────
# Package first — must be read before any module that imports it.
read_verilog -sv rtl/ramsey_pkg.sv

# Sub-modules (order within a group doesn't matter for non-project mode)
read_verilog -sv rtl/uart/uart_rx.sv
read_verilog -sv rtl/uart/uart_tx.sv
read_verilog -sv rtl/uart/uart_top.sv
read_verilog -sv rtl/uart/uart_interface.sv

read_verilog -sv rtl/counter/photon_counter.sv
read_verilog -sv rtl/sequencer/pulse_sequencer.sv
read_verilog -sv rtl/accumulator/shot_accumulator.sv

read_verilog -sv rtl/spi/spi_master.sv
read_verilog -sv rtl/spi/adf4351_ctrl.sv
read_verilog -sv rtl/spi/freq_calc.sv

# Top level last
read_verilog -sv rtl/ramsey_top.sv

# ── Constraints ───────────────────────────────────────────────────────────────
read_xdc constraints/nexys_video.xdc

# ── Synthesis ─────────────────────────────────────────────────────────────────
puts "\n--- Synthesis ---"
synth_design -top $TOP -part $PART
write_checkpoint -force "$RUN_DIR/post_synth.dcp"
report_utilization    -file "$RUN_DIR/util_synth.rpt"
report_timing_summary -file "$RUN_DIR/timing_synth.rpt"

# ── Implementation ────────────────────────────────────────────────────────────
puts "\n--- Optimize ---"
opt_design

puts "\n--- Place ---"
place_design
write_checkpoint -force "$RUN_DIR/post_place.dcp"
report_timing_summary -file "$RUN_DIR/timing_place.rpt"

puts "\n--- Physical optimization (post-place) ---"
phys_opt_design

puts "\n--- Route ---"
route_design
write_checkpoint -force "$RUN_DIR/post_route.dcp"

puts "\n--- Physical optimization (post-route) ---"
phys_opt_design

# ── Reports ───────────────────────────────────────────────────────────────────
puts "\n--- Reports ---"
report_timing_summary -file "$RUN_DIR/timing.rpt" -warn_on_violation
report_utilization    -file "$RUN_DIR/util.rpt"
report_power          -file "$RUN_DIR/power.rpt"
report_drc            -file "$RUN_DIR/drc.rpt"

# ── Bitstream ─────────────────────────────────────────────────────────────────
puts "\n--- Bitstream ---"
write_bitstream -force "$RUN_DIR/ramsey.bit"

puts "\n============================================================"
puts " BUILD COMPLETE: $RUN_DIR/ramsey.bit"
puts "============================================================"
