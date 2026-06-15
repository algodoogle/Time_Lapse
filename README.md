# Time Lapse

A screen time-lapse recorder built with Pygame and Pillow. Captures screenshots at a fixed interval, saves them as sequential PNG frames, and can assemble them into a video with ffmpeg.

## Usage

Run `main.py` — a 360×374 window opens with controls for recording and converting frames to video.

| Button | Action |
|--------|--------|
| **Start** | Begin capturing screenshots at the selected interval |
| **Pause** | Pause capture |
| **Resume** | Continue capturing after a pause |
| **Stop** | Stop and reset the session |
| **Convert to Video** | Run ffmpeg to assemble frames into a timestamped `.mp4` |
| **FPS: 30fps / 60fps** | Toggle capture interval: 1 frame/2 s (30 fps) or 1 frame/1 s (60 fps) |
| **display: all / primary** | Toggle between capturing all monitors or the primary monitor only |
| **Save Folder** | Choose a save folder via file dialog (default: `./frames/`) |

### Notes

- Screenshots are saved as `0.png`, `1.png`, `2.png`, … in the chosen folder.
- Duplicate frames (no pixel change from the previous capture) are skipped automatically.
- **Convert to Video** requires ffmpeg to be installed and available on your PATH. The output file is named after the date and time recording started, e.g. `2024-06-15_14-30-22.mp4`, and is saved in the same folder as the frames.
- Save and preview happen in a background thread so the UI stays responsive during capture.

### Display info

- Total frames captured (including skipped duplicates)
- Saved frames count
- Skipped frames count
- Estimated video time at the selected frame rate

## Requirements

- Python 3.8+
- `pygame`
- `Pillow`

Install with:

```
py -m pip install -r requirements.txt
```

## Build with PyInstaller

```
py -m PyInstaller --onefile --noconsole --clean main.py
```
