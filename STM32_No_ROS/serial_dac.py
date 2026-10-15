#!/usr/bin/env python3
"""Receive local voltage targets and communicate with the STM32 using pyserial."""

import argparse
import math
import socket
import time

from config import (
    MIN_LINEAR_VELOCITY, MAX_LINEAR_VELOCITY, MIN_VOLTAGE, MAX_VOLTAGE,
    SEND_PERIOD, LOCAL_HOST, LOCAL_PORT, CMD_TIMEOUT, SERIAL_PORT,
)


def voltage_to_velocity(voltage):
    return MIN_LINEAR_VELOCITY + (voltage - MIN_VOLTAGE) * (
        MAX_LINEAR_VELOCITY - MIN_LINEAR_VELOCITY
    ) / (MAX_VOLTAGE - MIN_VOLTAGE)


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
    parser.add_argument('--channel', type=int, choices=range(4), default=1)
    args = parser.parse_args()
    mapping = (MIN_LINEAR_VELOCITY, MAX_LINEAR_VELOCITY, MIN_VOLTAGE, MAX_VOLTAGE)
    if (args.baud <= 0 or not all(math.isfinite(v) for v in mapping)
            or not -100 <= MIN_LINEAR_VELOCITY <= 0 <= MAX_LINEAR_VELOCITY <= 100
            or MIN_LINEAR_VELOCITY >= MAX_LINEAR_VELOCITY
            or not 0 <= MIN_VOLTAGE < MAX_VOLTAGE <= 5):
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
            print(exchange(port, f'CH:{args.channel}', f'OK:CH:{args.channel}', 1.0))
            print(exchange(port, 'MAP:' + ','.join(f'{v:.3f}' for v in mapping), 'OK:MAP:', 1.0))
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
                    response = exchange(port, f'CMD:{target:.3f}', 'OK:CMD:')
                    if now >= next_display:
                        print(f'[STM32] {response}')
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
