#!/usr/bin/env python3
"""
log_serial.py — save what the Arduino prints to a CSV file. Stop with Ctrl-C.

    python analysis/log_serial.py <port> data/bare_run1.csv

    port examples:  COM3 (Windows)   /dev/cu.usbmodem14101 (Mac)   /dev/ttyACM0 or /dev/ttyUSB0 (Linux)
    needs:          pip install pyserial

Opening the port resets the Uno, so the sketch restarts, time_ms starts near 0 and the
header line "time_ms,raw_adc,temperature_C" is the first thing saved. That is what we want.
"""
import sys
import serial  # pyserial

if len(sys.argv) != 3:
    sys.exit("usage: python log_serial.py <port> <output.csv>")

port, outfile = sys.argv[1], sys.argv[2]
with serial.Serial(port, 115200, timeout=2) as ser, open(outfile, "w", newline="") as f:
    print(f"logging {port} -> {outfile}   (Ctrl-C to stop)")
    n = 0
    try:
        while True:
            line = ser.readline().decode("ascii", errors="ignore").strip()
            if not line:
                continue
            f.write(line + "\n")
            n += 1
            if n % 50 == 0:
                f.flush()
                print("\r" + line + "        ", end="")
    except KeyboardInterrupt:
        print(f"\nsaved {n} lines to {outfile}")
