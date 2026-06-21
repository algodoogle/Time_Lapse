import pygame
from pygame.locals import *
import time
import os
import subprocess
import threading
import tkinter
import tkinter.filedialog
from PIL import ImageGrab
import logging
import datetime

# Module-level logger shared by every function. setUpLogging() configures the
# root logger's handlers; records from this logger propagate up to them.
log = logging.getLogger(__name__)

WINDOW_W = 360
WINDOW_H = 374

# -- hit boxes [x1, y1, x2, y2] ------------------------------------------
left_box   = [0,   294, 180, 358]   # Start / Pause / Resumepygame.font.SysFont
right_box  = [180, 294, 360, 358]   # Convert / Stop
fps_box    = [0,   258, 120, 290]   # options row -- equal thirds
disp_box   = [120, 258, 240, 290]
folder_box = [240, 258, 360, 290]

# -- colors ---------------------------------------------------------------
fps_color_30    = tuple(bytes.fromhex("277da1"))
fps_color_60    = tuple(bytes.fromhex("577590"))
disp_color_all  = tuple(bytes.fromhex("4d908e"))
disp_color_pr   = tuple(bytes.fromhex("43aa8b"))
C_Save          = tuple(bytes.fromhex("90be6d"))
C_Start         = tuple(bytes.fromhex("f9c74f"))
C_conv          = tuple(bytes.fromhex("f9844a"))
C_Pause         = tuple(bytes.fromhex("f8961e"))
C_Stop          = tuple(bytes.fromhex("f94144"))
C_Resume        = tuple(bytes.fromhex("f3722c"))




 # -- capture settings -----------------------------------------------------
fps_mode = '30fps'
seconds_between_frames = 2.0
display_mode = 'all'

default_path = os.path.join(os.getcwd(), 'frames')
os.makedirs(default_path, exist_ok=True)
path = default_path



# -- session state --------------------------------------------------------
on_frame = 0
skipped = 0
status = 'stopped'
running = True
last_bytes = b''
last_preview = pygame.Surface((10, 10))
mouse_pos = [0, 0]
convert_status = ''

# -- timing ---------------------------------------------------------------
clock = pygame.time.Clock()
start_time = time.perf_counter()
total_paused = 0.0
pause_start = 0.0
frame_captures = 1

# -- background capture threads -------------------------------------------
# Phase 1: grab + compare  ->  capture_result = (on_frame_delta, skipped_delta, new_last_bytes)
capture_lock = threading.Lock()
capture_result = None
capture_in_progress = False

# Phase 2: save + preview  ->  preview_result = pygame.Surface
preview_lock = threading.Lock()
preview_result = None



# -- helpers ------------------------------------------------------------------

def get_save_folder(current_path):
    root = tkinter.Tk()
    root.withdraw()
    folder = tkinter.filedialog.askdirectory(title='Select save folder')
    root.destroy()
    if folder:
        os.makedirs(folder, exist_ok=True)
        return folder
    return current_path


def get_time_str(frames, fps):
    seconds = int(round(frames / fps))
    if seconds >= 3600:
        hours = seconds // 3600
        remaining = seconds % 3600
        minutes = remaining // 60
        seconds = remaining % 60
        return f'{hours}h,{minutes}m,{seconds}s'
    if seconds >= 60:
        minutes = seconds // 60
        seconds = seconds % 60
        return f'{minutes}m,{seconds}s'
    return f'{seconds}s'


def is_in(rect, xy):
    return rect[0] <= xy[0] < rect[2] and rect[1] <= xy[1] < rect[3]


def draw_button(surface, rect, label, font, color, hovered=False):
    """Draw a filled rect button with centered, word-wrapped text. Brightens on hover."""
    r, g, b = color
    fill = (max(r - 30, 0), max(g - 30, 0), max(b - 30, 0)) if hovered else color
    pygame.draw.rect(surface, fill, rect)

    btn_w = rect[2] - rect[0]
    btn_h = rect[3] - rect[1]

    # Greedy word-wrap: split onto new lines at spaces when text is too wide
    lines, current = [], ''
    for word in label.split():
        test = (current + ' ' + word).strip()
        if font.size(test)[0] <= btn_w:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    line_h = font.get_height()
    total_h = len(lines) * line_h
    start_y = rect[1] + (btn_h - total_h) // 2
    for i, line in enumerate(lines):
        ls = font.render(line, True, (255, 255, 255))
        tx = rect[0] + (btn_w - ls.get_width()) // 2
        surface.blit(ls, [tx, start_y + i * line_h])


def make_preview(im):
    """Convert a PIL image to a pygame Surface scaled to fit the 360x180 preview."""
    rgb = im.convert('RGB')
    surf = pygame.image.fromstring(rgb.tobytes(), rgb.size, 'RGB')
    if surf.get_width() > 360:
        scale = surf.get_width() / 360
        surf = pygame.transform.smoothscale(surf, (360, int(surf.get_height() / scale)))
    if surf.get_height() > 180:
        scale = surf.get_height() / 180
        surf = pygame.transform.smoothscale(surf, (int(surf.get_width() / scale), 180))
    return surf

def set_up_screen():
    screen = pygame.display.set_mode([WINDOW_W, WINDOW_H])
    pygame.display.set_caption('Time Lapse')

    try:
        icon = pygame.image.load('icon.ico')
        pygame.display.set_icon(icon)
    except Exception:
        pass
    return screen

def active_elapsed():
    now = time.perf_counter()
    current_pause = (now - pause_start) if status == 'paused' else 0.0
    return now - start_time - total_paused - current_pause

def do_save_preview(im, snap_frame, snap_path):
    """Phase 2 (fire-and-forget): save PNG and build preview surface."""
    global preview_result

    try:
        frame_path = os.path.join(snap_path, f'{snap_frame}.png')
        im.save(frame_path, compress_level=1)
        log.debug('Saved frame %s -> %s', snap_frame, frame_path)

        prev = make_preview(im)

        with preview_lock:
            preview_result = prev
    except Exception as e:
        log.warning('Save/preview failed: %s', e)

def do_capture(snap_last, snap_frame, snap_path, snap_display):
    """Phase 1: grab screen and compare to last frame. Spawns Phase 2 on change."""
    global capture_in_progress, capture_result
    try:
        im = ImageGrab.grab(all_screens=(snap_display == 'all'))
        raw = im.tobytes()

        if raw == snap_last:
            result = (0, 1, snap_last)
        else:
            result = (1, 0, raw)
            threading.Thread(
                target=do_save_preview,
                args=(im, snap_frame, snap_path),
                daemon=True,
            ).start()
    except Exception as e:
        log.warning('Screenshot capture failed: %s', e)
        result = (0, 1, snap_last)

    with capture_lock:
        capture_result = result
    capture_in_progress = False   # cleared here so next capture can start immediately

def run_ffmpeg():
    global convert_status
    fps = 30 if fps_mode == '30fps' else 60
    try:
        mtime = os.path.getmtime(os.path.join(path, '0.png'))
        timestamp = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d_%H-%M-%S')
    except OSError:
        timestamp = 'output'
    out_file = os.path.join(path, f'{timestamp}.mp4')
    cmd = [
        'ffmpeg', '-y',
        '-framerate', str(fps),
        '-i', os.path.join(path, '%d.png'),
        '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p',
        out_file,
    ]
    log.info('Running ffmpeg: %s', ' '.join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        stdout = result.stdout.decode(errors='replace').strip()
        stderr = result.stderr.decode(errors='replace').strip()
        if stdout:
            log.debug('ffmpeg stdout:\n%s', stdout)
        if stderr:
            log.debug('ffmpeg stderr:\n%s', stderr)
        if result.returncode == 0:
            log.info('ffmpeg finished successfully -> %s', out_file)
            for f in os.listdir(path):
                if f.endswith('.png'):
                    try:
                        os.remove(os.path.join(path, f))
                    except OSError as e:
                        log.warning('Could not delete frame %s: %s', f, e)
            log.info('Frame images deleted')
            convert_status = 'done'
        else:
            log.error('ffmpeg exited with code %d', result.returncode)
            convert_status = 'error'
    except FileNotFoundError:
        log.error('ffmpeg executable not found in PATH')
        convert_status = 'not found'
    except Exception as e:
        log.exception('Unexpected error running ffmpeg: %s', e)
        convert_status = 'error'

def on_click():
    global status, start_time, total_paused, frame_captures, on_frame, skipped
    global last_bytes, convert_status, pause_start, fps_mode
    global seconds_between_frames, display_mode, path
    if status == 'stopped' and is_in(left_box, mouse_pos):
        log.debug('Time Lapse started')
        status = 'running'
        start_time = time.perf_counter()
        total_paused = 0.0
        frame_captures = 1
        on_frame = 0
        skipped = 0
        last_bytes = b''
        convert_status = ''

    elif status == 'running' and is_in(left_box, mouse_pos):
        log.debug('Time Lapse paused')
        status = 'paused'
        pause_start = time.perf_counter()

    elif status == 'paused' and is_in(left_box, mouse_pos):
        log.debug('Time Lapse unpaused')
        status = 'running'
        total_paused += time.perf_counter() - pause_start

    elif status in ('paused', 'running') and is_in(right_box, mouse_pos):
        log.debug('Time Lapse stopped')
        if status == 'paused':
            total_paused += time.perf_counter() - pause_start
        status = 'stopped'

    elif status == 'stopped' and is_in(right_box, mouse_pos) and convert_status != 'converting':
        log.debug('converting...')
        convert_status = 'converting'
        threading.Thread(target=run_ffmpeg, daemon=True).start()

    elif status == 'stopped' and is_in(fps_box, mouse_pos):
        if fps_mode == '30fps':
            log.debug('fps_mode set to 60fps')
            fps_mode = '60fps'
            seconds_between_frames = 1.0
        else:
            log.debug('fps_mode set to 30fps')
            fps_mode = '30fps'
            seconds_between_frames = 2.0

    elif status == 'stopped' and is_in(disp_box, mouse_pos):
        display_mode = 'primary' if display_mode == 'all' else 'all'
        log.debug(f'display_mode set to: {display_mode}')

    elif status == 'stopped' and is_in(folder_box, mouse_pos):
        path = get_save_folder(path)
        log.debug(f'path set to: {path}')


def do_draw():
    screen.fill([236, 240, 241])

    # Preview area
    pygame.draw.rect(screen, (0, 0, 0), [0, 0, 360, 180])
    px = int(round((360 - last_preview.get_width()) / 2))
    py = int(round((180 - last_preview.get_height()) / 2))
    screen.blit(last_preview, [px, py])

    # Stats
    effective_fps = 30 if fps_mode == '30fps' else 60
    total_frames = on_frame + skipped
    y = 184
    gap = 18
    screen.blit(font.render(f'total frames:  {total_frames:<8} time: {get_time_str(total_frames, effective_fps)}', True, (0, 0, 0)), [5, y])
    screen.blit(font.render(f'saved frames:  {on_frame:<8} time: {get_time_str(on_frame, effective_fps)}', True, (0, 0, 0)), [5, y + gap])
    screen.blit(font.render(f'skipped frames:{skipped:<8} time: {get_time_str(skipped, effective_fps)}', True, (0, 0, 0)), [5, y + gap * 2])
    display_path = path if len(path) <= 30 else '...' + path[-27:]
    screen.blit(font.render(f'save folder: {display_path}', True, (0, 0, 0)), [5, y + gap * 3])

    # Options row -- three equal columns, normal font, 32 px tall
    fps_color = fps_color_30 if fps_mode == '30fps' else fps_color_60
    draw_button(screen, fps_box, f'FPS: {fps_mode}', font, fps_color, status == 'stopped' and is_in(fps_box, mouse_pos))

    disp_color = disp_color_all if display_mode == 'all' else disp_color_pr
    draw_button(screen, disp_box, f'display: {display_mode}', font, disp_color, status == 'stopped' and is_in(disp_box, mouse_pos))

    draw_button(screen, folder_box, 'Save Folder', font, C_Save, status == 'stopped' and is_in(folder_box, mouse_pos))

    # Action buttons
    if status == 'stopped':
        draw_button(screen, left_box,  'Start', font_big, C_Start, is_in(left_box,  mouse_pos))
        if convert_status == 'converting':
            conv_label = 'Converting'
        elif convert_status == 'done':
            conv_label = 'Done!'
        elif convert_status == 'error':
            conv_label = 'ffmpeg error'
        elif convert_status == 'not found':
            conv_label = 'ffmpeg not found'
        else:
            conv_label = 'Convert to Video'
        draw_button(screen, right_box, conv_label, font_big, C_conv, is_in(right_box, mouse_pos))

    elif status == 'running':
        draw_button(screen, left_box,  'Pause',  font_big, C_Pause, is_in(left_box,  mouse_pos))
        draw_button(screen, right_box, 'Stop',   font_big, C_Stop,   is_in(right_box, mouse_pos))

    elif status == 'paused':
        draw_button(screen, left_box,  'Resume', font_big, C_Resume, is_in(left_box,  mouse_pos))
        draw_button(screen, right_box, 'Stop',   font_big, C_Stop,   is_in(right_box, mouse_pos))

    # Progress bar (next-frame countdown)
    if status == 'running':
        elapsed = active_elapsed()
        next_due = frame_captures * seconds_between_frames
        progress = 1.0 - (next_due - elapsed) / seconds_between_frames
        progress = max(0.0, min(1.0, progress))
        pygame.draw.rect(screen, (204, 204, 240), [0, 358, int(360 * progress), 16])

    pygame.display.flip()

    
# -- main ---------------------------------------------------------------------

def main():
    global screen, font, font_big, running, mouse_pos
    global on_frame, skipped, last_bytes, last_preview
    global capture_result, capture_in_progress, preview_result, frame_captures
    pygame.init()
    screen = set_up_screen()

    pygame.font.init()
    font = pygame.font.Font(pygame.font.match_font('CONSOLAS'), 15)
    font_big = pygame.font.Font(pygame.font.match_font('CONSOLAS'), 30)

    log.info('App started.')


    # -- main loop ------------------------------------------------------------
    while running:
        clock.tick(30)
        click = False

        for e in pygame.event.get():
            if e.type == QUIT:
                running = False
            if e.type == MOUSEBUTTONDOWN and e.button == 1:
                click = True
            if e.type == MOUSEMOTION:
                mouse_pos = list(e.pos)

        # -- handle clicks ----------------------------------------------------
        if click: on_click()
            

        # -- apply Phase 1 result: counters + last_bytes ----------------------
        with capture_lock:
            r = capture_result
            if r is not None:
                capture_result = None
        if r is not None:
            df, ds, new_bytes = r
            on_frame   += df
            skipped    += ds
            last_bytes  = new_bytes

        # -- apply Phase 2 result: preview surface (arrives later) ------------
        with preview_lock:
            p = preview_result
            if p is not None:
                preview_result = None
        if p is not None:
            last_preview = p

        # -- trigger Phase 1 capture if due -----------------------------------
        if status == 'running' and not capture_in_progress and \
                active_elapsed() >= frame_captures * seconds_between_frames:
            frame_captures += 1
            capture_in_progress = True
            threading.Thread(
                target=do_capture,
                args=(last_bytes, on_frame, path, display_mode),
                daemon=True,
            ).start()

        # -- draw -------------------------------------------------------------
        do_draw()

def setUpLogging():
    log = logging.getLogger()
    log.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s | %(funcName)s:%(lineno)d | %(message)s")

    # Create a file handler to write logs to a file
    os.makedirs("logs", exist_ok=True)
    file_handler = logging.FileHandler(f'logs/{time.strftime("%y-%m-%d %HH-%MM-%SS", time.localtime())}.log', mode='w', encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Create a stream handler to print logs to the console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)  # You can set the desired log level for console output
    #console_handler.setLevel(logging.DEBUG)  # You can set the desired log level for console output

    console_handler.setFormatter(formatter)


    # Add the handlers to the logger
    log.addHandler(file_handler)
    log.addHandler(console_handler)


if __name__ == '__main__':
    setUpLogging()
    main()