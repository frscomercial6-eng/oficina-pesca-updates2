import os
import sys
import hashlib
import binascii
import sqlite3
import hmac
import base64
import json
import logging
import configparser
import tempfile
import subprocess
import re
import threading
import time
import glob
import shutil
from datetime import date, datetime
from typing import Optional
from contextlib import contextmanager

APP_VERSION = "1.0.0"

# Caminhos globais
# Quando empacotado com PyInstaller:
#   DIRETORIO_ATUAL  -> pasta do .exe (grava banco de dados)
#   DIRETORIO_RECURSOS -> pasta dos arquivos bundlados (imagens, etc.)
if getattr(sys, 'frozen', False):
    DIRETORIO_ATUAL = os.path.dirname(sys.executable)
    DIRETORIO_RECURSOS = sys._MEIPASS
else:
    DIRETORIO_ATUAL = os.path.dirname(os.path.abspath(__file__))
    DIRETORIO_RECURSOS = DIRETORIO_ATUAL

CAMINHO_BANCO = os.path.join(DIRETORIO_ATUAL, 'oficina.db')
CAMINHO_LOG = os.path.join(DIRETORIO_ATUAL, 'logs', 'oficina.log')

# ─── config.cfg ──────────────────────────────────────────────────────────────
def _ler_cfg() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg_path = os.path.join(DIRETORIO_ATUAL, 'config.cfg')
    if os.path.exists(cfg_path):
        cfg.read(cfg_path, encoding='utf-8')
    return cfg

_CFG = _ler_cfg()
SERVIDOR_URL = _CFG.get('app', 'servidor_url', fallback='http://localhost:8000')
URL_APP_CELULAR_PUBLICA = _CFG.get('app', 'url_app_celular_publica', fallback='').strip()
WHATSAPP_ADMIN_DESTINO = _CFG.get('app', 'whatsapp_admin', fallback='').strip()
URL_CHECK_VERSAO = _CFG.get('versao', 'url_check', fallback='')
URL_CHECK_LICENCAS = _CFG.get('versao', 'url_check_licencas', fallback='').strip()
INTERVALO_DIAS_CHECK_VERSAO = max(1, _CFG.getint('versao', 'intervalo_dias_check', fallback=15))
CLOUD_BACKUP_EMAIL = _CFG.get('cloud_backup', 'email_cliente', fallback='').strip()
CLOUD_BACKUP_ENABLED = _CFG.getboolean('cloud_backup', 'habilitado', fallback=True)
CLOUD_SYNC_API_KEY = _CFG.get('cloud_backup', 'api_key', fallback='').strip()
CLOUD_AUTO_SYNC = _CFG.getboolean('cloud_backup', 'auto_sync', fallback=True)
CLOUD_SYNC_INTERVAL_SEG = _CFG.getint('cloud_backup', 'sync_interval_seg', fallback=60)
INFINITEPAY_LINK_PAGAMENTO = _CFG.get('pagamento', 'infinitepay_link', fallback='').strip()
INFINITEPAY_API_CHECKOUT_URL = _CFG.get(
    'pagamento',
    'infinitepay_checkout_url',
    fallback='https://api.infinitepay.io/invoices/public/checkout/links'
).strip()
INFINITEPAY_API_TOKEN = _CFG.get('pagamento', 'infinitepay_api_token', fallback='').strip()
INFINITEPAY_HANDLE = _CFG.get('pagamento', 'infinitepay_handle', fallback='frsoficinadepesca').strip()

# Cores do tema (para CustomTkinter)
COR_PRIMARIA = "#27ae60"  # Verde para botões principais
COR_SECUNDARIA = "#e67e22"  # Laranja para ações
COR_ERRO = "#c0392b"  # Vermelho para erros
TRIAL_DIAS = 15
VALOR_ATUALIZACAO_NAO_PERMANENTE = 50.00
VALOR_LICENCA_MENSAL = 149.90
VALOR_LICENCA_TRIMESTRAL = 249.90
VALOR_LICENCA_PERMANENTE = 599.90
# Permite segredo externo para licenciamento sem quebrar instalações antigas.
# Se a variável de ambiente não existir, mantém fallback compatível.
LICENCA_SECRET = os.environ.get("OFP_LICENCA_SECRET", "OFP-2026-PRIVATE-SECRET")

_CLOUD_SYNC_THREAD: Optional[threading.Thread] = None
_CLOUD_SYNC_STARTED = False


def obter_modo_operacao() -> str:
    """Retorna modo de operação atual: local (padrão) ou rede."""
    try:
        cfg = _ler_cfg()
        # Adiciona um log de aviso se o modo é rede mas o servidor_url ainda é localhost
        if cfg.get('app', 'modo', fallback='local').lower() == 'rede':
            servidor_url_cfg = cfg.get('app', 'servidor_url', fallback='http://localhost:8000').strip().lower()
            if "localhost" in servidor_url_cfg or "127.0.0.1" in servidor_url_cfg:
                get_logger("config").warning("Modo 'rede' ativado, mas 'servidor_url' ainda aponta para 'localhost'. Dispositivos externos não conseguirão se conectar.")

        modo = str(cfg.get('app', 'modo', fallback='local')).strip().lower()
        return modo if modo in {'local', 'rede'} else 'local'
    except Exception:
        return 'local'


def _restaurar_banco_por_backup_se_necessario() -> tuple[bool, str]:
    """Restaura oficina.db automaticamente do backup mais recente quando ausente."""
    try:
        if os.path.exists(CAMINHO_BANCO) and os.path.getsize(CAMINHO_BANCO) > 0:
            return False, "Banco local já existe; restauração automática não necessária."
    except Exception:
        pass

    diretorios_backup = [
        os.path.join(DIRETORIO_ATUAL, "backup_db"),
        os.path.join(os.path.dirname(DIRETORIO_ATUAL), "backup_db"),
        os.path.join(os.getcwd(), "backup_db"),
    ]

    candidatos = []
    vistos = set()
    for pasta in diretorios_backup:
        if not os.path.isdir(pasta):
            continue
        for padrao in ("*.db", "*.sqlite", "*.sqlite3"):
            for caminho in glob.glob(os.path.join(pasta, padrao)):
                try:
                    abs_path = os.path.abspath(caminho)
                    if abs_path in vistos:
                        continue
                    vistos.add(abs_path)
                    if os.path.abspath(CAMINHO_BANCO) == abs_path:
                        continue
                    if os.path.getsize(abs_path) <= 0:
                        continue
                    candidatos.append(abs_path)
                except Exception:
                    continue

    if not candidatos:
        return False, "Nenhum backup local encontrado para restauração automática."

    candidatos.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    os.makedirs(os.path.dirname(CAMINHO_BANCO), exist_ok=True)

    for origem in candidatos:
        try:
            shutil.copy2(origem, CAMINHO_BANCO)
            with sqlite3.connect(CAMINHO_BANCO, timeout=5) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
                cursor.fetchone()
            return True, f"Banco restaurado automaticamente de: {origem}"
        except Exception:
            try:
                if os.path.exists(CAMINHO_BANCO):
                    os.remove(CAMINHO_BANCO)
            except Exception:
                pass
            continue

    return False, "Falha ao restaurar banco a partir dos backups encontrados."


def configurar_logging() -> logging.Logger:
    """Configura logger da aplicação com saída em arquivo."""
    logger = logging.getLogger("oficina")
    if logger.handlers:
        return logger

    os.makedirs(os.path.dirname(CAMINHO_LOG), exist_ok=True)
    logger.setLevel(logging.INFO)

    handler = logging.FileHandler(CAMINHO_LOG, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def get_logger(nome: Optional[str] = None) -> logging.Logger:
    base_logger = configurar_logging()
    if not nome:
        return base_logger
    return base_logger.getChild(nome)

@contextmanager
def get_db_connection():
    """Context manager para garantir que a conexão sempre feche."""
    conn = sqlite3.connect(CAMINHO_BANCO, timeout=10)
    # WAL mode: permite leituras simultâneas sem bloquear escritas
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
    except sqlite3.Error as e:
        get_logger("db").exception("Erro no banco de dados: %s", e)
        raise
    finally:
        conn.close()


def obter_info_nova_versao() -> dict:
    """Obtém dados da versão remota. Retorna dict vazio em caso de falha."""
    if not URL_CHECK_VERSAO:
        return {}
    try:
        import urllib.request
        req = urllib.request.Request(
            URL_CHECK_VERSAO,
            headers={"User-Agent": f"OficinaPesca/{APP_VERSION}"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def eh_versao_mais_nova(versao_remota: str, versao_local: str) -> bool:
    """Compara versões no formato semântico simples (ex.: 1.2.3)."""
    def _to_tuple(v: str) -> tuple[int, ...]:
        partes = []
        for p in str(v or "").strip().split("."):
            try:
                partes.append(int(p))
            except ValueError:
                partes.append(0)
        return tuple(partes)

    remota = _to_tuple(versao_remota)
    local = _to_tuple(versao_local)

    tamanho = max(len(remota), len(local))
    remota += (0,) * (tamanho - len(remota))
    local += (0,) * (tamanho - len(local))
    return remota > local


def verificar_nova_versao() -> tuple[bool, str, str]:
    """Verifica se há nova versão disponível. Retorna (disponivel, versao_nova, novidades)."""
    data = obter_info_nova_versao()
    versao_remota = str(data.get("versao", "")).strip()
    if versao_remota and eh_versao_mais_nova(versao_remota, APP_VERSION):
        return True, versao_remota, str(data.get("novidades", ""))
    return False, "", ""


def obter_politica_atualizacao(licenca_ativa: bool, validade_licenca: str, tipo_licenca: str = "") -> tuple[bool, str]:
    """Retorna política de atualização: (automatica_liberada, mensagem)."""
    tipo = str(tipo_licenca or "").upper().strip()
    validade = str(validade_licenca or "").upper().strip()
    if not tipo:
        tipo = "PERMANENTE" if validade == "PERMANENTE" else "MENSAL"

    if licenca_ativa and (validade == "PERMANENTE" or tipo == "PERMANENTE"):
        return True, "Atualização automática liberada para cliente permanente."

    if tipo == "TRIMESTRAL":
        valor_plano = VALOR_LICENCA_TRIMESTRAL
        nome_plano = "trimestral"
    else:
        valor_plano = VALOR_LICENCA_MENSAL
        nome_plano = "mensal"

    valor = f"{valor_plano:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    msg = (
        f"Cliente {nome_plano}: atualização mediante renovação do plano (R$ {valor}). "
        "Pagamento via InfinitePay (PIX/cartão)."
    )
    return False, msg


def _sha256_texto(texto: str) -> str:
    return hashlib.sha256(str(texto or "").encode("utf-8")).hexdigest().lower()


def gerar_hash_publico_licenca(chave_licenca: str) -> str:
    """Retorna hash SHA-256 da chave para cadastro remoto sem expor a chave original."""
    return _sha256_texto(chave_licenca)


def validar_licenca_remota(url_licencas: str, chave_licenca: str) -> tuple[bool, str, str]:
    """
    Valida a licença em endpoint remoto (ex.: JSON no GitHub raw).

    Formato esperado do JSON remoto:
    {
      "licencas": {
        "<sha256_da_chave>": {"status": "ativo", "tipo": "PERMANENTE|MENSAL|TRIMESTRAL"}
      }
    }
    """
    url = str(url_licencas or "").strip()
    chave = str(chave_licenca or "").strip()
    if not url or not chave:
        return False, "Fonte remota de licenças não configurada.", ""

    try:
        import urllib.request

        req = urllib.request.Request(url, headers={"User-Agent": f"OficinaPesca/{APP_VERSION}"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        licencas = data.get("licencas", {}) if isinstance(data, dict) else {}
        if not isinstance(licencas, dict):
            return False, "Cadastro remoto de licenças inválido.", ""

        chave_hash = _sha256_texto(chave)
        registro = licencas.get(chave_hash, {})
        if not isinstance(registro, dict):
            return False, "Licença não encontrada no cadastro remoto.", ""

        status = str(registro.get("status", "")).lower().strip()
        tipo = str(registro.get("tipo", "")).upper().strip()
        if status != "ativo":
            return False, "Licença encontrada, porém inativa no cadastro remoto.", tipo

        if tipo not in {"PERMANENTE", "MENSAL", "TRIMESTRAL"}:
            tipo = ""

        return True, "Licença validada no cadastro remoto.", tipo
    except Exception as e:
        return False, f"Falha ao validar licença no cadastro remoto: {e}", ""


def deve_verificar_atualizacao(intervalo_dias: int = 15) -> bool:
    """Controla periodicidade de checagem de atualização por data (ex.: 15 dias)."""
    intervalo = max(1, int(intervalo_dias or 15))
    hoje = date.today().toordinal()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'ultimo_check_update_ordinal'")
        row = cursor.fetchone()

        try:
            ultimo = int(row[0]) if row and row[0] is not None else 0
        except Exception:
            ultimo = 0

        if ultimo <= 0 or (hoje - ultimo) >= intervalo:
            cursor.execute(
                "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('ultimo_check_update_ordinal', ?)",
                (hoje,),
            )
            conn.commit()
            return True

    return False


def validar_email_basico(email: str) -> bool:
    email = str(email or "").strip()
    if not email or len(email) > 254:
        return False
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def obter_email_backup_nuvem() -> str:
    global CLOUD_BACKUP_EMAIL
    if CLOUD_BACKUP_EMAIL:
        return CLOUD_BACKUP_EMAIL

    cfg = _ler_cfg()
    CLOUD_BACKUP_EMAIL = cfg.get('cloud_backup', 'email_cliente', fallback='').strip()
    return CLOUD_BACKUP_EMAIL


def salvar_email_backup_nuvem(email: str) -> tuple[bool, str]:
    global CLOUD_BACKUP_EMAIL, _CFG
    email = str(email or "").strip().lower()
    if not validar_email_basico(email):
        return False, "E-mail inválido para backup na nuvem."

    cfg_path = os.path.join(DIRETORIO_ATUAL, 'config.cfg')
    cfg = _ler_cfg()
    if not cfg.has_section('cloud_backup'):
        cfg.add_section('cloud_backup')
    cfg.set('cloud_backup', 'email_cliente', email)

    with open(cfg_path, 'w', encoding='utf-8') as f:
        cfg.write(f)

    CLOUD_BACKUP_EMAIL = email
    _CFG = cfg
    return True, "E-mail de backup em nuvem salvo com sucesso."


def obter_config_backup_nuvem() -> dict:
    cfg = _ler_cfg()
    return {
        "email": cfg.get('cloud_backup', 'email_cliente', fallback='').strip().lower(),
        "habilitado": cfg.getboolean('cloud_backup', 'habilitado', fallback=True),
        "api_key": cfg.get('cloud_backup', 'api_key', fallback='').strip(),
        "auto_sync": cfg.getboolean('cloud_backup', 'auto_sync', fallback=True),
        "sync_interval_seg": max(20, cfg.getint('cloud_backup', 'sync_interval_seg', fallback=60)),
    }


def _obter_token_admin_servidor(usuario_admin: str, senha_admin: str) -> tuple[bool, str, str]:
    try:
        import urllib.request
        import urllib.error
        import urllib.parse

        url_token = f"{SERVIDOR_URL.rstrip('/')}/api/token"
        body = urllib.parse.urlencode(
            {
                "username": usuario_admin,
                "password": senha_admin,
                "grant_type": "password",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url_token,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        role = str(data.get("role", "")).upper()
        token = str(data.get("access_token", "")).strip()
        if role != "ADMIN" or not token:
            return False, "Acesso negado: autenticação ADMIN não confirmada no servidor.", ""
        return True, "Token ADMIN válido.", token
    except urllib.error.URLError as e:
        motivo = str(getattr(e, "reason", e))
        motivo_lower = motivo.lower()
        if "10061" in motivo or "connection refused" in motivo_lower or "conex" in motivo_lower and "recus" in motivo_lower:
            return (
                False,
                "Servidor de nuvem indisponível no momento (conexão recusada). "
                "Inicie o servidor local e confira a URL em config.cfg (app.servidor_url).",
                "",
            )
        return False, f"Falha de conexão com o servidor: {motivo}", ""
    except Exception as e:
        return False, f"Falha de autenticação no servidor: {e}", ""


def enviar_backup_nuvem(email_cliente: str, usuario_admin: str, senha_admin: str) -> tuple[bool, str]:
    """Envia cópia do banco para nuvem do cliente via API (somente ADMIN)."""
    email = str(email_cliente or "").strip().lower()
    if not validar_email_basico(email):
        return False, "E-mail de nuvem inválido."

    if not os.path.exists(CAMINHO_BANCO):
        return False, "Banco de dados não encontrado para backup."

    ok_token, msg_token, token = _obter_token_admin_servidor(usuario_admin, senha_admin)
    if not ok_token:
        return False, msg_token

    try:
        import urllib.request

        with open(CAMINHO_BANCO, "rb") as f:
            conteudo = f.read()

        nome_backup = f"oficina_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        payload = {
            "email_cliente": email,
            "arquivo_nome": nome_backup,
            "conteudo_b64": base64.b64encode(conteudo).decode("ascii"),
            "origem": "desktop_admin",
            "versao_app": APP_VERSION,
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{SERVIDOR_URL.rstrip('/')}/api/cloud-backup",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "User-Agent": f"OficinaPesca/{APP_VERSION}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        arquivo = str(data.get("arquivo", nome_backup))
        return True, f"Backup em nuvem criado com sucesso: {arquivo}"
    except Exception as e:
        return False, f"Falha ao enviar backup para nuvem: {e}"

def sincronizar_dados_da_nuvem(usuario_admin: str, senha_admin: str) -> tuple[bool, str]:
    """Baixa o banco mais recente da nuvem e atualiza o arquivo local."""
    email = obter_email_backup_nuvem()
    if not email:
        return False, "E-mail de nuvem não configurado em Dados da Oficina."

    ok_token, msg_token, token = _obter_token_admin_servidor(usuario_admin, senha_admin)
    if not ok_token:
        return False, msg_token

    try:
        import urllib.request
        import urllib.parse

        url = f"{SERVIDOR_URL.rstrip('/')}/api/cloud-backup/latest?email_cliente={urllib.parse.quote(email)}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": f"OficinaPesca/{APP_VERSION}"
            },
            method="GET"
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if not data.get("ok"):
            return False, "Erro ao buscar dados na nuvem."

        conteudo = base64.b64decode(data["conteudo_b64"])
        
        # Fazer backup do banco atual antes de substituir
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_local_pre = f"{CAMINHO_BANCO}.pre_sync_{carimbo}"
        if os.path.exists(CAMINHO_BANCO):
            import shutil
            shutil.copy2(CAMINHO_BANCO, backup_local_pre)

        # Escrever o novo banco
        with open(CAMINHO_BANCO, "wb") as f:
            f.write(conteudo)

        return True, f"Sincronização concluída! Dados do celular importados com sucesso."
    except Exception as e:
        return False, f"Falha ao sincronizar: {e}"


def enviar_backup_nuvem_api_key(email_cliente: str, api_key: str, origem: str = "desktop_auto") -> tuple[bool, str]:
    """Envia cópia do banco para nuvem usando API key técnica (instalação única)."""
    email = str(email_cliente or "").strip().lower()
    key = str(api_key or "").strip()
    if not validar_email_basico(email):
        return False, "E-mail de nuvem inválido."
    if not key:
        return False, "API key de nuvem não configurada."
    if not os.path.exists(CAMINHO_BANCO):
        return False, "Banco de dados não encontrado para backup."

    try:
        import urllib.request

        with open(CAMINHO_BANCO, "rb") as f:
            conteudo = f.read()

        nome_backup = f"oficina_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        payload = {
            "email_cliente": email,
            "arquivo_nome": nome_backup,
            "conteudo_b64": base64.b64encode(conteudo).decode("ascii"),
            "origem": origem,
            "versao_app": APP_VERSION,
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{SERVIDOR_URL.rstrip('/')}/api/cloud-backup",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-OFP-Cloud-Key": key,
                "User-Agent": f"OficinaPesca/{APP_VERSION}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        arquivo = str(data.get("arquivo", nome_backup))
        return True, f"Backup automático enviado para nuvem: {arquivo}"
    except Exception as e:
        return False, f"Falha no backup automático em nuvem: {e}"


def iniciar_sincronizacao_automatica_nuvem() -> tuple[bool, str]:
    """Monitora alterações no banco e replica automaticamente para nuvem do cliente."""
    global _CLOUD_SYNC_THREAD, _CLOUD_SYNC_STARTED
    if _CLOUD_SYNC_STARTED and _CLOUD_SYNC_THREAD and _CLOUD_SYNC_THREAD.is_alive():
        return True, "Sincronização automática já está ativa."

    if obter_modo_operacao() != "rede":
        return False, "Sincronização automática em nuvem desativada no modo local."

    cfg = obter_config_backup_nuvem()
    if not cfg["habilitado"]:
        return False, "Backup em nuvem desabilitado no config.cfg."
    if not cfg["auto_sync"]:
        return False, "Sincronização automática desabilitada no config.cfg."
    if not cfg["email"] or not validar_email_basico(cfg["email"]):
        return False, "E-mail da nuvem do cliente não configurado."
    if not cfg["api_key"]:
        return False, "API key de nuvem não configurada."

    intervalo = int(cfg["sync_interval_seg"])
    logger = get_logger("cloud-sync")

    def _worker():
        ultimo_mtime = 0.0
        while True:
            try:
                if not os.path.exists(CAMINHO_BANCO):
                    time.sleep(intervalo)
                    continue

                atual_mtime = os.path.getmtime(CAMINHO_BANCO)
                if atual_mtime > ultimo_mtime:
                    ok, msg = enviar_backup_nuvem_api_key(cfg["email"], cfg["api_key"], origem="desktop_auto")
                    if ok:
                        ultimo_mtime = atual_mtime
                        logger.info(msg)
                    else:
                        logger.warning(msg)
                time.sleep(intervalo)
            except Exception as e:
                logger.exception("Falha no loop de sincronização automática: %s", e)
                time.sleep(max(intervalo, 30))

    _CLOUD_SYNC_THREAD = threading.Thread(target=_worker, daemon=True, name="ofp-cloud-sync")
    _CLOUD_SYNC_THREAD.start()
    _CLOUD_SYNC_STARTED = True
    return True, "Sincronização automática com nuvem iniciada."


def executar_atualizacao(
    url_download: str,
    app_executavel: str = "",
    processo_pid: Optional[int] = None,
    silenciosa: bool = True,
) -> tuple[bool, str]:
    """Baixa instalador e inicia atualização. Retorna (ok, mensagem)."""
    url = str(url_download or "").strip()
    if not url:
        return False, "URL de download não configurada."

    if not url.lower().startswith(("http://", "https://")):
        return False, "URL de download inválida."

    try:
        import urllib.request
        nome_arquivo = os.path.basename(url.split("?")[0]) or "Setup_OficinaPesca.exe"
        if not nome_arquivo.lower().endswith(".exe"):
            nome_arquivo = "Setup_OficinaPesca.exe"

        destino = os.path.join(tempfile.gettempdir(), nome_arquivo)
        urllib.request.urlretrieve(url, destino)

        log_instalador = os.path.join(tempfile.gettempdir(), "ofp_auto_update_install.log")
        args_instalador = [destino]
        if silenciosa:
            args_instalador.extend(["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"])
        args_instalador.append(f"/LOG={log_instalador}")

        app_exec = str(app_executavel or "").strip()
        if not app_exec:
            app_exec = sys.executable

        pid_txt = str(int(processo_pid)) if processo_pid else ""

        # Executa via .bat para esperar o app fechar, atualizar e reabrir em seguida.
        script_fd, script_path = tempfile.mkstemp(prefix="ofp_auto_update_", suffix=".bat")
        os.close(script_fd)
        comando_instalador = " ".join([f'"{p}"' if " " in p else p for p in args_instalador])
        linhas = [
            "@echo off",
            "setlocal",
            f"set \"OFP_PID={pid_txt}\"",
            f"set \"OFP_INSTALLER={destino}\"",
            f"set \"OFP_APP={app_exec}\"",
            "if not \"%OFP_PID%\"==\"\" goto wait_app",
            "goto run_installer",
            ":wait_app",
            "tasklist /FI \"PID eq %OFP_PID%\" | find \"%OFP_PID%\" >nul",
            "if not errorlevel 1 (",
            "  timeout /t 1 /nobreak >nul",
            "  goto wait_app",
            ")",
            ":run_installer",
            f"start /wait \"\" {comando_instalador}",
            "if exist \"%OFP_APP%\" start \"\" \"%OFP_APP%\"",
            "endlocal",
        ]

        with open(script_path, "w", encoding="utf-8") as f:
            f.write("\n".join(linhas))

        subprocess.Popen(["cmd", "/c", script_path], shell=False)
        return True, "Atualização silenciosa iniciada. O sistema será reaberto ao concluir."
    except Exception as e:
        return False, f"Falha ao iniciar atualização: {e}"


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """Gera um hash seguro para senha usando PBKDF2-SHA256 e salt."""
    if salt is None:
        salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100_000)
    return f"pbkdf2_sha256${binascii.hexlify(salt).decode()}${binascii.hexlify(digest).decode()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verifica senha contra hash PBKDF2 ou SHA-256 antigo."""
    if stored_hash.startswith("pbkdf2_sha256$"):
        try:
            _, salt_hex, digest_hex = stored_hash.split("$")
            salt = binascii.unhexlify(salt_hex)
            return hash_password(password, salt) == stored_hash
        except Exception:
            return False
    return hashlib.sha256(password.encode('utf-8')).hexdigest() == stored_hash


def validate_password(password: str) -> tuple[bool, str]:
    password = password.strip()
    if len(password) < 8:
        return False, "A senha deve ter pelo menos 8 caracteres."
    if not any(ch.isupper() for ch in password):
        return False, "Use ao menos uma letra maiúscula."
    if not any(ch.islower() for ch in password):
        return False, "Use ao menos uma letra minúscula."
    if not any(ch.isdigit() for ch in password):
        return False, "Use ao menos um número."
    if not any(ch in "!@#$%&*()-_=+[]{};:,.<>?/~^" for ch in password):
        return False, "Use ao menos um caractere especial."
    return True, ""


def inicializar_banco():
    try:
        ok_restore, msg_restore = _restaurar_banco_por_backup_se_necessario()
        if ok_restore:
            get_logger("db").info(msg_restore)
    except Exception as e:
        get_logger("db").warning("Falha na restauração automática do banco: %s", e)

    conn = sqlite3.connect(CAMINHO_BANCO)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE,
            senha TEXT,
            role TEXT DEFAULT 'OPERADOR'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            telefone TEXT,
            email TEXT,
            cep TEXT,
            rua TEXT,
            numero TEXT,
            bairro TEXT,
            cidade TEXT,
            estado TEXT,
            data_cadastro TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            preco_custo REAL DEFAULT 0,
            preco_venda REAL DEFAULT 0,
            estoque INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ordens_servico (
            id_os INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_nome TEXT,
            equipamento TEXT,
            modelo TEXT,
            defeito TEXT,
            valor_pecas REAL,
            valor_obra REAL,
            valor_total REAL,
            entrada REAL,
            restante REAL,
            status TEXT,
            data_abertura TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor INTEGER
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES ('ultimo_orcamento', 500)")
    cursor.execute(
        "INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES ('trial_inicio_ordinal', ?)",
        (date.today().toordinal(),)
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orcamentos_aguardo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT,
            equipamento TEXT,
            defeito TEXT,
            valor_total REAL,
            sinal REAL,
            saldo REAL,
            status TEXT,
            data TEXT,
            itens_detalhes TEXT,
            dados_adicionais TEXT
        )
    """)

    # Garantir migração do schema existente para adicionar dados_adicionais
    cursor.execute("PRAGMA table_info(orcamentos_aguardo)")
    colunas = [row[1] for row in cursor.fetchall()]
    if 'dados_adicionais' not in colunas:
        cursor.execute("ALTER TABLE orcamentos_aguardo ADD COLUMN dados_adicionais TEXT")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fluxo_caixa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT,
            descricao TEXT,
            tipo TEXT,
            valor REAL,
            categoria TEXT,
            metodo_pagamento TEXT
        )
    """)

    cursor.execute("PRAGMA table_info(fluxo_caixa)")
    colunas_fluxo = [row[1] for row in cursor.fetchall()]
    if 'categoria' not in colunas_fluxo:
        cursor.execute("ALTER TABLE fluxo_caixa ADD COLUMN categoria TEXT")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dados_oficina (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            nome_oficina TEXT,
            endereco_oficina TEXT,
            telefone_oficina TEXT,
            chave_pix TEXT,
            logo_path TEXT,
            logo_patrocinador_path TEXT
        )
    """)
    cursor.execute("PRAGMA table_info(dados_oficina)")
    colunas_oficina = [row[1] for row in cursor.fetchall()]
    if 'logo_patrocinador_path' not in colunas_oficina:
        cursor.execute("ALTER TABLE dados_oficina ADD COLUMN logo_patrocinador_path TEXT")
    cursor.execute(
        """
        INSERT OR IGNORE INTO dados_oficina
            (id, nome_oficina, endereco_oficina, telefone_oficina, chave_pix, logo_path, logo_patrocinador_path)
        VALUES
            (1, '', '', '', '', '', '')
        """
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historico_servicos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_nome TEXT,
            data_servico TEXT,
            equipamento TEXT,
            defeito_relatado TEXT,
            servicos_detalhados TEXT,
            valor_total REAL
        )
    """)

    conn.commit()
    conn.close()


def existe_algum_usuario() -> bool:
    """Indica se já existe ao menos um usuário cadastrado."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM usuarios")
        return int(cursor.fetchone()[0] or 0) > 0


def dados_oficina_sao_padrao() -> bool:
    """Retorna True se os dados da oficina ainda não foram configurados."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nome_oficina FROM dados_oficina WHERE id = 1")
            row = cursor.fetchone()
            if not row or not (row[0] or "").strip():
                return True
    except Exception:
        pass
    return False


def obter_chave_pix_oficina() -> str:
    """Retorna a chave PIX cadastrada nos dados da oficina."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chave_pix FROM dados_oficina WHERE id = 1")
            row = cursor.fetchone()
            return (row[0] or "").strip() if row else ""
    except Exception:
        return ""


def _assinar_payload(payload_b64: str) -> str:
    assinatura = hmac.new(
        LICENCA_SECRET.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return assinatura[:20].upper()


def gerar_chave_licenca(cliente: str, dias_validade: Optional[int] = None, tipo_licenca: str = "") -> str:
    cliente = (cliente or "CLIENTE").strip().upper()
    tipo_in = str(tipo_licenca or "").upper().strip()

    if tipo_in == "PERMANENTE":
        dias_validade = None
    elif tipo_in == "TRIMESTRAL" and (dias_validade is None or dias_validade <= 0):
        dias_validade = 90
    elif tipo_in == "MENSAL" and (dias_validade is None or dias_validade <= 0):
        dias_validade = 30

    if dias_validade is not None and dias_validade > 0:
        validade = date.fromordinal(date.today().toordinal() + dias_validade).isoformat()
    else:
        validade = "PERMANENTE"

    if tipo_in not in {"PERMANENTE", "MENSAL", "TRIMESTRAL"}:
        tipo_in = "PERMANENTE" if validade == "PERMANENTE" else "MENSAL"

    payload = {
        "cli": cliente,
        "val": validade,
        "tipo": tipo_in,
        "ver": 1,
    }
    payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("ascii").rstrip("=")
    assinatura = _assinar_payload(payload_b64)
    return f"OFP-{payload_b64}-{assinatura}"


def validar_chave_licenca(chave: str):
    chave = (chave or "").strip()
    if not chave.startswith("OFP-"):
        return False, "Formato de chave invalido.", None

    try:
        _, payload_b64, assinatura = chave.split("-", 2)
    except ValueError:
        return False, "Chave incompleta.", None

    assinatura_ok = _assinar_payload(payload_b64)
    if not hmac.compare_digest(assinatura_ok, assinatura.upper()):
        return False, "Assinatura da chave invalida.", None

    try:
        padding = "=" * ((4 - len(payload_b64) % 4) % 4)
        payload_json = base64.urlsafe_b64decode((payload_b64 + padding).encode("ascii")).decode("utf-8")
        payload = json.loads(payload_json)
    except Exception:
        return False, "Conteudo da chave invalido.", None

    validade = str(payload.get("val", "PERMANENTE"))
    tipo = str(payload.get("tipo", "")).upper().strip()
    if tipo not in {"PERMANENTE", "MENSAL", "TRIMESTRAL"}:
        tipo = "PERMANENTE" if validade == "PERMANENTE" else "MENSAL"
        payload["tipo"] = tipo

    if validade != "PERMANENTE":
        try:
            data_validade = date.fromisoformat(validade)
        except ValueError:
            return False, "Data de validade invalida na chave.", None
        if date.today() > data_validade:
            return False, f"Licenca expirada em {data_validade.strftime('%d/%m/%Y')}.", payload

    return True, "Licenca valida.", payload


def ativar_licenca(chave: str):
    valida, msg, payload = validar_chave_licenca(chave)
    if not valida:
        return False, msg

    cliente = str((payload or {}).get("cli", "CLIENTE"))
    validade = str((payload or {}).get("val", "PERMANENTE"))
    tipo = str((payload or {}).get("tipo", "")).upper().strip()
    if tipo not in {"PERMANENTE", "MENSAL", "TRIMESTRAL"}:
        tipo = "PERMANENTE" if validade == "PERMANENTE" else "MENSAL"

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('licenca_chave', ?)",
            (chave.strip(),)
        )
        cursor.execute(
            "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('licenca_cliente', ?)",
            (cliente,)
        )
        cursor.execute(
            "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('licenca_validade', ?)",
            (validade,)
        )
        cursor.execute(
            "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('licenca_tipo', ?)",
            (tipo,)
        )
        conn.commit()

    return True, "Licenca ativada com sucesso."


def obter_status_licenca():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'licenca_chave'")
        row_chave = cursor.fetchone()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'licenca_cliente'")
        row_cliente = cursor.fetchone()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'licenca_validade'")
        row_validade = cursor.fetchone()

    chave = row_chave[0] if row_chave and row_chave[0] else ""
    cliente = row_cliente[0] if row_cliente and row_cliente[0] else ""
    validade = row_validade[0] if row_validade and row_validade[0] else "PERMANENTE"

    if not chave:
        return False, "Sem licenca ativa.", "", "PERMANENTE"

    valida, msg, _payload = validar_chave_licenca(chave)
    if not valida:
        return False, msg, cliente, validade

    return True, "Licenca ativa.", cliente, validade


def obter_tipo_licenca() -> str:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'licenca_tipo'")
        row_tipo = cursor.fetchone()
        if row_tipo and row_tipo[0]:
            tipo = str(row_tipo[0]).upper().strip()
            if tipo in {"PERMANENTE", "MENSAL", "TRIMESTRAL"}:
                return tipo

        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'licenca_validade'")
        row_validade = cursor.fetchone()
        validade = str(row_validade[0] if row_validade and row_validade[0] else "").upper().strip()

    return "PERMANENTE" if validade == "PERMANENTE" else "MENSAL"


def obter_chave_licenca_ativa() -> str:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'licenca_chave'")
        row = cursor.fetchone()
    return str(row[0] if row and row[0] else "").strip()


def obter_status_trial():
    """Retorna status do trial: (ativo, dias_restantes, data_limite)."""
    hoje_ordinal = date.today().toordinal()
    data_limite = ""

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES ('trial_inicio_ordinal', ?)",
            (hoje_ordinal,)
        )
        conn.commit()

        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'trial_inicio_ordinal'")
        row = cursor.fetchone()

        try:
            inicio_ordinal = int(row[0]) if row and row[0] is not None else hoje_ordinal
        except Exception:
            inicio_ordinal = hoje_ordinal

    dias_passados = max(0, hoje_ordinal - inicio_ordinal)
    dias_restantes = max(0, TRIAL_DIAS - dias_passados)
    limite_ordinal = inicio_ordinal + TRIAL_DIAS
    data_limite = date.fromordinal(limite_ordinal).strftime("%d/%m/%Y")

    return dias_restantes > 0, dias_restantes, data_limite

# Configurações de API externas
import os
import sys
import hashlib
import binascii
import sqlite3
import hmac
import base64
import json
import logging
import configparser
import tempfile
import subprocess
import re
import threading
import time
import glob
import shutil
from datetime import date, datetime
from typing import Optional
from contextlib import contextmanager

APP_VERSION = "1.0.0"

# Caminhos globais
# Quando empacotado com PyInstaller:
#   DIRETORIO_ATUAL  -> pasta do .exe (grava banco de dados)
#   DIRETORIO_RECURSOS -> pasta dos arquivos bundlados (imagens, etc.)
if getattr(sys, 'frozen', False):
    DIRETORIO_ATUAL = os.path.dirname(sys.executable)
    DIRETORIO_RECURSOS = sys._MEIPASS
else:
    DIRETORIO_ATUAL = os.path.dirname(os.path.abspath(__file__))
    DIRETORIO_RECURSOS = DIRETORIO_ATUAL

CAMINHO_BANCO = os.path.join(DIRETORIO_ATUAL, 'oficina.db')
CAMINHO_LOG = os.path.join(DIRETORIO_ATUAL, 'logs', 'oficina.log')

# ─── config.cfg ──────────────────────────────────────────────────────────────
def _ler_cfg() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg_path = os.path.join(DIRETORIO_ATUAL, 'config.cfg')
    if os.path.exists(cfg_path):
        cfg.read(cfg_path, encoding='utf-8')
    return cfg

_CFG = _ler_cfg()
SERVIDOR_URL = _CFG.get('app', 'servidor_url', fallback='http://localhost:8000')
URL_APP_CELULAR_PUBLICA = _CFG.get('app', 'url_app_celular_publica', fallback='').strip()
WHATSAPP_ADMIN_DESTINO = _CFG.get('app', 'whatsapp_admin', fallback='').strip()
URL_CHECK_VERSAO = _CFG.get('versao', 'url_check', fallback='')
URL_CHECK_LICENCAS = _CFG.get('versao', 'url_check_licencas', fallback='').strip()
INTERVALO_DIAS_CHECK_VERSAO = max(1, _CFG.getint('versao', 'intervalo_dias_check', fallback=15))
CLOUD_BACKUP_EMAIL = _CFG.get('cloud_backup', 'email_cliente', fallback='').strip()
CLOUD_BACKUP_ENABLED = _CFG.getboolean('cloud_backup', 'habilitado', fallback=True)
CLOUD_SYNC_API_KEY = _CFG.get('cloud_backup', 'api_key', fallback='').strip()
CLOUD_AUTO_SYNC = _CFG.getboolean('cloud_backup', 'auto_sync', fallback=True)
CLOUD_SYNC_INTERVAL_SEG = _CFG.getint('cloud_backup', 'sync_interval_seg', fallback=60)
INFINITEPAY_LINK_PAGAMENTO = _CFG.get('pagamento', 'infinitepay_link', fallback='').strip()
INFINITEPAY_API_CHECKOUT_URL = _CFG.get(
    'pagamento',
    'infinitepay_checkout_url',
    fallback='https://api.infinitepay.io/invoices/public/checkout/links'
).strip()
INFINITEPAY_API_TOKEN = _CFG.get('pagamento', 'infinitepay_api_token', fallback='').strip()
INFINITEPAY_HANDLE = _CFG.get('pagamento', 'infinitepay_handle', fallback='frsoficinadepesca').strip()

# Cores do tema (para CustomTkinter)
COR_PRIMARIA = "#27ae60"  # Verde para botões principais
COR_SECUNDARIA = "#e67e22"  # Laranja para ações
COR_ERRO = "#c0392b"  # Vermelho para erros
TRIAL_DIAS = 15
VALOR_ATUALIZACAO_NAO_PERMANENTE = 50.00
VALOR_LICENCA_MENSAL = 149.90
VALOR_LICENCA_TRIMESTRAL = 249.90
VALOR_LICENCA_PERMANENTE = 599.90
# Permite segredo externo para licenciamento sem quebrar instalações antigas.
# Se a variável de ambiente não existir, mantém fallback compatível.
LICENCA_SECRET = os.environ.get("OFP_LICENCA_SECRET", "OFP-2026-PRIVATE-SECRET")

_CLOUD_SYNC_THREAD: Optional[threading.Thread] = None
_CLOUD_SYNC_STARTED = False


def obter_modo_operacao() -> str:
    """Retorna modo de operação atual: local (padrão) ou rede."""
    try:
        cfg = _ler_cfg()
        # Adiciona um log de aviso se o modo é rede mas o servidor_url ainda é localhost
        if cfg.get('app', 'modo', fallback='local').lower() == 'rede':
            servidor_url_cfg = cfg.get('app', 'servidor_url', fallback='http://localhost:8000').strip().lower()
            if "localhost" in servidor_url_cfg or "127.0.0.1" in servidor_url_cfg:
                get_logger("config").warning("Modo 'rede' ativado, mas 'servidor_url' ainda aponta para 'localhost'. Dispositivos externos não conseguirão se conectar.")

        modo = str(cfg.get('app', 'modo', fallback='local')).strip().lower()
        return modo if modo in {'local', 'rede'} else 'local'
    except Exception:
        return 'local'


def _restaurar_banco_por_backup_se_necessario() -> tuple[bool, str]:
    """Restaura oficina.db automaticamente do backup mais recente quando ausente."""
    try:
        if os.path.exists(CAMINHO_BANCO) and os.path.getsize(CAMINHO_BANCO) > 0:
            return False, "Banco local já existe; restauração automática não necessária."
    except Exception:
        pass

    diretorios_backup = [
        os.path.join(DIRETORIO_ATUAL, "backup_db"),
        os.path.join(os.path.dirname(DIRETORIO_ATUAL), "backup_db"),
        os.path.join(os.getcwd(), "backup_db"),
    ]

    candidatos = []
    vistos = set()
    for pasta in diretorios_backup:
        if not os.path.isdir(pasta):
            continue
        for padrao in ("*.db", "*.sqlite", "*.sqlite3"):
            for caminho in glob.glob(os.path.join(pasta, padrao)):
                try:
                    abs_path = os.path.abspath(caminho)
                    if abs_path in vistos:
                        continue
                    vistos.add(abs_path)
                    if os.path.abspath(CAMINHO_BANCO) == abs_path:
                        continue
                    if os.path.getsize(abs_path) <= 0:
                        continue
                    candidatos.append(abs_path)
                except Exception:
                    continue

    if not candidatos:
        return False, "Nenhum backup local encontrado para restauração automática."

    candidatos.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    os.makedirs(os.path.dirname(CAMINHO_BANCO), exist_ok=True)

    for origem in candidatos:
        try:
            shutil.copy2(origem, CAMINHO_BANCO)
            with sqlite3.connect(CAMINHO_BANCO, timeout=5) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
                cursor.fetchone()
            return True, f"Banco restaurado automaticamente de: {origem}"
        except Exception:
            try:
                if os.path.exists(CAMINHO_BANCO):
                    os.remove(CAMINHO_BANCO)
            except Exception:
                pass
            continue

    return False, "Falha ao restaurar banco a partir dos backups encontrados."


def configurar_logging() -> logging.Logger:
    """Configura logger da aplicação com saída em arquivo."""
    logger = logging.getLogger("oficina")
    if logger.handlers:
        return logger

    os.makedirs(os.path.dirname(CAMINHO_LOG), exist_ok=True)
    logger.setLevel(logging.INFO)

    handler = logging.FileHandler(CAMINHO_LOG, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def get_logger(nome: Optional[str] = None) -> logging.Logger:
    base_logger = configurar_logging()
    if not nome:
        return base_logger
    return base_logger.getChild(nome)

@contextmanager
def get_db_connection():
    """Context manager para garantir que a conexão sempre feche."""
    conn = sqlite3.connect(CAMINHO_BANCO, timeout=10)
    # WAL mode: permite leituras simultâneas sem bloquear escritas
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
    except sqlite3.Error as e:
        get_logger("db").exception("Erro no banco de dados: %s", e)
        raise
    finally:
        conn.close()


def obter_info_nova_versao() -> dict:
    """Obtém dados da versão remota. Retorna dict vazio em caso de falha."""
    if not URL_CHECK_VERSAO:
        return {}
    try:
        import urllib.request
        req = urllib.request.Request(
            URL_CHECK_VERSAO,
            headers={"User-Agent": f"OficinaPesca/{APP_VERSION}"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def eh_versao_mais_nova(versao_remota: str, versao_local: str) -> bool:
    """Compara versões no formato semântico simples (ex.: 1.2.3)."""
    def _to_tuple(v: str) -> tuple[int, ...]:
        partes = []
        for p in str(v or "").strip().split("."):
            try:
                partes.append(int(p))
            except ValueError:
                partes.append(0)
        return tuple(partes)

    remota = _to_tuple(versao_remota)
    local = _to_tuple(versao_local)

    tamanho = max(len(remota), len(local))
    remota += (0,) * (tamanho - len(remota))
    local += (0,) * (tamanho - len(local))
    return remota > local


def verificar_nova_versao() -> tuple[bool, str, str]:
    """Verifica se há nova versão disponível. Retorna (disponivel, versao_nova, novidades)."""
    data = obter_info_nova_versao()
    versao_remota = str(data.get("versao", "")).strip()
    if versao_remota and eh_versao_mais_nova(versao_remota, APP_VERSION):
        return True, versao_remota, str(data.get("novidades", ""))
    return False, "", ""


def obter_politica_atualizacao(licenca_ativa: bool, validade_licenca: str, tipo_licenca: str = "") -> tuple[bool, str]:
    """Retorna política de atualização: (automatica_liberada, mensagem)."""
    tipo = str(tipo_licenca or "").upper().strip()
    validade = str(validade_licenca or "").upper().strip()
    if not tipo:
        tipo = "PERMANENTE" if validade == "PERMANENTE" else "MENSAL"

    if licenca_ativa and (validade == "PERMANENTE" or tipo == "PERMANENTE"):
        return True, "Atualização automática liberada para cliente permanente."

    if tipo == "TRIMESTRAL":
        valor_plano = VALOR_LICENCA_TRIMESTRAL
        nome_plano = "trimestral"
    else:
        valor_plano = VALOR_LICENCA_MENSAL
        nome_plano = "mensal"

    valor = f"{valor_plano:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    msg = (
        f"Cliente {nome_plano}: atualização mediante renovação do plano (R$ {valor}). "
        "Pagamento via InfinitePay (PIX/cartão)."
    )
    return False, msg


def _sha256_texto(texto: str) -> str:
    return hashlib.sha256(str(texto or "").encode("utf-8")).hexdigest().lower()


def gerar_hash_publico_licenca(chave_licenca: str) -> str:
    """Retorna hash SHA-256 da chave para cadastro remoto sem expor a chave original."""
    return _sha256_texto(chave_licenca)


def validar_licenca_remota(url_licencas: str, chave_licenca: str) -> tuple[bool, str, str]:
    """
    Valida a licença em endpoint remoto (ex.: JSON no GitHub raw).

    Formato esperado do JSON remoto:
    {
      "licencas": {
        "<sha256_da_chave>": {"status": "ativo", "tipo": "PERMANENTE|MENSAL|TRIMESTRAL"}
      }
    }
    """
    url = str(url_licencas or "").strip()
    chave = str(chave_licenca or "").strip()
    if not url or not chave:
        return False, "Fonte remota de licenças não configurada.", ""

    try:
        import urllib.request

        req = urllib.request.Request(url, headers={"User-Agent": f"OficinaPesca/{APP_VERSION}"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        licencas = data.get("licencas", {}) if isinstance(data, dict) else {}
        if not isinstance(licencas, dict):
            return False, "Cadastro remoto de licenças inválido.", ""

        chave_hash = _sha256_texto(chave)
        registro = licencas.get(chave_hash, {})
        if not isinstance(registro, dict):
            return False, "Licença não encontrada no cadastro remoto.", ""

        status = str(registro.get("status", "")).lower().strip()
        tipo = str(registro.get("tipo", "")).upper().strip()
        if status != "ativo":
            return False, "Licença encontrada, porém inativa no cadastro remoto.", tipo

        if tipo not in {"PERMANENTE", "MENSAL", "TRIMESTRAL"}:
            tipo = ""

        return True, "Licença validada no cadastro remoto.", tipo
    except Exception as e:
        return False, f"Falha ao validar licença no cadastro remoto: {e}", ""


def deve_verificar_atualizacao(intervalo_dias: int = 15) -> bool:
    """Controla periodicidade de checagem de atualização por data (ex.: 15 dias)."""
    intervalo = max(1, int(intervalo_dias or 15))
    hoje = date.today().toordinal()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'ultimo_check_update_ordinal'")
        row = cursor.fetchone()

        try:
            ultimo = int(row[0]) if row and row[0] is not None else 0
        except Exception:
            ultimo = 0

        if ultimo <= 0 or (hoje - ultimo) >= intervalo:
            cursor.execute(
                "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('ultimo_check_update_ordinal', ?)",
                (hoje,),
            )
            conn.commit()
            return True

    return False


def validar_email_basico(email: str) -> bool:
    email = str(email or "").strip()
    if not email or len(email) > 254:
        return False
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def obter_email_backup_nuvem() -> str:
    global CLOUD_BACKUP_EMAIL
    if CLOUD_BACKUP_EMAIL:
        return CLOUD_BACKUP_EMAIL

    cfg = _ler_cfg()
    CLOUD_BACKUP_EMAIL = cfg.get('cloud_backup', 'email_cliente', fallback='').strip()
    return CLOUD_BACKUP_EMAIL


def salvar_email_backup_nuvem(email: str) -> tuple[bool, str]:
    global CLOUD_BACKUP_EMAIL, _CFG
    email = str(email or "").strip().lower()
    if not validar_email_basico(email):
        return False, "E-mail inválido para backup na nuvem."

    cfg_path = os.path.join(DIRETORIO_ATUAL, 'config.cfg')
    cfg = _ler_cfg()
    if not cfg.has_section('cloud_backup'):
        cfg.add_section('cloud_backup')
    cfg.set('cloud_backup', 'email_cliente', email)

    with open(cfg_path, 'w', encoding='utf-8') as f:
        cfg.write(f)

    CLOUD_BACKUP_EMAIL = email
    _CFG = cfg
    return True, "E-mail de backup em nuvem salvo com sucesso."


def obter_config_backup_nuvem() -> dict:
    cfg = _ler_cfg()
    return {
        "email": cfg.get('cloud_backup', 'email_cliente', fallback='').strip().lower(),
        "habilitado": cfg.getboolean('cloud_backup', 'habilitado', fallback=True),
        "api_key": cfg.get('cloud_backup', 'api_key', fallback='').strip(),
        "auto_sync": cfg.getboolean('cloud_backup', 'auto_sync', fallback=True),
        "sync_interval_seg": max(20, cfg.getint('cloud_backup', 'sync_interval_seg', fallback=60)),
    }


def _obter_token_admin_servidor(usuario_admin: str, senha_admin: str) -> tuple[bool, str, str]:
    try:
        import urllib.request
        import urllib.error
        import urllib.parse

        url_token = f"{SERVIDOR_URL.rstrip('/')}/api/token"
        body = urllib.parse.urlencode(
            {
                "username": usuario_admin,
                "password": senha_admin,
                "grant_type": "password",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url_token,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        role = str(data.get("role", "")).upper()
        token = str(data.get("access_token", "")).strip()
        if role != "ADMIN" or not token:
            return False, "Acesso negado: autenticação ADMIN não confirmada no servidor.", ""
        return True, "Token ADMIN válido.", token
    except urllib.error.URLError as e:
        motivo = str(getattr(e, "reason", e))
        motivo_lower = motivo.lower()
        if "10061" in motivo or "connection refused" in motivo_lower or "conex" in motivo_lower and "recus" in motivo_lower:
            return (
                False,
                "Servidor de nuvem indisponível no momento (conexão recusada). "
                "Inicie o servidor local e confira a URL em config.cfg (app.servidor_url).",
                "",
            )
        return False, f"Falha de conexão com o servidor: {motivo}", ""
    except Exception as e:
        return False, f"Falha de autenticação no servidor: {e}", ""


def enviar_backup_nuvem(email_cliente: str, usuario_admin: str, senha_admin: str) -> tuple[bool, str]:
    """Envia cópia do banco para nuvem do cliente via API (somente ADMIN)."""
    email = str(email_cliente or "").strip().lower()
    if not validar_email_basico(email):
        return False, "E-mail de nuvem inválido."

    if not os.path.exists(CAMINHO_BANCO):
        return False, "Banco de dados não encontrado para backup."

    ok_token, msg_token, token = _obter_token_admin_servidor(usuario_admin, senha_admin)
    if not ok_token:
        return False, msg_token

    try:
        import urllib.request

        with open(CAMINHO_BANCO, "rb") as f:
            conteudo = f.read()

        nome_backup = f"oficina_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        payload = {
            "email_cliente": email,
            "arquivo_nome": nome_backup,
            "conteudo_b64": base64.b64encode(conteudo).decode("ascii"),
            "origem": "desktop_admin",
            "versao_app": APP_VERSION,
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{SERVIDOR_URL.rstrip('/')}/api/cloud-backup",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "User-Agent": f"OficinaPesca/{APP_VERSION}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        arquivo = str(data.get("arquivo", nome_backup))
        return True, f"Backup em nuvem criado com sucesso: {arquivo}"
    except Exception as e:
        return False, f"Falha ao enviar backup para nuvem: {e}"

def sincronizar_dados_da_nuvem(usuario_admin: str, senha_admin: str) -> tuple[bool, str]:
    """Baixa o banco mais recente da nuvem e atualiza o arquivo local."""
    email = obter_email_backup_nuvem()
    if not email:
        return False, "E-mail de nuvem não configurado em Dados da Oficina."

    ok_token, msg_token, token = _obter_token_admin_servidor(usuario_admin, senha_admin)
    if not ok_token:
        return False, msg_token

    try:
        import urllib.request
        import urllib.parse

        url = f"{SERVIDOR_URL.rstrip('/')}/api/cloud-backup/latest?email_cliente={urllib.parse.quote(email)}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": f"OficinaPesca/{APP_VERSION}"
            },
            method="GET"
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if not data.get("ok"):
            return False, "Erro ao buscar dados na nuvem."

        conteudo = base64.b64decode(data["conteudo_b64"])
        
        # Fazer backup do banco atual antes de substituir
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_local_pre = f"{CAMINHO_BANCO}.pre_sync_{carimbo}"
        if os.path.exists(CAMINHO_BANCO):
            import shutil
            shutil.copy2(CAMINHO_BANCO, backup_local_pre)

        # Escrever o novo banco
        with open(CAMINHO_BANCO, "wb") as f:
            f.write(conteudo)

        return True, f"Sincronização concluída! Dados do celular importados com sucesso."
    except Exception as e:
        return False, f"Falha ao sincronizar: {e}"


def enviar_backup_nuvem_api_key(email_cliente: str, api_key: str, origem: str = "desktop_auto") -> tuple[bool, str]:
    """Envia cópia do banco para nuvem usando API key técnica (instalação única)."""
    email = str(email_cliente or "").strip().lower()
    key = str(api_key or "").strip()
    if not validar_email_basico(email):
        return False, "E-mail de nuvem inválido."
    if not key:
        return False, "API key de nuvem não configurada."
    if not os.path.exists(CAMINHO_BANCO):
        return False, "Banco de dados não encontrado para backup."

    try:
        import urllib.request

        with open(CAMINHO_BANCO, "rb") as f:
            conteudo = f.read()

        nome_backup = f"oficina_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        payload = {
            "email_cliente": email,
            "arquivo_nome": nome_backup,
            "conteudo_b64": base64.b64encode(conteudo).decode("ascii"),
            "origem": origem,
            "versao_app": APP_VERSION,
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{SERVIDOR_URL.rstrip('/')}/api/cloud-backup",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-OFP-Cloud-Key": key,
                "User-Agent": f"OficinaPesca/{APP_VERSION}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        arquivo = str(data.get("arquivo", nome_backup))
        return True, f"Backup automático enviado para nuvem: {arquivo}"
    except Exception as e:
        return False, f"Falha no backup automático em nuvem: {e}"


def iniciar_sincronizacao_automatica_nuvem() -> tuple[bool, str]:
    """Monitora alterações no banco e replica automaticamente para nuvem do cliente."""
    global _CLOUD_SYNC_THREAD, _CLOUD_SYNC_STARTED
    if _CLOUD_SYNC_STARTED and _CLOUD_SYNC_THREAD and _CLOUD_SYNC_THREAD.is_alive():
        return True, "Sincronização automática já está ativa."

    if obter_modo_operacao() != "rede":
        return False, "Sincronização automática em nuvem desativada no modo local."

    cfg = obter_config_backup_nuvem()
    if not cfg["habilitado"]:
        return False, "Backup em nuvem desabilitado no config.cfg."
    if not cfg["auto_sync"]:
        return False, "Sincronização automática desabilitada no config.cfg."
    if not cfg["email"] or not validar_email_basico(cfg["email"]):
        return False, "E-mail da nuvem do cliente não configurado."
    if not cfg["api_key"]:
        return False, "API key de nuvem não configurada."

    intervalo = int(cfg["sync_interval_seg"])
    logger = get_logger("cloud-sync")

    def _worker():
        ultimo_mtime = 0.0
        while True:
            try:
                if not os.path.exists(CAMINHO_BANCO):
                    time.sleep(intervalo)
                    continue

                atual_mtime = os.path.getmtime(CAMINHO_BANCO)
                if atual_mtime > ultimo_mtime:
                    ok, msg = enviar_backup_nuvem_api_key(cfg["email"], cfg["api_key"], origem="desktop_auto")
                    if ok:
                        ultimo_mtime = atual_mtime
                        logger.info(msg)
                    else:
                        logger.warning(msg)
                time.sleep(intervalo)
            except Exception as e:
                logger.exception("Falha no loop de sincronização automática: %s", e)
                time.sleep(max(intervalo, 30))

    _CLOUD_SYNC_THREAD = threading.Thread(target=_worker, daemon=True, name="ofp-cloud-sync")
    _CLOUD_SYNC_THREAD.start()
    _CLOUD_SYNC_STARTED = True
    return True, "Sincronização automática com nuvem iniciada."


def executar_atualizacao(
    url_download: str,
    app_executavel: str = "",
    processo_pid: Optional[int] = None,
    silenciosa: bool = True,
) -> tuple[bool, str]:
    """Baixa instalador e inicia atualização. Retorna (ok, mensagem)."""
    url = str(url_download or "").strip()
    if not url:
        return False, "URL de download não configurada."

    if not url.lower().startswith(("http://", "https://")):
        return False, "URL de download inválida."

    try:
        import urllib.request
        nome_arquivo = os.path.basename(url.split("?")[0]) or "Setup_OficinaPesca.exe"
        if not nome_arquivo.lower().endswith(".exe"):
            nome_arquivo = "Setup_OficinaPesca.exe"

        destino = os.path.join(tempfile.gettempdir(), nome_arquivo)
        urllib.request.urlretrieve(url, destino)

        log_instalador = os.path.join(tempfile.gettempdir(), "ofp_auto_update_install.log")
        args_instalador = [destino]
        if silenciosa:
            args_instalador.extend(["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"])
        args_instalador.append(f"/LOG={log_instalador}")

        app_exec = str(app_executavel or "").strip()
        if not app_exec:
            app_exec = sys.executable

        pid_txt = str(int(processo_pid)) if processo_pid else ""

        # Executa via .bat para esperar o app fechar, atualizar e reabrir em seguida.
        script_fd, script_path = tempfile.mkstemp(prefix="ofp_auto_update_", suffix=".bat")
        os.close(script_fd)
        comando_instalador = " ".join([f'"{p}"' if " " in p else p for p in args_instalador])
        linhas = [
            "@echo off",
            "setlocal",
            f"set \"OFP_PID={pid_txt}\"",
            f"set \"OFP_INSTALLER={destino}\"",
            f"set \"OFP_APP={app_exec}\"",
            "if not \"%OFP_PID%\"==\"\" goto wait_app",
            "goto run_installer",
            ":wait_app",
            "tasklist /FI \"PID eq %OFP_PID%\" | find \"%OFP_PID%\" >nul",
            "if not errorlevel 1 (",
            "  timeout /t 1 /nobreak >nul",
            "  goto wait_app",
            ")",
            ":run_installer",
            f"start /wait \"\" {comando_instalador}",
            "if exist \"%OFP_APP%\" start \"\" \"%OFP_APP%\"",
            "endlocal",
        ]

        with open(script_path, "w", encoding="utf-8") as f:
            f.write("\n".join(linhas))

        subprocess.Popen(["cmd", "/c", script_path], shell=False)
        return True, "Atualização silenciosa iniciada. O sistema será reaberto ao concluir."
    except Exception as e:
        return False, f"Falha ao iniciar atualização: {e}"


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """Gera um hash seguro para senha usando PBKDF2-SHA256 e salt."""
    if salt is None:
        salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100_000)
    return f"pbkdf2_sha256${binascii.hexlify(salt).decode()}${binascii.hexlify(digest).decode()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verifica senha contra hash PBKDF2 ou SHA-256 antigo."""
    if stored_hash.startswith("pbkdf2_sha256$"):
        try:
            _, salt_hex, digest_hex = stored_hash.split("$")
            salt = binascii.unhexlify(salt_hex)
            return hash_password(password, salt) == stored_hash
        except Exception:
            return False
    return hashlib.sha256(password.encode('utf-8')).hexdigest() == stored_hash


def validate_password(password: str) -> tuple[bool, str]:
    password = password.strip()
    if len(password) < 8:
        return False, "A senha deve ter pelo menos 8 caracteres."
    if not any(ch.isupper() for ch in password):
        return False, "Use ao menos uma letra maiúscula."
    if not any(ch.islower() for ch in password):
        return False, "Use ao menos uma letra minúscula."
    if not any(ch.isdigit() for ch in password):
        return False, "Use ao menos um número."
    if not any(ch in "!@#$%&*()-_=+[]{};:,.<>?/~^" for ch in password):
        return False, "Use ao menos um caractere especial."
    return True, ""


def inicializar_banco():
    try:
        ok_restore, msg_restore = _restaurar_banco_por_backup_se_necessario()
        if ok_restore:
            get_logger("db").info(msg_restore)
    except Exception as e:
        get_logger("db").warning("Falha na restauração automática do banco: %s", e)

    conn = sqlite3.connect(CAMINHO_BANCO)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE,
            senha TEXT,
            role TEXT DEFAULT 'OPERADOR'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            telefone TEXT,
            email TEXT,
            cep TEXT,
            rua TEXT,
            numero TEXT,
            bairro TEXT,
            cidade TEXT,
            estado TEXT,
            data_cadastro TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            preco_custo REAL DEFAULT 0,
            preco_venda REAL DEFAULT 0,
            estoque INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ordens_servico (
            id_os INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_nome TEXT,
            equipamento TEXT,
            modelo TEXT,
            defeito TEXT,
            valor_pecas REAL,
            valor_obra REAL,
            valor_total REAL,
            entrada REAL,
            restante REAL,
            status TEXT,
            data_abertura TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor INTEGER
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES ('ultimo_orcamento', 500)")
    cursor.execute(
        "INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES ('trial_inicio_ordinal', ?)",
        (date.today().toordinal(),)
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orcamentos_aguardo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT,
            equipamento TEXT,
            defeito TEXT,
            valor_total REAL,
            sinal REAL,
            saldo REAL,
            status TEXT,
            data TEXT,
            itens_detalhes TEXT,
            dados_adicionais TEXT
        )
    """)

    # Garantir migração do schema existente para adicionar dados_adicionais
    cursor.execute("PRAGMA table_info(orcamentos_aguardo)")
    colunas = [row[1] for row in cursor.fetchall()]
    if 'dados_adicionais' not in colunas:
        cursor.execute("ALTER TABLE orcamentos_aguardo ADD COLUMN dados_adicionais TEXT")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fluxo_caixa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT,
            descricao TEXT,
            tipo TEXT,
            valor REAL,
            categoria TEXT,
            metodo_pagamento TEXT
        )
    """)

    cursor.execute("PRAGMA table_info(fluxo_caixa)")
    colunas_fluxo = [row[1] for row in cursor.fetchall()]
    if 'categoria' not in colunas_fluxo:
        cursor.execute("ALTER TABLE fluxo_caixa ADD COLUMN categoria TEXT")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dados_oficina (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            nome_oficina TEXT,
            endereco_oficina TEXT,
            telefone_oficina TEXT,
            chave_pix TEXT,
            logo_path TEXT,
            logo_patrocinador_path TEXT
        )
    """)
    cursor.execute("PRAGMA table_info(dados_oficina)")
    colunas_oficina = [row[1] for row in cursor.fetchall()]
    if 'logo_patrocinador_path' not in colunas_oficina:
        cursor.execute("ALTER TABLE dados_oficina ADD COLUMN logo_patrocinador_path TEXT")
    cursor.execute(
        """
        INSERT OR IGNORE INTO dados_oficina
            (id, nome_oficina, endereco_oficina, telefone_oficina, chave_pix, logo_path, logo_patrocinador_path)
        VALUES
            (1, '', '', '', '', '', '')
        """
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historico_servicos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_nome TEXT,
            data_servico TEXT,
            equipamento TEXT,
            defeito_relatado TEXT,
            servicos_detalhados TEXT,
            valor_total REAL
        )
    """)

    conn.commit()
    conn.close()


def existe_algum_usuario() -> bool:
    """Indica se já existe ao menos um usuário cadastrado."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM usuarios")
        return int(cursor.fetchone()[0] or 0) > 0


def dados_oficina_sao_padrao() -> bool:
    """Retorna True se os dados da oficina ainda não foram configurados."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nome_oficina FROM dados_oficina WHERE id = 1")
            row = cursor.fetchone()
            if not row or not (row[0] or "").strip():
                return True
    except Exception:
        pass
    return False


def obter_chave_pix_oficina() -> str:
    """Retorna a chave PIX cadastrada nos dados da oficina."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chave_pix FROM dados_oficina WHERE id = 1")
            row = cursor.fetchone()
            return (row[0] or "").strip() if row else ""
    except Exception:
        return ""


def _assinar_payload(payload_b64: str) -> str:
    assinatura = hmac.new(
        LICENCA_SECRET.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return assinatura[:20].upper()


def gerar_chave_licenca(cliente: str, dias_validade: Optional[int] = None, tipo_licenca: str = "") -> str:
    cliente = (cliente or "CLIENTE").strip().upper()
    tipo_in = str(tipo_licenca or "").upper().strip()

    if tipo_in == "PERMANENTE":
        dias_validade = None
    elif tipo_in == "TRIMESTRAL" and (dias_validade is None or dias_validade <= 0):
        dias_validade = 90
    elif tipo_in == "MENSAL" and (dias_validade is None or dias_validade <= 0):
        dias_validade = 30

    if dias_validade is not None and dias_validade > 0:
        validade = date.fromordinal(date.today().toordinal() + dias_validade).isoformat()
    else:
        validade = "PERMANENTE"

    if tipo_in not in {"PERMANENTE", "MENSAL", "TRIMESTRAL"}:
        tipo_in = "PERMANENTE" if validade == "PERMANENTE" else "MENSAL"

    payload = {
        "cli": cliente,
        "val": validade,
        "tipo": tipo_in,
        "ver": 1,
    }
    payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("ascii").rstrip("=")
    assinatura = _assinar_payload(payload_b64)
    return f"OFP-{payload_b64}-{assinatura}"


def validar_chave_licenca(chave: str):
    chave = (chave or "").strip()
    if not chave.startswith("OFP-"):
        return False, "Formato de chave invalido.", None

    try:
        _, payload_b64, assinatura = chave.split("-", 2)
    except ValueError:
        return False, "Chave incompleta.", None

    assinatura_ok = _assinar_payload(payload_b64)
    if not hmac.compare_digest(assinatura_ok, assinatura.upper()):
        return False, "Assinatura da chave invalida.", None

    try:
        padding = "=" * ((4 - len(payload_b64) % 4) % 4)
        payload_json = base64.urlsafe_b64decode((payload_b64 + padding).encode("ascii")).decode("utf-8")
        payload = json.loads(payload_json)
    except Exception:
        return False, "Conteudo da chave invalido.", None

    validade = str(payload.get("val", "PERMANENTE"))
    tipo = str(payload.get("tipo", "")).upper().strip()
    if tipo not in {"PERMANENTE", "MENSAL", "TRIMESTRAL"}:
        tipo = "PERMANENTE" if validade == "PERMANENTE" else "MENSAL"
        payload["tipo"] = tipo

    if validade != "PERMANENTE":
        try:
            data_validade = date.fromisoformat(validade)
        except ValueError:
            return False, "Data de validade invalida na chave.", None
        if date.today() > data_validade:
            return False, f"Licenca expirada em {data_validade.strftime('%d/%m/%Y')}.", payload

    return True, "Licenca valida.", payload


def ativar_licenca(chave: str):
    valida, msg, payload = validar_chave_licenca(chave)
    if not valida:
        return False, msg

    cliente = str((payload or {}).get("cli", "CLIENTE"))
    validade = str((payload or {}).get("val", "PERMANENTE"))
    tipo = str((payload or {}).get("tipo", "")).upper().strip()
    if tipo not in {"PERMANENTE", "MENSAL", "TRIMESTRAL"}:
        tipo = "PERMANENTE" if validade == "PERMANENTE" else "MENSAL"

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('licenca_chave', ?)",
            (chave.strip(),)
        )
        cursor.execute(
            "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('licenca_cliente', ?)",
            (cliente,)
        )
        cursor.execute(
            "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('licenca_validade', ?)",
            (validade,)
        )
        cursor.execute(
            "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('licenca_tipo', ?)",
            (tipo,)
        )
        conn.commit()

    return True, "Licenca ativada com sucesso."


def obter_status_licenca():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'licenca_chave'")
        row_chave = cursor.fetchone()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'licenca_cliente'")
        row_cliente = cursor.fetchone()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'licenca_validade'")
        row_validade = cursor.fetchone()

    chave = row_chave[0] if row_chave and row_chave[0] else ""
    cliente = row_cliente[0] if row_cliente and row_cliente[0] else ""
    validade = row_validade[0] if row_validade and row_validade[0] else "PERMANENTE"

    if not chave:
        return False, "Sem licenca ativa.", "", "PERMANENTE"

    valida, msg, _payload = validar_chave_licenca(chave)
    if not valida:
        return False, msg, cliente, validade

    return True, "Licenca ativa.", cliente, validade


def obter_tipo_licenca() -> str:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'licenca_tipo'")
        row_tipo = cursor.fetchone()
        if row_tipo and row_tipo[0]:
            tipo = str(row_tipo[0]).upper().strip()
            if tipo in {"PERMANENTE", "MENSAL", "TRIMESTRAL"}:
                return tipo

        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'licenca_validade'")
        row_validade = cursor.fetchone()
        validade = str(row_validade[0] if row_validade and row_validade[0] else "").upper().strip()

    return "PERMANENTE" if validade == "PERMANENTE" else "MENSAL"


def obter_chave_licenca_ativa() -> str:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'licenca_chave'")
        row = cursor.fetchone()
    return str(row[0] if row and row[0] else "").strip()


def obter_status_trial():
    """Retorna status do trial: (ativo, dias_restantes, data_limite)."""
    hoje_ordinal = date.today().toordinal()
    data_limite = ""

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES ('trial_inicio_ordinal', ?)",
            (hoje_ordinal,)
        )
        conn.commit()

        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'trial_inicio_ordinal'")
        row = cursor.fetchone()

        try:
            inicio_ordinal = int(row[0]) if row and row[0] is not None else hoje_ordinal
        except Exception:
            inicio_ordinal = hoje_ordinal

    dias_passados = max(0, hoje_ordinal - inicio_ordinal)
    dias_restantes = max(0, TRIAL_DIAS - dias_passados)
    limite_ordinal = inicio_ordinal + TRIAL_DIAS
    data_limite = date.fromordinal(limite_ordinal).strftime("%d/%m/%Y")

    return dias_restantes > 0, dias_restantes, data_limite

# Configurações de API externas
URL_VIACEP = "https://viacep.com.br/ws/{}/json/"  # Para busca de CEP