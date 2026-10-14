import serial
import time

PORT = "/dev/ttyUSB0"
BAUD = 115200

ser = serial.Serial(
    port=PORT,
    baudrate=BAUD,
    timeout=0.5,
    write_timeout=0.5
)

print("UART connected")

time.sleep(1)

ser.reset_input_buffer()

for i in range(10):

    command = "PING\n"

    print(f"Sending: PING ({i + 1})")

    ser.write(command.encode("ascii"))
    ser.flush()

    deadline = time.monotonic() + 1.0

    received = False

    while time.monotonic() < deadline:

        response = ser.readline().decode(
            "utf-8",
            errors="replace"
        ).strip()

        if response:
            print("STM32:", repr(response))
            received = True

        if response == "PONG":
            break

    if not received:
        print("No response received")

    time.sleep(0.5)

ser.close()