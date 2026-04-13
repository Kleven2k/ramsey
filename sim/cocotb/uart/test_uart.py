import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, ClockCycles

CLK_PERIOD_NS = 10  # 100 MHz

CLK_FREQ  = 100_000_000
BAUD      = 115_200
BIT_TICKS = CLK_FREQ // BAUD  # 868 cycles per bit

# ── Helpers ───────────────────────────────────────────────────────────────────

async def reset(dut):
    """Assert reset for 4 cycles, deassert, then wait one more rising edge."""
    dut.rst.value             = 1
    dut.rx_pin.value          = 1  # idle high (no incoming byte)
    dut.tx_send.value         = 0
    dut.tx_msg_type.value     = 0
    dut.tx_msg_len.value      = 0
    dut.tx_payload_byte.value = 0
    await ClockCycles(dut.clk, 4)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

async def uart_send_byte(dut, byte):
    """Drive one byte onto rx_pin with correct UART framing (LSB first)."""
    dut.rx_pin.value = 0                    # start bit
    await ClockCycles(dut.clk, BIT_TICKS)
    for i in range(8):                      # 8 data bits, LSB first
        dut.rx_pin.value = (byte >> i) & 1
        await ClockCycles(dut.clk, BIT_TICKS)
    dut.rx_pin.value = 1                    # stop bit
    await ClockCycles(dut.clk, BIT_TICKS)

async def uart_recv_byte(dut):
    """Wait for a falling edge on tx_pin, then sample the 8 data bits at mid-bit.

    Sampling is offset by BIT_TICKS//2 after the start-bit edge so we land
    in the centre of each subsequent bit, matching what uart_rx does on the
    RX path.
    """
    await FallingEdge(dut.tx_pin)                 # wait for start bit
    await ClockCycles(dut.clk, BIT_TICKS // 2)   # advance to centre of start bit
    byte = 0
    for i in range(8):
        await ClockCycles(dut.clk, BIT_TICKS)    # advance to centre of data bit
        byte |= int(dut.tx_pin.value) << i        # LSB first
    await ClockCycles(dut.clk, BIT_TICKS)        # consume stop bit
    return byte

async def uart_send_packet(dut, msg_type, payload=None):
    """Send a complete framed packet on rx_pin.

    Frame layout: [0xAA][TYPE][LEN_HI][LEN_LO][PAYLOAD...][CRC]
    CRC = XOR of all payload bytes (header/type/length not included).
    """
    if payload is None:
        payload = []
    crc = 0
    for b in payload:
        crc ^= b
    length = len(payload)
    for byte in [0xAA, msg_type, (length >> 8) & 0xFF, length & 0xFF] + payload + [crc]:
        await uart_send_byte(dut, byte)

async def uart_recv_packet(dut):
    """Receive a complete framed packet from tx_pin.

    Scans for the 0xAA header byte, then reads type, 2-byte length,
    payload, and CRC. Returns (msg_type, payload_bytes, crc_ok).
    """
    # Discard bytes until we see the 0xAA header
    while True:
        b = await uart_recv_byte(dut)
        if b == 0xAA:
            break
    msg_type = await uart_recv_byte(dut)
    len_hi   = await uart_recv_byte(dut)
    len_lo   = await uart_recv_byte(dut)
    length   = (len_hi << 8) | len_lo
    # await inside a list comprehension is valid in Python and runs sequentially
    payload  = [await uart_recv_byte(dut) for _ in range(length)]
    crc_rx   = await uart_recv_byte(dut)
    crc_calc = 0
    for b in payload:
        crc_calc ^= b
    return msg_type, payload, (crc_rx == crc_calc)


# ── Tests ────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_tx_byte(dut):
    """Basic TX smoke test: send a zero-payload ACK and verify it round-trips."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.tx_msg_type.value = 0x04    # ACK — no payload
    dut.tx_msg_len.value  = 0
    dut.tx_send.value     = 1
    await RisingEdge(dut.clk)
    dut.tx_send.value     = 0

    msg_type, payload, crc_ok = await uart_recv_packet(dut)

    assert msg_type == 0x04
    assert payload  == []
    assert crc_ok

@cocotb.test()
async def test_rx_byte(dut):
    """Send a single raw byte on rx_pin; verify no simulation error occurs.

    No output signal is asserted for a bare 0xAA byte — the RX FSM moves to
    RX_GET_TYPE and waits for the next byte. Inspect the VCD for internal
    state if a deeper check is needed.
    """
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    await uart_send_byte(dut, 0xAA)
    await ClockCycles(dut.clk, 4)

@cocotb.test()
async def test_rx_packet(dut):
    """Send a valid 3-byte CONFIG packet; verify msg_type and length are latched.

    Note: rx_payload_byte is a streaming signal (one cycle per byte). Only
    msg_type and rx_msg_len are checked here; inspect the VCD for the byte
    stream if needed.
    """
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    async def wait_crc():
        await RisingEdge(dut.rx_crc_ok)

    payload = [0x04, 0x05, 0x06]
    # Start listening for rx_crc_ok BEFORE sending — it is a single-cycle pulse.
    crc_task = cocotb.start_soon(wait_crc())
    await uart_send_packet(dut, msg_type=0x02, payload=payload)
    await crc_task

    assert dut.rx_msg_type.value == 0x02
    assert dut.rx_msg_len.value  == len(payload)

@cocotb.test()
async def test_rx_bad_crc(dut):
    """Send a packet with a corrupted CRC byte; verify rx_crc_ok never fires."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    payload = [0x07, 0x08, 0x09]
    # Correct CRC = 0x07 ^ 0x08 ^ 0x09 = 0x06 — sending 0xFF instead.

    crc_fired = False

    async def monitor_crc():
        nonlocal crc_fired
        await RisingEdge(dut.rx_crc_ok)
        crc_fired = True

    monitor_task = cocotb.start_soon(monitor_crc())

    await uart_send_byte(dut, 0xAA)        # header
    await uart_send_byte(dut, 0x02)        # type: CONFIG
    await uart_send_byte(dut, 0x00)        # length hi
    await uart_send_byte(dut, 0x03)        # length lo: 3 bytes
    for b in payload:
        await uart_send_byte(dut, b)
    await uart_send_byte(dut, 0xFF)        # wrong CRC (correct is 0x06)

    # uart_send_byte already waits a full stop-bit period, so the FSM has had
    # time to evaluate the CRC byte. A few extra cycles are enough.
    await ClockCycles(dut.clk, 10)
    monitor_task.cancel()

    assert not crc_fired, "rx_crc_ok should not have fired with a bad CRC"

@cocotb.test()
async def test_tx_packet(dut):
    """Send a 3-byte DATA packet with payload; verify the full frame over UART.

    tx_payload_req fires once per byte: the first pulse comes from TX_LEN_LO
    (requesting byte 0), then once per consumed byte for bytes 1..N-1.
    drive_payload() catches each pulse and puts the next byte on the bus.
    """
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    payload = [0x10, 0x20, 0x30]

    async def drive_payload():
        for b in payload:
            await RisingEdge(dut.tx_payload_req)
            dut.tx_payload_byte.value = b

    dut.tx_msg_type.value = 0x05   # DATA
    dut.tx_msg_len.value  = len(payload)

    cocotb.start_soon(drive_payload())

    dut.tx_send.value = 1
    await RisingEdge(dut.clk)
    dut.tx_send.value = 0

    msg_type, recv_payload, crc_ok = await uart_recv_packet(dut)

    assert msg_type     == 0x05
    assert recv_payload == payload
    assert crc_ok

@cocotb.test()
async def test_tx_zero_payload(dut):
    """Send an ACK (no payload); verify every byte of the raw frame individually.

    Expected wire sequence: [0xAA][0x04][0x00][0x00][0x00]
    The final 0x00 is the CRC — XOR of an empty payload is zero.
    """
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    dut.tx_msg_type.value = 0x04   # ACK
    dut.tx_msg_len.value  = 0
    dut.tx_send.value     = 1
    await RisingEdge(dut.clk)
    dut.tx_send.value     = 0

    b0 = await uart_recv_byte(dut)  # header
    b1 = await uart_recv_byte(dut)  # type
    b2 = await uart_recv_byte(dut)  # len hi
    b3 = await uart_recv_byte(dut)  # len lo
    b4 = await uart_recv_byte(dut)  # crc

    assert b0 == 0xAA
    assert b1 == 0x04
    assert b2 == 0x00
    assert b3 == 0x00
    assert b4 == 0x00  # CRC = XOR of empty payload = 0x00

@cocotb.test()
async def test_rx_noise_recovery(dut):
    """Send garbage bytes before the 0xAA header; verify FSM discards them and
    correctly parses the valid packet that follows."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset(dut)

    payload = [0x0A, 0x0B]

    async def wait_crc():
        await RisingEdge(dut.rx_crc_ok)

    # Start listening before any bytes arrive — rx_crc_ok is a single-cycle pulse.
    crc_task = cocotb.start_soon(wait_crc())

    for b in [0x00, 0xFF, 0x12, 0x55]:  # garbage — none are 0xAA, FSM stays in RX_WAIT_HEADER
        await uart_send_byte(dut, b)

    await uart_send_packet(dut, msg_type=0x02, payload=payload)
    await crc_task

    assert dut.rx_msg_type.value == 0x02
    assert dut.rx_msg_len.value  == len(payload)
