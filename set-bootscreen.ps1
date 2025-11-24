# Параметры: путь к видео и авторизация в формате user:pass@ip
param(
    [Parameter(Mandatory=$true)]
    [string]$video,
    
    [Parameter(Mandatory=$true)]
    [string]$auth,
    
    [Parameter(Mandatory=$false)]
    [double]$start = 0,
    
    [Parameter(Mandatory=$false)]
    [double]$end = 0,
    
    [Parameter(Mandatory=$false)]
    [int]$fps = 12,
    
    [Parameter(Mandatory=$false)]
    [switch]$fade
)

# Проверка наличия обязательных аргументов
if (!$video -or !$auth) {
    Write-Host "Error: Missing required arguments" -ForegroundColor Red
    Write-Host "Usage: .\set-bootscreen.ps1 <video_file> <user:pass@ip> [-start <seconds>] [-end <seconds>] [-fps <fps>] [-fade]" -ForegroundColor Yellow
    Write-Host "Example: .\set-bootscreen.ps1 video.mp4 root:password@192.168.1.100 -start 5 -end 30 -fps 12 -fade" -ForegroundColor Yellow
    exit 1
}

# Проверка существования видео файла
if (!(Test-Path $video)) {
    Write-Host "Error: Video file not found: $video" -ForegroundColor Red
    exit 1
}

# Проверка формата строки авторизации
if ($auth -notmatch '^[^:]+:[^@]+@[\d\.]+$') {
    Write-Host "Error: Invalid auth format. Expected: user:pass@ip" -ForegroundColor Red
    Write-Host "Example: root:creality_2023@192.168.1.100" -ForegroundColor Yellow
    exit 1
}

# Проверка и установка ffmpeg если отсутствует
$ffmpegLocal = Get-ChildItem -Path . -Filter "ffmpeg-*" -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
if (!$ffmpegLocal) {
    $ffmpegLocal = Get-ChildItem -Path .\ffmpeg -Filter "ffmpeg-*" -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
}

if ($ffmpegLocal) {
    # Найден локальный ffmpeg - добавляем в PATH
    $ffmpegBinPath = Join-Path $ffmpegLocal.FullName "bin"
    $env:PATH = "$ffmpegBinPath;$env:PATH"
} elseif (!(Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    # Нет ни локального, ни в системном PATH - скачиваем
    Write-Host "Downloading ffmpeg..."
    Invoke-WebRequest https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl-shared.zip -OutFile ffmpeg.zip
    Expand-Archive ffmpeg.zip -Force
    $ffmpegLocal = Get-ChildItem -Path . -Filter "ffmpeg-*" -Directory -Recurse | Select-Object -First 1
    $ffmpegBinPath = Join-Path $ffmpegLocal.FullName "bin"
    $env:PATH = "$ffmpegBinPath;$env:PATH"
}

# Парсинг авторизации: user:pass@ip -> отдельные переменные
$user, $rest = $auth -split ':'
$pass, $ip = $rest -split '@'

# Создание директории для экспорта и очистка старых файлов
New-Item export\part0 -ItemType Directory -Force | Out-Null
Remove-Item export\part0\*.jpg -ErrorAction SilentlyContinue

# Получение длительности видео через ffprobe
$ffprobeOutput = & ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 $video 2>$null
$videoDuration = [double]$ffprobeOutput

# Если end не указан, используем полную длительность видео
if ($end -le 0) {
    $end = $videoDuration
}

# Вычисляем длительность и точное количество кадров (минус 1 кадр для буфера)
$duration = $end - $start
$frameCount = [math]::Floor($duration * $fps) - 1

# Построение video filters с учетом fade
$vf = "scale=800:480:force_original_aspect_ratio=increase,crop=800:480,transpose=1"
if ($fade) {
    $fadeDuration = 1.0
    $fadeOutStart = $duration - $fadeDuration - (2.0 / $fps)
    $vf += ",fade=t=in:st=0:d=${fadeDuration},fade=t=out:st=${fadeOutStart}:d=${fadeDuration}"
}

# Построение команды ffmpeg с учетом параметров обрезки
$ffmpegArgs = @()
if ($start -gt 0) {
    $ffmpegArgs += @("-ss", $start)
}
$ffmpegArgs += @("-i", $video, "-frames:v", $frameCount, "-vf", $vf, "-r", $fps, "-q:v", "1", "export\part0\pic_%03d.jpg", "-y")

# Раскадровка видео: поворот на 90°, масштаб 800x480
Write-Host "Processing video (start: $start s, end: $end s, duration: $duration s, frames: $frameCount, fps: $fps)..."
$ffmpegArgs += @("-stats", "-loglevel", "error")
$ffmpegResult = & ffmpeg $ffmpegArgs 2>&1

# Проверка успешности выполнения ffmpeg
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: ffmpeg failed" -ForegroundColor Red
    Write-Host $ffmpegResult -ForegroundColor Red
    exit 1
}

# Проверка что файлы были созданы
$exportedFiles = Get-ChildItem export\part0\pic_*.jpg -ErrorAction SilentlyContinue
if ($exportedFiles.Count -eq 0) {
    Write-Host "Error: No frames exported" -ForegroundColor Red
    exit 1
}

Write-Host "Exported $($exportedFiles.Count) frames" -ForegroundColor Green

# Создание конфигурационного файла
"width: 480`nheight: 800`nfps: $fps`nparts: 1`n{ part0 }" | Out-File export\boot-display.conf -Encoding ASCII

# Установка Posh-SSH модуля если отсутствует
if (!(Get-Module Posh-SSH -ListAvailable)) {
    Write-Host "Installing Posh-SSH module..."
    Install-Module Posh-SSH -Force -Scope CurrentUser
}
Import-Module Posh-SSH

# Подготовка учетных данных для SSH
$pw = ConvertTo-SecureString $pass -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential($user, $pw)

# Подключение по SSH и создание backup старой папки
Write-Host "Connecting to printer $ip..."
$s = New-SSHSession -ComputerName $ip -Credential $cred -AcceptKey
$timestamp = Get-Date -Format yyyyMMdd_HHmmss
Invoke-SSHCommand -SSHSession $s -Command "[ -d /etc/boot-display ] && mv /etc/boot-display /etc/boot-display-BACK-$timestamp; mkdir -p /etc/boot-display" | Out-Null

# Загрузка файлов через SFTP
Write-Host "Uploading files..."
$sftp = New-SFTPSession -ComputerName $ip -Credential $cred -AcceptKey

# Создаём директорию part0 через SSH (SFTP создание не работает надёжно)
Invoke-SSHCommand -SSHSession $s -Command "mkdir -p /etc/boot-display/part0" | Out-Null

# Загружаем конфигурационный файл
Set-SFTPItem -SFTPSession $sftp -Path (Resolve-Path export\boot-display.conf).Path -Destination /etc/boot-display -Force

# Загружаем все кадры в папку part0
Write-Host "Uploading frames..."
Get-ChildItem export\part0\*.jpg | ForEach-Object {
    Set-SFTPItem -SFTPSession $sftp -Path $_.FullName -Destination /etc/boot-display/part0 -Force
}

# Закрытие соединений
Remove-SSHSession $s | Out-Null
Remove-SFTPSession $sftp | Out-Null

Write-Host "Done!" -ForegroundColor Green
