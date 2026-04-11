@echo off
setlocal

cd /d "%~dp0"

echo ============================================
echo  GERANDO EXE E INSTALADOR - OFICINA PESCA
echo ============================================
echo.

where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo ERRO: PyInstaller nao encontrado no PATH.
    pause
    exit /b 1
)

if not exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    echo ERRO: Inno Setup nao encontrado em:
    echo C:\Program Files ^(x86^)^\Inno Setup 6\ISCC.exe
    pause
    exit /b 1
)

if exist "build\oficina" (
    echo Limpando build anterior...
    rmdir /s /q "build\oficina"
)

if exist "dist\Oficina_Pesca" (
    echo Limpando dist anterior...
    rmdir /s /q "dist\Oficina_Pesca"
)

echo [1/2] Gerando executavel com PyInstaller...
pyinstaller --noconfirm oficina.spec
if errorlevel 1 (
    echo.
    echo ERRO ao gerar o executavel.
    pause
    exit /b 1
)

echo.
echo [2/2] Gerando instalador com Inno Setup...
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" instalar.iss
if errorlevel 1 (
    echo.
    echo ERRO ao gerar o instalador.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  FINALIZADO COM SUCESSO
echo ============================================
echo EXE: dist\Oficina_Pesca\Oficina_Pesca.exe
echo SETUP: INSTALADOR_FINAL\Setup_OficinaPesca.exe
echo.
pause