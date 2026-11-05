#!/usr/bin/env bash
# Run once with sudo; udev applies permissions again on every connection.
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
    echo "Run: sudo bash $0 <login-user>" >&2
    exit 1
fi
serial_user=${1:-${SUDO_USER:-}}
if [[ -z "$serial_user" || "$serial_user" == root ]]; then
    echo "Specify the normal login user, for example: sudo bash $0 nilesh" >&2
    exit 1
fi
id "$serial_user" >/dev/null
getent group dialout >/dev/null || groupadd --system dialout
usermod -aG dialout "$serial_user"

install -m 0644 "$(dirname -- "${BASH_SOURCE[0]}")/../udev/99-four-motor-serial.rules" \
    /etc/udev/rules.d/99-four-motor-serial.rules
udevadm control --reload-rules
udevadm trigger --subsystem-match=tty --action=change
udevadm settle
echo "Serial permissions configured for $serial_user. Log out and back in before running the node."
