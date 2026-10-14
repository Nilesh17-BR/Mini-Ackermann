# Mini Ackermann

ROS 2 host scripts and STM32 firmware for converting linear velocity commands
into analog control voltage using an MCP4728 DAC.

## Project layout

```text
STM32/
├── README.md                 # Wiring, firmware, configuration and operation
├── setup.sh                  # Host dependency installation and checks
├── cmd_vel_stm2_dac.py        # ROS 2 to UART bridge
├── ros_cmd.py                # Interactive velocity publisher
├── test_urt.py               # UART PING test
└── dac_stm32/
    └── dac_stm32.ino         # STM32 Black Pill firmware
```

## Setup

Install and source ROS 2 on the host first. Replace `<distro>` below with your
installed distribution. The setup script installs missing host dependencies
using apt; it does not install ROS 2 itself or flash the firmware.

```bash
source /opt/ros/<distro>/setup.bash
cd STM32
./setup.sh
```

Follow the [STM32 README](STM32/README.md) for hardware wiring, firmware upload,
serial port configuration, and running the bridge and velocity publisher.
These are standalone Python scripts; a colcon build is not needed.

## Command flow

```text
ros_cmd.py → /cmd_vel_ros (geometry_msgs/Twist)
           → cmd_vel_stm2_dac.py → UART → STM32 → I2C → MCP4728
```

Only `linear.x` is used. Steering is not implemented in this workspace.
The default mapping converts -5 to +5 m/s into 0 to 5 V; zero velocity is
2.5 V. Keep the downstream drive disabled during startup and configuration,
and verify that this neutral voltage matches the controller before operation.
