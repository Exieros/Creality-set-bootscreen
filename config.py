"""Конфигурация и константы для Video Export Tool."""

# FFmpeg настройки
FFMPEG_DOWNLOAD_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl-shared.zip"
FFMPEG_ARCHIVE_BIN_PATH = "/bin/"

# Настройки видео по умолчанию
DEFAULT_FPS = 12
DEFAULT_START_TIME = 0
VIDEO_WIDTH = 480
VIDEO_HEIGHT = 800
JPEG_QUALITY = 1  # 1 = максимальное качество

# Fade эффекты
FADE_DURATION = 1.0  # секунды

# Пути
DEFAULT_OUTPUT_DIR = "export/part0"
DEFAULT_REMOTE_DIR = "/etc/boot-display"

# Boot display конфигурация
BOOT_CONFIG_TEMPLATE = """width: {width}
height: {height}
fps: {fps}
parts: 1
{{ part0 }}
"""

# Форматы видео
VIDEO_FILE_TYPES = [
    ('Видео файлы', '*.mp4 *.avi *.mkv *.mov'),
    ('Все файлы', '*.*')
]

# SSH настройки
DEFAULT_SSH_PORT = 22
SSH_TIMEOUT = 10
