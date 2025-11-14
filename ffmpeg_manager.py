"""Модуль для управления FFmpeg: поиск, загрузка и установка."""

import os
import sys
import zipfile
import urllib.request
from tqdm import tqdm
from config import FFMPEG_DOWNLOAD_URL, FFMPEG_ARCHIVE_BIN_PATH


def download_ffmpeg(script_dir: str) -> str | None:
    """
    Скачивает и распаковывает FFmpeg в папку со скриптом.
    
    Args:
        script_dir: Директория для установки FFmpeg
        
    Returns:
        Путь к ffmpeg.exe или None при ошибке
    """
    print("⚠ Для раскадровки необходим FFmpeg, который не найден в системе. Загрузка...")
    print(f"📥 Источник: {FFMPEG_DOWNLOAD_URL}")
    
    zip_path = os.path.join(script_dir, "ffmpeg.zip")
    ffmpeg_exe = os.path.join(script_dir, "ffmpeg.exe")
    
    try:
        # Скачиваем FFmpeg с прогресс-баром
        print("\nЗагрузка FFmpeg (~80 MB)...")
        
        class DownloadProgressBar(tqdm):
            def update_to(self, b=1, bsize=1, tsize=None):
                if tsize is not None:
                    self.total = tsize
                self.update(b * bsize - self.n)
        
        with DownloadProgressBar(unit='B', unit_scale=True, miniters=1, desc='FFmpeg') as t:
            urllib.request.urlretrieve(FFMPEG_DOWNLOAD_URL, zip_path, reporthook=t.update_to)
        
        # Распаковываем с прогресс-баром
        print("\nРаспаковка...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Получаем список файлов для распаковки
            files_to_extract = [f for f in zip_ref.namelist() 
                              if FFMPEG_ARCHIVE_BIN_PATH in f and not f.endswith('/')]
            
            # Распаковываем с прогресс-баром
            with tqdm(total=len(files_to_extract), desc='Распаковка', unit='файл') as pbar:
                for file in files_to_extract:
                    filename = os.path.basename(file)
                    target_path = os.path.join(script_dir, filename)
                    with zip_ref.open(file) as source:
                        with open(target_path, 'wb') as target:
                            target.write(source.read())
                    pbar.update(1)
        
        # Удаляем архив
        os.remove(zip_path)
        print("✓ FFmpeg успешно установлен (ffmpeg.exe и все необходимые DLL)!")
        return ffmpeg_exe
        
    except Exception as e:
        print(f"✗ Ошибка загрузки FFmpeg: {e}")
        if os.path.exists(zip_path):
            os.remove(zip_path)
        return None


def find_ffmpeg() -> str | None:
    """
    Ищет ffmpeg в системе или рядом со скриптом, скачивает при необходимости.
    
    Returns:
        Путь к ffmpeg или None при ошибке
    """
    # Проверяем системный PATH
    import shutil
    if shutil.which('ffmpeg'):
        return 'ffmpeg'
    
    # Проверяем рядом со скриптом
    script_dir = os.path.dirname(os.path.abspath(__file__))
    local_ffmpeg = os.path.join(script_dir, 'ffmpeg.exe')
    if os.path.exists(local_ffmpeg):
        return local_ffmpeg
    
    # Проверяем в dist/_internal (для PyInstaller)
    try:
        base_path = sys._MEIPASS  # pyright: ignore[reportAttributeAccessIssue]
        bundled_ffmpeg = os.path.join(base_path, 'ffmpeg.exe')
        if os.path.exists(bundled_ffmpeg):
            return bundled_ffmpeg
    except:
        pass
    
    # Не найден - пытаемся скачать
    return download_ffmpeg(script_dir)


def get_ffmpeg_path() -> str:
    """
    Получает путь к FFmpeg, автоматически загружая при необходимости.
    
    Returns:
        Путь к ffmpeg
        
    Raises:
        RuntimeError: Если FFmpeg не найден и не удалось скачать
    """
    ffmpeg_cmd = find_ffmpeg()
    if not ffmpeg_cmd:
        raise RuntimeError(
            "FFmpeg не найден!\n"
            "Установите ffmpeg и добавьте в PATH или поместите ffmpeg.exe в папку со скриптом"
        )
    return ffmpeg_cmd
