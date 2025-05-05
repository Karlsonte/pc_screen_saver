import multiprocessing
import ctypes
import os
import psutil
import pygame
import numpy as np
import random
import time
import pygame._sdl2.video
import win32.lib.win32con as win32con
import keyboard
import threading
import signal
import sys
import gc
import yaml

from typing import List, Tuple, Dict
from collections import OrderedDict
from win32 import win32gui
from PIL import Image

with open('config.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# Font settings
FONT: str = config['font']['path']
FONT_SIZE: int = config['font']['size']

# Visual elements
PRIMES: List[int] = config['visual']['primes']
PRIMES_NOISE_PROB: float = config['visual']['primes_noise_prob']
NOISE_DENSITY: float = config['visual']['noise_density']

# Colors (using Tuple for immutable RGB/RGBA values)
BG_COLOR: Tuple[int, int, int, int] = tuple(config['colors']['background'])
COLOR_0: Tuple[int, int, int] = tuple(config['colors']['base'])
COLOR_1: Tuple[int, int, int] = tuple(config['colors']['active'])
COLOR_8: Tuple[int, int, int] = tuple(config['colors']['net'])
COLOR_DISK: Tuple[int, int, int] = tuple(config['colors']['disk'])
PREDEFINED_COLORS: List[Tuple[int, int, int]] = [tuple(c) for c in config['colors']['predefined']]

# Network settings
NET_NOSIE_DENSITY: float = config['visual']['net_noise_density']
AVERAGE_NET_SPEED: float = config['speeds']['average_net_speed']
MIN_NET_ACTIVITY: float = config['visual']['min_net_activity']

# Disk settings
DISK_NOSIE_DENSITY: float = config['visual']['disk_noise_density']
AVERAGE_DISK_SPEED: float = config['speeds']['average_disk_speed']
MIN_DISK_ACTIVITY: float = config['visual']['min_disk_activity']

# Monitor offsets
SECOND_MONITOR_VER_OFFSET: int = int(config['monitor_offsets'][1][1])
SECOND_MONITOR_HOR_OFFSET: int = int(config['monitor_offsets'][1][0])
THHIRD_MONITOR_VER_OFFSET: int = int(config['monitor_offsets'][2][1])
THHIRD_MONITOR_HOR_OFFSET: int = int(config['monitor_offsets'][2][0])

# Performance settings
UPDATE_RATE: float = config['performance']['update_rate']
FPS: int = config['performance']['fps']
CACHE_SIZE: int = config['performance']['cache_size']

MonitorOffset = Tuple[int, int]
MONITOR_OFFSETS: Dict[int, MonitorOffset] = {
    0: (0, 0),
    1: (SECOND_MONITOR_HOR_OFFSET, SECOND_MONITOR_VER_OFFSET),
    2: (THHIRD_MONITOR_HOR_OFFSET, THHIRD_MONITOR_VER_OFFSET)
}

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

pygame.init()
pygame.display.init()

class TextureCache(OrderedDict):
    def __init__(self, max_size=CACHE_SIZE):
        super().__init__()
        self.max_size = max_size

    def get_texture(self, key, generator_func):
        if key not in self:
            if len(self) >= self.max_size:
                _, tex = self.popitem(last=False)
                del tex
                gc.collect()
            self[key] = generator_func()
        return self[key]

    def clear_cache(self):
        for tex in self.values():
            del tex
        self.clear()
        gc.collect()

def cleanup():
    gc.collect()

def global_escape_listener(stop_event):
    keyboard.wait('esc')
    stop_event.set()

def handle_exit(signum, frame):
    sys.exit(0)

def load_image_centered(path, target_width, target_height):
    img = Image.open(path).convert('L')
    w_img, h_img = img.size
    scale = min(target_width / w_img, target_height / h_img)
    new_w = int(w_img * scale)
    new_h = int(h_img * scale)

    try:
        resample = Image.Resampling.LANCZOS
    except AttributeError:
        resample = Image.LANCZOS

    img_resized = img.resize((new_w, new_h), resample)
    binary_array = np.zeros((target_width, target_height), dtype=bool)
    offset_x = (target_width - new_w) // 2
    offset_y = (target_height - new_h) // 2
    img_array = np.array(img_resized) > 128
    binary_array[offset_x:offset_x + new_w, offset_y:offset_y + new_h] = img_array.T
    return binary_array

def update_shared_data(shared, stop_event):
    while not stop_event.is_set():
        shared['cpu'] = psutil.cpu_percent(interval=0.1)
        shared['mem'] = psutil.virtual_memory().percent
        io = psutil.disk_io_counters()
        shared['disk'] = (io.read_bytes + io.write_bytes) / (1024 * 1024)
        net = psutil.net_io_counters()
        shared['net'] = (net.bytes_sent + net.bytes_recv) / 1024
        time.sleep(0.5)

def terminate_by_pid(pid):
    try:
        p = psutil.Process(pid)
        p.terminate()
        p.wait(timeout=3)
    except psutil.NoSuchProcess:
        pass
    except psutil.TimeoutExpired:
        try:
            p.kill()
        except Exception:
            pass
    except Exception as e:
        print(f"[!] Failed to terminate PID {pid}: {e}")

def run_display(shared, monitor_index, offset_x, screen_size, stop_event):
    renderer = None
    window = None
    cleanup_counter = 0
    cleanup_interval = int(60 / UPDATE_RATE) * 5
    try:
        monitor_offsets = MONITOR_OFFSETS
        offset_x, offset_y = monitor_offsets.get(monitor_index, (0, 0))

        window = pygame._sdl2.video.Window(f"Monitor {monitor_index}", size=screen_size)
        window.resizable = True
        window.position = (offset_x, offset_y)
        window.borderless = True
        window.show()
        time.sleep(0.5)

        hwnd = ctypes.windll.user32.FindWindowW(None, f"Monitor {monitor_index}")
        if hwnd:
            win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                                   win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                   win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.BringWindowToTop(hwnd)

        renderer = pygame._sdl2.Renderer(window)
        pygame.mouse.set_visible(False)

        cols = screen_size[0] // FONT_SIZE
        rows = screen_size[1] // FONT_SIZE
        image_name = f'image_{monitor_index}.jpg'
        binary_img = load_image_centered(os.path.join(os.getcwd(), image_name), cols, rows)
        ones_positions = set(zip(*np.where(binary_img)))

        font = pygame.font.Font(FONT, FONT_SIZE)
        cache = TextureCache()
        clock = pygame.time.Clock()

        center_x, center_y = cols // 2, rows // 2
        max_radius = np.hypot(center_x, center_y)
        Y, X = np.mgrid[0:rows, 0:cols]
        norm_distance = np.hypot(X - center_x, Y - center_y) / max_radius

        while not stop_event.is_set():
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    stop_event.set()
                    break

            cpu = shared['cpu']
            mem = shared['mem']
            disk = min(shared['disk'] / AVERAGE_DISK_SPEED, 1.0)
            net = min(shared['net'] / AVERAGE_NET_SPEED, 1.0)

            mem_color = (
                min(255, int(COLOR_1[0] + (255 - COLOR_1[0]) * (mem / 100))),
                int(COLOR_1[1] * (1 - mem / 100)),
                int(COLOR_1[2] * (1 - mem / 100))
            )

            renderer.draw_color = BG_COLOR
            renderer.clear()
            ring_boundary = 1.0 - (cpu / 100)

            for y in range(rows):
                for x in range(cols):
                    pos = (x, y)
                    distance = norm_distance[y, x]
                    px, py = x * FONT_SIZE, y * FONT_SIZE

                    if pos in ones_positions:
                        tex = cache.get_texture((1, mem_color), lambda: pygame._sdl2.Texture.from_surface(renderer, font.render("1", False, mem_color)))
                        tex.draw(dstrect=(px, py, FONT_SIZE, FONT_SIZE))
                    elif disk > MIN_DISK_ACTIVITY and random.random() < disk * DISK_NOSIE_DENSITY:
                        tex = cache.get_texture((3, COLOR_DISK), lambda: pygame._sdl2.Texture.from_surface(renderer, font.render("3", False, COLOR_DISK)))
                        tex.draw(dstrect=(px, py, FONT_SIZE, FONT_SIZE))
                    elif net > MIN_NET_ACTIVITY and random.random() < net * NET_NOSIE_DENSITY:
                        tex = cache.get_texture((8, COLOR_8), lambda: pygame._sdl2.Texture.from_surface(renderer, font.render("8", False, COLOR_8)))
                        tex.draw(dstrect=(px, py, FONT_SIZE, FONT_SIZE))
                    elif distance >= ring_boundary:
                        noise_prob = NOISE_DENSITY * ((distance - ring_boundary) / (1 - ring_boundary + 1e-9))
                        if random.random() < noise_prob and random.random() < PRIMES_NOISE_PROB:
                            char = random.choice(PRIMES)
                            color = random.choice(PREDEFINED_COLORS)
                            # color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
                            tex = cache.get_texture((char, color), lambda: pygame._sdl2.Texture.from_surface(renderer, font.render(str(char), False, color)))
                            tex.draw(dstrect=(px, py, FONT_SIZE, FONT_SIZE))
                        else:
                            tex = cache.get_texture((0, COLOR_0), lambda: pygame._sdl2.Texture.from_surface(renderer, font.render("0", False, COLOR_0)))
                            tex.draw(dstrect=(px, py, FONT_SIZE, FONT_SIZE))
                    else:
                        tex = cache.get_texture((0, COLOR_0), lambda: pygame._sdl2.Texture.from_surface(renderer, font.render("0", False, COLOR_0)))
                        tex.draw(dstrect=(px, py, FONT_SIZE, FONT_SIZE))

            renderer.present()
            time.sleep(UPDATE_RATE)
            clock.tick(FPS)
            cleanup_counter += 1
            if cleanup_counter >= cleanup_interval:
                cache.clear_cache()
                gc.collect()
                cleanup_counter = 0
    except Exception as e:
        print(f"[display-{monitor_index}] Error: {e}")
    finally:
        try:
            if 'cache' in locals():
                cache.clear_cache()
            if 'binary_img' in locals():
                del binary_img
            if 'norm_distance' in locals():
                del norm_distance
            if 'ones_positions' in locals():
                del ones_positions
            gc.collect()
            if renderer:
                del renderer
            if window:
                window.destroy()
        except Exception as e:
            print(f"[display-{monitor_index}] Cleanup error: {e}")
        finally:
            pygame.display.quit()
            pygame.quit()
            cleanup()

def main():
    multiprocessing.set_start_method("spawn")
    stop_event = multiprocessing.Event()
    displays = []
    display_pids = []
    updater = None
    try:
        if sys.platform == 'win32':
            kernel32 = ctypes.WinDLL('kernel32')
            user32 = ctypes.WinDLL('user32')
            user32.OpenClipboard(None)
            user32.EmptyClipboard()
            user32.CloseClipboard()

        desktop_sizes = pygame.display.get_desktop_sizes()
        manager = multiprocessing.Manager()
        shared = manager.dict(cpu=0, mem=0, disk=0, net=0)

        esc_thread = threading.Thread(target=global_escape_listener, args=(stop_event,)) # , daemon=True
        esc_thread.start()

        updater = multiprocessing.Process(target=update_shared_data, args=(shared, stop_event)) # , daemon=True
        updater.start()

        def signal_handler(signum, frame):
            stop_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        displays = [multiprocessing.Process(target=run_display, args=(shared, i, 0, size, stop_event)) for i, size in enumerate(desktop_sizes)]

        for d in displays:
            d.start()
            display_pids.append(d.pid)

        for d in displays:
            d.join()

    except KeyboardInterrupt:
        stop_event.set()
    except Exception as e:
        print(f"[main] Error: {e}")
        stop_event.set()
    finally:
        stop_event.set()

        # Завершение дисплеев
        for d in displays:
            if d.is_alive():
                d.terminate()
                d.join(timeout=3)
                if d.is_alive() and d.pid:
                    terminate_by_pid(d.pid)

        # Завершение апдейтера
        if updater:
            if updater.is_alive():
                updater.terminate()
                updater.join(timeout=3)
                if updater.is_alive() and updater.pid:
                    terminate_by_pid(updater.pid)

        # Завершение esc_thread
        if esc_thread.is_alive():
            esc_thread.join(timeout=1)

        manager.shutdown()
        multiprocessing.active_children().clear()
        pygame.quit()
        os._exit(0)

if __name__ == "__main__":
    main()

