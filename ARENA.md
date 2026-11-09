# Robot Arena: camera games

Games played through the rovers' cameras. No extra electronics: each rover wears a printed
marker, and the other rover's camera recognises it. Hits, catches and treasure finds all come
from what the camera sees, with the effects (lasers, explosions, cracked glass, clue photos,
confetti) animated on top of the live video.

**Open:** http://richardfacko.local:8000/arena (or `rover2.local`, either works)

## Set up (once)

1. **Let the rovers update.** They pull this code from GitHub by themselves within a minute, and
   install OpenCV (the library that recognises markers) on their own the first time. That
   install takes a few minutes. To do it by hand instead: `sudo apt install -y python3-opencv`,
   then `sudo systemctl restart robot-drive`.
2. **Print the markers:** open http://richardfacko.local:8000/markers and press Print (100% size).
3. **Stick them on.** Rover 1 wears marker **1**, Rover 2 wears marker **2**. Put one on the back
   and one on each side of the rover, flat, at roughly camera height. Cardboard backing keeps them flat.
   Keep the white border; it's part of the marker.
4. **Check it:** open the arena, pick any player, and point one rover's camera at the other's
   marker. In *Free drive* a blue box appears around every marker the camera sees.

## How to play

On the first screen, pick how you're playing:

| Choice | What you get |
|---|---|
| **Drive Rover 1 / Drive Rover 2** | This phone is that rover's controller. Turn the phone sideways: D-pad on the left, camera in the middle, FIRE on the right. Each player uses their own phone. |
| **Both players, one PC** | Split screen on one keyboard. Left player: W A S D drive, **E** fire, **Q** special, 1 2 3 speed. Right player: arrows drive, **Enter** fire, **Right Shift** special, 7 8 9 speed. Space stops both. |
| **Watch** | Both cameras and the score on a big screen, no controls. |

Anyone can choose the game and press **Start**. Everyone sees the same game, because Rover 1
(the first rover in the list) keeps score for everybody.

### Laser Battle
- 10 HP each, 12 shots, then a 3-second reload.
- Put the crosshair on the other rover's marker. It turns red and says **LOCKED**: fire!
- Close range (marker big on screen) does 2 damage.
- **Shield** (Q / Right Shift / the round button): blocks every hit for 3 seconds, then
  needs 15 seconds to recharge.
- First to 0 HP loses. After 3 minutes, more HP wins. Wins are counted across rematches.

### Manhunt
- Pick who hides, then Start. The hider gets a **2-minute head start**. Meanwhile the
  hunter's screen is blindfolded and their rover can't move.
- When the hunt starts, and then **every minute**, the hider's camera takes a photo that pops
  up on the hunter's screen. Old photos stay in a strip under the camera; tap one to see it big.
- **Catch:** drive close enough that the hider's marker fills the catch ring, and hold it for
  1 second. The ring fills up as you lock on.
- The hunter has 10 minutes. If time runs out, the hider wins.
- Hunter's special: **Ping** (2 per game) gets an extra photo right now.
  Hider's special: **Jam** (1 per game) scrambles the next photo.
- Hider tip: you can tilt or turn the camera before a photo to make it harder.

### Treasure Hunt
- Print the treasure markers (10 to 19) and hide them around the house, standing up at camera height.
- Press Start. Drive up to a treasure until the camera locks on (gold box) to claim it.
- Each treasure counts once, first come first served. Most treasure after 5 minutes wins.

## Changing the rules

Put an `ARENA` section in Rover 1's `~/rover.json` with only what you want to change, then
`sudo systemctl restart robot-drive`:

```json
{"NAME": "Rover 1", "ARENA": {"HP": 15, "HIDE_S": 60, "CLUE_EVERY_S": 45, "HUNT_S": 900}}
```

All settings, with what they do, are at the top of `arena.py` (`SETTINGS`).
`MARKER_ID` in `rover.json` changes which marker a rover wears (normally 1 for the first rover
in `FLEET`, 2 for the second).

## If something's not working

| Problem | Fix |
|---|---|
| Yellow note "Camera targeting off: OpenCV not installed" | Wait a few minutes for the update, or run `sudo apt install -y python3-opencv` and restart robot-drive. |
| Marker not detected | More light; no glare on shiny paper; marker flat and not too small; the whole marker including its white border in view. Test in Free drive. |
| Hits don't count | The crosshair zone is the dashed box in the middle. The marker has to be inside it and close enough that the label doesn't say "out of range". |
| Phone can't open `richardfacko.local` | Some Android phones don't understand `.local` names. Use the Pi's number instead, e.g. `http://192.168.2.159:8000/arena`. Tip: `hostname -I` on the Pi. |
| The two phones see different games | Both must use the same rover list. The game always runs on the first rover in the list. |
| Playing away from home | Rover 1 hotspot (`Rover-Pi`). Rover 2 and both phones join it. Use `http://10.42.0.1:8000/arena`. |

The arena runs inside `robot_drive.py`. If anything in the games goes wrong, plain driving still works.

## Files

| File | What it does |
|---|---|
| `arena.py` | Marker detection, the game rules and scorekeeping, the markers page |
| `arena.html` | The arena page: phone controller, split screen, animations and sounds |
