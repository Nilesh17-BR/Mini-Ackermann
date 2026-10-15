import serial
import time

PORT = "COM6"
BAUD = 115200

with serial.Serial(PORT, BAUD, timeout=1) as ser:

    time.sleep(2)
    ser.reset_input_buffer()

    commands = [
        "PING",
        "CH:0",
        "CH:1",
        "CH:2",
        "CH:3",
        "STOP"
    ]

    for command in commands:

        print(f"\nSending: {command}")

        ser.write((command + "\n").encode())
        ser.flush()

        deadline = time.monotonic() + 1.0

        while time.monotonic() < deadline:

            if ser.in_waiting:
                response = ser.readline().decode(
                    errors="replace"
                ).strip()

                print(f"STM32: {response}")

            time.sleep(0.01)