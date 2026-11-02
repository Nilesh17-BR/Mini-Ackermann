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
import argparse
import math
from pynput import keyboard
from serial_dac import voltage_to_velocity

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
entering_input = False
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


def enter_target(unit):
    global voltage, entering_input

    try:
        label = 'voltage (V)' if unit == 'v' else 'velocity (m/s)'
        raw = input(f'\nEnter {label}, then press Enter: ').strip().lower()
        # The shortcut key can also be echoed into the console input buffer.
        value = float(raw.lstrip(unit).strip())
        if not math.isfinite(value):
            raise ValueError
        if unit == 'l':
            value = max(MIN_LINEAR_VELOCITY, min(MAX_LINEAR_VELOCITY, value))
            value = MIN_VOLTAGE + (value - MIN_LINEAR_VELOCITY) * (
                MAX_VOLTAGE - MIN_VOLTAGE
            ) / (MAX_LINEAR_VELOCITY - MIN_LINEAR_VELOCITY)
        with lock:
            if running:
                voltage = max(MIN_VOLTAGE, min(MAX_VOLTAGE, value))
    except (ValueError, EOFError):
        print('Invalid input; target unchanged.', flush=True)
    finally:
        with lock:
            pressed.clear()
            entering_input = False


def on_press(key):
    global voltage, hold_enabled, running, entering_input

    with lock:
        if key == keyboard.Key.esc:
            running = False
            return False
        if entering_input:
            return
        if key in pressed:
            return

        pressed.add(key)

        char = (getattr(key, 'char', None) or '').lower()
        if char in ('v', 'l'):
            entering_input = True
            pressed.clear()
            threading.Thread(target=enter_target, args=(char,), daemon=True).start()

        elif key == keyboard.Key.up:
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


def terminal_commands():
    global voltage, running

    while running:
        try:
            command = input().strip().lower()
        except EOFError:
            with lock:
                running = False
            return
        if command in ('q', 'quit'):
            with lock:
                running = False
            return
        if command in ('n', 'neutral'):
            with lock:
                voltage = neutral
            continue
        try:
            unit, value = command.split()
            value = float(value)
            if not math.isfinite(value):
                raise ValueError
            if unit in ('vel', 'velocity'):
                value = max(MIN_LINEAR_VELOCITY, min(MAX_LINEAR_VELOCITY, value))
                value = MIN_VOLTAGE + (value - MIN_LINEAR_VELOCITY) * (
                    MAX_VOLTAGE - MIN_VOLTAGE
                ) / (MAX_LINEAR_VELOCITY - MIN_LINEAR_VELOCITY)
            elif unit not in ('v', 'voltage'):
                raise ValueError
            with lock:
                voltage = max(MIN_VOLTAGE, min(MAX_VOLTAGE, value))
        except ValueError:
            print('Use: v 2.0 | vel 1.0 | n (neutral) | q (quit)', flush=True)


def main():
    global running

    parser = argparse.ArgumentParser(description='Control voltage or mapped velocity.')
    parser.add_argument('--terminal', action='store_true',
                        help='type voltage/velocity commands instead of using arrow keys')
    args = parser.parse_args()
    destination = (LOCAL_HOST, LOCAL_PORT)

    listener = None

    print("\nSTM32 VOLTAGE CONTROL")
    if args.terminal:
        print('Type v 2.0 (volts) or vel 1.0 (m/s), then Enter.')
        print('n: neutral | q: quit | Values are clamped to the configured range.')
        print('Velocity is a mapped command, not measured speed.')
        threading.Thread(target=terminal_commands, daemon=True).start()
    else:
        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()
        print("UP     : Increase voltage")
        print("DOWN   : Decrease voltage")
        print("H      : Toggle continuous hold mode")
        print("V      : Enter voltage; press Enter to apply")
        print("L      : Enter velocity; press Enter to apply")
        print("SPACE  : Neutral")
        print("ESC    : Exit")
        print('Use --terminal to type voltage or velocity targets.')
    print(f"Neutral voltage: {neutral:.3f} V")
    print("HOLD: OFF")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        last_step = time.monotonic()
        last_display = None

        try:
            while True:
                now = time.monotonic()

                with lock:
                    if not running:
                        break

                    if hold_enabled and not entering_input and now - last_step >= INTERVAL:
                        if keyboard.Key.up in pressed and keyboard.Key.down not in pressed:
                            change_voltage(1)
                        elif keyboard.Key.down in pressed and keyboard.Key.up not in pressed:
                            change_voltage(-1)
                        last_step = now

                    if not hold_enabled:
                        last_step = now

                    target = voltage
                    mode = hold_enabled
                    editing = entering_input

                sender.sendto(
                    f"{target:.6f}".encode("ascii"),
                    destination
                )

                if not editing and (target, mode) != last_display:
                    print(
                        f"Voltage: {target:.3f} V "
                        f"| Commanded velocity: {voltage_to_velocity(target):+.3f} m/s "
                        f"| HOLD: {'ON' if mode else 'OFF'}",
                        flush=True
                    )
                    last_display = (target, mode)

                time.sleep(SEND_PERIOD)

        except KeyboardInterrupt:
            pass

        finally:
            for _ in range(3):
                sender.sendto(b"STOP", destination)
                time.sleep(0.05)
            if listener is not None:
                listener.stop()

    print("\nNeutral requested. Exiting.")


if __name__ == "__main__":
    main()
