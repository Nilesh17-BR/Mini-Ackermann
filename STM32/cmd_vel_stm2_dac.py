#!/usr/bin/env python3

import time
import serial
import rclpy

from rclpy.node import Node
from geometry_msgs.msg import Twist


# ==========================================
# USER CONFIGURATION
# ==========================================

SERIAL_PORT = "/dev/ttyUSB1"
BAUD_RATE = 115200

# DAC Channel
# 0 = A, 1 = B, 2 = C, 3 = D
DAC_CHANNEL = 1

# Velocity range (m/s)
MIN_LINEAR_VELOCITY = -5.0
MAX_LINEAR_VELOCITY = 5.0

# DAC voltage range
MIN_VOLTAGE = 0.5
MAX_VOLTAGE = 3.3

# Communication
SEND_RATE = 10.0
CMD_TIMEOUT = 0.5


# ==========================================
# ROS2 NODE
# ==========================================

class STM32DAC(Node):

    def __init__(self):

        super().__init__("stm32_dac")

        self.velocity = 0.0
        self.last_cmd_time = time.monotonic()

        # Open UART
        self.ser = serial.Serial(
            SERIAL_PORT,
            BAUD_RATE,
            timeout=0.2,
            write_timeout=0.5
        )

        time.sleep(1)

        self.ser.reset_input_buffer()

        # Check STM32
        self.send_command("PING", "PONG")

        # Select DAC channel
        self.send_command(
            f"CH:{DAC_CHANNEL}",
            f"OK:CH:{DAC_CHANNEL}"
        )

        # Configure velocity-to-voltage mapping
        mapping = (
            f"MAP:{MIN_LINEAR_VELOCITY:.3f},"
            f"{MAX_LINEAR_VELOCITY:.3f},"
            f"{MIN_VOLTAGE:.3f},"
            f"{MAX_VOLTAGE:.3f}"
        )

        self.send_command(mapping, "OK:MAP:")

        # Subscribe to /cmd_vel
        self.create_subscription(
            Twist,
            "/cmd_vel_ros",
            self.cmd_callback,
            10
        )

        # Send velocity periodically
        self.timer = self.create_timer(
            1.0 / SEND_RATE,
            self.send_velocity
        )

        self.get_logger().info(
            f"STM32 Ready | Channel: {DAC_CHANNEL}"
        )


    # ==========================================
    # SEND CONFIGURATION COMMAND
    # ==========================================

    def send_command(self, command, expected):

        for attempt in range(5):

            self.ser.write(
                (command + "\n").encode()
            )

            self.ser.flush()

            deadline = time.monotonic() + 1.0

            while time.monotonic() < deadline:

                response = self.ser.readline().decode(
                    errors="replace"
                ).strip()

                if response.startswith(expected):
                    print(f"[STM32] {response}")
                    return

                if response.startswith("ERR:"):
                    raise RuntimeError(response)

            print(f"Retry {attempt + 1}/5: {command}")

        raise RuntimeError(
            f"STM32 not responding to {command}"
        )


    # ==========================================
    # RECEIVE ROS2 VELOCITY
    # ==========================================

    def cmd_callback(self, msg):

        self.velocity = msg.linear.x
        self.last_cmd_time = time.monotonic()


    # ==========================================
    # SEND VELOCITY TO STM32
    # ==========================================

    def send_velocity(self):

        # Stop if ROS2 commands are missing
        if time.monotonic() - self.last_cmd_time > CMD_TIMEOUT:
            velocity = 0.0
        else:
            velocity = self.velocity

        # Limit velocity
        velocity = max(
            MIN_LINEAR_VELOCITY,
            min(velocity, MAX_LINEAR_VELOCITY)
        )

        # Send UART command
        command = f"CMD:{velocity:.3f}\n"

        try:

            self.ser.write(command.encode())
            self.ser.flush()

            # Wait for STM32 response
            response = self.ser.readline().decode(
                errors="replace"
            ).strip()

            if response.startswith("OK:CMD:"):

                print(f"[STM32] {response}", flush=True)

            elif response.startswith("ERR:"):

                self.get_logger().error(response)

                self.timer.cancel()

            elif response:

                print(f"[STM32] {response}", flush=True)

            else:

                self.get_logger().warning(
                    "No response from STM32"
                )

        except serial.SerialException as e:

            self.get_logger().error(str(e))
            self.timer.cancel()


    # ==========================================
    # SHUTDOWN
    # ==========================================

    def destroy_node(self):

        if hasattr(self, "ser") and self.ser.is_open:

            try:
                self.ser.write(b"STOP\n")
                self.ser.flush()
                time.sleep(0.1)
            except serial.SerialException:
                pass

            self.ser.close()

        super().destroy_node()


# ==========================================
# MAIN
# ==========================================

def main():

    rclpy.init()

    node = None

    try:
        node = STM32DAC()
        rclpy.spin(node)

    except KeyboardInterrupt:
        print("\nStopping STM32 DAC")

    except Exception as e:
        print(f"ERROR: {e}")

    finally:

        if node is not None:
            node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()