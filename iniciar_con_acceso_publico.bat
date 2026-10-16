@echo off
chcp 65001 > nul
title Mi Inventario Samuel Navarrete - Acceso Publico Seguro (Internet)
cd /d "%~dp0"
echo =================================================================
echo   MI INVENTARIO - SAMUEL NAVARRETE (CELULARES)
echo   Iniciando con enlace publico para acceder desde cualquier lugar
echo =================================================================
echo.
echo [1/2] Iniciando servidor del inventario...
start "Servidor Inventario" /min cmd /c "python run.py"

echo [2/2] Conectando con Cloudflare Tunnel para generar enlace de Internet...
timeout /t 2 /nobreak > nul
echo.
echo =================================================================
echo   TU ENLACE DE ACCESO APARECERA A CONTINUACION (https://....trycloudflare.com)
echo   Puedes abrirlo en tu celular, tablet o cualquier computadora.
echo   Mantén esta ventana abierta mientras necesites el acceso.
echo =================================================================
echo.
cloudflared tunnel --url http://127.0.0.1:8000
