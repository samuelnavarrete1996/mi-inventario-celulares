@echo off
chcp 65001 > nul
title Mi Inventario - Samuel Navarrete (Celulares)
cd /d "%~dp0"
echo =================================================================
echo   Iniciando Mi Inventario - Samuel Navarrete (Celulares)
echo =================================================================
echo.
echo Iniciando servidor web y abriendo el navegador...
echo.
python run.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Ocurrio un problema al ejecutar Python.
    echo Asegurate de tener Python instalado y accesible en la terminal.
    echo.
    pause
)
