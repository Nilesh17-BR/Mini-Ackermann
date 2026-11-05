# Four-wheel ROS 2 serial DAC

Flash the updated `Arduino/Arduino.ino` first: this bridge requires `CMD4`
(the older `CH`/`CMD` commands cannot retain four independent targets).
The firmware updates the four DAC channels sequentially within one command.

ROS package name: `four_motor_ctrl` (the source folder remains `4_motor_crtl`).

Edit `four_motor_ctrl/config.py` for the same velocity limits, VESC calibration, serial port,
send period and timeout used by `STM32_No_ROS`. This directory has its own
copy of those settings. Velocities are in m/s and clamp to the configured limits.

Default topic: `/wheel_velocities`, type `std_msgs/msg/Float64MultiArray`.
Each message must contain exactly four finite values:

| Topic value | Wheel | Default DAC output |
| --- | --- | --- |
| `data[0]` | 1 | A (0) |
| `data[1]` | 2 | B (1) |
| `data[2]` | 3 | C (2) |
| `data[3]` | 4 | D (3) |

Set `WHEEL_CHANNELS` in topic index order. For example,
`("C", "B", "A", "D")` routes wheel 1 to C, wheel 2 to B,
wheel 3 to A and wheel 4 to D. Every channel must appear exactly once.

From the repository root, with your ROS 2 environment sourced:

```bash
rosdep install --from-paths 4_motor_crtl --ignore-src -r -y
colcon build --symlink-install --packages-select four_motor_ctrl
source install/setup.bash
ros2 run four_motor_ctrl ros_serial_dac --port /dev/ttyUSB0
```

Optional overrides: `--topic /your_topic --baud 115200`.

To automatically grant serial port access on each connection, run once:

```bash
sudo bash 4_motor_crtl/scripts/setup_serial_permissions.sh "$USER"
```

Log out and back in afterward to activate your `dialout` group membership.
The installed udev rules grant that group read/write access to USB serial
ports (`ttyUSB*` and `ttyACM*`). Run the ROS node as your normal user.

Example publisher (four equal forward velocities):

```bash
ros2 topic pub -r 20 /wheel_velocities std_msgs/msg/Float64MultiArray '{data: [0.2, 0.2, 0.2, 0.2]}'
```

Missing/stale messages (default 0.5 s), malformed arrays and nonfinite values
request calibrated neutral on all four outputs. Shutdown sends `STOP`;
the firmware also retains its 500 ms serial watchdog.
The startup handshake checks `CMD4` support using four neutral commands.

`ros_serial_dac.py` is the executable ROS node. `serial_dac.py` contains
velocity conversion and serial communication helper functions imported by the
node. Settings are kept in `config.py`; only the ROS node needs to be run.

Use `--symlink-install` so edits to `four_motor_ctrl/config.py` remain available
to the installed node. Restart the node after editing settings.
