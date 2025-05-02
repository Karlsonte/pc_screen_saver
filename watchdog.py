from pynput import mouse, keyboard
import subprocess
import time
import sys
from win32 import win32gui, win32api
import win32.lib.win32con as win32con
import psutil
from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
from comtypes import CLSCTX_ALL

time_for_inactivity = 0.25 # minutes
last_activity_time = time.time()
IDLE_THRESHOLD = round(time_for_inactivity * 60)  # seconds

def is_audio_playing(threshold=0.01, ignore_processes=None):
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


def is_media_playing():
    ignore_list = ['discord.exe']  # можно добавить 'teams.exe' и т.п.
    if is_audio_playing(ignore_processes=ignore_list):
        return True
    media_process_names = ['vlc.exe', 'mpv.exe', 'potplayer.exe', 'kmplayer.exe', 'wmplayer.exe', 'chrome.exe', 'firefox.exe', 'opera.exe']
    for proc in psutil.process_iter(['name']):
        try:
            if any(p in proc.info['name'].lower() for p in media_process_names) and is_audio_playing(ignore_processes=ignore_list):
                print(f'({any(p in proc.info['name'].lower() for p in media_process_names) = })')
                print(f'({is_audio_playing(ignore_processes=ignore_list) = })')
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False

def on_input(*args):
    global last_activity_time
    last_activity_time = time.time()

# слушаем мышь и клавиатуру
mouse_listener = mouse.Listener(on_move=on_input, on_click=on_input, on_scroll=on_input)
keyboard_listener = keyboard.Listener(on_press=on_input, on_release=on_input)

mouse_listener.start()
keyboard_listener.start()

proc = None
print(f'{IDLE_THRESHOLD = }')
skiping_check:float = 0

try:
    while True:
        idle = time.time() - last_activity_time
        if idle > IDLE_THRESHOLD and proc is None:
            if is_fullscreen_app_running() or is_media_playing():
                skiping_check = IDLE_THRESHOLD if idle > IDLE_THRESHOLD else idle
                print("[watchdog] fullscreen or media playing, skipping screensaver")
                time.sleep(skiping_check)
            else:
                print("[watchdog] launching screensaver")
                proc = subprocess.Popen([sys.executable, "screen_saver.py"])

        elif idle < 1 and proc:
            print("[watchdog] user activity detected, terminating screensaver")
            try:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait()
            except Exception as e:
                print(f"[watchdog-error] Failed to terminate screensaver: {e}")
            finally:
                proc = None

        time.sleep(1)
except KeyboardInterrupt:
    print("[watchdog] Interrupted by user")
    if proc and proc.poll() is None:
        proc.terminate()
        proc.wait()
finally:
    mouse_listener.stop()
    keyboard_listener.stop()
