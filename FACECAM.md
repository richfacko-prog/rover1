# Face Cam

Park the rover and it takes a photo whenever it sees someone's face. The camera can't aim, so
the rover just watches whatever is in front of it, and it can spot faces up to about 3–4 m away.

**Open:** http://richardfacko.local:8000/facecam (or `rover2.local`). There's also a
**Face Cam** link at the top of the normal driving page.

## How to use it

1. Park the rover facing where people walk past or sit: a doorway, the sofa, the front door.
2. Open the Face Cam page and press **Start watching**.
3. Walk in front of it and look toward the rover. A yellow box appears around your face, then
   *Snap!* The page flashes and the photo pops into the gallery.

You can close the page; it keeps watching. Driving still works while it watches.

## What it does

- Looks for faces about 4 times a second. Far-away faces are tiny, so it also checks an
  enlarged copy of the picture.
- A face has to appear about 1 second in a row before it counts, so shadows and posters
  don't set it off.
- Then it watches 1 more second and keeps the sharpest frame with the biggest face.
- It takes **one photo per person**: it waits until nobody's been seen for 3 seconds (or a
  minute has passed) before taking another.
- Every photo is saved twice: the **whole picture**, and a **close-up** of the face(s),
  enlarged and sharpened because people are usually far away.
- **Snap a photo now** takes one straight away, face or not.

## The photos

- In the gallery, tap a photo to see it big. Switch between **Close-up** and **Whole picture**,
  **Download** it, or **Delete** it.
- On the Pi they're in `~/face_photos`. It keeps the newest 500 and deletes older ones.
- To copy them all to the PC (PowerShell): `scp -r richfacko@richardfacko.local:face_photos .`

## Settings

Put a `FACECAM` section in that rover's `~/rover.json` with only what you want to change,
then `sudo systemctl restart robot-drive`:

```json
{"NAME": "Rover 1", "FACECAM": {"START_WATCHING": true, "COOLDOWN_S": 5}}
```

| Setting | Default | What it does |
|---|---|---|
| `START_WATCHING` | false | Start watching as soon as the rover turns on |
| `COOLDOWN_S` | 8 | Shortest time between photos |
| `GONE_S` | 3 | How long nobody must be seen before the next person counts as new |
| `REPEAT_S` | 60 | Take another photo of someone who just stays there after this long |
| `FAR` | true | Look for far-away faces too (turn off to save CPU) |
| `CONFIRM` | 3 | Checks in a row with a face before it counts |
| `BURST_S` | 1.0 | How long it watches for the best shot |
| `MAX_PHOTOS` | 500 | Older photos are deleted beyond this |

**Sharper photos from far away:** the photos are the same size as the video (640 × 480). For
more detail, set `"VIDEO_SIZE": [1280, 960]` in `rover.json`. Photos get sharper and it sees
faces farther away, but the live video gets a bit slower over Wi-Fi.

## If it doesn't take photos

| Problem | Fix |
|---|---|
| "OpenCV isn't installed yet" | The rover's updater installs it by itself, or run `sudo apt install -y python3-opencv` and restart robot-drive. |
| No yellow box around faces | Face the rover, more light, closer than about 4 m. Faces from the side or in the dark aren't detected. |
| Box appears but no photo | It already has a photo of you: step out of view for 3 seconds. |
| Too many photos | Raise `COOLDOWN_S` or `GONE_S`. |

The face detector is OpenCV's LBP frontal-face model, in `models/` (see the license note there).
