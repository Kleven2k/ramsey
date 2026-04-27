"""
End-to-end integration test.

Wires pulse_sequencer → photon_counter(×2) → shot_accumulator and runs a
simulated ODMR sweep with fake APD pulses injected at known rates.

Signal path:  apd_sig → photon_counter (gate=gate)    → shot_accumulator.sig_count
Reference:    apd_ref → photon_counter (gate=ref_gate) → shot_accumulator.ref_count

For each shot the sequencer asserts counter_clear before the readout window,
so both counters start from zero each shot.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, ClockCycles

CLK_PERIOD_NS = 10  # 100 MHz

# ── Sweep parameters ──────────────────────────────────────────────────────────
N_SHOTS       = 3
N_FREQ_POINTS = 3

# Timing (clock cycles) — small values for fast simulation
INIT_DUR    = 8
MW_DUR      = 4
DEAD_TIME   = 0   # CW mode
READOUT_DUR = 60  # long enough to inject pulses + 3-cycle synchronizer latency
REF_DUR     = 60

# Injected APD pulse counts per shot
SIG_PULSES_PER_SHOT = 4   # expected sig accumulation = 4 × N_SHOTS = 12
REF_PULSES_PER_SHOT = 2   # expected ref accumulation = 2 × N_SHOTS = 6

# ── Helpers ───────────────────────────────────────────────────────────────────

async def reset(dut):
    dut.rst.value         = 1
    dut.run.value         = 0
    dut.sweep_start.value = 0
    dut.apd_sig.value     = 0
    dut.apd_ref.value     = 0
    dut.rd_addr.value     = 0
    dut.n_shots.value      = N_SHOTS
    dut.init_dur.value     = INIT_DUR
    dut.mw_dur.value       = MW_DUR
    dut.dead_time.value    = DEAD_TIME
    dut.readout_dur.value  = READOUT_DUR
    dut.ref_dur.value      = REF_DUR
    await ClockCycles(dut.clk, 4)
    dut.rst.value = 0
    await ClockCycles(dut.clk, 20)  # wait for DEPTH=16 clear cycles to complete

async def pulse_run(dut):
    dut.run.value = 1
    await RisingEdge(dut.clk)
    dut.run.value = 0

async def inject_pulses(dut, signal, n):
    """Inject n single-cycle pulses on signal with 3-cycle gaps between them."""
    for _ in range(n):
        await ClockCycles(dut.clk, 3)
        signal.value = 1
        await RisingEdge(dut.clk)
        signal.value = 0

async def read_accum(dut, addr):
    dut.rd_addr.value = addr
    await ClockCycles(dut.clk, 2)
    return int(dut.rd_sig.value), int(dut.rd_ref.value)

# ── Injection monitors (run as background coroutines) ─────────────────────────

async def sig_injector(dut):
    """Each time gate opens, inject SIG_PULSES_PER_SHOT pulses."""
    while True:
        await RisingEdge(dut.gate)
        await inject_pulses(dut, dut.apd_sig, SIG_PULSES_PER_SHOT)

async def ref_injector(dut):
    """Each time ref_gate opens, inject REF_PULSES_PER_SHOT pulses."""
    while True:
        await RisingEdge(dut.ref_gate)
        await inject_pulses(dut, dut.apd_ref, REF_PULSES_PER_SHOT)

# ── Tests ────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_single_freq_point(dut):
    """One frequency point: N_SHOTS shots accumulate to expected totals."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    cocotb.start_soon(sig_injector(dut))
    cocotb.start_soon(ref_injector(dut))

    dut.sweep_start.value = 1
    await pulse_run(dut)
    dut.sweep_start.value = 0
    await RisingEdge(dut.sweep_point_done)
    await ClockCycles(dut.clk, 10)  # let RMW pipeline drain

    sig, ref = await read_accum(dut, 0)

    expected_sig = SIG_PULSES_PER_SHOT * N_SHOTS
    expected_ref = REF_PULSES_PER_SHOT * N_SHOTS

    assert sig == expected_sig, f"sig: expected {expected_sig}, got {sig}"
    assert ref == expected_ref, f"ref: expected {expected_ref}, got {ref}"

@cocotb.test()
async def test_multi_freq_sweep(dut):
    """N_FREQ_POINTS points, each accumulates independently."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    cocotb.start_soon(sig_injector(dut))
    cocotb.start_soon(ref_injector(dut))

    # Reset accumulator pointer once at sweep start, then trigger sequencer per point
    dut.sweep_start.value = 1
    await RisingEdge(dut.clk)
    dut.sweep_start.value = 0

    for _ in range(N_FREQ_POINTS):
        await pulse_run(dut)
        await RisingEdge(dut.sweep_point_done)
        await ClockCycles(dut.clk, 5)

    await ClockCycles(dut.clk, 10)  # pipeline drain

    # All points should have identical counts
    expected_sig = SIG_PULSES_PER_SHOT * N_SHOTS
    expected_ref = REF_PULSES_PER_SHOT * N_SHOTS

    for pt in range(N_FREQ_POINTS):
        sig, ref = await read_accum(dut, pt)
        assert sig == expected_sig, f"point {pt} sig: expected {expected_sig}, got {sig}"
        assert ref == expected_ref, f"point {pt} ref: expected {expected_ref}, got {ref}"

@cocotb.test()
async def test_freq_index_tracking(dut):
    """freq_index advances with sweep_point_done and resets on run."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    cocotb.start_soon(sig_injector(dut))
    cocotb.start_soon(ref_injector(dut))

    assert int(dut.freq_index.value) == 0, "freq_index should start at 0"

    # sweep_start resets pointer; run just triggers the sequencer per point
    dut.sweep_start.value = 1
    await RisingEdge(dut.clk)
    dut.sweep_start.value = 0

    for expected_idx in range(1, N_FREQ_POINTS + 1):
        await pulse_run(dut)
        await RisingEdge(dut.sweep_point_done)
        await ClockCycles(dut.clk, 2)  # wr_ptr NBA lands on next clk; need +2 to see it
        assert int(dut.freq_index.value) == expected_idx, \
            f"freq_index: expected {expected_idx}, got {dut.freq_index.value}"

    # sweep_start resets pointer back to 0
    dut.sweep_start.value = 1
    await RisingEdge(dut.clk)
    dut.sweep_start.value = 0
    await RisingEdge(dut.clk)

    assert int(dut.freq_index.value) == 0, \
        f"freq_index should reset to 0 on sweep_start, got {dut.freq_index.value}"

@cocotb.test()
async def test_signal_ref_independent(dut):
    """Signal and reference counts are accumulated into separate entries."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    cocotb.start_soon(sig_injector(dut))
    cocotb.start_soon(ref_injector(dut))

    dut.sweep_start.value = 1
    await pulse_run(dut)
    dut.sweep_start.value = 0
    await RisingEdge(dut.sweep_point_done)
    await ClockCycles(dut.clk, 10)

    sig, ref = await read_accum(dut, 0)

    assert sig != ref, "signal and reference should differ (different injection rates)"
    assert sig == SIG_PULSES_PER_SHOT * N_SHOTS, f"sig wrong: {sig}"
    assert ref == REF_PULSES_PER_SHOT * N_SHOTS, f"ref wrong: {ref}"

@cocotb.test()
async def test_busy_lifecycle(dut):
    """busy is high during the sweep and low before/after."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    cocotb.start_soon(sig_injector(dut))
    cocotb.start_soon(ref_injector(dut))

    assert dut.busy.value == 0, "busy should be low before run"

    dut.sweep_start.value = 1
    await pulse_run(dut)
    dut.sweep_start.value = 0
    await ClockCycles(dut.clk, 1)
    assert dut.busy.value == 1, "busy should be high during sweep"

    await RisingEdge(dut.sweep_point_done)
    await ClockCycles(dut.clk, 2)
    assert dut.busy.value == 0, "busy should be low after sweep"
