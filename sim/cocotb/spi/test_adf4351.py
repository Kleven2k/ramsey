import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles

CLK_PERIOD_NS = 10  # 100 MHz
# Wrapper: CLK_DIV=2 → SCLK period = 4 cycles, 32 bits → 32*4 = 128 cycles per register
# LE_CYCLES=2, DONE_ST=1 → ~3 extra cycles per register
# 6 registers * ~131 cycles ≈ 786 cycles total shift time

# ── Helpers ───────────────────────────────────────────────────────────────────

async def reset(dut):
    dut.rst.value          = 1
    dut.load.value         = 0
    dut.lock_detect.value  = 0
    for reg in [dut.r0, dut.r1, dut.r2, dut.r3, dut.r4, dut.r5]:
        reg.value = 0
    await ClockCycles(dut.clk, 4)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

async def capture_le_words(dut, n=6):
    """Capture n 32-bit words by sampling sdata on SCLK rising edges,
    recording each word at the LE rising edge."""
    words = []
    for _ in range(n):
        bits = []
        for _ in range(32):
            await RisingEdge(dut.sclk)
            bits.append(int(dut.sdata.value))
        word = 0
        for b in bits:
            word = (word << 1) | b
        await RisingEdge(dut.le)
        words.append(word)
    return words

# ── Tests ────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_six_registers_sent(dut):
    """All 6 registers are transmitted — verified by counting LE pulses."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    for reg, val in [(dut.r5, 0x00580005),
                     (dut.r4, 0x00859CC4),
                     (dut.r3, 0x000004B3),
                     (dut.r2, 0x00004E42),
                     (dut.r1, 0x08008011),
                     (dut.r0, 0x00350000)]:
        reg.value = val

    dut.load.value = 1
    await RisingEdge(dut.clk)
    dut.load.value = 0

    le_count = 0
    async def count_le():
        nonlocal le_count
        while True:
            await RisingEdge(dut.le)
            le_count += 1

    cocotb.start_soon(count_le())

    # Wait long enough for all 6 transfers + debounce
    await ClockCycles(dut.clk, 1200)

    assert le_count == 6, f"expected 6 LE pulses, got {le_count}"

@cocotb.test()
async def test_register_order(dut):
    """Registers are sent R5 first, R0 last (ADF4351 requirement)."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    # Use distinct values with address bits embedded (lower 3 bits = reg index)
    R = [0x00350000,   # r0: addr=0
         0x08008011,   # r1: addr=1
         0x00004E42,   # r2: addr=2
         0x000004B3,   # r3: addr=3
         0x00859CC4,   # r4: addr=4
         0x00580005]   # r5: addr=5

    dut.r0.value, dut.r1.value, dut.r2.value = R[0], R[1], R[2]
    dut.r3.value, dut.r4.value, dut.r5.value = R[3], R[4], R[5]

    dut.load.value = 1
    await RisingEdge(dut.clk)
    dut.load.value = 0

    words = await capture_le_words(dut, 6)

    expected_order = [R[5], R[4], R[3], R[2], R[1], R[0]]
    for i, (got, exp) in enumerate(zip(words, expected_order)):
        assert got == exp, f"transfer {i}: expected 0x{exp:08X}, got 0x{got:08X}"

@cocotb.test()
async def test_busy_during_transfer(dut):
    """busy is high from load until spi_ready."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    assert dut.busy.value == 0, "busy should be low before load"

    dut.load.value = 1
    await RisingEdge(dut.clk)
    dut.load.value = 0
    await ClockCycles(dut.clk, 1)

    assert dut.busy.value == 1, "busy should be high after load"

    # Assert lock_detect after registers are sent
    await ClockCycles(dut.clk, 900)
    dut.lock_detect.value = 1

    await RisingEdge(dut.spi_ready)
    await ClockCycles(dut.clk, 1)  # busy=0 and spi_ready=1 latch together; IDLE clears busy next cycle
    assert dut.busy.value == 0, "busy should be low after spi_ready"

@cocotb.test()
async def test_debounce(dut):
    """spi_ready does not assert if lock_detect glitches before debounce completes."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.load.value = 1
    await RisingEdge(dut.clk)
    dut.load.value = 0

    # Wait for all registers to be sent
    await ClockCycles(dut.clk, 900)

    # Glitch: assert then deassert lock_detect before DEBOUNCE_CYCLES (8) complete
    dut.lock_detect.value = 1
    await ClockCycles(dut.clk, 4)   # only 4 of 8 debounce cycles
    dut.lock_detect.value = 0
    await ClockCycles(dut.clk, 2)

    assert dut.spi_ready.value == 0, "spi_ready should not assert on glitch"

    # Now hold lock_detect stable — should lock properly
    dut.lock_detect.value = 1
    await RisingEdge(dut.spi_ready)  # should arrive after 8 stable cycles

@cocotb.test()
async def test_ready_then_idle(dut):
    """After spi_ready pulses, controller returns to IDLE for next load."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.lock_detect.value = 1  # pre-assert so debounce completes quickly

    dut.load.value = 1
    await RisingEdge(dut.clk)
    dut.load.value = 0

    await RisingEdge(dut.spi_ready)
    await ClockCycles(dut.clk, 2)

    assert dut.busy.value == 0,      "busy should be low after ready"
    assert dut.spi_ready.value == 0, "spi_ready should be single-cycle"
