@echo off
chcp 65001 >nul
title VitaMusic - Servidor (Sync + Buscador online)
cd /d "%~dp0"

REM ============================================================
REM   Configuracion: edita estas dos lineas si hace falta
REM ============================================================
set "MUSIC_DIR="
set "PORT=8787"

REM Forzar UTF-8 para metadatos con acentos / simbolos
set "PYTHONUTF8=1"

echo ============================================================
echo   Crescendo - Servidor
echo   Carpeta de musica : %MUSIC_DIR%
echo   Puerto            : %PORT%
echo ============================================================
echo.

REM Crear la carpeta de musica si no existe
if not exist "%MUSIC_DIR%" mkdir "%MUSIC_DIR%"

REM Verificar que Python este disponible
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] No se encontro "python" en el PATH.
    echo Instala Python 3 desde https://www.python.org y marca "Add to PATH".
    echo.
    pause
    exit /b 1
)

REM Verificar que el servidor exista junto a este .bat
if not exist "%~dp0sync_server.py" (
    echo [ERROR] No se encontro sync_server.py junto a este archivo .bat.
    echo Coloca VitaMusic-Servidor.bat en la misma carpeta que sync_server.py
    echo.
    pause
    exit /b 1
)

python "%~dp0sync_server.py" "%MUSIC_DIR%" %PORT%

echo.
echo ============================================================
echo   El servidor se detuvo.
echo ============================================================
pause >nul
