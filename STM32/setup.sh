#!/usr/bin/env bash
set -euo pipefail
mode=install
case "${1:-}" in
  '') ;;
  --check) mode=check ;;
  --help|-h)
    echo 'Usage: ./setup.sh [--check | --help]'
    echo 'Source ROS 2 first. Default installs missing apt dependencies; --check only checks imports.'
    exit 0 ;;
  *) echo 'Usage: ./setup.sh [--check | --help]' >&2; exit 2 ;;
esac
if (( $# > 1 )); then echo 'Too many arguments' >&2; exit 2; fi
if [[ ! "${ROS_DISTRO:-}" =~ ^[a-z][a-z0-9_]*$ ]]; then
  echo 'Source an installed ROS 2 setup.bash first, or set ROS_DISTRO to its distribution name.' >&2
  exit 1
fi
ros_setup="/opt/ros/${ROS_DISTRO}/setup.bash"
if [[ -f "$ros_setup" ]]; then
  set +u
  source "$ros_setup"
  set -u
fi
if ! command -v ros2 >/dev/null 2>&1; then
  echo 'Install and source ROS 2 before running this script.' >&2
  exit 1
fi
if [[ "$mode" == install ]] && ! /usr/bin/python3 -c 'import serial; import rclpy; from geometry_msgs.msg import Twist' 2>/dev/null; then
  if ! command -v apt-get >/dev/null 2>&1; then
    echo 'Install Python 3, pyserial, rclpy and geometry_msgs manually; automatic installation requires apt.' >&2
    exit 1
  fi
  privilege=()
  if (( EUID != 0 )); then
    if ! command -v sudo >/dev/null 2>&1; then
      echo 'Dependency installation requires sudo or root.' >&2
      exit 1
    fi
    privilege=(sudo)
  fi
  "${privilege[@]}" apt-get update
  "${privilege[@]}" apt-get install -y python3 python3-serial "ros-${ROS_DISTRO}-rclpy" "ros-${ROS_DISTRO}-geometry-msgs"
fi
/usr/bin/python3 - <<'PY'
import serial
import rclpy
from geometry_msgs.msg import Twist
print('Dependencies OK: pyserial, rclpy, geometry_msgs')
PY
cat <<'TEXT'
Host setup complete. Source ROS 2 in every terminal and use /usr/bin/python3.
Next: flash the STM32 and configure serial ports using README.md.
Check your serial device's group. If it is dialout, run:
  sudo usermod -aG dialout "$USER"
Then log out and back in. This script does not change group membership.
TEXT
