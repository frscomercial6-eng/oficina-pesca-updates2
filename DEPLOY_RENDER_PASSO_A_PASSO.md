# Deploy no Render - Oficina de Pesca

## 1) Publicar o codigo no GitHub
1. Crie um repositório no GitHub.
2. Envie os arquivos do projeto para esse repositório.
3. Confirme que estes arquivos existem na raiz do projeto:
   - requirements.txt
   - render.yaml
   - servidor.py

## 2) Criar servico no Render
1. Entre em https://render.com
2. Clique em New + e depois Web Service.
3. Conecte seu repositório GitHub.
4. Se o Render detectar render.yaml, confirme o deploy por ele.

## 3) Configuracao esperada
- Environment: Python
- Build Command: pip install -r requirements.txt
- Start Command: uvicorn servidor:app --host 0.0.0.0 --port $PORT
- Plano: Free (para testes)

## 4) Variavel de ambiente
No Render, adicione:
- OFP_JWT_SECRET = (gerar um valor forte)

Exemplo de segredo:
- OFP_JWT_SECRET = oficina-pesca-2026-segredo-forte

## 5) Pegar URL publica
Depois do deploy, o Render vai mostrar algo como:
- https://oficina-pesca-api.onrender.com

Teste no navegador:
- https://oficina-pesca-api.onrender.com/web/login
- https://oficina-pesca-api.onrender.com/app
- https://oficina-pesca-api.onrender.com/api/versao

## 6) Usar essa URL no sistema desktop
No arquivo config.cfg, em [app], preencha:
- url_app_celular_publica = https://SEU-SERVICO.onrender.com/app

Assim o botao APP CELULAR vai compartilhar o link publico.

## 7) Usar essa URL no APK Android
No arquivo android_apk/app/build.gradle.kts, altere:
- MOBILE_APP_URL para https://SEU-SERVICO.onrender.com/app

Depois gere o APK no Android Studio.

## 8) Observacoes importantes
1. Plano Free pode dormir por inatividade e demorar para abrir na primeira vez.
2. SQLite em hospedagem free pode nao ser ideal para producao definitiva.
3. Quando validar com clientes, migrar para plano pago ou VPS e persistencia adequada.
