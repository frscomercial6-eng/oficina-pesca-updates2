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

set "PY_CMD="

if exist "venv\Scripts\python.exe" (
  set "PY_CMD=venv\Scripts\python.exe"
  goto deps
)

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m venv venv
  if exist "venv\Scripts\python.exe" (
    set "PY_CMD=venv\Scripts\python.exe"
    goto deps
  )
)

where python >nul 2>nul
if %errorlevel%==0 (
  python -m venv venv
  if exist "venv\Scripts\python.exe" (
    set "PY_CMD=venv\Scripts\python.exe"
    goto deps
  )
  set "PY_CMD=python"
  goto deps
)

echo Python nao encontrado neste computador.
echo Instale Python 3.11+ ou configure no PATH.
goto fim

:deps
echo  Verificando dependencias do servidor...
%PY_CMD% -c "import fastapi, uvicorn, jinja2, jose, multipart" >nul 2>nul
if %errorlevel% neq 0 (
  echo  Instalando dependencias do servidor...
  %PY_CMD% -m pip install --upgrade pip
  %PY_CMD% -m pip install fastapi uvicorn jinja2 python-multipart python-jose cryptography
  if %errorlevel% neq 0 (
    echo  Falha ao instalar dependencias do servidor.
    goto fim
  )
)

echo  Iniciando servidor web...
%PY_CMD% servidor.py

:fim
echo.
echo  Servidor encerrado. Pressione qualquer tecla para fechar.
pause > nul
