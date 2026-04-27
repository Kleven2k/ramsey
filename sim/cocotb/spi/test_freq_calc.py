import math
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles

CLK_PERIOD_NS = 10  # 100 MHz

FREF_KHZ  = 25_000
FIXED_MOD = 1_000

R2_CFG = 0x18004E42
R3_CFG = 0x008004B3
R4_BASE = 0x008FA03C
R5_CFG = 0x00580005

# ── Reference model ───────────────────────────────────────────────────────────

def expected_values(freq_khz):
    """Compute expected INT, FRAC, MOD (GCD-reduced), OUTDIV for a given frequency in kHz."""
    for d_sel, d_val in enumerate([1, 2, 4, 8, 16, 32, 64]):
        fvco = freq_khz * d_val
        if 2_200_000 <= fvco <= 4_400_000:
            break
    INT  = fvco // FREF_KHZ
    rem  = fvco % FREF_KHZ
    FRAC = (rem * FIXED_MOD) // FREF_KHZ
    MOD  = FIXED_MOD
    if FRAC > 0:
        g = math.gcd(FRAC, MOD)
        FRAC //= g
        MOD  //= g
    return INT, FRAC, MOD, d_sel

# ── Helpers ───────────────────────────────────────────────────────────────────

async def reset(dut):
    dut.rst.value      = 1
    dut.freq_khz.value = 0
    dut.start.value    = 0
    await ClockCycles(dut.clk, 4)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

async def calculate(dut, freq_khz):
    """Drive freq_khz, pulse start, wait for done, return (r0,r1,r4)."""
    dut.freq_khz.value = freq_khz
    dut.start.value    = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0
    await RisingEdge(dut.done)
    await RisingEdge(dut.clk)  # let outputs settle
    return int(dut.r0.value), int(dut.r1.value), int(dut.r4.value)

# ── Tests ────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_integer_n_1350mhz(dut):
    """1350 MHz — clean integer-N (no fractional part)."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    freq = 1_350_000  # kHz
    INT, FRAC, MOD, d_sel = expected_values(freq)
    # fvco = 2700 MHz, INT=108, FRAC=0, OUTDIV=÷2 (d_sel=1)
    assert INT == 108 and FRAC == 0 and d_sel == 1

    r0, r1, r4 = await calculate(dut, freq)

    got_int  = (r0 >> 15) & 0xFFFF
    got_frac = (r0 >>  3) & 0xFFF
    got_outdiv = (r4 >> 20) & 0x7

    assert got_int   == INT,   f"INT: expected {INT}, got {got_int}"
    assert got_frac  == FRAC,  f"FRAC: expected {FRAC}, got {got_frac}"
    assert got_outdiv == d_sel, f"OUTDIV: expected {d_sel}, got {got_outdiv}"

@cocotb.test()
async def test_fractional_n(dut):
    """1350.050 MHz — FRAC != 0."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    freq = 1_350_050  # kHz — 50 kHz above 1350 MHz
    INT, FRAC, MOD, d_sel = expected_values(freq)
    # fvco=2700100, INT=108, raw FRAC=4, MOD=1000 → GCD(4,1000)=4 → FRAC=1, MOD=250
    assert INT == 108 and FRAC == 1 and MOD == 250 and d_sel == 1

    r0, _, _ = await calculate(dut, freq)

    got_int  = (r0 >> 15) & 0xFFFF
    got_frac = (r0 >>  3) & 0xFFF

    assert got_int  == INT,  f"INT: expected {INT}, got {got_int}"
    assert got_frac == FRAC, f"FRAC: expected {FRAC}, got {got_frac}"

@cocotb.test()
async def test_outdiv_4(dut):
    """800 MHz output — needs ÷4 divider (OUTDIV sel = 2)."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    freq = 800_000  # kHz → fvco = 3200 MHz with ÷4
    INT, FRAC, MOD, d_sel = expected_values(freq)
    assert d_sel == 2  # ÷4

    r0, _, r4 = await calculate(dut, freq)

    got_int    = (r0 >> 15) & 0xFFFF
    got_outdiv = (r4 >> 20) & 0x7

    assert got_int    == INT,   f"INT: expected {INT}, got {got_int}"
    assert got_outdiv == d_sel, f"OUTDIV sel: expected {d_sel}, got {got_outdiv}"

@cocotb.test()
async def test_r1_mod_packed(dut):
    """R1 always contains MOD=1000 and PHASE=1."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    _, r1, _ = await calculate(dut, 1_350_000)

    got_mod   = (r1 >> 3) & 0xFFF
    got_phase = (r1 >> 15) & 0xFFF
    got_addr  = r1 & 0x7

    # 1350 MHz is integer-N (FRAC=0) so GCD reduction is skipped, MOD stays 1000
    assert got_mod   == 1000, f"MOD in R1: expected 1000, got {got_mod}"
    assert got_phase == 1,    f"PHASE in R1: expected 1, got {got_phase}"
    assert got_addr  == 1,    f"R1 addr bits: expected 1, got {got_addr}"

@cocotb.test()
async def test_r4_base_preserved(dut):
    """R4 base bits outside [22:20] are unchanged from R4_BASE=0x00859CC4."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    OUTDIV_MASK = 0x00700000  # bits [22:20]

    _, _, r4 = await calculate(dut, 1_350_000)

    # Non-divider bits must match R4_BASE
    assert (r4 & ~OUTDIV_MASK) == (R4_BASE & ~OUTDIV_MASK), \
        f"R4 base bits corrupted: expected 0x{R4_BASE & ~OUTDIV_MASK:08X}, got 0x{r4 & ~OUTDIV_MASK:08X}"

@cocotb.test()
async def test_fixed_registers(dut):
    """R2, R3, R5 match the configured parameters."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    await calculate(dut, 1_350_000)

    assert int(dut.r2.value) == R2_CFG, f"R2: got 0x{int(dut.r2.value):08X}"
    assert int(dut.r3.value) == R3_CFG, f"R3: got 0x{int(dut.r3.value):08X}"
    assert int(dut.r5.value) == R5_CFG, f"R5: got 0x{int(dut.r5.value):08X}"

@cocotb.test()
async def test_sequential_calculations(dut):
    """Two back-to-back calculations produce independent correct results."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    for freq in [1_350_000, 1_360_000]:
        INT, FRAC, _, d_sel = expected_values(freq)
        r0, _, r4 = await calculate(dut, freq)

        got_int    = (r0 >> 15) & 0xFFFF
        got_frac   = (r0 >>  3) & 0xFFF
        got_outdiv = (r4 >> 20) & 0x7

        assert got_int    == INT,   f"freq={freq}: INT expected {INT}, got {got_int}"
        assert got_frac   == FRAC,  f"freq={freq}: FRAC expected {FRAC}, got {got_frac}"
        assert got_outdiv == d_sel, f"freq={freq}: OUTDIV expected {d_sel}, got {got_outdiv}"
