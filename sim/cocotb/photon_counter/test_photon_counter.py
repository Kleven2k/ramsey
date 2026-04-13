import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles


CLK_PERIOD_NS = 10  # 100 MHz


async def reset(dut):
    dut.rst.value    = 1
    dut.apd_in.value = 0
    dut.gate.value   = 0
    dut.clear.value  = 0
    await ClockCycles(dut.clk, 4)
    dut.rst.value = 0
    await RisingEdge(dut.clk)


async def send_pulses(dut, n, period_cycles=10):
    """Send n TTL pulses on apd_in. Each pulse is 1 cycle high."""
    for _ in range(n):
        dut.apd_in.value = 1
        await ClockCycles(dut.clk, 1)
        dut.apd_in.value = 0
        await ClockCycles(dut.clk, period_cycles - 1)

# ── Tests ────────────────────────────────────────────────────

@cocotb.test()
async def test_basic_count(dut):
    """Count N pulses during gate window, verify count == N after gate closes."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    n = 10
    dut.gate.value = 1
    await send_pulses(dut, n)
    dut.gate.value = 0
    await ClockCycles(dut.clk, 4)

    assert dut.count.value == n, f"Expected {n}, got {dut.count.value}"


@cocotb.test()
async def test_gate_inhibit(dut):
    """Pulses sent with gate low must not increment count."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.gate.value = 0
    await send_pulses(dut, 10)
    await ClockCycles(dut.clk, 4)

    assert dut.count.value == 0, f"Expected 0, got {dut.count.value}"


@cocotb.test()
async def test_hold_after_gate(dut):
    """Count must hold stable after gate goes low — no spurious increments."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.gate.value = 1
    await send_pulses(dut, 5)
    dut.gate.value = 0

    count_at_close = dut.count.value.integer
    await send_pulses(dut, 5)  # more pulses with gate low
    await ClockCycles(dut.clk, 4)

    assert dut.count.value == count_at_close, (
        f"Count changed after gate closed: {count_at_close} -> {dut.count.value}"
    )


@cocotb.test()
async def test_clear(dut):
    """Clear resets count to zero; counting resumes correctly after."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.gate.value = 1
    await send_pulses(dut, 5)

    dut.clear.value = 1
    await ClockCycles(dut.clk, 2)
    dut.clear.value = 0
    await ClockCycles(dut.clk, 2)

    assert dut.count.value == 0, f"Expected 0 after clear, got {dut.count.value}"

    await send_pulses(dut, 3)
    dut.gate.value = 0
    await ClockCycles(dut.clk, 4)

    assert dut.count.value == 3, f"Expected 3 after resume, got {dut.count.value}"


@cocotb.test()
async def test_max_rate(dut):
    """Drive pulses at 10 MHz (every 10 cycles). All should be counted."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    n = 20
    dut.gate.value = 1
    await send_pulses(dut, n, period_cycles=10)
    dut.gate.value = 0
    await ClockCycles(dut.clk, 4)

    assert dut.count.value == n, f"Expected {n}, got {dut.count.value}"
