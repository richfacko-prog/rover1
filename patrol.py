"""
NIGHT PATROL for the rover (works on both rovers).

- Roams around and avoids obstacles (same brain as robot.py).
- Records video to the SD card in 5-minute clips: ~/patrol_videos/
- Stops by itself after PATROL_MINUTES (saves the batteries).
- Takes rests now and then so the motors and batteries last longer.

Before running:
  The drive page uses the camera and motors, so pause it first (in Terminal):
      sudo systemctl stop robot-drive
  Then run this file in Thonny (green Run), or in Terminal:
      python3 ~/rover/patrol.py
  Afterwards, turn the drive page back on:
      sudo systemctl start robot-drive

Watch the videos: open ~/patrol_videos in the Pi's file manager and double-click a clip
(or copy them to a USB stick). They are .mp4 files.
"""
import os
from datetime import datetime
from time import sleep, time
from gpiozero import Robot, DigitalOutputDevice, DigitalInputDevice

from rover_config import CFG, motor_pins

# ---------- settings you can change ----------
PATROL_MINUTES = 60      # how long to patrol in total
START_DELAY = 30         # seconds to wait before starting (time to put it down and leave)
DRIVE_SECONDS = 120      # drive this long...
REST_SECONDS = 30        # ...then sit still and watch this long (saves battery)
CLIP_MINUTES = 5         # length of each video file
RECORD_VIDEO = True
SPEED = 0.8              # a bit slower than full power: safer indoors, longer battery
TURN_SPEED = 1.0
STOP_CM = 35
CLEAR_CM = 60
# ---------------------------------------------

left_pins, right_pins = motor_pins(CFG)
robot = Robot(left=left_pins, right=right_pins)
trig = DigitalOutputDevice(CFG["TRIG_GPIO"])     # pin 29
echo = DigitalInputDevice(CFG["ECHO_GPIO"])      # pin 31
VIDEO_DIR = os.path.expanduser("~/patrol_videos")


def log(msg):
    print(datetime.now().strftime("%H:%M:%S"), msg, flush=True)


# ---------- distance sensor ----------
def ping():
    trig.on(); sleep(0.00002); trig.off()
    t0 = time()
    while not echo.value:
        if time() - t0 > 0.03:
            return None
    rise = time()
    while echo.value:
        if time() - rise > 0.03:
            return 500.0
    return (time() - rise) * 34300 / 2


def distance_cm():
    r = sorted(x for x in (ping(), ping(), ping()) if x is not None)
    return r[len(r) // 2] if r else None


# ---------- moving ----------
def spin(direction, seconds):
    (robot.left if direction == "left" else robot.right)(TURN_SPEED)
    sleep(seconds); robot.stop(); sleep(0.1)


def avoid():
    robot.stop(); sleep(0.1)
    robot.backward(SPEED); sleep(0.5); robot.stop(); sleep(0.1)
    spin("left", 0.35); left = distance_cm() or 0
    spin("right", 0.7); right = distance_cm() or 0
    if right >= CLEAR_CM and right >= left:
        return
    if left >= CLEAR_CM:
        spin("left", 0.7); return
    for _ in range(25):                       # keep turning until it sees open space
        spin("right", 0.15)
        d = distance_cm()
        if d and d >= CLEAR_CM:
            return


# ---------- camera ----------
class Recorder:
    def __init__(self):
        self.cam = None
        self.clip_start = 0
        if not RECORD_VIDEO:
            return
        try:
            from picamera2 import Picamera2
            from picamera2.encoders import H264Encoder
            from picamera2.outputs import FfmpegOutput
            self.H264Encoder, self.FfmpegOutput = H264Encoder, FfmpegOutput
            os.makedirs(VIDEO_DIR, exist_ok=True)
            self.cam = Picamera2()
            self.cam.configure(self.cam.create_video_configuration(main={"size": (1280, 720)}))
            self.start_clip()
        except Exception as e:
            log(f"Camera not working, patrolling without video: {e}")
            self.cam = None

    def start_clip(self):
        name = os.path.join(VIDEO_DIR, datetime.now().strftime("patrol_%Y-%m-%d_%H-%M-%S.mp4"))
        self.cam.start_recording(self.H264Encoder(bitrate=3_000_000), self.FfmpegOutput(name))
        self.clip_start = time()
        log(f"Recording {name}")

    def tick(self):
        if self.cam and time() - self.clip_start > CLIP_MINUTES * 60:
            self.cam.stop_recording()
            self.start_clip()

    def stop(self):
        if self.cam:
            self.cam.stop_recording()
            self.cam.close()


def main():
    log(f"{CFG['NAME']}: night patrol starts in {START_DELAY} seconds. Put me down!")
    sleep(START_DELAY)
    rec = Recorder()
    end = time() + PATROL_MINUTES * 60
    phase_end = time() + DRIVE_SECONDS
    driving = True
    log("Patrolling...")
    try:
        while time() < end:
            rec.tick()
            if time() > phase_end:                     # switch between driving and resting
                driving = not driving
                phase_end = time() + (DRIVE_SECONDS if driving else REST_SECONDS)
                robot.stop()
                log("Driving" if driving else "Resting and watching")
            if not driving:
                sleep(0.2)
                continue
            d = distance_cm()
            if d is not None and d < STOP_CM:
                log(f"Obstacle at {d:.0f} cm, turning")
                avoid()
            else:
                robot.forward(SPEED)
            sleep(0.03)
        log("Patrol time is over. Parking.")
    finally:
        robot.stop()
        rec.stop()
        log(f"Done. Videos are in {VIDEO_DIR}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
