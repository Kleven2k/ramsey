import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles

CLK_PERIOD_NS = 10  # 100 MHz

# ── Helpers ───────────────────────────────────────────────────────────────────

async def reset(dut):
    dut.rst.value         = 1
    dut.run.value         = 0
    dut.n_shots.value     = 0
    dut.spi_ready.value   = 0
    dut.init_dur.value    = 0
    dut.mw_dur.value      = 0
    dut.dead_time.value   = 0
    dut.readout_dur.value = 0
    dut.ref_dur.value     = 0
    await ClockCycles(dut.clk, 4)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

async def count_high_cycles(dut, signal):
    """Wait for signal to go high, count consecutive cycles it stays high."""
    await RisingEdge(signal)
    count = 0
    while signal.value == 1:
        await RisingEdge(dut.clk)
        count += 1
    return count

async def pulse_run(dut):
    """Assert run for one clock cycle."""
    dut.run.value = 1
    await RisingEdge(dut.clk)
    dut.run.value = 0

# ── Tests ────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_cw_single_shot(dut):
    """CW ODMR single shot: verify laser_gate, mw_gate, and gate durations."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.n_shots.value     = 1
    dut.init_dur.value    = 5
    dut.mw_dur.value      = 4
    dut.dead_time.value   = 0
    dut.readout_dur.value = 6
    dut.ref_dur.value     = 3

    await pulse_run(dut)

    laser_cycles = await count_high_cycles(dut, dut.laser_gate)
    assert laser_cycles == 5, f"init_dur: expected 5, got {laser_cycles}"

    mw_cycles = await count_high_cycles(dut, dut.mw_gate)
    assert mw_cycles == 8, f"mw_gate (MW1+MW2): expected 8, got {mw_cycles}"

    gate_cycles = await count_high_cycles(dut, dut.gate)
    assert gate_cycles == 6, f"readout_dur: expected 6, got {gate_cycles}"

    await RisingEdge(dut.sweep_point_done)

@cocotb.test()
async def test_shot_loop(dut):
    """n_shots=3: verify counter_clear fires 3 times, sweep_point_done fires once."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.n_shots.value     = 3
    dut.init_dur.value    = 4
    dut.mw_dur.value      = 3
    dut.dead_time.value   = 0
    dut.readout_dur.value = 4
    dut.ref_dur.value     = 3

    done_count  = 0
    clear_count = 0

    async def count_done():
        nonlocal done_count
        while True:
            await RisingEdge(dut.sweep_point_done)
            done_count += 1

    async def count_clear():
        nonlocal clear_count
        while True:
            await RisingEdge(dut.counter_clear)
            clear_count += 1

    cocotb.start_soon(count_done())
    cocotb.start_soon(count_clear())

    await pulse_run(dut)
    await RisingEdge(dut.sweep_point_done)
    await ClockCycles(dut.clk, 2)

    assert done_count  == 1, f"sweep_point_done: expected 1, got {done_count}"
    assert clear_count == 3, f"counter_clear: expected 3, got {clear_count}"

@cocotb.test()
async def test_ramsey(dut):
    """Ramsey: verify dead_time gap between MW1 falling and MW2 rising."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.n_shots.value     = 1
    dut.init_dur.value    = 4
    dut.mw_dur.value      = 5
    dut.dead_time.value   = 8
    dut.readout_dur.value = 4
    dut.ref_dur.value     = 3

    await pulse_run(dut)

    # Skip init pulse
    await count_high_cycles(dut, dut.laser_gate)

    # MW1 high for mw_dur cycles
    mw1_cycles = await count_high_cycles(dut, dut.mw_gate)
    assert mw1_cycles == 5, f"MW1 duration: expected 5, got {mw1_cycles}"

    # Count cycles between MW1 falling and MW2 rising (dead_time)
    gap = 0
    while True:
        await RisingEdge(dut.clk)
        if dut.mw_gate.value == 1:
            break
        gap += 1
    assert gap == 8, f"dead_time gap: expected 8, got {gap}"

    # mw_gate is already high (gap loop exited on the rising edge).
    # Count remaining high cycles directly instead of using count_high_cycles
    # (which would wait for the next 0→1 transition and miss this pulse).
    # Gap loop already consumed the first high cycle of MW2 (the break edge).
    mw2_cycles = 1
    while dut.mw_gate.value == 1:
        await RisingEdge(dut.clk)
        mw2_cycles += 1
    assert mw2_cycles == 5, f"MW2 duration: expected 5, got {mw2_cycles}"

@cocotb.test()
async def test_counter_clear(dut):
    """Verify counter_clear pulses exactly once per shot and never outside shots."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.n_shots.value     = 3
    dut.init_dur.value    = 4
    dut.mw_dur.value      = 3
    dut.dead_time.value   = 0
    dut.readout_dur.value = 4
    dut.ref_dur.value     = 3

    clear_count = 0

    async def count_clear():
        nonlocal clear_count
        while True:
            await RisingEdge(dut.counter_clear)
            clear_count += 1

    cocotb.start_soon(count_clear())

    await pulse_run(dut)
    await RisingEdge(dut.sweep_point_done)
    await ClockCycles(dut.clk, 2)

    assert clear_count == 3, f"counter_clear: expected 3 (one per shot), got {clear_count}"

@cocotb.test()
async def test_busy(dut):
    """Verify busy goes high on run and low when returning to IDLE."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.n_shots.value     = 1
    dut.init_dur.value    = 4
    dut.mw_dur.value      = 3
    dut.dead_time.value   = 0
    dut.readout_dur.value = 4
    dut.ref_dur.value     = 3

    assert dut.busy.value == 0, "busy should be low before run"

    await pulse_run(dut)
    await ClockCycles(dut.clk, 1)

    assert dut.busy.value == 1, "busy should be high after run"

    await RisingEdge(dut.sweep_point_done)
    await ClockCycles(dut.clk, 2)  # sweep_point_done and IDLE transition latch together;
                                    # IDLE sets busy=0 on the following cycle

    assert dut.busy.value == 0, "busy should be low after sweep_point_done"
