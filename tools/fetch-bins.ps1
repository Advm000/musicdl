# Télécharge les binaires embarqués (yt-dlp + ffmpeg) dans bin/
# Usage : powershell -ExecutionPolicy Bypass -File tools/fetch-bins.ps1
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root = Split-Path $PSScriptRoot -Parent
$bin = Join-Path $root 'bin'
New-Item -ItemType Directory -Force $bin | Out-Null

Write-Host '[1/2] yt-dlp.exe…'
Invoke-WebRequest -Uri 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe' -OutFile (Join-Path $bin 'yt-dlp.exe') -UseBasicParsing

Write-Host '[2/2] ffmpeg + ffprobe…'
$zip = Join-Path $env:TEMP 'ffmpeg-ess.zip'
$tmp = Join-Path $env:TEMP 'ffmpeg-ess'
Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile $zip -UseBasicParsing
Expand-Archive -Path $zip -DestinationPath $tmp -Force
Copy-Item (Get-ChildItem $tmp -Recurse -Filter ffmpeg.exe | Select-Object -First 1).FullName (Join-Path $bin 'ffmpeg.exe') -Force
Copy-Item (Get-ChildItem $tmp -Recurse -Filter ffprobe.exe | Select-Object -First 1).FullName (Join-Path $bin 'ffprobe.exe') -Force
Remove-Item $zip -Force; Remove-Item $tmp -Recurse -Force

Write-Host 'OK — binaires installés dans bin/'
