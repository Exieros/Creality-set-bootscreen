"""
Простой скрипт для экспорта видео в раскадровку
Использует tkinter для выбора файла и ffmpeg для экспорта
"""

import sys
import argparse
import re
import logging
from tkinter import Tk, filedialog

from config import VIDEO_FILE_TYPES, DEFAULT_SSH_PORT, DEFAULT_FPS
from ffmpeg_manager import get_ffmpeg_path
from video_processor import export_video
from printer_uploader import PrinterUploader

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def select_video_file() -> str:
    """Открывает диалог выбора видео файла"""
    root = Tk()
    root.withdraw()  # Скрываем главное окно
    root.attributes('-topmost', True)  # Поверх всех окон
    
    file_path = filedialog.askopenfilename(
        title='Выберите видео файл',
        filetypes=VIDEO_FILE_TYPES
    )
    
    root.destroy()
    return file_path


def parse_connection_string(conn_str: str) -> dict[str, str | int]:
    """
    Парсит строку подключения формата username:password@ip:port
    Порт опционален (по умолчанию 22)
    
    Args:
        conn_str: Строка подключения
        
    Returns:
        Словарь с ключами: user, password, ip, port
        
    Raises:
        ValueError: Если формат строки неверный
    """
    # Паттерн: username:password@ip:port или username:password@ip
    pattern = r'^([^:@]+):([^@]+)@([^:]+)(?::(\d+))?$'
    match = re.match(pattern, conn_str)
    
    if not match:
        raise ValueError(
            "Неверный формат строки подключения.\n"
            "Используйте: username:password@ip:port или username:password@ip"
        )
    
    user, password, ip, port = match.groups()
    port = int(port) if port else DEFAULT_SSH_PORT
    
    return {
        'user': user,
        'password': password,
        'ip': ip,
        'port': port
    }


def upload_to_printer(connection_string: str, export_dir: str = 'export', remote_dir: str = '/etc/boot-display') -> bool:
    """
    Загружает экспорт на принтер
    
    Args:
        connection_string: Строка подключения username:password@ip:port
        export_dir: Локальная папка с экспортом
        remote_dir: Удаленная директория на принтере
        
    Returns:
        True при успехе, False при ошибке
    """
    try:
        # Парсим строку подключения
        conn = parse_connection_string(connection_string)
        
        logger.info(f"\nПодключение к принтеру {conn['user']}@{conn['ip']}:{conn['port']}...")
        
        # Создаем uploader и подключаемся
        uploader = PrinterUploader()
        uploader.connect(
            ip=str(conn['ip']),
            port=int(conn['port']),
            user=str(conn['user']),
            password=str(conn['password'])
        )
        
        logger.info(f"Загрузка файлов из {export_dir} в {remote_dir}...")
        
        # Загружаем файлы
        success, message, uploaded_files = uploader.upload_export_to_printer(export_dir, remote_dir)
        
        uploader.close()
        
        if success:
            logger.info(f"✓ {message}")
            return True
        else:
            logger.error(f"✗ {message}")
            return False
            
    except ValueError as e:
        logger.error(f"✗ Ошибка: {e}")
        return False
    except Exception as e:
        logger.error(f"✗ Ошибка подключения: {e}")
        return False


def main() -> int:
    """Главная функция программы"""
    parser = argparse.ArgumentParser(description='Экспорт видео в раскадровку')
    parser.add_argument('video', nargs='?', help='Путь к видео файлу (опционально)')
    parser.add_argument('-s', '--start', type=float, default=0, help='Время начала (сек)')
    parser.add_argument('-e', '--end', type=float, help='Время конца (сек)')
    parser.add_argument('-f', '--fps', type=int, default=DEFAULT_FPS, help=f'Кадров в секунду (по умолчанию {DEFAULT_FPS})')
    parser.add_argument('--fade', action='store_true', help='Добавить fade in/out')
    parser.add_argument('--scale-mode', choices=['stretch', 'crop'], default='stretch', help='Режим масштабирования: stretch (растянуть) или crop (обрезать)')
    parser.add_argument('--upload', metavar='USER:PASS@IP:PORT', help='Загрузить на принтер (например: root:password@192.168.1.100:22)')
    
    args = parser.parse_args()
    
    try:
        # Получаем путь к FFmpeg
        ffmpeg_cmd = get_ffmpeg_path()
        
        # Выбираем видео файл
        video_path = args.video
        if not video_path:
            logger.info("Выберите видео файл...")
            video_path = select_video_file()
            
            if not video_path:
                logger.info("Файл не выбран. Выход.")
                return 1
        
        # Экспортируем
        success = export_video(
            video_path,
            ffmpeg_cmd,
            start_time=args.start,
            end_time=args.end,
            fps=args.fps,
            fade=args.fade,
            scale_mode=args.scale_mode
        )
        
        if not success:
            return 1
        
        # Загружаем на принтер если указан параметр --upload
        if args.upload:
            upload_success = upload_to_printer(args.upload, 'export')
            return 0 if upload_success else 1
        
        return 0
        
    except RuntimeError as e:
        logger.error(f"✗ {e}")
        return 1
    except KeyboardInterrupt:
        logger.info("\n\nПрервано пользователем")
        return 1
    except Exception as e:
        logger.error(f"✗ Неожиданная ошибка: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
