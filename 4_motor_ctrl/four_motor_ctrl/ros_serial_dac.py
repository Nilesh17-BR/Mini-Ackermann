#!/usr/bin/env python3
"""Send four ROS wheel velocities to independently mapped DAC channels."""

import argparse
import math
import time

from . import config as cfg
from .serial_dac import exchange, firmware_mapping, velocity_to_firmware_command


def channel_commands(data):
    """Validate a whole wheel message, then return commands in DAC A-D order."""
    if len(data) != 4 or not all(math.isfinite(value) for value in data):
        raise ValueError('Expected exactly four finite wheel velocities')
    commands = [0.0] * 4
    for value, channel in zip(data, cfg.WHEEL_CHANNELS):
        commands['ABCD'.index(channel)] = velocity_to_firmware_command(value)
    return commands


def validate_config():
    if len(cfg.WHEEL_CHANNELS) != 4 or set(cfg.WHEEL_CHANNELS) != set('ABCD'):
        raise ValueError('WHEEL_CHANNELS must contain A, B, C, D exactly once')
    values = (cfg.MIN_LINEAR_VELOCITY, cfg.MAX_LINEAR_VELOCITY,
              cfg.MIN_VOLTAGE, cfg.NEUTRAL_VOLTAGE, cfg.MAX_VOLTAGE,
              cfg.SEND_PERIOD, cfg.CMD_TIMEOUT)
    if (not all(math.isfinite(v) for v in values)
            or not -100 <= cfg.MIN_LINEAR_VELOCITY < 0 < cfg.MAX_LINEAR_VELOCITY <= 100
            or not 0 <= cfg.MIN_VOLTAGE < cfg.NEUTRAL_VOLTAGE < cfg.MAX_VOLTAGE <= 5
            or not 0 < cfg.SEND_PERIOD < 0.5 or cfg.CMD_TIMEOUT <= 0):
        raise ValueError('Invalid calibration or timing in config.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default=cfg.SERIAL_PORT)
    parser.add_argument('--baud', type=int, default=cfg.SERIAL_BAUD)
    parser.add_argument('--topic', default=cfg.VELOCITY_TOPIC)
    args, ros_args = parser.parse_known_args()
    try:
        validate_config()
        if args.baud <= 0:
            raise ValueError('Baud rate must be positive')
    except ValueError as error:
        parser.error(str(error))
    import serial
    import rclpy
    from std_msgs.msg import Float64MultiArray

    rclpy.init(args=ros_args)
    node = rclpy.create_node('four_wheel_serial_dac')
    state = {'commands': [0.0] * 4, 'last_target': float('-inf')}

    def receive(msg):
        try:
            state['commands'] = channel_commands(msg.data)
            state['last_target'] = time.monotonic()
        except ValueError as error:
            state['commands'] = [0.0] * 4
            state['last_target'] = float('-inf')
            node.get_logger().warning(f'{error}; requesting neutral on all wheels.')

    subscription = node.create_subscription(Float64MultiArray, args.topic, receive, 1)
    port = None
    failed = False
    try:
        port = serial.Serial(args.port, args.baud, timeout=0.05, write_timeout=0.2)
        time.sleep(1)
        port.reset_input_buffer()
        print(exchange(port, 'PING', 'PONG', 1.0))
        print(exchange(port, 'MAP:' + ','.join(f'{v:.6f}' for v in firmware_mapping()),
                       'OK:MAP:', 1.0))
        # Require CMD4 support while all outputs are neutral.
        print(exchange(port, 'CMD4:0,0,0,0', 'OK:CMD4:'))
        for index, channel in enumerate(cfg.WHEEL_CHANNELS):
            print(f'data[{index}] = wheel {index + 1} -> channel {channel}')
        print(f'Ready: {args.topic} (std_msgs/msg/Float64MultiArray, m/s)')
        next_send = time.monotonic()
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.0)
            now = time.monotonic()
            if now >= next_send:
                commands = (state['commands'] if now - state['last_target'] <= cfg.CMD_TIMEOUT
                            else [0.0] * 4)
                exchange(port, 'CMD4:' + ','.join(f'{v:.6f}' for v in commands), 'OK:CMD4:')
                next_send = now + cfg.SEND_PERIOD
            time.sleep(0.005)
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
