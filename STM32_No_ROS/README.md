# STM32 voltage control without ROS

Control the STM32 Black Pill and MCP4728 DAC using two separate Python scripts.
Both scripts run on the same computer. No ROS installation is required.

| File | Purpose |
| --- | --- |
| `voltage_control.py` | Keyboard voltage controls; sends local UDP targets |
| `serial_dac.py` | Receives targets and communicates with STM32 using pyserial |
| `config.py` | Shared voltage mapping, serial port and UDP settings |
| `requirements.txt` | Python dependencies |
| `dac_stm32/dac_stm32.ino` | STM32 firmware |

```text
Keyboard -> voltage_control.py -> UDP 127.0.0.1:5005
         -> serial_dac.py -> UART -> STM32 -> I2C -> MCP4728
```

## Install dependencies

From the repository root:

```bash
cd STM32_No_ROS
python -m pip install -r requirements.txt
```

The serial bridge requires `pyserial`. The keyboard controller requires
`pynput` and a desktop session that supports keyboard capture.

## Run in two terminals

In terminal 1, from `STM32_No_ROS`, start the serial bridge:

```powershell
python serial_dac.py --port COM6
```

Replace `COM6` with your adapter's port. On Linux, for example:

```bash
python3 serial_dac.py --port /dev/ttyUSB1
```

Wait for PONG, channel/mapping acknowledgements and the Ready message. Leave
this terminal running. Optional serial settings:

```powershell
python serial_dac.py --port COM6 --baud 115200 --channel 1
```

Channels 0, 1, 2 and 3 select DAC outputs A, B, C and D respectively.
Only `serial_dac.py` should open the UART port. Close the ROS bridge and
other serial test programs before starting it.

In terminal 2, open the same folder and start the keyboard controller:

```bash
python voltage_control.py
```

The controller starts at neutral with HOLD disabled. Terminal 2 displays
the requested voltage and HOLD state. Terminal 1 displays STM32 responses.
These values describe commanded output; they are not voltage measurements.

## Keyboard controls

No Enter key is needed. Keyboard capture can also see presses while another
application is focused; stop the controller when finished.

| Key | Action |
| --- | --- |
| Up arrow | Increase voltage by `STEP` |
| Down arrow | Decrease voltage by `STEP` |
| `h` | Toggle HOLD mode, initially OFF |
| Space | Request neutral, currently 1.9 V |
| Esc | Exit and send a local neutral request |
| Ctrl+C in terminal 2 | Exit and send a local neutral request |

With HOLD **OFF**, each arrow-key press changes voltage once. Release and
press again for another change. Releasing a key keeps the last voltage.

With HOLD **ON**, holding Up or Down repeats changes every `INTERVAL` seconds.
The initial key press also changes voltage once. Release the arrow to keep
the current target. Holding both arrows pauses repeated changes. Targets
are limited to the configured minimum and maximum.

Space requests neutral immediately, but does not disable HOLD or clear held
arrows. Release the arrows to keep neutral; otherwise repeated changes may
resume while HOLD is ON.

## Step size and rate

The current keyboard script uses these constants in `voltage_control.py`:

```python
STEP = 0.1       # volts per change
INTERVAL = 0.2   # seconds between repeated changes with HOLD ON
```

The nominal repeat rate is:

```text
rate (volts/second) = STEP / INTERVAL
```

With the defaults, `0.1 / 0.2 = 0.5 V/s`. A 1 V change takes approximately
2 seconds while an arrow is held with HOLD ON. Actual timing depends on the
loop and keyboard events; the first press changes voltage immediately.

| STEP | INTERVAL | Nominal repeat rate |
| --- | --- | --- |
| 0.1 V | 0.2 s | 0.5 V/s |
| 0.1 V | 0.5 s | 0.2 V/s |
| 0.05 V | 0.2 s | 0.25 V/s |

Edit these constants and restart the keyboard controller to change them.
Use positive values; intervals below `SEND_PERIOD` are limited by the loop.

The earlier Enter-based controller is commented out in the source. Its
`--rate`, `--step`, numeric entry and `a` sweep command are not supported by
the active keyboard version. HOLD repeats changes while an arrow is held;
it stops changing at the voltage limit and does not reverse automatically.

## Shared settings and voltage mapping

Edit `config.py`, then restart both scripts:

| Setting | Current value | Meaning |
| --- | --- | --- |
| `MIN_LINEAR_VELOCITY` | -5.0 | Firmware mapping lower input |
| `MAX_LINEAR_VELOCITY` | 5.0 | Firmware mapping upper input |
| `MIN_VOLTAGE` | 0.5 V | Minimum target voltage |
| `MAX_VOLTAGE` | 3.3 V | Maximum target voltage |
| `SEND_PERIOD` | 0.1 s | Nominal target/send period, approximately 10 Hz |
| `LOCAL_HOST` | 127.0.0.1 | Local UDP address |
| `LOCAL_PORT` | 5005 | Local UDP port |
| `CMD_TIMEOUT` | 0.5 s | Maximum age of a received target |
| `SERIAL_PORT` | COM6 | Default UART device, overridden by `--port` |

The firmware accepts velocity-style CMD values, so the bridge converts volts
back into that mapping. No physical velocity measurement is involved:

```text
velocity = velocity_min + (voltage - voltage_min)
           * (velocity_max - velocity_min) / (voltage_max - voltage_min)
```

Current mapping: -5 maps to 0.5 V, zero maps to 1.9 V, and +5 maps to 3.3 V.
Neutral is the voltage corresponding to zero, not the minimum voltage.
Settings in this folder are independent of the ROS folder.

## Shutdown and timeouts

Exit the keyboard controller with Esc or Ctrl+C first. It sends three local
STOP messages; the bridge translates them into zero velocity (neutral) and
continues running. Then press Ctrl+C in terminal 1 to stop the serial bridge;
it attempts the firmware STOP command before closing UART.

If local voltage targets stop arriving for more than `CMD_TIMEOUT`, the
bridge sends zero velocity. The firmware also requests neutral on all channels
after more than 500 ms without valid UART CMD messages. Serial errors or STM32
ERR responses stop the bridge, which attempts STOP during cleanup.

## Firmware and wiring

Upload `dac_stm32/dac_stm32.ino` through the Arduino IDE with the STM32duino
core and the board/upload method appropriate to your STM32. This is the same
firmware as the ROS version; an existing upload does not need changing solely
to use these scripts.

| Connection | STM32 pin or setting |
| --- | --- |
| UART adapter RX | PA9 / USART1 TX |
| UART adapter TX | PA10 / USART1 RX |
| Adapter ground | Common ground with STM32 and DAC |
| MCP4728 SDA | PB7 |
| MCP4728 SCL | PB6 |
| MCP4728 LDAC | Ground |
| UART | 115200 baud, 8 data bits, no parity, 1 stop bit |
| DAC I2C address | 0x60 |

Firmware assumes a 5 V DAC supply. Measure the supply and adjust `DAC_VDD`
in the sketch if needed. Use compatible UART and I2C logic levels.
Firmware starts by writing 0 V to all channels; MAP and STOP write neutral
to all channels. Keep the downstream drive disabled during startup and
mapping changes, and measure the actual neutral voltage before enabling it.

## Troubleshooting

- **Missing `serial` or `pynput`:** install `requirements.txt` using the same Python interpreter used to run the scripts.
- **Keyboard capture unavailable:** run the controller in a supported desktop session; headless sessions and some Linux display configurations may not support pynput capture.
- **Serial port missing or busy:** check the adapter's device name and close other programs using it.
- **Linux permission denied:** check serial device ownership and your group membership.
- **No PONG:** check port, firmware, baud rate, crossed TX/RX and common ground.
- **UDP address already in use:** close the other bridge using port 5005; run one bridge and one controller.
- **Target displayed but output stays neutral:** confirm the bridge is running on the same computer with matching UDP settings, and check terminal 1 for errors.
- **DAC errors or unexpected voltage:** check supply, address, wiring, mapping and actual output with a meter.
