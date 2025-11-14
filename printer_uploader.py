"""Модуль для загрузки файлов на принтер по SSH/SFTP."""

import os
import paramiko
from datetime import datetime
from tqdm import tqdm


class PrinterUploader:
    """Класс для работы с принтером через SSH/SFTP."""
    
    def __init__(self):
        self.ssh = None
        self.sftp = None
    
    def connect(self, ip: str, port: int, user: str, password: str, timeout: int = 10):
        """
        Подключается к принтеру по SSH.
        
        Args:
            ip: IP адрес принтера
            port: SSH порт
            user: Имя пользователя
            password: Пароль
            timeout: Таймаут подключения в секундах
            
        Raises:
            Exception: При ошибке подключения
        """
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect(ip, port=port, username=user, password=password, timeout=timeout)
        
        # Пробуем подключить SFTP
        try:
            # ОТЛАДКА: Раскомментируйте для теста fallback на SCP
            raise Exception("SFTP not available")
            self.sftp = self.ssh.open_sftp()
        except Exception as e:
            print(f"⚠ SFTP недоступен (голый root без entwares) ({e}), используется fallback на SCP")
            self.sftp = None
    
    def close(self):
        """Закрывает соединение с принтером."""
        if self.sftp:
            self.sftp.close()
            self.sftp = None
        if self.ssh:
            self.ssh.close()
            self.ssh = None
    
    def backup_and_prepare_directory(self, remote_dir: str):
        """
        Создает backup текущей директории и создает новую пустую.
        
        Args:
            remote_dir: Путь к директории на принтере
        """
        # Генерируем уникальную метку времени
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Переименовываем текущую папку в backup с временной меткой
        backup_cmd = f'if [ -d {remote_dir} ]; then mv {remote_dir} {remote_dir}-BACK-{timestamp}; fi'
        stdin, stdout, stderr = self.ssh.exec_command(backup_cmd) # pyright: ignore[reportOptionalMemberAccess]
        stdout.read()
        
        # Создаем новую папку
        stdin, stdout, stderr = self.ssh.exec_command(f'mkdir -p {remote_dir}') # pyright: ignore[reportOptionalMemberAccess]
        stdout.read()
    
    def upload_file_scp(self, local_path: str, remote_path: str):
        """
        Загружает файл через SCP (fallback если SFTP недоступен).
        
        Args:
            local_path: Локальный путь к файлу
            remote_path: Удаленный путь на принтере
        """
        with open(local_path, 'rb') as f:
            file_data = f.read()
        
        # Экранируем путь для безопасности
        remote_path_escaped = remote_path.replace("'", "'\\''")
        
        # Загружаем через cat команду
        cmd = f"cat > '{remote_path_escaped}'"
        stdin, stdout, stderr = self.ssh.exec_command(cmd) # pyright: ignore[reportOptionalMemberAccess]
        stdin.write(file_data) # pyright: ignore[reportOptionalMemberAccess]
        stdin.close() # pyright: ignore[reportOptionalMemberAccess]
        
        # Ждем завершения
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            error = stderr.read().decode('utf-8', errors='ignore')
            raise Exception(f"Ошибка загрузки {remote_path}: {error}")
    
    def upload_directory(self, local_dir: str, remote_dir: str, pbar=None) -> list[str]:
        """
        Рекурсивно загружает директорию на принтер.
        
        Args:
            local_dir: Локальная директория
            remote_dir: Удаленная директория на принтере
            pbar: Прогресс-бар (опционально)
            
        Returns:
            Список загруженных файлов и папок
        """
        uploaded = []
        
        for item in os.listdir(local_dir):
            local_path = os.path.join(local_dir, item)
            remote_path = f'{remote_dir}/{item}'
            
            if os.path.isdir(local_path):
                # Создаем папку на удаленном сервере
                if self.sftp:
                    try:
                        self.sftp.mkdir(remote_path)
                    except IOError:
                        pass  # Папка уже существует
                else:
                    # Через SSH команду
                    self.ssh.exec_command(f"mkdir -p '{remote_path.replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'") # pyright: ignore[reportOptionalMemberAccess]
                
                # Рекурсивно загружаем содержимое
                uploaded.extend(self.upload_directory(local_path, remote_path, pbar))
                uploaded.append(f"{item}/ (папка)")
            else:
                # Загружаем файл
                if self.sftp:
                    self.sftp.put(local_path, remote_path)
                else:
                    self.upload_file_scp(local_path, remote_path)
                uploaded.append(item)
                
                # Обновляем прогресс-бар
                if pbar:
                    pbar.update(1)
                    pbar.set_postfix_str(f"{item[:30]}...")
        
        return uploaded
    
    def upload_export_to_printer(self, export_dir: str, remote_dir: str = '/etc/boot-display') -> tuple[bool, str, list[str]]:
        """
        Загружает содержимое export директории на принтер.
        
        Args:
            export_dir: Локальная директория с экспортом
            remote_dir: Удаленная директория на принтере
            
        Returns:
            Кортеж (success, message, uploaded_files)
        """
        try:
            if not os.path.exists(export_dir):
                return False, f"Папка {export_dir} не найдена. Сначала выполните экспорт.", []
            
            # Создаем backup и готовим директорию
            self.backup_and_prepare_directory(remote_dir)
            
            # Подсчитываем общее количество файлов для загрузки
            total_files = sum([len(files) for _, _, files in os.walk(export_dir)])
            
            # Загружаем файлы с прогресс-баром
            with tqdm(total=total_files, desc='Загрузка на принтер', unit='файл') as pbar:
                uploaded_files = self.upload_directory(export_dir, remote_dir, pbar)
            
            message = f"Успешно загружено {len(uploaded_files)} файлов"
            
            return True, message, uploaded_files
            
        except Exception as e:
            return False, f"Ошибка:\n{str(e)}", []
