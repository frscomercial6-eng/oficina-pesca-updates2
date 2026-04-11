@echo off
title GERADOR DE APK - OFICINA DE PESCA
setlocal EnableExtensions

echo ============================================
echo  GERANDO APK - OFICINA DE PESCA (ANDROID)
echo ============================================
echo.

set "BASE_DIR=%~dp0"
set "APK_DIR=%BASE_DIR%android_apk"

echo [DEBUG] Verificando pasta do projeto...
if not exist "%APK_DIR%" goto err_no_folder

cd /d "%APK_DIR%"

echo [DEBUG] Verificando Java...

:: 1. Tenta o que ja esta configurado no Windows
java -version >nul 2>&1
if %errorlevel% equ 0 goto check_gradle

:: 2. Tenta a variavel JAVA_HOME se existir
if exist "%JAVA_HOME%\bin\java.exe" (
    set "PATH=%JAVA_HOME%\bin;%PATH%"
    goto check_gradle
)

:: 3. Procura em varias pastas comuns onde o Java costuma se esconder
for %%J in (
    "C:\Program Files\Android\Android Studio\jbr"
    "C:\Program Files\Android\Android Studio\jre"
    "C:\Program Files\Java\jdk-17"
    "C:\Program Files\Java\jdk-21"
    "C:\Program Files\Java\jdk-11"
) do (
    if exist "%%~J\bin\java.exe" (
        set "JAVA_HOME=%%~J"
        set "PATH=%%~J\bin;%PATH%"
        echo [DEBUG] Java encontrado em: %%~J
        goto check_gradle
    )
)

goto err_no_java

:check_gradle

echo [DEBUG] Verificando Gradle Wrapper...
if not exist gradlew.bat goto try_repair_gradle
if not exist "gradle\wrapper\gradle-wrapper.properties" goto try_repair_gradle

echo [1/1] Executando Gradle para gerar APK...
call gradlew.bat clean assembleDebug

if %errorlevel% neq 0 goto err_gradle_fail

echo.
echo Processo concluido com SUCESSO!
set "FINAL_APK=app\build\outputs\apk\debug\app-debug.apk"

if exist "%FINAL_APK%" (
    echo Abrindo a pasta do instalador...
    explorer /select,"%FINAL_APK%"
)

echo.
echo Pressione qualquer tecla para sair.
pause
exit /b 0

:try_repair_gradle
echo [DEBUG] Gradle Wrapper nao encontrado. Tentando restauracao automatica...
echo Isso pode levar um momento (baixando componentes essenciais do Gradle 8.5)...
echo.

if not exist "gradle\wrapper" mkdir "gradle\wrapper"

:: Remove o arquivo possivelmente corrompido antes de criar o novo
if exist "gradle\wrapper\gradle-wrapper.properties" del /f /q "gradle\wrapper\gradle-wrapper.properties"

powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; " ^
    "Write-Host '-> Baixando gradlew.bat...'; (New-Object System.Net.WebClient).DownloadFile('https://raw.githubusercontent.com/gradle/gradle/v8.5.0/gradlew.bat', 'gradlew.bat'); " ^
    "Write-Host '-> Baixando gradlew...'; (New-Object System.Net.WebClient).DownloadFile('https://raw.githubusercontent.com/gradle/gradle/v8.5.0/gradlew', 'gradlew'); " ^
    "Write-Host '-> Baixando jar...'; (New-Object System.Net.WebClient).DownloadFile('https://github.com/gradle/gradle/raw/v8.5.0/gradle/wrapper/gradle-wrapper.jar', 'gradle/wrapper/gradle-wrapper.jar');"

echo -> Criando configuracao...
> "gradle\wrapper\gradle-wrapper.properties" (
    echo distributionBase=GRADLE_USER_HOME
    echo distributionPath=wrapper/dists
    echo distributionUrl=https://services.gradle.org/distributions/gradle-8.5-bin.zip
    echo networkTimeout=10000
    echo validateDistributionUrl=true
    echo zipStoreBase=GRADLE_USER_HOME
    echo zipStorePath=wrapper/dists
)

if exist gradlew.bat (
    echo.
    echo [DEBUG] Arquivos do Gradle restaurados com sucesso!
    echo Iniciando a compilacao...
    goto check_gradle
) else (
    goto err_no_gradle
)

:err_no_folder
echo ERRO: A pasta "android_apk" nao foi encontrada em:
echo "%BASE_DIR%"
pause
exit /b 1

:err_no_java
echo ERRO: Java (JDK) nao encontrado. 
echo.
echo O sistema precisa do JDK para gerar o APK. 
echo Por favor, siga estes passos:
echo 1. Baixe o instalador aqui: https://adoptium.net/pt-BR/temurin/releases/?version=17
echo 2. Execute o arquivo baixado e instale ate o fim.
echo 3. Apos instalar, feche esta janela e tente rodar o script novamente.
pause
exit /b 1

:err_no_gradle
echo ERRO: O arquivo "gradlew.bat" nao foi encontrado em:
echo "%CD%"
echo.
echo Conteudo atual da pasta:
dir /b
echo.
echo DICA: Abra esta pasta "android_apk" no Android Studio para que ele
echo gere automaticamente os arquivos do Gradle Wrapper que estao faltando.
echo Apos o "Sync" do Android Studio terminar, tente rodar este script de novo.
pause
exit /b 1

:err_gradle_fail
echo.
echo ERRO: A compilacao do Gradle falhou. Verifique as mensagens de erro acima.
pause
exit /b 1