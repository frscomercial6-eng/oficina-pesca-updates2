@echo off
setlocal

cd /d "%~dp0"

set "SETUP_PATH=INSTALADOR_FINAL\Setup_OficinaPesca.exe"
set "PACOTE_DIR=PACOTE_ENVIO"
set "RAR_FILE=%PACOTE_DIR%\Oficina_Pesca_Instalador.rar"
set "ZIP_FILE=%PACOTE_DIR%\Oficina_Pesca_Instalador.zip"
set "WINRAR_EXE=C:\Program Files\WinRAR\WinRAR.exe"

echo ============================================
echo  EMPACOTAR INSTALADOR PARA ENVIO
echo ============================================
echo.

if not exist "%SETUP_PATH%" (
    echo ERRO: instalador nao encontrado em:
    echo %SETUP_PATH%
    echo.
    echo Gere primeiro com gerar_release.bat
    pause
    exit /b 1
)

if not exist "%PACOTE_DIR%" mkdir "%PACOTE_DIR%"

copy /Y "%SETUP_PATH%" "%PACOTE_DIR%\Setup_OficinaPesca.exe" >nul

if exist "%RAR_FILE%" del /f /q "%RAR_FILE%" >nul 2>nul
if exist "%ZIP_FILE%" del /f /q "%ZIP_FILE%" >nul 2>nul

if exist "%WINRAR_EXE%" (
    echo WinRAR encontrado. Gerando arquivo RAR...
    "%WINRAR_EXE%" a -ep1 "%RAR_FILE%" "%PACOTE_DIR%\Setup_OficinaPesca.exe"
    if errorlevel 1 (
        echo.
        echo ERRO ao gerar RAR.
        pause
        exit /b 1
    )
    echo.
    echo RAR gerado com sucesso:
    echo %RAR_FILE%
) else (
    echo WinRAR nao encontrado. Gerando ZIP...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '%PACOTE_DIR%\Setup_OficinaPesca.exe' -DestinationPath '%ZIP_FILE%' -Force"
    if errorlevel 1 (
        echo.
        echo ERRO ao gerar ZIP.
        pause
        exit /b 1
    )
    echo.
    echo ZIP gerado com sucesso:
    echo %ZIP_FILE%
)

echo.
echo Abrindo pasta final...
start "" explorer "%PACOTE_DIR%"
echo.
pause