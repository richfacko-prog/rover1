#!/bin/bash
# Runs every minute (rover-update.timer). If GitHub has new code, download it and
# restart the camera/drive program. Does nothing if there's no internet (e.g. hotspot mode).
REPO="$(cd "$(dirname "$0")/.." && pwd)"
U="$(stat -c %U "$REPO")"
LOG=/var/log/rover-update.log
cd "$REPO" || exit 0
sudo -u "$U" git fetch -q origin main 2>/dev/null || exit 0

# the arena games need OpenCV to recognise the printed markers; install it once if missing
RESTART=0
if ! dpkg -s python3-opencv >/dev/null 2>&1; then
    echo "$(date '+%F %T') installing python3-opencv for the arena games" >> "$LOG"
    if apt-get install -y --no-install-recommends python3-opencv >> "$LOG" 2>&1 || \
       { apt-get update >> "$LOG" 2>&1 && apt-get install -y --no-install-recommends python3-opencv >> "$LOG" 2>&1; }; then
        RESTART=1
    fi
fi

LOCAL=$(sudo -u "$U" git rev-parse HEAD)
REMOTE=$(sudo -u "$U" git rev-parse origin/main)
if [ "$LOCAL" = "$REMOTE" ]; then
    [ "$RESTART" = 1 ] && systemctl restart robot-drive
    exit 0
fi

CHANGED=$(sudo -u "$U" git diff --name-only "$LOCAL" "$REMOTE")
sudo -u "$U" git reset -q --hard origin/main
echo "$(date '+%F %T') updated ${LOCAL:0:7} -> ${REMOTE:0:7}: $(echo $CHANGED)" >> "$LOG"

# if the service files changed, install the new versions
if echo "$CHANGED" | grep -qE '^pi/.*\.(service|timer)$'; then
    bash "$REPO/pi/install.sh" --units-only
fi
systemctl restart robot-drive
