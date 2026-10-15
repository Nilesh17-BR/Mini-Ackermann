# Mini Ackermann

Host scripts and STM32 firmware for controlling an MCP4728 DAC through UART.
Choose the ROS 2 setup or the standalone keyboard setup without ROS.

## Project layout

| Folder | Contents | Instructions |
| --- | --- | --- |
| `STM32/` | ROS 2 velocity/voltage publishers, UART bridge and firmware | [ROS setup](STM32/README.md) |
| `STM32_No_ROS/` | Separate keyboard voltage controller, pyserial bridge, shared settings and firmware | [Non-ROS setup](STM32_No_ROS/README.md) |

## Without ROS

Install dependencies from the repository root:

```bash
cd STM32_No_ROS
python -m pip install -r requirements.txt
```

In terminal 1, start the serial bridge (replace COM6 with your adapter's port):

```bash
python serial_dac.py --port COM6
```

In terminal 2, from the same folder:

```bash
python voltage_control.py
```

Up/Down changes voltage, `h` toggles repeated changes while holding an arrow,
Space requests neutral, and Esc exits. No Enter key is needed. The current
keyboard version uses `STEP` and `INTERVAL` constants rather than `--rate`
and `--step` options. See the [non-ROS README](STM32_No_ROS/README.md) for
rate examples, all controls, configuration, wiring and shutdown behavior.

## With ROS 2

Install and source ROS 2 first. Replace `<distro>` with your distribution:

```bash
source /opt/ros/<distro>/setup.bash
cd STM32
./setup.sh
```

Follow the [STM32 README](STM32/README.md) to run `cmd_vel_stm2_dac.py`
with either `ros_cmd.py` (velocity commands) or `ros_voltage_cmd.py`
(voltage targets and an automatic up/down ramp). A colcon build is not needed.

## Hardware and mapping

Both setups use STM32 Black Pill firmware and an MCP4728 DAC. Current host
settings map -5 to +5 input commands to 0.5-3.3 V, with neutral at 1.9 V.
Only the ROS bridge's `linear.x` is used; steering is not implemented.
Run only one setup on the UART port at a time.

Firmware startup writes 0 V before mapping is configured. Keep the downstream
drive disabled during startup and configuration, and verify actual output
and the controller's required neutral voltage before operation. Wiring and
firmware-upload instructions are in each folder's README.
