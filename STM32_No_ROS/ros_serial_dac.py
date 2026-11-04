#!/usr/bin/env python3
"""Receive ROS 2 Twist.linear.x velocities using the standalone DAC calibration."""

import argparse
import math
import time

from config import (
    MIN_LINEAR_VELOCITY, MAX_LINEAR_VELOCITY, MIN_VOLTAGE, MAX_VOLTAGE,
    NEUTRAL_VOLTAGE, SEND_PERIOD, CMD_TIMEOUT, SERIAL_PORT,
)
from serial_dac import firmware_mapping, velocity_to_firmware_command, exchange


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default=SERIAL_PORT, help=f'UART device (default: {SERIAL_PORT})')
    parser.add_argument('--topic', default='/cmd_vel_ros', help='Twist velocity topic')
    parser.add_argument('--baud', type=int, default=115200)
    parser.add_argument('--channel', type=str.lower, choices=('all', '0', '1', '2', '3'),
                        default='all', help='DAC output: all (default), or one channel 0-3')
    args, ros_args = parser.parse_known_args()
    mapping = (MIN_LINEAR_VELOCITY, MAX_LINEAR_VELOCITY, MIN_VOLTAGE, MAX_VOLTAGE, NEUTRAL_VOLTAGE)
    if (args.baud <= 0 or not all(math.isfinite(v) for v in mapping)
            or not -100 <= MIN_LINEAR_VELOCITY < 0 < MAX_LINEAR_VELOCITY <= 100
            or MIN_LINEAR_VELOCITY >= MAX_LINEAR_VELOCITY
            or not 0 <= MIN_VOLTAGE < NEUTRAL_VOLTAGE < MAX_VOLTAGE <= 5):
        parser.error('Invalid baud rate or mapping in config.py')
    try:
        import serial
    except ImportError:
        parser.exit(1, 'Install pyserial: python -m pip install -r requirements.txt\n')
    import rclpy
    from geometry_msgs.msg import Twist

    rclpy.init(args=ros_args)
    node = rclpy.create_node("calibrated_stm32_dac")
    state = {"velocity": 0.0, "last_target": float("-inf")}

    def receive_velocity(msg):
        value = msg.linear.x
        if math.isfinite(value):
            state["velocity"] = max(MIN_LINEAR_VELOCITY, min(MAX_LINEAR_VELOCITY, value))
            state["last_target"] = time.monotonic()
        else:
            state["velocity"] = 0.0
            state["last_target"] = float("-inf")
            node.get_logger().warning("Invalid linear.x; requesting neutral.")

    subscription = node.create_subscription(Twist, args.topic, receive_velocity, 1)
    port = None
    failed = False
    try:
        port = serial.Serial(args.port, args.baud, timeout=0.05, write_timeout=0.2)
        time.sleep(1)
        port.reset_input_buffer()
        print(exchange(port, 'PING', 'PONG', 1.0))
        channel = args.channel.upper()
        print(exchange(port, f'CH:{channel}', f'OK:CH:{channel}', 1.0))
        print(exchange(port, 'MAP:' + ','.join(f'{v:.6f}' for v in firmware_mapping()), 'OK:MAP:', 1.0))
        print(f'Ready on {args.port}; subscribing to {args.topic} linear.x (m/s). Ctrl+C to stop.')
        next_send = next_display = time.monotonic()
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.0)
            now = time.monotonic()
            if now >= next_send:
                target = state["velocity"] if now - state["last_target"] <= CMD_TIMEOUT else 0.0
                command = velocity_to_firmware_command(target)
                response = exchange(port, f'CMD:{command:.6f}', 'OK:CMD:')
                if now >= next_display:
                    print(f'[STM32] {response} | Commanded velocity: {target:+.3f} m/s')
                    next_display = now + 1.0
                next_send = now + SEND_PERIOD
            time.sleep(0.01)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    except (serial.SerialException, OSError, RuntimeError) as error:
        print(f'ERROR: {error}')
        failed = True
    finally:
        if port is not None and port.is_open:
            try:
                print(exchange(port, 'STOP', 'OK:STOP'))
            except (serial.SerialException, OSError, RuntimeError) as error:
                print(f'Could not confirm neutral: {error}')
                failed = True
            finally:
                port.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
