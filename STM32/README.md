# STM32 velocity-to-DAC setup

This folder contains standalone ROS 2 Python scripts and Arduino firmware for
an STM32 Black Pill driving an MCP4728 four-channel DAC.

## Requirements and host setup

Use a Linux host with Python 3, an installed ROS 2 distribution, a USB-to-UART
adapter, an STM32 Black Pill, and an MCP4728 DAC. Firmware compilation requires
an Arduino IDE with the STM32duino core; the sketch targets STM32duino 3.x.

Replace `<distro>` with your installed ROS 2 distribution:

```bash
source /opt/ros/<distro>/setup.bash
cd /path/to/Mini-Ackermann/STM32
./setup.sh
```

The script checks system Python imports and installs missing `python3`,
`python3-serial`, `ros-${ROS_DISTRO}-rclpy`, and
`ros-${ROS_DISTRO}-geometry-msgs` packages through apt, using sudo if needed.
ROS 2 and its apt repositories must already be configured. It does not flash
firmware or change serial permissions. To check without installing:

```bash
./setup.sh --check
```

On a custom ROS installation, source its setup file first. On hosts without
apt, install the dependencies manually. Use `/usr/bin/python3` for the checked
system dependencies and source ROS 2 in every terminal.

Check serial device names and ownership:

```bash
ls -l /dev/ttyUSB* /dev/ttyACM*
```

If the adapter belongs to `dialout`, add your user and log out and back in:

```bash
sudo usermod -aG dialout "$USER"
```

## Wiring

| Connection | STM32 pin / configuration |
| --- | --- |
| Adapter RX | PA9 / USART1 TX |
| Adapter TX | PA10 / USART1 RX |
| Adapter ground | Common ground with STM32 and DAC |
| MCP4728 SDA | PB7 |
| MCP4728 SCL | PB6 |
| MCP4728 LDAC | Ground for immediate updates |
| UART | 115200 baud, 8 data bits, no parity, 1 stop bit |
| I2C | Address `0x60`, clock 100 kHz |

Use UART logic levels compatible with the MCU. Check DAC module supply and I2C
pull-up levels for MCU compatibility. Firmware assumes a 5 V DAC supply;
measure it and update `DAC_VDD` if needed. Update `DAC_ADDRESS` if the device
uses a different address. The Black Pill USB connector alone does not replace
a UART adapter connected to PA9/PA10 for this firmware.

## Upload firmware

Open `dac_stm32/dac_stm32.ino` in the Arduino IDE. Select the board matching
your actual STM32 chip and an upload method supported by your hardware, then
compile and upload. The sketch uses core Arduino and Wire libraries and writes
the MCP4728 protocol directly; no additional DAC library is required.

Keep the downstream drive disabled during startup and mapping changes.
Firmware startup writes **0 V to all channels**, before neutral is configured.
Default zero velocity is **2.5 V**. Verify the controller's neutral input and
measure the DAC output before enabling the drive.

## Configuration

Edit constants at the top of `cmd_vel_stm2_dac.py`:

| Setting | Default |
| --- | --- |
| `SERIAL_PORT` | `/dev/ttyUSB1` |
| `BAUD_RATE` | 115200 |
| `DAC_CHANNEL` | 1 (B); 0/1/2/3 select A/B/C/D |
| Velocity range | -5 to +5 m/s |
| Voltage range | 0 to 5 V |
| `SEND_RATE` | 10 Hz |
| `CMD_TIMEOUT` | 0.5 seconds |

`test_urt.py` defaults to **`/dev/ttyUSB0`**. Update its `PORT` separately.
These settings are source constants, not ROS parameters. Only one program
should use the serial port at a time.

## Run

First test UART with the firmware uploaded:

```bash
/usr/bin/python3 test_urt.py
```

Expect PONG responses. Close the test before starting the bridge.
In terminal 1:

```bash
source /opt/ros/<distro>/setup.bash
cd /path/to/Mini-Ackermann/STM32
/usr/bin/python3 cmd_vel_stm2_dac.py
```

The bridge sends PING, selects the DAC channel, and configures its mapping.
Expect `STM32 Ready | Channel: 1` on successful initialization.
In terminal 2:

```bash
source /opt/ros/<distro>/setup.bash
cd /path/to/Mini-Ackermann/STM32
/usr/bin/python3 ros_cmd.py
```

Enter a number to set velocity, `p` to increase by 0.5 m/s, `s` to decrease
by 0.5 m/s, `0` for neutral, or `q` to quit. Press Enter after each command.
The publisher sends `geometry_msgs/msg/Twist` on `/cmd_vel_ros` at 5 Hz.
The bridge uses only `linear.x` and clamps velocity to the configured range.
To inspect messages in another sourced terminal:

```bash
ros2 topic echo /cmd_vel_ros
```

## Mapping and timeout behavior

### Manual voltage control and automatic ramp

Keep `cmd_vel_stm2_dac.py` running in terminal 1. In a second terminal with
ROS 2 sourced, run this publisher instead of `ros_cmd.py`:

```bash
/usr/bin/python3 ros_voltage_cmd.py --step 0.1 --rate 0.2
```

Enter `p` or `s` to increase or decrease the voltage, or enter a number in
volts. Enter `a` to repeatedly ramp up and down at `--rate` volts/second;
`m` holds the current target. Manual adjustments also leave automatic mode.
Enter `n` to request neutral or `q` to exit and request neutral. Press Enter
after each command. `0` requests the minimum allowed voltage, not neutral.

This script imports the mapping constants from `cmd_vel_stm2_dac.py` and
converts voltage targets to `/cmd_vel_ros` velocity messages at 10 Hz. With
the current bridge settings, targets are clamped to 0.5–3.3 V and neutral is
1.9 V. Restart both scripts after changing mapping constants. The displayed
voltage is a requested target, not a measured DAC output. Run only one
publisher on `/cmd_vel_ros` at a time.

```text
voltage = voltage_min + (velocity - velocity_min)
          * (voltage_max - voltage_min) / (velocity_max - velocity_min)
```

Defaults: -5 m/s → 0 V, 0 m/s → 2.5 V, +5 m/s → approximately 5 V,
limited by the 12-bit DAC's full-scale code.

After 0.5 seconds without ROS commands, the bridge sends zero velocity.
After more than 500 ms without valid UART velocity commands, firmware writes
neutral to all channels. STOP also writes neutral to all channels once mapped,
or 0 V before mapping. These actions require successful I2C communication.
Normal bridge shutdown attempts STOP; the publisher sends zero before exiting.

## UART protocol

ASCII commands are terminated with `\n`.

| Command | Response / behavior |
| --- | --- |
| `PING` | `PONG` |
| `STATUS` | Reports channel, DAC readiness, configuration and neutral voltage. |
| `CH:1` | `OK:CH:1`; resets outputs and selects B. |
| `MAP:-5.000,5.000,0.000,5.000` | `OK:MAP:...`; writes new neutral to all channels. |
| `CMD:1.000` | `OK:CMD:1.000,CH:1,VL:3.000` with default mapping/channel. |
| `STOP` | `OK:STOP` if writes succeed. |

Mappings must include zero velocity, have increasing velocity and voltage
ranges, stay within ±100 m/s and 0–5 V. Errors return `ERR:...`; the serial
watchdog emits `WARN:SERIAL_TIMEOUT`.

## Troubleshooting

- **Missing module:** source ROS 2, run `./setup.sh --check`, and use system Python.
- **Port missing or denied:** verify adapter, configured port, device group, and group membership after logging back in.
- **No PONG:** verify firmware, baud rate, crossed TX/RX, common ground, and that another program is not using the port.
- **DAC errors:** check supply, address, SDA/SCL and pull-ups; restart after correcting hardware faults.
- **Unexpected output:** verify mapping constants and `DAC_VDD`, and measure the voltage before enabling the drive.
