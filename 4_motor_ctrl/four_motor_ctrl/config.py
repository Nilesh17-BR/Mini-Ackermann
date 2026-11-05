# Shared mapping and local communication settings.
MIN_LINEAR_VELOCITY = -5.0
MAX_LINEAR_VELOCITY = 5.0
# Measured VESC input = gain * DAC output + offset.
VESC_GAIN = 0.72857
VESC_OFFSET = 0.00238  # V: fitted intercept from measurements; DAC = (target VESC - offset) / gain.
MIN_VESC_VOLTAGE = 0.50
MAX_VESC_VOLTAGE = 2.80
NEUTRAL_VESC_VOLTAGE = (MIN_VESC_VOLTAGE + MAX_VESC_VOLTAGE) / 2.0
MIN_VOLTAGE = (MIN_VESC_VOLTAGE - VESC_OFFSET) / VESC_GAIN
NEUTRAL_VOLTAGE = (NEUTRAL_VESC_VOLTAGE - VESC_OFFSET) / VESC_GAIN
MAX_VOLTAGE = (MAX_VESC_VOLTAGE - VESC_OFFSET) / VESC_GAIN
SEND_PERIOD = 0.1

# VESC voltage = 0.72857 × DAC voltage + 0.00238
# DAC voltage = (VESC voltage - VESC_OFFSET) / VESC_GAIN

LOCAL_HOST = "127.0.0.1"
LOCAL_PORT = 5005
CMD_TIMEOUT = 0.5
SERIAL_PORT = "/dev/ttyUSB0"

# ROS Float64MultiArray: data[i] is wheel i+1 velocity in m/s.
VELOCITY_TOPIC = "/wheel_velocities"
SERIAL_BAUD = 115200
# Entry i selects the DAC channel for data[i]. Use each of A, B, C, D once.
WHEEL_CHANNELS = ("A", "B", "C", "D")
