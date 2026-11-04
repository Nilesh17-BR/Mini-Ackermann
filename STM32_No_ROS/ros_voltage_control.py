#!/usr/bin/env python3
"""Publish calibrated voltage/velocity keyboard targets as ROS 2 Twist.linear.x."""

import rclpy
from geometry_msgs.msg import Twist
import time
import threading
import argparse
import math
from serial_dac import voltage_to_velocity, velocity_to_voltage

from config import (
    MIN_VOLTAGE,
    MAX_VOLTAGE,
    NEUTRAL_VOLTAGE,
    VESC_GAIN,
    VESC_OFFSET,
    MIN_LINEAR_VELOCITY,
    MAX_LINEAR_VELOCITY,
    SEND_PERIOD,
)

STEP = 0.1
INTERVAL = 0.2


def voltage_estimates(velocity):
    """Return target VESC voltage and required DAC voltage, not feedback."""
    required_dac_voltage = velocity_to_voltage(velocity)
    vesc_voltage = required_dac_voltage * VESC_GAIN + VESC_OFFSET
    return vesc_voltage, required_dac_voltage


def neutral_voltage():
    return NEUTRAL_VOLTAGE


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
            min(MAX_VOLTAGE, voltage + direction * STEP / VESC_GAIN)
        ),
        3
    )


def enter_target(unit):
    global voltage, entering_input

    try:
        label = 'VESC voltage (V)' if unit == 'v' else 'velocity (m/s)'
        raw = input(f'\nEnter {label}, then press Enter: ').strip().lower()
        # The shortcut key can also be echoed into the console input buffer.
        value = float(raw.lstrip(unit).strip())
        if not math.isfinite(value):
            raise ValueError
        if unit == 'l':
            value = max(MIN_LINEAR_VELOCITY, min(MAX_LINEAR_VELOCITY, value))
            value = velocity_to_voltage(value)
        else:
            value = (value - VESC_OFFSET) / VESC_GAIN
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
                value = velocity_to_voltage(value)
            elif unit in ('v', 'voltage'):
                value = (value - VESC_OFFSET) / VESC_GAIN
            else:
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
    parser.add_argument('--topic', default='/cmd_vel_ros', help='Twist velocity topic')
    args, ros_args = parser.parse_known_args()
    global keyboard
    if not args.terminal:
        from pynput import keyboard
    rclpy.init(args=ros_args)
    node = rclpy.create_node('calibrated_voltage_control')
    publisher = node.create_publisher(Twist, args.topic, 1)

    listener = None

    print("\nSTM32 ROS VOLTAGE CONTROL")
    if args.terminal:
        print('Type v 2.0 (VESC volts) or vel 1.0 (m/s), then Enter.')
        print('n: neutral | q: quit | Values are clamped to the configured range.')
        print('Velocity is a mapped command, not measured speed.')
        threading.Thread(target=terminal_commands, daemon=True).start()
    else:
        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()
        print("UP     : Increase target VESC voltage")
        print("DOWN   : Decrease target VESC voltage")
        print("H      : Toggle continuous hold mode")
        print("V      : Enter VESC voltage; press Enter to apply")
        print("L      : Enter velocity; press Enter to apply")
        print("SPACE  : Neutral")
        print("ESC    : Exit")
        print('Use --terminal to type voltage or velocity targets.')
    print(f"Neutral VESC voltage: {neutral * VESC_GAIN + VESC_OFFSET:.3f} V | DAC: {neutral:.3f} V")
    print("HOLD: OFF")

    try:
        last_step = time.monotonic()
        last_display = None

        try:
            while rclpy.ok():
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

                message = Twist()
                message.linear.x = voltage_to_velocity(target)
                publisher.publish(message)
                rclpy.spin_once(node, timeout_sec=0.0)

                if not editing and (target, mode) != last_display:
                    commanded_velocity = voltage_to_velocity(target)
                    vesc_voltage, required_dac_voltage = voltage_estimates(commanded_velocity)
                    print(
                        f"DAC command: {target:.3f} V "
                        f"| Commanded velocity: {commanded_velocity:+.3f} m/s "
                        f"| Target VESC voltage: {vesc_voltage:.3f} V "
                        f"| Required DAC voltage: {required_dac_voltage:.3f} V "
                        f"| HOLD: {'ON' if mode else 'OFF'}",
                        flush=True
                    )
                    last_display = (target, mode)

                time.sleep(SEND_PERIOD)

        except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
            pass

        finally:
            for _ in range(3):
                if rclpy.ok():
                    publisher.publish(Twist())
                    time.sleep(0.05)
            if listener is not None:
                listener.stop()

    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

    print("\nNeutral requested. Exiting.")


if __name__ == "__main__":
    main()
