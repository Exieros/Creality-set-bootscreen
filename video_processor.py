"""Модуль для обработки видео: экспорт кадров и создание конфигурации."""

import os
import subprocess
import json
import logging
from typing import Optional
from config import (
    DEFAULT_OUTPUT_DIR, VIDEO_WIDTH, VIDEO_HEIGHT,
    JPEG_QUALITY, FADE_DURATION, BOOT_CONFIG_TEMPLATE
)

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def get_video_duration(video_path: str, ffmpeg_cmd: str) -> float:
    """
    Получает длительность видео используя ffprobe.
    
    Args:
        video_path: Путь к видео файлу
        ffmpeg_cmd: Путь к ffmpeg (используется для получения ffprobe)
        
    Returns:
        Длительность в секундах
        
    Raises:
        RuntimeError: Если не удалось определить длительность
    """
    # Пытаемся использовать ffprobe с JSON выводом
    ffprobe_cmd = ffmpeg_cmd.replace('ffmpeg', 'ffprobe')
    
    try:
        cmd = [
            ffprobe_cmd,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return float(data['format']['duration'])
    except:
        pass
    
    # Fallback: парсим stderr ffmpeg
    result = subprocess.run(
        [ffmpeg_cmd, '-i', video_path],
        capture_output=True,
        text=True
    )
    
    for line in result.stderr.split('\n'):
        if 'Duration:' in line:
            time_str = line.split('Duration:')[1].split(',')[0].strip()
            h, m, s = time_str.split(':')
            return int(h) * 3600 + int(m) * 60 + float(s)
    
    raise RuntimeError("Не удалось определить длительность видео")


def create_boot_config(output_dir: str, fps: int) -> None:
    """
    Создает конфигурационный файл boot-display.conf.
    
    Args:
        output_dir: Директория для экспорта (part0)
        fps: Кадров в секунду
    """
    export_base = os.path.dirname(output_dir)
    config_path = os.path.join(export_base, 'boot-display.conf')
    
    config_content = BOOT_CONFIG_TEMPLATE.format(
        width=VIDEO_WIDTH,
        height=VIDEO_HEIGHT,
        fps=fps
    )
    
    with open(config_path, 'w') as f:
        f.write(config_content)


def export_video(
    video_path: str,
    ffmpeg_cmd: str,
    start_time: float = 0,
    end_time: Optional[float] = None,
    fps: int = 12,
    fade: bool = False,
    scale_mode: str = 'stretch'
) -> bool:
    """
    Экспортирует видео в раскадровку.
    
    Args:
        video_path: Путь к видео файлу
        ffmpeg_cmd: Путь к ffmpeg
        start_time: Время начала в секундах
        end_time: Время конца в секундах (None = до конца видео)
        fps: Кадров в секунду для экспорта
        fade: Добавить fade in/out эффекты
        scale_mode: Режим масштабирования ('stretch' или 'crop')
        
    Returns:
        True при успехе, False при ошибке
    """
    if not os.path.exists(video_path):
        logger.error(f"Ошибка: файл не найден: {video_path}")
        return False
    
    # Создаем выходную папку
    output_dir = DEFAULT_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)
    
    # Создаем boot-display.conf в папке export
    create_boot_config(output_dir, fps)
    
    # Очищаем папку от старых кадров
    for file in os.listdir(output_dir):
        if file.startswith('pic_') and file.endswith('.jpg'):
            os.remove(os.path.join(output_dir, file))
    
    # Получаем длительность видео если end_time не указан
    if end_time is None:
        try:
            end_time = get_video_duration(video_path, ffmpeg_cmd)
        except RuntimeError as e:
            logger.error(str(e))
            return False
    
    duration = end_time - start_time
    frame_count = int(duration * fps)
    
    logger.info(f"Видео: {os.path.basename(video_path)}")
    logger.info(f"Экспорт: {start_time:.2f}s - {end_time:.2f}s ({duration:.2f}s)")
    logger.info(f"Кадров: {frame_count} ({fps} fps)")
    logger.info(f"Fade: {'Включен' if fade else 'Выключен'}")
    
    # Формируем команду ffmpeg
    output_pattern = os.path.join(output_dir, 'pic_%03d.jpg')
    
    # Базовые фильтры: масштаб и поворот на 90° до 480x800
    if scale_mode == 'crop':
        # Обрезка с сохранением пропорций (заполняет весь кадр)
        vf_filters = f'scale={VIDEO_HEIGHT}:{VIDEO_WIDTH}:force_original_aspect_ratio=increase,crop={VIDEO_HEIGHT}:{VIDEO_WIDTH},transpose=1'
    else:
        # Растяжение без сохранения пропорций (по умолчанию)
        vf_filters = f'scale={VIDEO_HEIGHT}:{VIDEO_WIDTH},transpose=1'
    
    # Добавляем fade эффекты
    if fade:
        fade_out_start = duration - FADE_DURATION - (2.0 / fps)
        vf_filters += f',fade=t=in:st=0:d={FADE_DURATION},fade=t=out:st={fade_out_start:.3f}:d={FADE_DURATION}'
    
    cmd = [
        ffmpeg_cmd,
        '-ss', str(start_time),
        '-i', video_path,
        '-vf', vf_filters,
        '-r', str(fps),
        '-frames:v', str(frame_count),
        '-q:v', str(JPEG_QUALITY),
        '-start_number', '0',
        output_pattern,
        '-y'
    ]
    
    logger.info(f"\nЗапуск ffmpeg...")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        
        if result.returncode == 0:
            actual_count = len([f for f in os.listdir(output_dir) 
                              if f.startswith('pic_') and f.endswith('.jpg')])
            logger.info(f"✓ Успешно экспортировано {actual_count} кадров в {output_dir}")
            return True
        else:
            logger.error(f"✗ Ошибка ffmpeg:")
            logger.error(result.stderr[:500])
            return False
            
    except FileNotFoundError:
        logger.error("✗ Ошибка: ffmpeg не найден. Установите ffmpeg и добавьте в PATH")
        return False
    except Exception as e:
        logger.error(f"✗ Ошибка: {e}")
        return False
