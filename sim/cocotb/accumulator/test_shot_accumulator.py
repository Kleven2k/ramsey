import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles

CLK_PERIOD_NS = 10  # 100 MHz

# ── Helpers ───────────────────────────────────────────────────────────────────

async def reset(dut):
    dut.rst.value              = 1
    dut.gate.value             = 0
    dut.ref_gate.value         = 0
    dut.sweep_point_done.value = 0
    dut.sweep_start.value      = 0
    dut.sig_count.value        = 0
    dut.ref_count.value        = 0
    dut.rd_addr.value          = 0
    await ClockCycles(dut.clk, 4)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

async def close_sig_window(dut, count):
    """Set sig_count and drop gate for one cycle to trigger accumulation."""
    dut.sig_count.value = count
    dut.gate.value = 0
    await RisingEdge(dut.clk)

async def close_ref_window(dut, count):
    """Set ref_count and drop ref_gate for one cycle to trigger accumulation."""
    dut.ref_count.value = count
    dut.ref_gate.value = 0
    await RisingEdge(dut.clk)

async def read_mem(dut, addr):
    """Read sig and ref accumulated values at freq_index addr."""
    dut.rd_addr.value = addr
    await ClockCycles(dut.clk, 2)  # registered read: 1 cycle latency + 1 margin
    return int(dut.rd_sig.value), int(dut.rd_ref.value)

async def pulse_sweep_done(dut):
    dut.sweep_point_done.value = 1
    await RisingEdge(dut.clk)
    dut.sweep_point_done.value = 0

# ── Tests ────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_single_shot_signal(dut):
    """Single shot: signal counts accumulate correctly at freq_index 0."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    # Open signal window
    dut.gate.value = 1
    await ClockCycles(dut.clk, 5)

    # Close window with count = 42
    await close_sig_window(dut, 42)

    # Wait for RMW pipeline (3 cycles)
    await ClockCycles(dut.clk, 4)

    sig, ref = await read_mem(dut, 0)
    assert sig == 42, f"signal: expected 42, got {sig}"
    assert ref == 0,  f"ref should be 0, got {ref}"

@cocotb.test()
async def test_single_shot_reference(dut):
    """Single shot: reference counts accumulate correctly at freq_index 0."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    # Open reference window
    dut.ref_gate.value = 1
    await ClockCycles(dut.clk, 5)

    # Close window with count = 17
    await close_ref_window(dut, 17)

    await ClockCycles(dut.clk, 4)

    sig, ref = await read_mem(dut, 0)
    assert sig == 0,  f"signal should be 0, got {sig}"
    assert ref == 17, f"reference: expected 17, got {ref}"

@cocotb.test()
async def test_accumulation_multi_shot(dut):
    """Multiple shots: counts accumulate (not overwrite) across shots."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    shots = [10, 20, 30]  # 3 shots, expected sum = 60

    for count in shots:
        dut.gate.value = 1
        await ClockCycles(dut.clk, 3)
        await close_sig_window(dut, count)
        await ClockCycles(dut.clk, 4)  # let RMW complete before next shot

    sig, _ = await read_mem(dut, 0)
    assert sig == 60, f"accumulated signal: expected 60, got {sig}"

@cocotb.test()
async def test_freq_index_advances(dut):
    """sweep_point_done advances freq_index; each point accumulates independently."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    # Freq point 0: sig=100
    dut.gate.value = 1
    await ClockCycles(dut.clk, 2)
    await close_sig_window(dut, 100)
    await ClockCycles(dut.clk, 4)
    await pulse_sweep_done(dut)
    await RisingEdge(dut.clk)

    assert int(dut.freq_index.value) == 1, f"freq_index should be 1, got {dut.freq_index.value}"

    # Freq point 1: sig=200
    dut.gate.value = 1
    await ClockCycles(dut.clk, 2)
    await close_sig_window(dut, 200)
    await ClockCycles(dut.clk, 4)

    sig0, _ = await read_mem(dut, 0)
    sig1, _ = await read_mem(dut, 1)
    assert sig0 == 100, f"freq[0] signal: expected 100, got {sig0}"
    assert sig1 == 200, f"freq[1] signal: expected 200, got {sig1}"

@cocotb.test()
async def test_run_resets_pointer(dut):
    """Asserting run resets freq_index back to 0."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    # Advance pointer to 2
    await pulse_sweep_done(dut)
    await RisingEdge(dut.clk)
    await pulse_sweep_done(dut)
    await RisingEdge(dut.clk)

    assert int(dut.freq_index.value) == 2, f"freq_index should be 2, got {dut.freq_index.value}"

    # Run resets pointer
    dut.sweep_start.value = 1
    await RisingEdge(dut.clk)
    dut.sweep_start.value = 0
    await RisingEdge(dut.clk)

    assert int(dut.freq_index.value) == 0, f"freq_index should be 0 after run, got {dut.freq_index.value}"
