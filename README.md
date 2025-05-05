# Binary Screensaver 

Windows-скринсейвер на Python с мониторингом активности (мышь, клавиатура, звук, полноэкранные приложения).  
Запускает визуализацию (`screen_saver.py`) при простое и корректно завершает её при возобновлении активности.

![Demo](demo.gif)

## 🔧 Установка

1. **Зависимости**:
   ```bash:
   $ pip install -r requirements.txt
   ```
### Настройка
#### Перед запуском проверьте файлы конфигурации:
	config.yaml – настройки цветов, шрифтов, мониторов и порогов активности.
	image_0.jpg, image_1.jpg – фоновые изображения для каждого монитора (можно заменить своими). цифра после "image_" это индекс монитора.
	font.ttf – файл шрифта (указан в config.yaml).

### Запуск:
	```bash:
	$ python watchdog.py
	```

🚀 Как это работает:
#### Watchdog (watchdog.py):
	Следит за активностью (ввод, звук, полноэкранные приложения).
	Запускает screen_saver.py при простое (настраивается в config.yaml).
	Автоматически завершает скринсейвер при нажатии "Esc".

#### Скринсейвер (screen_saver.py):
	Показывает анимированную матрицу с эффектами на всех мониторах.
	Динамически меняет цвета в зависимости от нагрузки CPU, памяти, диска и сети.
	Оптимизирует память через кэширование и периодическую очистку.

⚠️ Возможные проблемы и решения
#### Утечки памяти:
	В коде реализован TextureCache с автоматической очисткой.
	Совет: Убедитесь, что CACHE_SIZE в config.yaml не слишком велик.

#### "Зомби"-процессы:
	Watchdog использует terminate_subprocess() с двойной проверкой (terminate() + kill()).
	Для скринсейвера добавлен обработчик SIGTERM.

#### Ошибки аудио/мониторов:
	Проверьте, что в ignore_processes (конфиг) добавлены все фоновые приложения с звуком которые нужно игнорировать.
	Для многомониторных систем укажите правильные monitor_offsets.



A Python-based Windows screensaver with activity monitoring (mouse, keyboard, audio, full-screen apps).
Launches the visualization (screen_saver.py) during inactivity and gracefully terminates it upon resuming activity.

## 🔧 Installation
1. **Dependencies**
	```bash:
	$ pip install -r requirements.txt 
	``` 

### Configuration
#### Before running, ensure the following files are properly set up:
	config.yaml – Settings for colors, fonts, monitors, and activity thresholds.
	image_0.jpg, image_1.jpg – Background images for each monitor (replace with your own). The number after image_ corresponds to the monitor index.
	font.ttf – Font file (specified in config.yaml).

### Launch
	```bash:
	$ python watchdog.py 
	```
🚀 How It Works
#### Watchdog (watchdog.py)
	Monitors activity (input, audio, full-screen applications).
	Starts screen_saver.py after a period of inactivity (configurable in config.yaml).
	Automatically stops the screensaver when Esc is pressed.

#### Screensaver (screen_saver.py)
	Displays an animated matrix with effects across all monitors.
	Dynamically adjusts colors based on CPU, RAM, disk, and network load.
	Optimizes memory usage via caching and periodic cleanup.

⚠️ Troubleshooting
#### Memory Leaks
	The code includes a TextureCache with automatic cleanup.
	Recommendation: Ensure CACHE_SIZE in config.yaml is not set too high.

#### Zombie Processes
	Watchdog uses terminate_subprocess() with dual verification (terminate() + kill()).
	The screensaver includes a SIGTERM handler for proper termination.

#### Audio/Monitor Issues
	Verify that ignore_processes (in config) lists all background audio apps to exclude.
	For multi-monitor setups, ensure correct monitor_offsets values.