#!/usr/bin/env python3
"""Receive local voltage targets and communicate with the STM32 using pyserial."""

import argparse
import math
import socket
import time

from config import (
    MIN_LINEAR_VELOCITY, MAX_LINEAR_VELOCITY, MIN_VOLTAGE, MAX_VOLTAGE,
    SEND_PERIOD, LOCAL_HOST, LOCAL_PORT, CMD_TIMEOUT, SERIAL_PORT,
    NEUTRAL_VOLTAGE, MIN_VESC_VOLTAGE, MAX_VESC_VOLTAGE,
    NEUTRAL_VESC_VOLTAGE, VESC_GAIN, VESC_OFFSET,
)


def velocity_to_vesc_voltage(velocity):
    """Map configured velocity limits to VESC voltage limits, with zero at center."""
    velocity = max(MIN_LINEAR_VELOCITY, min(MAX_LINEAR_VELOCITY, velocity))
    if velocity <= 0:
        return NEUTRAL_VESC_VOLTAGE + velocity * (
            NEUTRAL_VESC_VOLTAGE - MIN_VESC_VOLTAGE) / (-MIN_LINEAR_VELOCITY)
    return NEUTRAL_VESC_VOLTAGE + velocity * (
        MAX_VESC_VOLTAGE - NEUTRAL_VESC_VOLTAGE) / MAX_LINEAR_VELOCITY


def vesc_voltage_to_velocity(voltage):
    voltage = max(MIN_VESC_VOLTAGE, min(MAX_VESC_VOLTAGE, voltage))
    if voltage <= NEUTRAL_VESC_VOLTAGE:
        return (voltage - NEUTRAL_VESC_VOLTAGE) * (-MIN_LINEAR_VELOCITY) / (
            NEUTRAL_VESC_VOLTAGE - MIN_VESC_VOLTAGE)
    return (voltage - NEUTRAL_VESC_VOLTAGE) * MAX_LINEAR_VELOCITY / (
        MAX_VESC_VOLTAGE - NEUTRAL_VESC_VOLTAGE)


def velocity_to_voltage(velocity):
    """Convert a velocity to compensated DAC output for the serial transport."""
    return (velocity_to_vesc_voltage(velocity) - VESC_OFFSET) / VESC_GAIN


def voltage_to_velocity(voltage):
    """Convert a DAC output to velocity via its estimated VESC input voltage."""
    return vesc_voltage_to_velocity(voltage * VESC_GAIN + VESC_OFFSET)


# The existing firmware interpolates linearly and uses CMD:0 for STOP/watchdog.
# Use an asymmetric transport range so CMD:0 still produces calibrated neutral.
def firmware_mapping():
    protocol_max = MAX_LINEAR_VELOCITY
    protocol_min = -protocol_max * (NEUTRAL_VOLTAGE - MIN_VOLTAGE) / (
        MAX_VOLTAGE - NEUTRAL_VOLTAGE)
    return protocol_min, protocol_max, MIN_VOLTAGE, MAX_VOLTAGE


def velocity_to_firmware_command(velocity):
    if velocity == 0.0:
        return 0.0
    protocol_min, protocol_max, low, high = firmware_mapping()
    return protocol_min + (velocity_to_voltage(velocity) - low) * (
        protocol_max - protocol_min) / (high - low)


def parse_target(data):
    if data == b'STOP':
        return 0.0
    voltage = float(data.decode('ascii'))
    if not math.isfinite(voltage):
        raise ValueError('Voltage must be finite')
    voltage = max(MIN_VOLTAGE, min(voltage, MAX_VOLTAGE))
    return voltage_to_velocity(voltage)


def exchange(port, command, expected, timeout=0.3):
    port.write((command + '\n').encode('ascii'))
    port.flush()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = port.readline().decode('ascii', errors='replace').strip()
        if response.startswith('ERR:'):
            raise RuntimeError(response)
        if response.startswith(expected):
            return response
    raise RuntimeError(f'No {expected} response to {command}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default=SERIAL_PORT, help='UART device (default: COM6)')
    parser.add_argument('--baud', type=int, default=115200)
    parser.add_argument('--channel', type=str.lower, choices=('all', '0', '1', '2', '3'),
                        default='all', help='DAC output: all (default), or one channel 0-3')
    args = parser.parse_args()
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
    port = None
    failed = False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
            receiver.bind((LOCAL_HOST, LOCAL_PORT))
            receiver.setblocking(False)
            port = serial.Serial(args.port, args.baud, timeout=0.05, write_timeout=0.2)
            time.sleep(1)
            port.reset_input_buffer()
            print(exchange(port, 'PING', 'PONG', 1.0))
            channel = args.channel.upper()
            print(exchange(port, f'CH:{channel}', f'OK:CH:{channel}', 1.0))
            print(exchange(port, 'MAP:' + ','.join(f'{v:.6f}' for v in firmware_mapping()), 'OK:MAP:', 1.0))
            print(f'Ready on {args.port}; listening on {LOCAL_HOST}:{LOCAL_PORT}. Ctrl+C to stop.')
            velocity = 0.0
            last_target = float('-inf')
            next_send = next_display = time.monotonic()
            while True:
                # Drain pending targets so the newest command wins.
                for _ in range(100):
                    try:
                        data, _ = receiver.recvfrom(128)
                    except BlockingIOError:
                        break
                    try:
                        velocity = parse_target(data)
                        last_target = time.monotonic()
                    except (ValueError, UnicodeError):
                        velocity = 0.0
                        last_target = float('-inf')
                        print('Invalid voltage target; requesting neutral.')
                now = time.monotonic()
                if now >= next_send:
                    target = velocity if now - last_target <= CMD_TIMEOUT else 0.0
                    command = velocity_to_firmware_command(target)
                    response = exchange(port, f'CMD:{command:.6f}', 'OK:CMD:')
                    if now >= next_display:
                        print(f'[STM32] {response} | Commanded velocity: {target:+.3f} m/s')
                        next_display = now + 1.0
                    next_send = now + SEND_PERIOD
                time.sleep(0.01)
    except KeyboardInterrupt:
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
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
