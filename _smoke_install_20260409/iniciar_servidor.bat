@echo off
chcp 65001 > nul
title Servidor Oficina de Pesca

echo.
echo  ============================================================
echo   SERVIDOR OFICINA DE PESCA
echo  ============================================================
echo.
echo  Iniciando servidor... Aguarde.
echo.

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 servidor.py
  goto fim
)

where python >nul 2>nul
if %errorlevel%==0 (
  python servidor.py
  goto fim
)

echo Python nao encontrado neste computador.
echo Instale Python 3.11+ ou configure no PATH.

:fim
echo.
echo  Servidor encerrado. Pressione qualquer tecla para fechar.
pause > nul
