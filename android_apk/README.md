# APK Mobile - Oficina de Pesca

Projeto Android (WebView) para gerar APK do app celular da Oficina de Pesca.

## 1) Definir URL publica
Edite o arquivo `app/build.gradle.kts` e altere a linha:

`buildConfigField("String", "MOBILE_APP_URL", "\"https://SEU-LINK-PUBLICO/app\"")`

Exemplo real:

`buildConfigField("String", "MOBILE_APP_URL", "\"https://oficina-pesca-api.onrender.com/app\"")`

## 2) Gerar APK no Android Studio
1. Abra a pasta `android_apk` no Android Studio.
2. Aguarde o Gradle Sync.
3. Menu: Build > Build APK(s).
4. APK gerado em:
   `app/build/outputs/apk/debug/app-debug.apk`

## 3) Instalar no celular
1. Envie o `app-debug.apk` para o celular.
2. Habilite instalacao de fontes desconhecidas.
3. Instale e abra o app.

## Observacoes
- Este APK depende da URL publica estar online.
- Para ambiente local de testes, pode usar URL temporaria (ngrok/cloudflare tunnel).
