#!/usr/bin/env bash
# setup.sh - One-shot setup for rpi-sps30-air-quality on Raspberry Pi OS
# Run as: bash setup.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_USER="${SUDO_USER:-pi}"

echo "╔══════════════════════════════════════════════╗"
echo "║   SPS30 Air Quality Monitor – Setup Script   ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── 1. System dependencies ────────────────────────────────────────────────────
echo "→ Installing system dependencies…"
sudo apt-get update -qq
sudo apt-get install -y -qq python3-pip python3-venv python3-smbus i2c-tools

# ── 2. Enable I2C if not already enabled ─────────────────────────────────────
if ! grep -q "^dtparam=i2c_arm=on" /boot/config.txt 2>/dev/null && \
   ! grep -q "^dtparam=i2c_arm=on" /boot/firmware/config.txt 2>/dev/null; then
  echo "→ Enabling I2C in /boot/config.txt (reboot required after setup)…"
  if [ -f /boot/firmware/config.txt ]; then
    echo "dtparam=i2c_arm=on" | sudo tee -a /boot/firmware/config.txt
  else
    echo "dtparam=i2c_arm=on" | sudo tee -a /boot/config.txt
  fi
  sudo modprobe i2c-dev || true
fi

# ── 3. Python virtual environment ─────────────────────────────────────────────
echo "→ Creating Python virtual environment…"
python3 -m venv "${REPO_DIR}/.venv"
source "${REPO_DIR}/.venv/bin/activate"
pip install --upgrade pip setuptools wheel -q
# -e . installs the project as an editable package so `collector`, `api`,
# and `alerts` are importable from anywhere in the venv
pip install -e "${REPO_DIR}"
deactivate
echo "   venv ready at ${REPO_DIR}/.venv"

# ── 4. Data directory ─────────────────────────────────────────────────────────
mkdir -p "${REPO_DIR}/data"
sudo chown -R "${SERVICE_USER}:${SERVICE_USER}" "${REPO_DIR}/data"
chmod -R 775 "${REPO_DIR}/data"
echo "→ Data directory ready at ${REPO_DIR}/data"

# ── 5. .env file ──────────────────────────────────────────────────────────────
if [ ! -f "${REPO_DIR}/.env" ]; then
  cp "${REPO_DIR}/.env.example" "${REPO_DIR}/.env"
  echo "→ Created .env from .env.example — edit it to configure Telegram alerts"
fi

# ── 6. Install & start systemd services ──────────────────────────────────────
echo "→ Installing systemd services…"

for SVC in air-collector air-api; do
  SRC="${REPO_DIR}/systemd/${SVC}.service"
  DST="/etc/systemd/system/${SVC}.service"

  # Patch WorkingDirectory and ExecStart paths in service file
  sudo sed \
    -e "s|/home/pi/rpi-sps30-air-quality|${REPO_DIR}|g" \
    -e "s|User=pi|User=${SERVICE_USER}|g" \
    -e "s|Group=pi|Group=${SERVICE_USER}|g" \
    "${SRC}" | sudo tee "${DST}" > /dev/null

  sudo systemctl daemon-reload
  sudo systemctl enable "${SVC}"
  sudo systemctl restart "${SVC}"
  echo "   ${SVC}.service: enabled & started"
done

# ── 7. Sensor detection ───────────────────────────────────────────────────────
echo ""
echo "→ Detecting SPS30 on I2C bus 1 (address 0x69)…"
if i2cdetect -y 1 2>/dev/null | grep -q "69"; then
  echo "   ✅ SPS30 detected at 0x69"
else
  echo "   ⚠️  SPS30 not detected at 0x69 — check wiring or reboot if I2C was just enabled"
fi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  Setup complete!                             ║"
echo "║                                              ║"
echo "║  Dashboard: http://$(hostname -I | awk '{print $1}'):8000      ║"
echo "║  API docs:  http://$(hostname -I | awk '{print $1}'):8000/docs  ║"
echo "║                                              ║"
echo "║  Useful commands:                            ║"
echo "║  journalctl -fu air-collector                ║"
echo "║  journalctl -fu air-api                      ║"
echo "╚══════════════════════════════════════════════╝"

