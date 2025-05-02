import multiprocessing
import ctypes
import os
import psutil
import pygame
import numpy as np
from PIL import Image
import random
import time
import pygame._sdl2.video
from win32 import win32gui
import win32.lib.win32con as win32con
import keyboard
import threading
import signal
import sys

# Constants
# Available fonts:  Micro5-Regular.ttf | PixelifySans-Regular.ttf | SourceCodePro-Light.ttf | CourierPrime-Regular.ttf | Hack-Regular.ttf
FONT = os.path.join(os.getcwd(), 'SourceCodePro-Light.ttf')
FONT_SIZE = 10

PRIMES = [4, 5, 6, 7, 9]
PRIMES_NOISE_PROB = 0.1

BG_COLOR = (0, 0, 0, 0)
COLOR_0 = (40, 60, 40)
COLOR_1 = (0, 255, 0)

COLOR_8 = (255, 255, 0)
NET_NOSIE_DENSITY = 0.005

COLOR_DISK = (0, 0, 255)
DISK_NOSIE_DENSITY = 0.005

NOISE_DENSITY = 0.3

SECOND_MONITOR_VER_OFFSET = -442
SECOND_MONITOR_HOR_OFFSET = -1080

UPDATE_RATE = 0.1
FPS = 24


pygame.init()

def global_escape_listener(stop_event):
    keyboard.wait('esc')
    print("[ESC] Global exit triggered")
    stop_event.set()

def handle_exit(signum, frame):
    print(f"[screen_saver] Exit signal: {signum}")
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
        time.sleep(0.2)


def render_char(renderer, font, cache, char, color):
    key = (char, color)
    if key not in cache:
        surf = font.render(str(char), False, color)
        cache[key] = pygame._sdl2.Texture.from_surface(renderer, surf)
    return cache[key]


def run_display(shared, monitor_index, offset_x, screen_size, stop_event):
    try:
        pygame.display.init()
        monitor_offsets = {
        0: (0, 0),
        1: (SECOND_MONITOR_HOR_OFFSET, SECOND_MONITOR_VER_OFFSET)
            }
        offset_x, offset_y = monitor_offsets.get(monitor_index, (0, 0))

        window = pygame._sdl2.video.Window(f"Monitor {monitor_index}", size=screen_size)
        window.resizable = True
        window.position = (offset_x, offset_y)
        window.borderless = True
        window.show()
        time.sleep(0.5)  # Подождать, чтобы окно точно отобразилось

        # Ищем окно по заголовку
        hwnd = ctypes.windll.user32.FindWindowW(None, f"Monitor {monitor_index}")
        if hwnd:
            # Снимаем topmost, ставим topmost снова (форс-фокус)
            win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)

            # Принудительно активируем окно
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
        cache = {}
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
            disk = min(shared['disk'] / 50.0, 1.0)
            net = min(shared['net'] / 5000.0, 1.0)

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
                        render_char(renderer, font, cache, 1, mem_color).draw(dstrect=(px, py, FONT_SIZE, FONT_SIZE))
                    elif disk > 0.3 and random.random() < disk * DISK_NOSIE_DENSITY:
                        render_char(renderer, font, cache, 3, COLOR_DISK).draw(dstrect=(px, py, FONT_SIZE, FONT_SIZE))
                    elif net > 0.3 and random.random() < net * NET_NOSIE_DENSITY:
                        render_char(renderer, font, cache, 8, COLOR_8).draw(dstrect=(px, py, FONT_SIZE, FONT_SIZE))
                    elif distance >= ring_boundary:
                        noise_prob = NOISE_DENSITY * ((distance - ring_boundary) / (1 - ring_boundary + 1e-9))
                        if random.random() < noise_prob and random.random() < PRIMES_NOISE_PROB:
                            char = random.choice(PRIMES)
                            color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
                            render_char(renderer, font, cache, char, color).draw(dstrect=(px, py, FONT_SIZE, FONT_SIZE))
                        else:
                            render_char(renderer, font, cache, 0, COLOR_0).draw(dstrect=(px, py, FONT_SIZE, FONT_SIZE))
                    else:
                        render_char(renderer, font, cache, 0, COLOR_0).draw(dstrect=(px, py, FONT_SIZE, FONT_SIZE))

            renderer.present()
            time.sleep(UPDATE_RATE)
            clock.tick(FPS)
        # renderer.destroy()
        # window.destroy()
    except Exception as e:
        print(f"[display-{monitor_index}] Error: {e}")
    finally:
        # Правильное освобождение ресурсов
        try:
            if 'renderer' in locals():
                del renderer  # Явное удаление рендерера
            if 'window' in locals():
                window.destroy()  # Уничтожение окна
        except Exception as e:
            print(f"[display-{monitor_index}] Cleanup error: {e}")
        finally:
            pygame.display.quit()


def main():
    try:
        if sys.platform == 'win32':
            kernel32 = ctypes.WinDLL('kernel32')
            user32 = ctypes.WinDLL('user32')
            
            # Сброс буфера обмена при старте
            user32.OpenClipboard(None)
            user32.EmptyClipboard()
            user32.CloseClipboard()

        pygame.display.init()
        desktop_sizes = pygame.display.get_desktop_sizes()
        stop_event = multiprocessing.Event()
        manager = multiprocessing.Manager()
        shared = manager.dict(cpu=0, mem=0, disk=0, net=0)

        esc_thread = threading.Thread(target=global_escape_listener, args=(stop_event,), daemon=True)
        esc_thread.start()

        updater = multiprocessing.Process(target=update_shared_data, args=(shared, stop_event), daemon=True)
        updater.start()

        def signal_handler(signum, frame):
            print(f"[main] Signal {signum} received, shutting down...")
            stop_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        displays = []
        for i, size in enumerate(desktop_sizes):
            displays.append(multiprocessing.Process(target=run_display,
                                                    args=(shared, i, 0, size, stop_event)))

        for d in displays:
            d.start()
        try:
            for d in displays:
                d.join()
        except KeyboardInterrupt:
            print("[main] KeyboardInterrupt received")
            stop_event.set()
        finally:
            print("[main] Terminating display processes")
            for d in displays:
                if d.is_alive():
                    d.terminate()
                    d.join()
            if updater.is_alive():
                updater.terminate()
                updater.join()
            esc_thread.join()
            pygame.quit()
    except Exception as e:
        print(f"[main] Error: {e}")
    finally:
        print("[main] Performing cleanup")
        stop_event.set()
        # Даем процессам время на корректное завершение
        time.sleep(0.5)
        for d in displays:
            if d.is_alive():
                d.terminate()
        pygame.quit()
        # Явный выход для гарантии завершения
        os._exit(0)



if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        pygame.quit()
