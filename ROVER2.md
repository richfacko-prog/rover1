# Rover 2 (Raspberry Pi 3): build and setup

Rover 2 is a copy of Rover 1 with a Raspberry Pi 3 instead of the Pi 4. It runs **the same code
from this repo** and updates itself from GitHub the same way. The only things that differ live in a
small settings file on its own Pi, `~/rover.json` (name, colour, wheel directions, video speed).

## What's the same / what's different

| | Rover 1 (Pi 4) | Rover 2 (Pi 3) |
|---|---|---|
| Hostname | `richardfacko` | `rover2` |
| Page | http://richardfacko.local:8000 | http://rover2.local:8000 |
| Chassis, Pi case, camera/tilt mount | `3d/stl/` | **the same STL files** (Pi 3 and Pi 4 have the same 58 x 49 mm screw holes) |
| Wiring (GPIO header) | see README | **identical pin for pin** |
| Power for the Pi | USB-C | **micro-USB** cable from the power bank |
| Camera port | between micro-HDMI and audio | between full-size HDMI and audio (same ribbon, same direction: silver contacts toward the HDMI) |
| Video | 24 fps | 15 fps (set automatically by the installer; smoother with two rovers on one Wi-Fi) |
| Wi-Fi | 2.4 + 5 GHz | Pi 3 **B+**: 2.4 + 5 GHz. Plain Pi 3 **B**: 2.4 GHz only (make sure your router has 2.4 GHz on) |

The Pi 3's ports all sit on the same long edge as the Pi 4's, inside the Pi case's port window, so the
printed case fits as is. The full-size HDMI is taller than the Pi 4's micro-HDMI but still clears the window.

## Shopping / parts list (a second set of everything)

- Raspberry Pi 3 B or B+, microSD card (16 GB or more)
- Pi Camera Module (any version: v1, v2, v3) + a 25-30 cm ribbon cable
- 4x TT gear motors with 65 mm wheels, L298N motor driver, 6xAA battery holder
- HC-SR04 distance sensor, one 1k and one 2k resistor, small breadboard, jumper wires
- USB power bank (5 V 2.4 A is plenty for a Pi 3) + **micro-USB** cable
- Optional: official Pi 4 case fan (works on the Pi 3 too), SG90 servo for the tilt mount
- Screws, zip ties, Velcro: same list as `3d/stl/README.md`

Print the same parts as Rover 1: `lower_deck`, `upper_deck`, `sensor_bracket`, `deck_posts_x4`,
`pi_case_base`, `pi_case_lid`, and `camera_mount` (or `tilt_bracket` + `tilt_head`).
A different filament colour makes it easy to tell the rovers apart.

## Wiring (Pi physical pin numbers, same as Rover 1)

| Part | Pin |
|---|---|
| L298N IN1 / IN2 / IN3 / IN4 | 11 / 12 / 15 / 16 |
| L298N GND | 6 (or 14) **and** battery − |
| L298N 12V | battery + (Leave the ENA/ENB jumper caps on. Don't power the Pi from the L298N.) |
| Sensor VCC / GND / Trig | 2 / 9 / 29 |
| Sensor Echo | 1k resistor → joining row → 31; joining row → 2k resistor → 20 |
| Fan (optional) | red 4, black 6, blue 8 |
| Tilt servo (optional) | yellow 32, red 5V (pin 4 is shared with the fan: use a breadboard row, or the L298N's 5V screw), black 34 |

**Fan on the Pi 3:** add this line to the end of `/boot/firmware/config.txt`, then reboot:
`dtoverlay=gpio-fan,gpiopin=14,temp=60000` (fan comes on above 60 °C).

## Setting up the Pi 3

1. **Flash the SD card** on your PC with Raspberry Pi Imager:
   Device *Raspberry Pi 3*, OS *Raspberry Pi OS (64-bit)*. (The *Lite* version runs the video
   a bit smoother on the Pi 3's 1 GB, but has no desktop or Thonny. Either works.)
   In the settings (gear / "Edit settings"): hostname **rover2**, username **richfacko** + a password,
   your home Wi-Fi, and **enable SSH**.
2. **Assemble and wire** it like Rover 1. Plug in the camera with the Pi switched off.
3. **Boot it**, wait 2 minutes, then from PowerShell on the PC: `ssh richfacko@rover2.local`
4. **Check the camera:** `rpicam-hello --list-cameras` (it should list one camera).
5. **Install the rover code** (one line; installs anything missing, takes a few minutes the first time):
   ```
   git clone https://github.com/richfacko-prog/rover1.git ~/rover && sudo bash ~/rover/pi/install.sh "Rover 2" "#3b82f6"
   ```
6. **Calibrate the wheels** (rover propped up, AA pack on):
   ```
   sudo systemctl stop robot-drive
   python3 ~/rover/calibrate.py
   sudo systemctl start robot-drive
   ```
   The answers are saved in `~/rover.json` on this Pi only.
7. **Turn off Wi-Fi power saving** (fewer video freezes):
   `sudo nmcli connection modify "<your wifi name>" 802-11-wireless.powersave 2` then `sudo reboot`.
8. Open **http://rover2.local:8000**. Check the forward arrow drives forward and the sensor shows a distance.

## Rover 1 needs the new code too

Rover 1 picks up the new code from GitHub by itself. Run the installer once more on it so it gets
its name and colour (green) for the split screen:
```
sudo bash ~/rover/pi/install.sh "Rover 1" "#22aa77"
```
Its wheel directions are the defaults, so it needs no calibration.

## Split screen: drive both from the PC

Open **http://richardfacko.local:8000/fleet** (or `http://rover2.local:8000/fleet`: either rover serves it).

| | Left rover | Right rover |
|---|---|---|
| Drive | W A S D | arrow keys |
| Speed slow / medium / fast | 1 / 2 / 3 | 7 / 8 / 9 |
| Camera tilt (if fitted) | R / F | Page Up / Page Down |

- **Space** stops both. Letting go of the keys stops that rover (and each rover stops on its own after
  half a second if it stops hearing from the PC).
- **Drive all together** (checkbox at the top): either set of keys drives both rovers at once.
- Two people can play on one keyboard: one on W A S D, one on the arrows.
- The box at the top lists the rovers, left to right. Change it to swap sides or add a third rover,
  then press Apply (the PC remembers it). The default list is in `rover_config.py` (`FLEET`).
- A rover that's off shows "can't reach"; it reconnects by itself when it comes back.

Both rovers must be on the **same Wi-Fi** as the PC. In hotspot mode (Rover-Pi), split screen works if
Rover 2 joins Rover 1's hotspot: on Rover 2 run `sudo nmcli device wifi connect Rover-Pi password <hotspot password>`.

## Per-rover settings (`~/rover.json`)

Only put in what you want to change. Example for Rover 2:
```json
{"NAME": "Rover 2", "COLOR": "#3b82f6", "VIDEO_FPS": 15, "FLIP_RIGHT": true, "USE_TILT": true}
```
| Setting | What it does |
|---|---|
| `NAME`, `COLOR` | label and colour on the pages |
| `FLIP_LEFT`, `FLIP_RIGHT`, `SWAP_SIDES` | wheel directions (calibrate.py sets these) |
| `VIDEO_FPS`, `VIDEO_SIZE`, `FLIP_CAMERA` | camera |
| `USE_TILT` | `true` if the SG90 tilt servo is fitted |
| `FLEET` | rovers on the split-screen page |

After editing: `sudo systemctl restart robot-drive`.
