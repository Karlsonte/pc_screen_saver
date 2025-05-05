import subprocess
import time
import sys
import yaml
import os

# import win32.lib.win32con as win32con
import psutil
from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
from comtypes import CLSCTX_ALL
from pynput import mouse, keyboard
from win32 import win32gui, win32api
from typing import List
from ruamel.yaml import YAML

yaml_1 = YAML()
yaml_1.preserve_quotes = True

def get_all_drive_paths():
    return [p.device for p in psutil.disk_partitions() if 'cdrom' not in p.opts and p.fstype != '']

def scan_for_games_on_disks():
    drives = get_all_drive_paths()
    game_dirs = ['Games', 'SteamLibrary\\steamapps\\common', 'Epic Games']
    exe_files = []

    for drive in drives:
        for folder in game_dirs:
            full_path = os.path.join(drive, folder)
            if os.path.exists(full_path):
                for root, dirs, files in os.walk(full_path):
                    for file in files:
                        if file.endswith('.exe'):
                            exe_files.append(os.path.join(root, file))

    return exe_files

def update_config_with_games(exe_paths, config_path="config.yaml"):
    # Извлекаем только имена файлов
    game_exes = sorted(set(os.path.basename(p).lower() for p in exe_paths if p.endswith('.exe')))

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml_1.load(f)

    # Убедимся, что секция есть
    if 'watchdog' not in config:
        config['watchdog'] = {}

    if 'game_processes' not in config['watchdog']:
        config['watchdog']['game_processes'] = []

    # Добавим только новые exe-файлы
    existing = set(config['watchdog']['game_processes'])
    for exe in game_exes:
        if exe not in existing:
            config['watchdog']['game_processes'].append(exe)

    with open(config_path, 'w', encoding='utf-8') as f:
        yaml_1.dump(config, f)


exe_files = scan_for_games_on_disks()
update_config_with_games(exe_files)

with open('config.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

time_for_inactivity: float = config['watchdog']['inactivity_timeout']
audio_threshold: float = config['watchdog']['audio_threshold']
ignore_processes: List[str] = [str(c) for c in config['watchdog']['ignore_processes']]
media_processes: List[str] = [str(c) for c in config['watchdog']['media_processes']]
game_processes: List[str] = [str(c) for c in config['watchdog']['game_processes']]
last_activity_time = time.time()
idle_threshold = round(time_for_inactivity * 60)  # seconds

def is_audio_playing(threshold=audio_threshold, ignore_processes=None):
    if ignore_processes is None:
        ignore_processes = []

    sessions = AudioUtilities.GetAllSessions()
    for session in sessions:
        try:
            if session.State == 1:  # 1 = active
                process = session.Process
                if process and process.name().lower() in ignore_processes:
                    continue  # Пропускаем игнорируемый процесс

                volume = session._ctl.QueryInterface(IAudioMeterInformation)
                level = volume.GetPeakValue()
                if level > threshold:
                    return True
        except Exception as e:
            print(f"[audio-check-error] {e}")
            continue
    return False

def is_fullscreen_app_running():
    try:
        fg_win = win32gui.GetForegroundWindow()
        if not fg_win:
            return False

        rect = win32gui.GetWindowRect(fg_win)
        screen_w = win32api.GetSystemMetrics(0)
        screen_h = win32api.GetSystemMetrics(1)

        is_fs = (rect[2] - rect[0] == screen_w and rect[3] - rect[1] == screen_h)
        return is_fs
    except Exception as e:
        print(f"[fullscreen-check-error] {e}")
        return False

def on_input(*args):
    global last_activity_time
    last_activity_time = time.time()

def terminate_subprocess(p: subprocess.Popen):
    if p and p.poll() is None:
        try:
            p.terminate()
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=2)
        except Exception as e:
            print(f"[terminate-error] {e}")


def is_media_playing():
    if is_audio_playing(ignore_processes=ignore_processes):
        return True
    for proc in psutil.process_iter(['name']):
        try:
            if any(p in proc.info['name'].lower() for p in media_processes) and is_audio_playing(ignore_processes=ignore_processes) and any(p in proc.info['name'].lower() for p in game_processes):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False

# слушаем мышь и клавиатуру
mouse_listener = mouse.Listener(on_move=on_input, on_click=on_input, on_scroll=on_input)
keyboard_listener = keyboard.Listener(on_press=on_input, on_release=on_input)

mouse_listener.start()
keyboard_listener.start()

proc = None
skiping_check:float = 0

try:
    while True:
        idle = time.time() - last_activity_time
        if proc is not None:
            if proc.poll() is not None:  # Процесс завершился
                terminate_subprocess(proc)
                proc = None

        if idle > idle_threshold and proc is None:
            if  is_media_playing():
                skiping_check = idle_threshold if idle > idle_threshold else idle
                time.sleep(skiping_check)
            else:
                proc = subprocess.Popen([sys.executable, "screen_saver.py"])
                pid = proc.pid

        elif idle < 1 and proc:
            try:
                terminate_subprocess(proc)
            except Exception as e:
                print(f"[watchdog-error] Failed to terminate screensaver: {e}")
            finally:
                proc = None

        time.sleep(1)
except KeyboardInterrupt:
    if proc and proc.poll() is None:
        terminate_subprocess(proc)


finally:
    mouse_listener.stop()
    keyboard_listener.stop()
    if proc and proc.poll() is None:
        terminate_subprocess(proc)
