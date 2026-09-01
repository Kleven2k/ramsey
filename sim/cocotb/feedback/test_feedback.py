import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, ClockCycles

CLK_PERIOD_NS = 10  # 100 MHz


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def reset(dut):
    dut.rst.value = 1
    await ClockCycles(dut.clk, 4)
    dut.rst.value = 0
    await RisingEdge(dut.clk)


async def pulse_gate(dut, cycles):
    """Assert gate_in high for `cycles` clock cycles then drop it."""
    dut.gate_in.value = 1
    await ClockCycles(dut.clk, cycles)
    dut.gate_in.value = 0
    await RisingEdge(dut.clk)


# ---------------------------------------------------------------------------
# state_discriminator tests
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_disc_bright(dut):
    """Count above threshold → spin_state=1 (bright), valid pulses for 1 cycle."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.count.value     = 500
    dut.threshold.value = 400
    dut.gate_in.value   = 0

    # Open and close readout window
    await pulse_gate(dut, 5)

    # valid should pulse this cycle
    assert dut.valid.value == 1,      "valid should be 1 on gate falling edge"
    assert dut.spin_state.value == 1, "count>threshold → bright (|0⟩)"

    await RisingEdge(dut.clk)
    assert dut.valid.value == 0, "valid should clear after 1 cycle"


@cocotb.test()
async def test_disc_dark(dut):
    """Count below threshold → spin_state=0 (dark), correction needed."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.count.value     = 200
    dut.threshold.value = 400
    dut.gate_in.value   = 0

    await pulse_gate(dut, 5)

    assert dut.valid.value == 1,      "valid should pulse"
    assert dut.spin_state.value == 0, "count<threshold → dark (|1⟩)"


@cocotb.test()
async def test_disc_exactly_threshold(dut):
    """Count equal to threshold → bright (> is strict)."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.count.value     = 400
    dut.threshold.value = 400
    dut.gate_in.value   = 0

    await pulse_gate(dut, 5)

    assert dut.spin_state.value == 0, "count==threshold → dark (strict >)"


@cocotb.test()
async def test_disc_no_trigger_without_gate(dut):
    """valid must not assert unless gate_in falls."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.count.value     = 9999
    dut.threshold.value = 100
    dut.gate_in.value   = 0

    await ClockCycles(dut.clk, 10)
    assert dut.valid.value == 0, "valid must not assert without gate transition"


@cocotb.test()
async def test_disc_multiple_windows(dut):
    """Valid fires on each gate falling edge independently."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.threshold.value = 300
    dut.gate_in.value   = 0

    # First window — bright
    dut.count.value = 500
    await pulse_gate(dut, 4)
    assert dut.spin_state.value == 1, "first window: bright"

    await ClockCycles(dut.clk, 3)

    # Second window — dark
    dut.count.value = 100
    await pulse_gate(dut, 4)
    assert dut.spin_state.value == 0, "second window: dark"


# ---------------------------------------------------------------------------
# feedback_ctrl tests
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_fb_no_correction_when_bright(dut):
    """spin_state=1 (bright) → no correction pulse fired."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.enable.value         = 1
    dut.correction_dur.value = 10
    dut.spin_state.value     = 1
    dut.valid.value          = 0

    # Pulse valid
    dut.valid.value = 1
    await RisingEdge(dut.clk)
    dut.valid.value = 0

    await ClockCycles(dut.clk, 5)
    assert dut.mw_correction.value == 0, "no correction when spin_state=1"
    assert dut.busy.value == 0,          "not busy when bright"


@cocotb.test()
async def test_fb_correction_when_dark(dut):
    """spin_state=0 (dark) → correction pulse fires for correction_dur cycles."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    CORR_DUR = 8
    dut.enable.value         = 1
    dut.correction_dur.value = CORR_DUR
    dut.spin_state.value     = 0
    dut.valid.value          = 0

    # Trigger
    dut.valid.value = 1
    await RisingEdge(dut.clk)
    dut.valid.value = 0

    # mw_correction should be high immediately
    assert dut.mw_correction.value == 1, "correction should start"
    assert dut.busy.value == 1,          "busy during correction"

    # Count high cycles
    count = 1
    for _ in range(CORR_DUR + 5):
        await RisingEdge(dut.clk)
        if dut.mw_correction.value == 1:
            count += 1
        else:
            break

    assert count == CORR_DUR, f"correction_dur: expected {CORR_DUR}, got {count}"
    assert dut.busy.value == 0, "not busy after correction"


@cocotb.test()
async def test_fb_disabled(dut):
    """enable=0 → no correction even when dark."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.enable.value         = 0
    dut.correction_dur.value = 10
    dut.spin_state.value     = 0
    dut.valid.value          = 1
    await RisingEdge(dut.clk)
    dut.valid.value = 0

    await ClockCycles(dut.clk, 5)
    assert dut.mw_correction.value == 0, "no correction when disabled"


# ---------------------------------------------------------------------------
# latency_counter tests
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_lc_measures_latency(dut):
    """Latency counter measures cycles between gate falling edge and mw_correction rise."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.gate_in.value      = 0
    dut.mw_correction.value = 0

    EXPECTED_LATENCY = 5

    # Open then close gate
    dut.gate_in.value = 1
    await ClockCycles(dut.clk, 3)
    dut.gate_in.value = 0
    await RisingEdge(dut.clk)  # counter starts here

    # Wait EXPECTED_LATENCY cycles then fire correction
    await ClockCycles(dut.clk, EXPECTED_LATENCY)
    dut.mw_correction.value = 1
    await RisingEdge(dut.clk)
    dut.mw_correction.value = 0

    await RisingEdge(dut.clk)

    assert dut.latency_valid.value == 1, "latency_valid should pulse"
    measured = int(dut.latency_cycles.value)
    assert measured == EXPECTED_LATENCY, \
        f"latency: expected {EXPECTED_LATENCY}, got {measured}"


@cocotb.test()
async def test_lc_no_correction_no_latch(dut):
    """If correction never fires, latency_valid stays 0."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.gate_in.value       = 0
    dut.mw_correction.value = 0

    dut.gate_in.value = 1
    await ClockCycles(dut.clk, 3)
    dut.gate_in.value = 0

    await ClockCycles(dut.clk, 20)
    assert dut.latency_valid.value == 0, "latency_valid should stay 0 with no correction"


@cocotb.test()
async def test_lc_rearms_after_measurement(dut):
    """Counter rearms after first measurement for the next gate event."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.gate_in.value       = 0
    dut.mw_correction.value = 0

    for expected in [3, 7]:
        dut.gate_in.value = 1
        await ClockCycles(dut.clk, 2)
        dut.gate_in.value = 0
        await RisingEdge(dut.clk)

        await ClockCycles(dut.clk, expected)
        dut.mw_correction.value = 1
        await RisingEdge(dut.clk)
        dut.mw_correction.value = 0
        await RisingEdge(dut.clk)

        measured = int(dut.latency_cycles.value)
        assert measured == expected, f"expected {expected}, got {measured}"
        await ClockCycles(dut.clk, 5)