import serial
import serial.tools.list_ports
import threading

# ── Message types ─────────────────────────────────────────────────────────────
MSG_INIT   = 0x01
MSG_CONFIG = 0x02
MSG_START  = 0x03
MSG_ACK    = 0x04
MSG_DATA   = 0x05
MSG_STATUS = 0x06

HEADER = 0xAA

# ── Connection ────────────────────────────────────────────────────────────────
_ser       = None
_on_packet = None

def list_ports():
    """Return a list of available serial port names."""
    return [p.device for p in serial.tools.list_ports.comports()]

def connect(port, baud=115200):
    """Open the serial port and start the reader thread."""
    global _ser
    disconnect()
    _ser = serial.Serial(port, baud, timeout=5)
    threading.Thread(target=_reader_thread, daemon=True).start()

def disconnect():
    """Close the serial port if open."""
    global _ser
    if _ser and _ser.is_open:
        _ser.close()
    _ser = None

def is_connected():
    return _ser is not None and _ser.is_open

# ── Packet layer ──────────────────────────────────────────────────────────────
def send_packet(msg_type, payload=None):
    """Send a framed packet: [0xAA][TYPE][LEN_HI][LEN_LO][PAYLOAD][CRC].
    CRC = XOR of all payload bytes.
    Raises ConnectionError if not connected.
    """
    if not is_connected():
        raise ConnectionError("Not connected")
    if payload is None:
        payload = []
    crc = 0
    for b in payload:
        crc ^= b
    length = len(payload)
    frame = bytes([HEADER, msg_type, (length >> 8) & 0xFF, length & 0xFF]
                  + list(payload) + [crc])
    _ser.write(frame)

def recv_packet():
    """Block until a complete packet arrives. Returns (msg_type, payload).
    Discards bytes until the 0xAA header is found.
    Raises serial.SerialTimeoutException on timeout.
    """
    while True:
        b = _ser.read(1)
        if not b:
            raise serial.SerialTimeoutException("Timeout waiting for header")
        if b[0] == HEADER:
            break

    msg_type = _ser.read(1)[0]
    len_hi   = _ser.read(1)[0]
    len_lo   = _ser.read(1)[0]
    length   = (len_hi << 8) | len_lo
    payload  = list(_ser.read(length)) if length > 0 else []
    crc_rx   = _ser.read(1)[0]

    crc_calc = 0
    for b in payload:
        crc_calc ^= b
    if crc_rx != crc_calc:
        raise ValueError(f"CRC mismatch: got {crc_rx:#04x}, expected {crc_calc:#04x}")

    return msg_type, payload

# ── Callback + reader thread ──────────────────────────────────────────────────
def set_packet_callback(fn):
    """Register a function called on every received packet: fn(msg_type, payload)."""
    global _on_packet
    _on_packet = fn

def _reader_thread():
    while is_connected():
        try:
            msg_type, payload = recv_packet()
            if _on_packet:
                _on_packet(msg_type, payload)
        except Exception:
            break
