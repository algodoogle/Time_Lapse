# Time Lapse

A screen recording app built with Pygame and PyAutoGUI that captures screenshots at a fixed interval and saves them as individual PNG frames for later video assembly.

## Usage

Run `main.py` — a 360x360 window opens with Start, Pause/Resume, Stop buttons and a folder picker.

| Button | Action |
|--------|--------|
| **Start** | Begin capturing screenshots every 2 seconds |
| **Pause** | Pause capture (resume with the Resume button) |
| **Resume** | Continue capturing after pause |
| **Stop** | Stop and reset the session |
| **Folder icon** | Switch save folder (default: `./frames/`) |

### Controls

- Click any button with the mouse.
- Screenshots are saved as `0.png`, `1.png`, `2.png`, ... in the chosen folder.
- Duplicate frames (no change from last capture) are skipped automatically.

### Display info

- Total frames captured (including skipped duplicates)
- Saved frames count
- Skipped frames count
- Estimated video time (at 30 fps)

## Requirements

- Python 3.11+
- `pygame`
- `pyautogui`

Install with:

```
py -m pip install pygame pyautogui
```

## Build with PyInstaller

```
py -m PyInstaller --onefile --noconsole --clean main.py
```
