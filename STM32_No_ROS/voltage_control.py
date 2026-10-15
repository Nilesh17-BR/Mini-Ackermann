# #!/usr/bin/env python3
# """Send manual or automatic voltage targets to the separate serial_dac.py bridge."""

# import argparse
# import math
# import queue
# import socket
# import threading
# import time

# from config import MIN_VOLTAGE, MAX_VOLTAGE, MIN_LINEAR_VELOCITY, MAX_LINEAR_VELOCITY, SEND_PERIOD, LOCAL_HOST, LOCAL_PORT


# def neutral_voltage():
#     return MIN_VOLTAGE + (0 - MIN_LINEAR_VELOCITY) * (
#         MAX_VOLTAGE - MIN_VOLTAGE
#     ) / (MAX_LINEAR_VELOCITY - MIN_LINEAR_VELOCITY)


# class VoltageControl:
#     def __init__(self, step=0.1, rate=0.2):
#         self.step = step
#         self.rate = rate
#         self.voltage = neutral_voltage()
#         self.auto = False
#         self.phase = self.voltage - MIN_VOLTAGE
#         self.last_update = time.monotonic()

#     def update(self, now):
#         if self.auto:
#             span = MAX_VOLTAGE - MIN_VOLTAGE
#             self.phase = (self.phase + self.rate * (now - self.last_update)) % (2 * span)
#             self.voltage = MIN_VOLTAGE + span - abs(self.phase - span)
#         self.last_update = now
#         return self.voltage

#     def command(self, value):
#         if value == 'a':
#             self.phase = self.voltage - MIN_VOLTAGE
#             self.last_update = time.monotonic()
#             self.auto = True
#         elif value == 'm':
#             self.auto = False
#         else:
#             if value == 'p':
#                 voltage = self.voltage + self.step
#             elif value == 's':
#                 voltage = self.voltage - self.step
#             elif value == 'n':
#                 voltage = neutral_voltage()
#             else:
#                 voltage = float(value)
#                 if not math.isfinite(voltage):
#                     raise ValueError('Voltage must be finite')
#             self.voltage = max(MIN_VOLTAGE, min(voltage, MAX_VOLTAGE))
#             self.auto = False


# def read_input(commands):
#     try:
#         while True:
#             value = input().strip().lower()
#             commands.put(value)
#             if value == 'q':
#                 return
#     except EOFError:
#         commands.put('q')


# def positive_number(value):
#     number = float(value)
#     if not math.isfinite(number) or number <= 0:
#         raise argparse.ArgumentTypeError('must be a finite positive number')
#     return number


# def main():
#     parser = argparse.ArgumentParser(description=__doc__)
#     parser.add_argument('--step', type=positive_number, default=0.1, help='manual step in volts')
#     parser.add_argument('--rate', type=positive_number, default=0.2, help='automatic ramp in volts/second')
#     args = parser.parse_args()
#     control = VoltageControl(args.step, args.rate)
#     commands = queue.Queue()
#     print(f'Voltage range: {MIN_VOLTAGE:g}-{MAX_VOLTAGE:g} V; neutral: {control.voltage:g} V')
#     print('p/s: increase/decrease | number: set volts | a: automatic | m: hold')
#     print('n: neutral | q: quit. Press Enter after each command.')
#     print('Targets are sent to serial_dac.py; this script does not read hardware feedback.')
#     threading.Thread(target=read_input, args=(commands,), daemon=True).start()
#     with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
#         destination = (LOCAL_HOST, LOCAL_PORT)
#         try:
#             next_send = time.monotonic()
#             next_display = next_send
#             running = True
#             while running:
#                 control.update(time.monotonic())
#                 for _ in range(20):
#                     try:
#                         value = commands.get_nowait()
#                     except queue.Empty:
#                         break
#                     if value == 'q':
#                         running = False
#                         break
#                     try:
#                         control.command(value)
#                         print(f'Target: {control.voltage:.3f} V | {"automatic" if control.auto else "manual"}')
#                     except ValueError:
#                         print('Use p, s, a, m, n, q, or a finite voltage number.')
#                 if not running:
#                     break
#                 now = time.monotonic()
#                 if now >= next_send:
#                     sender.sendto(f'{control.update(now):.6f}'.encode('ascii'), destination)
#                     next_send = now + SEND_PERIOD
#                     if control.auto and now >= next_display:
#                         print(f'Target: {control.voltage:.3f} V | automatic')
#                         next_display = now + 1.0
#                 time.sleep(0.01)
#         except KeyboardInterrupt:
#             pass
#         finally:
#             for _ in range(3):
#                 sender.sendto(b'STOP', destination)
#                 time.sleep(0.05)
#     print('Neutral requested. Exiting.')


# if __name__ == '__main__':
#     main()



#!/usr/bin/env python3

import socket
import time
import threading
from pynput import keyboard

from config import (
    MIN_VOLTAGE,
    MAX_VOLTAGE,
    MIN_LINEAR_VELOCITY,
    MAX_LINEAR_VELOCITY,
    SEND_PERIOD,
    LOCAL_HOST,
    LOCAL_PORT
)

STEP = 0.1
INTERVAL = 0.2


def neutral_voltage():
    return MIN_VOLTAGE + (
        (0 - MIN_LINEAR_VELOCITY)
        * (MAX_VOLTAGE - MIN_VOLTAGE)
        / (MAX_LINEAR_VELOCITY - MIN_LINEAR_VELOCITY)
    )


neutral = neutral_voltage()
voltage = neutral

hold_enabled = False  # Default OFF
pressed = set()
running = True
lock = threading.Lock()


def change_voltage(direction):
    global voltage

    voltage = round(
        max(
            MIN_VOLTAGE,
            min(MAX_VOLTAGE, voltage + direction * STEP)
        ),
        3
    )


def on_press(key):
    global voltage, hold_enabled, running

    with lock:
        if key in pressed:
            return

        pressed.add(key)

        if key == keyboard.Key.up:
            change_voltage(1)

        elif key == keyboard.Key.down:
            change_voltage(-1)

        elif getattr(key, 'char', None) == 'h':
            hold_enabled = not hold_enabled
            print(f"\nHOLD: {'ON' if hold_enabled else 'OFF'}")

        elif key == keyboard.Key.space:
            voltage = neutral
            print("\nNEUTRAL")

        elif key == keyboard.Key.esc:
            running = False
            return False


def on_release(key):
    with lock:
        pressed.discard(key)
        # Keep last voltage. No neutral reset.


def main():
    global running

    destination = (LOCAL_HOST, LOCAL_PORT)

    listener = keyboard.Listener(
        on_press=on_press,
        on_release=on_release
    )
    listener.start()

    print("\nSTM32 VOLTAGE CONTROL")
    print("UP     : Increase voltage")
    print("DOWN   : Decrease voltage")
    print("H      : Toggle continuous hold mode")
    print("SPACE  : Neutral")
    print("ESC    : Exit")
    print(f"Neutral voltage: {neutral:.3f} V")
    print("HOLD: OFF")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        last_step = time.monotonic()

        try:
            while True:
                now = time.monotonic()

                with lock:
                    if not running:
                        break

                    if hold_enabled and now - last_step >= INTERVAL:
                        if keyboard.Key.up in pressed and keyboard.Key.down not in pressed:
                            change_voltage(1)
                        elif keyboard.Key.down in pressed and keyboard.Key.up not in pressed:
                            change_voltage(-1)
                        last_step = now

                    if not hold_enabled:
                        last_step = now

                    target = voltage
                    mode = hold_enabled

                sender.sendto(
                    f"{target:.6f}".encode("ascii"),
                    destination
                )

                print(
                    f"\rVoltage: {target:.3f} V "
                    f"| HOLD: {'ON ' if mode else 'OFF'}",
                    end="",
                    flush=True
                )

                time.sleep(SEND_PERIOD)

        except KeyboardInterrupt:
            pass

        finally:
            for _ in range(3):
                sender.sendto(b"STOP", destination)
                time.sleep(0.05)
            listener.stop()

    print("\nNeutral requested. Exiting.")


if __name__ == "__main__":
    main()
