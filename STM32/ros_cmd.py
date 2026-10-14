#!/usr/bin/env python3

import math
import threading
import time

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist


class VelocityPublisher(Node):

    def __init__(self):
        super().__init__('velocity_publisher')

        self.publisher = self.create_publisher(
            Twist,
            '/cmd_vel_ros',
            10
        )

        self.velocity = 0.0

        # Publish at 5 Hz
        self.timer = self.create_timer(
            0.2,
            self.publish_velocity
        )

    def publish_velocity(self):

        msg = Twist()
        msg.linear.x = self.velocity
        msg.angular.z = 0.0

        self.publisher.publish(msg)


def main():

    rclpy.init()
    node = VelocityPublisher()

    spin_thread = threading.Thread(
        target=rclpy.spin,
        args=(node,),
        daemon=True
    )
    spin_thread.start()

    print("\n====== LINEAR VELOCITY CONTROL ======")
    print("p : Increase velocity by 0.5 m/s")
    print("s : Decrease velocity by 0.5 m/s")
    print("0 : Stop")
    print("q : Quit")
    print("Number : Set velocity directly")
    print("=====================================\n")

    try:
        while True:

            value = input("Enter velocity: ").strip().lower()

            if value == 'q':
                break

            elif value == 'p':
                node.velocity += 0.5

            elif value == 's':
                node.velocity -= 0.5

            else:
                try:
                    velocity = float(value)

                    if not math.isfinite(velocity):
                        print("Invalid velocity")
                        continue

                    node.velocity = velocity

                except ValueError:
                    print("Invalid input! Use p, s, q or a number.")
                    continue

            print(f"Publishing: {node.velocity:.2f} m/s")

    except (KeyboardInterrupt, EOFError):
        pass

    finally:

        # Stop before exiting
        node.velocity = 0.0

        for _ in range(5):
            node.publish_velocity()
            time.sleep(0.05)

        rclpy.shutdown()
        spin_thread.join(timeout=1.0)
        node.destroy_node()

        print("\nVelocity stopped. Exiting...")


if __name__ == '__main__':
    main()