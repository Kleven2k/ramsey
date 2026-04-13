import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, ClockCycles

CLK_PERIOD_NS = 10  # 100 MHz
# Wrapper uses CLK_DIV=2, LE_CYCLES=2 → SCLK period = 4 system cycles

# ── Helpers ───────────────────────────────────────────────────────────────────

async def reset(dut):
    dut.rst.value   = 1
    dut.data.value  = 0
    dut.start.value = 0
    await ClockCycles(dut.clk, 4)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

async def capture_spi_bits(dut, n_bits=32):
    """Sample sdata on every SCLK rising edge, return as integer MSB-first."""
    bits = []
    for _ in range(n_bits):
        await RisingEdge(dut.sclk)
        bits.append(int(dut.sdata.value))
    value = 0
    for b in bits:
        value = (value << 1) | b
    return value

# ── Tests ────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_transfer_data(dut):
    """Verify 32 bits are shifted out MSB-first and match the input word."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    TEST_WORD = 0xDEADBEEF

    dut.data.value  = TEST_WORD
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0

    received = await capture_spi_bits(dut, 32)
    assert received == TEST_WORD, f"expected 0x{TEST_WORD:08X}, got 0x{received:08X}"

@cocotb.test()
async def test_busy_and_done(dut):
    """busy goes high on start, done pulses for one cycle after LE falls."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    assert dut.busy.value == 0, "busy should be low before start"

    dut.data.value  = 0xA5A5A5A5
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0

    await ClockCycles(dut.clk, 1)
    assert dut.busy.value == 1, "busy should be high during transfer"

    await RisingEdge(dut.done)
    await RisingEdge(dut.clk)
    assert dut.busy.value == 0, "busy should be low after done"

@cocotb.test()
async def test_le_pulse(dut):
    """LE pulses high after the last bit and returns low before done."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.data.value  = 0x00000001
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0

    # Wait for LE to go high
    await RisingEdge(dut.le)
    # LE must fall before done
    await FallingEdge(dut.le)
    await RisingEdge(dut.done)  # done comes after LE falls

@cocotb.test()
async def test_sclk_idle_low(dut):
    """SCLK is low when idle (SPI mode 0)."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    await ClockCycles(dut.clk, 5)
    assert dut.sclk.value == 0, f"SCLK should be low in idle, got {dut.sclk.value}"

@cocotb.test()
async def test_zero_word(dut):
    """All-zero word: sdata stays low for all 32 bits."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.data.value  = 0x00000000
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0

    received = await capture_spi_bits(dut, 32)
    assert received == 0, f"expected 0x00000000, got 0x{received:08X}"

@cocotb.test()
async def test_ones_word(dut):
    """All-ones word: sdata stays high for all 32 bits."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.data.value  = 0xFFFFFFFF
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0

    received = await capture_spi_bits(dut, 32)
    assert received == 0xFFFFFFFF, f"expected 0xFFFFFFFF, got 0x{received:08X}"

@cocotb.test()
async def test_back_to_back(dut):
    """Two consecutive transfers produce correct data for both words."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    WORD1 = 0x12345678
    WORD2 = 0x9ABCDEF0

    # First transfer
    dut.data.value  = WORD1
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0
    r1 = await capture_spi_bits(dut, 32)
    await RisingEdge(dut.done)

    # Second transfer immediately after done
    dut.data.value  = WORD2
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0
    r2 = await capture_spi_bits(dut, 32)
    await RisingEdge(dut.done)

    assert r1 == WORD1, f"word1: expected 0x{WORD1:08X}, got 0x{r1:08X}"
    assert r2 == WORD2, f"word2: expected 0x{WORD2:08X}, got 0x{r2:08X}"
