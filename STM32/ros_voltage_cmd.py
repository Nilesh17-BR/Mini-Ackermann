#!/usr/bin/env python3
"""Manual voltage control and automatic sweeps through the ROS-to-DAC bridge."""

import argparse
import math
import threading
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node

from cmd_vel_stm2_dac import (
    MIN_LINEAR_VELOCITY, MAX_LINEAR_VELOCITY, MIN_VOLTAGE, MAX_VOLTAGE,
)


def voltage_to_velocity(voltage):
    return MIN_LINEAR_VELOCITY + (voltage - MIN_VOLTAGE) * (
        MAX_LINEAR_VELOCITY - MIN_LINEAR_VELOCITY
    ) / (MAX_VOLTAGE - MIN_VOLTAGE)


def neutral_voltage():
    return MIN_VOLTAGE + (0.0 - MIN_LINEAR_VELOCITY) * (
        MAX_VOLTAGE - MIN_VOLTAGE
    ) / (MAX_LINEAR_VELOCITY - MIN_LINEAR_VELOCITY)


def positive_number(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite positive number")
    return number


class VoltagePublisher(Node):
    def __init__(self, step, rate):
        super().__init__('voltage_publisher')
        self.publisher = self.create_publisher(Twist, '/cmd_vel_ros', 10)
        self.lock = threading.Lock()
        self.voltage = neutral_voltage()
        self.step = step
        self.rate = rate
        self.auto = False
        self.phase = self.voltage - MIN_VOLTAGE
        self.last_update = time.monotonic()
        self.timer = self.create_timer(0.1, self.publish_voltage)

    def publish_voltage(self):
        with self.lock:
            now = time.monotonic()
            if self.auto:
                span = MAX_VOLTAGE - MIN_VOLTAGE
                self.phase = (self.phase + self.rate * (now - self.last_update)) % (2 * span)
                self.voltage = MIN_VOLTAGE + span - abs(self.phase - span)
            self.last_update = now
            msg = Twist()
            msg.linear.x = voltage_to_velocity(self.voltage)
            self.publisher.publish(msg)

    def command(self, value):
        with self.lock:
            if value == 'a':
                # Start by increasing from the current voltage, then bounce
                # between the configured limits indefinitely.
                self.phase = self.voltage - MIN_VOLTAGE
                self.last_update = time.monotonic()
                self.auto = True
            elif value == 'm':
                self.auto = False
            else:
                if value == 'p':
                    voltage = self.voltage + self.step
                elif value == 's':
                    voltage = self.voltage - self.step
                elif value == 'n':
                    voltage = neutral_voltage()
                else:
                    voltage = float(value)
                    if not math.isfinite(voltage):
                        raise ValueError("Voltage must be finite")
                self.voltage = max(MIN_VOLTAGE, min(voltage, MAX_VOLTAGE))
                self.auto = False
            return self.voltage, self.auto


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--step', type=positive_number, default=0.1,
                        help='manual increment in volts (default: 0.1)')
    parser.add_argument('--rate', type=positive_number, default=0.2,
                        help='automatic ramp speed in volts/second (default: 0.2)')
    args, ros_args = parser.parse_known_args()
    values = (MIN_LINEAR_VELOCITY, MAX_LINEAR_VELOCITY, MIN_VOLTAGE, MAX_VOLTAGE)
    if (not all(math.isfinite(v) for v in values)
            or not MIN_LINEAR_VELOCITY <= 0 <= MAX_LINEAR_VELOCITY
            or MIN_LINEAR_VELOCITY >= MAX_LINEAR_VELOCITY
            or not 0 <= MIN_VOLTAGE < MAX_VOLTAGE <= 5):
        parser.error('Invalid velocity/voltage mapping in cmd_vel_stm2_dac.py')

    rclpy.init(args=ros_args)
    node = VoltagePublisher(args.step, args.rate)
    executor = rclpy.executors.SingleThreadedExecutor()
    executor.add_node(node)
    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()
    print(f'\nVoltage range: {MIN_VOLTAGE:.3f} to {MAX_VOLTAGE:.3f} V')
    print(f'Starting at neutral: {neutral_voltage():.3f} V')
    print(f'p/s: increase/decrease by {args.step:g} V | number: set volts')
    print(f'a: automatic up/down ramp ({args.rate:g} V/s) | m: hold/manual')
    print('n: neutral | q: quit | Press Enter after each command.')
    print('Manual adjustments leave automatic mode. Out-of-range values are clamped.')
    try:
        while rclpy.ok():
            value = input('Voltage command: ').strip().lower()
            if value == 'q':
                break
            try:
                voltage, auto = node.command(value)
                print(f'Target: {voltage:.3f} V | {"automatic" if auto else "manual"}')
            except ValueError:
                print('Use p, s, a, m, n, q, or a finite voltage number.')
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        node.timer.cancel()
        node.command('n')
        # Stop the executor before sending the final neutral messages.
        executor.shutdown()
        spin_thread.join()
        if rclpy.ok():
            for _ in range(5):
                node.publish_voltage()
                time.sleep(0.05)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        print('\nNeutral requested. Exiting.')


if __name__ == '__main__':
    main()
