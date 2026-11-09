# Rovers

Raspberry Pi four-wheel rovers: they drive on their own and avoid obstacles, or stream the
camera and drive with the arrow keys from a web browser. Two rovers run the same code:

| Rover | Pi | Page |
|---|---|---|
| Rover 1 | Pi 4 | http://richardfacko.local:8000 |
| Rover 2 | Pi 3 or Pi 4 | http://rover2.local:8000 (build guide: [ROVER2.md](ROVER2.md)) |
| **Both, split screen** | | **http://richardfacko.local:8000/fleet** (W A S D = left rover, arrows = right rover) |
| **Arena games** | | **http://richardfacko.local:8000/arena** (Laser Battle, Manhunt, Treasure Hunt on two phones or one PC: [ARENA.md](ARENA.md)) |
| **Face Cam** | | **http://richardfacko.local:8000/facecam** (takes a photo when it sees a face: [FACECAM.md](FACECAM.md)) |

## Programs
| File | What it does |
|---|---|
| `robot_drive.py` | Live camera + arrow-key driving (starts automatically at boot), plus the `/fleet` split-screen page, the `/arena` games and `/facecam`. The distance sensor blocks driving forward when something is closer than 20 cm. |
| `arena.py`, `arena.html` | Camera games: the rovers recognise each other's printed markers. See [ARENA.md](ARENA.md). |
| `facecam.py`, `facecam.html`, `models/` | Face Cam: photo whenever it sees a face, saved to `~/face_photos`. See [FACECAM.md](FACECAM.md). |
| `robot.py` | Self-driving mode: avoids obstacles, detects when it's stuck, turns until it sees open space. Stop `robot-drive` first: `sudo systemctl stop robot-drive`. |
| `patrol.py` | Night patrol: roams, avoids obstacles, records video clips to `~/patrol_videos`. |
| `rover_config.py` | Reads each rover's own settings from `~/rover.json` (name, colour, wheel directions, camera). |
| `sensor_test.py`, `diagnose.py` | Check the distance sensor wiring. |
| `wheel_test.py`, `calibrate.py` | Check / fix which way the wheels spin (saved to `~/rover.json`). |
| `servo_test.py` | Check the tilt servo. |

## Per-rover settings
Both Pis run identical code. What's different about each rover lives in `~/rover.json` on that Pi
(outside the repo, so updates never overwrite it). See [ROVER2.md](ROVER2.md#per-rover-settings-roverjson).

## Automatic updates
Each Pi checks this repository every minute (`pi/rover-update.timer`). When new code is pushed,
it pulls it and restarts `robot-drive`. It also installs OpenCV once if it's missing (needed by the
arena games). Update history: `cat /var/log/rover-update.log`.
No internet (for example in hotspot mode) means no updates until it's back on home Wi-Fi.

One-time setup on a Pi (name and colour are optional):
```
git clone https://github.com/richfacko-prog/rover1.git ~/rover && sudo bash ~/rover/pi/install.sh "Rover 1" "#22aa77"
```

## Wiring (Pi physical pin numbers, same on the Pi 3 and Pi 4)
| Part | Pin |
|---|---|
| L298N IN1 / IN2 / IN3 / IN4 | 11 / 12 / 15 / 16 |
| L298N GND | 6 (or 14 if moved for the fan) + battery − |
| Sensor VCC / GND / Trig | 2 / 9 / 29 |
| Sensor Echo | 1k resistor → joining row → 31; joining row → 2k resistor → 20 |
| Fan (official Pi 4 case fan) | red 4, black 6, blue 8 |
| Tilt servo (SG90) | yellow 32, red 5V, black 34 |

Wheel directions are per rover (`FLIP_LEFT` / `FLIP_RIGHT` / `SWAP_SIDES` in `~/rover.json`; Rover 1 uses the defaults).

## 3D-printed parts
`3d/stl/`: two-deck chassis, deck posts, sensor bracket, Pi case, camera mount, tilt mount.
The same parts fit both rovers. `3d/*.py`: the scripts that generate them.

## Handy commands (on a Pi)
| To… | Command |
|---|---|
| Check the camera/drive service | `systemctl status robot-drive` |
| Stop / start it | `sudo systemctl stop robot-drive` / `sudo systemctl start robot-drive` |
| See this rover's settings | `cat ~/rover.json` |
| Hotspot mode on / off (Rover 1) | `sudo nmcli connection up RoverAP` / `sudo nmcli connection down RoverAP` |
| Hotspot page | http://10.42.0.1:8000 (Wi-Fi **Rover-Pi**) |
| Print the arena markers | http://richardfacko.local:8000/markers |
