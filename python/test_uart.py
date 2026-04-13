"""
test_uart.py — Raw UART debug script.

Sends an INIT packet and prints every byte received from the FPGA for 3 seconds.
Run from the ramsey/python directory:
    python test_uart.py COM5
"""

import sys
import time
import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM5"
BAUD = 115200

# INIT packet: [0xAA][0x01][0x00][0x00][0x00]
INIT_PACKET = bytes([0xAA, 0x01, 0x00, 0x00, 0x00])

print(f"Opening {PORT} at {BAUD} baud...")
ser = serial.Serial(PORT, BAUD, timeout=0.1)
time.sleep(0.1)

# Flush anything already in the buffer
ser.reset_input_buffer()

print(f"Sending INIT: {INIT_PACKET.hex(' ').upper()}")
ser.write(INIT_PACKET)

print("Listening for 3 seconds...")
start = time.time()
received = bytearray()

while time.time() - start < 3.0:
    chunk = ser.read(64)
    if chunk:
        received += chunk
        print(f"  RX: {chunk.hex(' ').upper()}")

ser.close()

if received:
    print(f"\nTotal received: {len(received)} bytes: {received.hex(' ').upper()}")
    # Expected ACK: AA 04 00 00 00
    if received[:5] == bytes([0xAA, 0x04, 0x00, 0x00, 0x00]):
        print("ACK packet received correctly.")
    else:
        print("Bytes received but did not match expected ACK.")
else:
    print("\nNo bytes received. FPGA is not responding.")
    print("Check: correct USB port (UART not PROG), bitstream flashed, reset not held.")
