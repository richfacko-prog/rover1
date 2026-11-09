#!/bin/bash
# One-time setup on each rover's Pi (Pi 4 or Pi 3):
#     sudo bash ~/rover/pi/install.sh                     (keeps the name it already has)
#     sudo bash ~/rover/pi/install.sh "Rover 2" "#3b82f6"  (sets this rover's name and colour)
# Also used by update.sh as:  install.sh --units-only
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
U="$(stat -c %U "$REPO")"
HOME_DIR="$(getent passwd "$U" | cut -d: -f6)"

install_units() {
    for f in robot-drive.service rover-update.service rover-update.timer; do
        sed -e "s#__USER__#$U#g" -e "s#__REPO__#$REPO#g" "$REPO/pi/$f" > "/etc/systemd/system/$f"
    done
    chmod +x "$REPO/pi/update.sh"
    systemctl daemon-reload
}

if [ "$1" = "--units-only" ]; then
    install_units
    exit 0
fi

# software the rover needs (already there on the full Raspberry Pi OS; Lite needs it)
# python3-opencv: lets the camera recognise the printed markers in the arena games
NEED=""
for p in git python3-picamera2 python3-gpiozero python3-lgpio python3-opencv; do
    dpkg -s "$p" >/dev/null 2>&1 || NEED="$NEED $p"
done
if [ -n "$NEED" ]; then
    echo "Installing:$NEED"
    apt-get update
    apt-get install -y --no-install-recommends $NEED
fi
usermod -aG gpio,video "$U" 2>/dev/null || true

# this rover's own settings file (outside the repo, so updates never touch it)
CONF="$HOME_DIR/rover.json"
python3 - "$CONF" "${1:-}" "${2:-}" <<'EOF'
import json, sys
path, name, color = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    data = json.load(open(path))
except Exception:
    data = {}
if name:
    data["NAME"] = name
if color:
    data["COLOR"] = color
try:
    model = open("/proc/device-tree/model").read()
except Exception:
    model = ""
if "Raspberry Pi 3" in model and "VIDEO_FPS" not in data:
    data["VIDEO_FPS"] = 15           # Pi 3: lighter video so two rovers share the Wi-Fi smoothly
if data:
    json.dump(data, open(path, "w"), indent=2)
    print("This rover's settings (" + path + "):", data)
EOF
[ -f "$CONF" ] && chown "$U": "$CONF"

install_units
systemctl enable robot-drive
systemctl restart robot-drive
systemctl enable --now rover-update.timer

echo
echo "All set!"
echo " - The camera/drive page starts automatically: http://$(hostname).local:8000"
echo " - Split screen with every rover:              http://$(hostname).local:8000/fleet"
echo " - Arena games (phones or one PC):             http://$(hostname).local:8000/arena"
echo " - Print the markers for the games:            http://$(hostname).local:8000/markers"
echo " - The Pi checks GitHub every minute and installs new code by itself."
echo " - Update history: cat /var/log/rover-update.log"
echo " - This rover's own settings: $CONF"
