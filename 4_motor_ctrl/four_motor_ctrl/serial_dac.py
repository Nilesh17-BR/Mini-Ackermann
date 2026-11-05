#!/usr/bin/env python3
"""Velocity conversion and serial protocol helpers for the four-wheel ROS node."""

import time

from . import config as cfg


def velocity_to_vesc_voltage(velocity):
    """Map configured velocity limits to VESC voltage limits, with zero at center."""
    velocity = max(cfg.MIN_LINEAR_VELOCITY, min(cfg.MAX_LINEAR_VELOCITY, velocity))
    if velocity <= 0:
        return cfg.NEUTRAL_VESC_VOLTAGE + velocity * (
            cfg.NEUTRAL_VESC_VOLTAGE - cfg.MIN_VESC_VOLTAGE) / (-cfg.MIN_LINEAR_VELOCITY)
    return cfg.NEUTRAL_VESC_VOLTAGE + velocity * (
        cfg.MAX_VESC_VOLTAGE - cfg.NEUTRAL_VESC_VOLTAGE) / cfg.MAX_LINEAR_VELOCITY

def velocity_to_voltage(velocity):
    """Convert a velocity to compensated DAC output for the serial transport."""
    return (velocity_to_vesc_voltage(velocity) - cfg.VESC_OFFSET) / cfg.VESC_GAIN

def firmware_mapping():
    protocol_max = cfg.MAX_LINEAR_VELOCITY
    protocol_min = -protocol_max * (cfg.NEUTRAL_VOLTAGE - cfg.MIN_VOLTAGE) / (
        cfg.MAX_VOLTAGE - cfg.NEUTRAL_VOLTAGE)
    return protocol_min, protocol_max, cfg.MIN_VOLTAGE, cfg.MAX_VOLTAGE

def velocity_to_firmware_command(velocity):
    if velocity == 0.0:
        return 0.0
    protocol_min, protocol_max, low, high = firmware_mapping()
    return protocol_min + (velocity_to_voltage(velocity) - low) * (
        protocol_max - protocol_min) / (high - low)

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
