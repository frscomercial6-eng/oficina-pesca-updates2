#!/usr/bin/env python3
"""
servidor.py — Servidor multi-usuário da Oficina de Pesca

Permite acesso simultâneo de:
  - Múltiplos PCs na rede local (LAN)
  - Celular / tablet via navegador
  - Qualquer dispositivo com acesso à internet

Como iniciar:
    python servidor.py
    python servidor.py --host 0.0.0.0 --porta 8000

Acesso pela rede local:
    Desktop: configure config.cfg → servidor_url = http://IP_DO_SERVIDOR:8000
    Celular:  abra o navegador em   http://IP_DO_SERVIDOR:8000
"""

import os
import sys
import json
import re
import base64
import hmac
import argparse
from datetime import datetime, timedelta, timezone
from typing import Optional

import uvicorn
from fastapi import (
    FastAPI, Depends, HTTPException, Request, Form,
    status as http_status,
)
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel

# Importa funções do sistema existente
# Adaptar caminho se necessário
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import (
    get_db_connection,
    hash_password,
    verify_password,
    validate_password,
    get_logger,
    inicializar_banco,
    APP_VERSION,
    _CFG,
)

logger = get_logger("servidor")

# ─── CONFIGURAÇÃO JWT ────────────────────────────────────────────────────────
JWT_SECRET = os.environ.get(
    "OFP_JWT_SECRET",
    _CFG.get("servidor", "jwt_secret", fallback="OFP-JWT-ALTERAR-EM-PRODUCAO")
)
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HORAS = 8

# ─── APP ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Oficina de Pesca",
    version=APP_VERSION,
    docs_url="/api/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates HTML (interface web/mobile)
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
os.makedirs(TEMPLATES_DIR, exist_ok=True)
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Arquivos estáticos (CSS/JS)
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token", auto_error=False)


# ─── MODELOS ─────────────────────────────────────────────────────────────────
class Token(BaseModel):
    access_token: str
    token_type: str
    usuario: str
    role: str


class ClienteIn(BaseModel):
    nome: str
    telefone: Optional[str] = ""
    email: Optional[str] = ""
    cep: Optional[str] = ""
    rua: Optional[str] = ""
    numero: Optional[str] = ""
    bairro: Optional[str] = ""
    cidade: Optional[str] = ""
    estado: Optional[str] = ""


class OrcamentoStatusIn(BaseModel):
    status: str


class LancamentoIn(BaseModel):
    descricao: str
    tipo: str  # ENTRADA | SAIDA
    valor: float
    categoria: Optional[str] = ""
    metodo_pagamento: Optional[str] = ""
    data: Optional[str] = ""


class ProdutoIn(BaseModel):
    nome: str
    preco_custo: float = 0.0
    preco_venda: float = 0.0
    estoque: int = 0


class CloudBackupIn(BaseModel):
    email_cliente: str
    arquivo_nome: str
    conteudo_b64: str
    origem: Optional[str] = "desktop_admin"
    versao_app: Optional[str] = ""


# ─── HELPERS AUTH ─────────────────────────────────────────────────────────────
def _criar_token(usuario: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HORAS)
    payload = {"sub": usuario, "role": role, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decodificar_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado.")


def _usuario_do_request(request: Request, bearer: str) -> dict:
    """Aceita Bearer token (API) ou cookie ofp_token (browser)."""
    if bearer:
        try:
            return _decodificar_token(bearer)
        except HTTPException:
            pass
    cookie = request.cookies.get("ofp_token", "")
    if cookie:
        try:
            return _decodificar_token(cookie)
        except HTTPException:
            pass
    raise HTTPException(status_code=401, detail="Não autenticado.")


async def get_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
) -> dict:
    return _usuario_do_request(request, token or "")


async def get_admin(
    request: Request,
    token: str = Depends(oauth2_scheme),
) -> dict:
    payload = _usuario_do_request(request, token or "")
    if str(payload.get("role", "")).upper() != "ADMIN":
        raise HTTPException(status_code=403, detail="Acesso restrito a ADMIN.")
    return payload


# ─── MIDDLEWARE: redireciona /web para login se sem cookie ───────────────────
def _checar_cookie(request: Request) -> Optional[dict]:
    cookie = request.cookies.get("ofp_token", "")
    if not cookie:
        return None
    try:
        return _decodificar_token(cookie)
    except HTTPException:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

# ─── AUTH ────────────────────────────────────────────────────────────────────
@app.post("/api/token", response_model=Token, tags=["Auth"])
async def api_login(form_data: OAuth2PasswordRequestForm = Depends()):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT senha, role FROM usuarios WHERE UPPER(usuario)=UPPER(?) LIMIT 1",
            (form_data.username.strip(),)
        )
        row = cur.fetchone()
    if not row or not verify_password(form_data.password, str(row[0] or "")):
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos.")
    role = str(row[1] or "OPERADOR")
    token = _criar_token(form_data.username.strip(), role)
    return Token(access_token=token, token_type="bearer",
                 usuario=form_data.username.strip(), role=role)


# ─── VERSÃO ───────────────────────────────────────────────────────────────────
@app.get("/api/versao", tags=["Sistema"])
async def api_versao():
    """Retorna informações da versão atual do servidor.
    Configure url_check no config.cfg dos clientes apontando para este endpoint."""
    versao_file = os.path.join(BASE_DIR, "versao.json")
    if os.path.exists(versao_file):
        with open(versao_file, encoding="utf-8") as f:
            return json.load(f)
    return {"versao": APP_VERSION, "novidades": ""}


@app.post("/api/cloud-backup", tags=["Backup"])
async def api_cloud_backup(
    request: Request,
    body: CloudBackupIn,
    token: str = Depends(oauth2_scheme),
):
    """Recebe backup do desktop e grava no repositório de nuvem por e-mail do cliente."""
    actor = "SISTEMA"
    key_cfg = _CFG.get("cloud_backup", "api_key", fallback="").strip()
    key_req = request.headers.get("X-OFP-Cloud-Key", "").strip()

    autorizado = False
    if key_cfg and key_req and hmac.compare_digest(key_cfg, key_req):
        autorizado = True
        actor = "AUTO_SYNC"

    if not autorizado:
        payload = _usuario_do_request(request, token or "")
        if str(payload.get("role", "")).upper() != "ADMIN":
            raise HTTPException(status_code=403, detail="Acesso restrito a ADMIN ou chave técnica.")
        actor = str(payload.get("sub", "ADMIN"))

    email = str(body.email_cliente or "").strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(status_code=400, detail="E-mail de cliente inválido.")

    nome_arquivo = os.path.basename(str(body.arquivo_nome or "backup.db")).strip()
    if not nome_arquivo.lower().endswith(".db"):
        nome_arquivo += ".db"

    try:
        conteudo = base64.b64decode(str(body.conteudo_b64 or "").encode("ascii"), validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Conteúdo de backup inválido (base64).")

    if not conteudo:
        raise HTTPException(status_code=400, detail="Backup vazio.")
    if len(conteudo) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Backup excede o limite de 50 MB.")

    cliente_dir = re.sub(r"[^a-z0-9._-]", "_", email)
    destino_dir = os.path.join(BASE_DIR, "cloud_backups", cliente_dir)
    os.makedirs(destino_dir, exist_ok=True)

    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_final = f"{carimbo}_{nome_arquivo}"
    destino = os.path.join(destino_dir, nome_final)

    with open(destino, "wb") as f:
        f.write(conteudo)

    logger.info(
        "Backup nuvem criado por=%s para cliente=%s arquivo=%s origem=%s versao=%s",
        actor,
        email,
        nome_final,
        str(body.origem or ""),
        str(body.versao_app or ""),
    )
    return {"ok": True, "arquivo": nome_final, "email_cliente": email}


# ─── CLIENTES ─────────────────────────────────────────────────────────────────
@app.get("/api/clientes", tags=["Clientes"])
async def api_listar_clientes(user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, nome, telefone, email, cidade, estado, data_cadastro "
            "FROM clientes ORDER BY nome"
        )
        rows = cur.fetchall()
    keys = ["id", "nome", "telefone", "email", "cidade", "estado", "data_cadastro"]
    return [dict(zip(keys, r)) for r in rows]


@app.get("/api/clientes/{cliente_id}", tags=["Clientes"])
async def api_get_cliente(cliente_id: int, user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM clientes WHERE id=?", (cliente_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    keys = ["id","nome","telefone","email","cep","rua","numero","bairro","cidade","estado","data_cadastro"]
    return dict(zip(keys, row))


@app.post("/api/clientes", status_code=201, tags=["Clientes"])
async def api_criar_cliente(cliente: ClienteIn, user=Depends(get_user)):
    now = datetime.now().strftime("%d/%m/%Y")
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO clientes "
            "(nome,telefone,email,cep,rua,numero,bairro,cidade,estado,data_cadastro) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (cliente.nome, cliente.telefone, cliente.email, cliente.cep,
             cliente.rua, cliente.numero, cliente.bairro, cliente.cidade,
             cliente.estado, now)
        )
        conn.commit()
        return {"id": cur.lastrowid, "nome": cliente.nome}


@app.put("/api/clientes/{cliente_id}", tags=["Clientes"])
async def api_atualizar_cliente(cliente_id: int, cliente: ClienteIn, user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE clientes SET nome=?,telefone=?,email=?,cep=?,rua=?,numero=?,"
            "bairro=?,cidade=?,estado=? WHERE id=?",
            (cliente.nome, cliente.telefone, cliente.email, cliente.cep,
             cliente.rua, cliente.numero, cliente.bairro, cliente.cidade,
             cliente.estado, cliente_id)
        )
        conn.commit()
    return {"ok": True}


# ─── ORÇAMENTOS / OS ──────────────────────────────────────────────────────────
@app.get("/api/orcamentos", tags=["Orçamentos"])
async def api_listar_orcamentos(status: Optional[str] = None, user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        if status:
            cur.execute(
                "SELECT id,cliente,equipamento,defeito,valor_total,sinal,saldo,status,data "
                "FROM orcamentos_aguardo WHERE status=? ORDER BY id DESC",
                (status,)
            )
        else:
            cur.execute(
                "SELECT id,cliente,equipamento,defeito,valor_total,sinal,saldo,status,data "
                "FROM orcamentos_aguardo ORDER BY id DESC"
            )
        rows = cur.fetchall()
    keys = ["id","cliente","equipamento","defeito","valor_total","sinal","saldo","status","data"]
    return [dict(zip(keys, r)) for r in rows]


@app.get("/api/orcamentos/{orcamento_id}", tags=["Orçamentos"])
async def api_get_orcamento(orcamento_id: int, user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM orcamentos_aguardo WHERE id=?", (orcamento_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado.")
    keys = ["id","cliente","equipamento","defeito","valor_total","sinal","saldo",
            "status","data","itens_detalhes","dados_adicionais"]
    return dict(zip(keys, row))


@app.put("/api/orcamentos/{orcamento_id}/status", tags=["Orçamentos"])
async def api_atualizar_status(orcamento_id: int, body: OrcamentoStatusIn, user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE orcamentos_aguardo SET status=? WHERE id=?",
            (body.status, orcamento_id)
        )
        conn.commit()
    return {"ok": True}


# ─── FINANCEIRO ───────────────────────────────────────────────────────────────
@app.get("/api/financeiro", tags=["Financeiro"])
async def api_listar_financeiro(
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    user=Depends(get_user)
):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id,data,descricao,tipo,valor,categoria,metodo_pagamento "
            "FROM fluxo_caixa ORDER BY id DESC LIMIT 500"
        )
        rows = cur.fetchall()
    keys = ["id","data","descricao","tipo","valor","categoria","metodo_pagamento"]
    return [dict(zip(keys, r)) for r in rows]


@app.get("/api/financeiro/saldo", tags=["Financeiro"])
async def api_saldo(user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(SUM(CASE WHEN tipo='ENTRADA' THEN valor ELSE -valor END),0) "
            "FROM fluxo_caixa"
        )
        saldo = cur.fetchone()[0]
        cur.execute(
            "SELECT COALESCE(SUM(saldo),0) FROM orcamentos_aguardo "
            "WHERE status NOT IN ('FINALIZADO','CANCELADO','REPROVADO')"
        )
        a_receber = cur.fetchone()[0]
    return {"saldo": round(float(saldo or 0), 2), "a_receber": round(float(a_receber or 0), 2)}


@app.post("/api/financeiro", status_code=201, tags=["Financeiro"])
async def api_lancar(lancamento: LancamentoIn, user=Depends(get_user)):
    data = lancamento.data or datetime.now().strftime("%d/%m/%Y")
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO fluxo_caixa (data,descricao,tipo,valor,categoria,metodo_pagamento) "
            "VALUES (?,?,?,?,?,?)",
            (data, lancamento.descricao, lancamento.tipo.upper(), lancamento.valor,
             lancamento.categoria, lancamento.metodo_pagamento)
        )
        conn.commit()
        return {"id": cur.lastrowid}


# ─── PRODUTOS ─────────────────────────────────────────────────────────────────
@app.get("/api/produtos", tags=["Produtos"])
async def api_listar_produtos(user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id,nome,preco_custo,preco_venda,estoque FROM produtos ORDER BY nome")
        rows = cur.fetchall()
    keys = ["id","nome","preco_custo","preco_venda","estoque"]
    return [dict(zip(keys, r)) for r in rows]


@app.post("/api/produtos", status_code=201, tags=["Produtos"])
async def api_criar_produto(produto: ProdutoIn, user=Depends(get_admin)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO produtos (nome,preco_custo,preco_venda,estoque) VALUES (?,?,?,?)",
            (produto.nome, produto.preco_custo, produto.preco_venda, produto.estoque)
        )
        conn.commit()
        return {"id": cur.lastrowid}


# ─── DADOS DA OFICINA ──────────────────────────────────────────────────────────
@app.get("/api/dados-oficina", tags=["Sistema"])
async def api_dados_oficina(user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT nome_oficina,endereco_oficina,telefone_oficina,chave_pix "
            "FROM dados_oficina WHERE id=1"
        )
        row = cur.fetchone()
    if not row:
        return {}
    return {"nome": row[0], "endereco": row[1], "telefone": row[2], "pix": row[3]}


# ─── DASHBOARD STATS ──────────────────────────────────────────────────────────
@app.get("/api/dashboard", tags=["Sistema"])
async def api_dashboard(user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM clientes")
        total_clientes = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM orcamentos_aguardo WHERE status='AGUARDANDO'")
        os_aguardando = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM orcamentos_aguardo WHERE status='EM ANDAMENTO'")
        os_andamento = cur.fetchone()[0]
        cur.execute(
            "SELECT COALESCE(SUM(CASE WHEN tipo='ENTRADA' THEN valor ELSE -valor END),0) "
            "FROM fluxo_caixa"
        )
        saldo = float(cur.fetchone()[0] or 0)
        cur.execute("SELECT COUNT(*) FROM orcamentos_aguardo WHERE status='FINALIZADO'")
        os_finalizadas = cur.fetchone()[0]
    return {
        "total_clientes": total_clientes,
        "os_aguardando": os_aguardando,
        "os_andamento": os_andamento,
        "os_finalizadas": os_finalizadas,
        "saldo": round(saldo, 2),
        "versao": APP_VERSION,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# INTERFACE WEB (mobile / navegador)
# ═══════════════════════════════════════════════════════════════════════════════

def _redir_login():
    return RedirectResponse("/web/login", status_code=302)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root(request: Request):
    if _checar_cookie(request):
        return RedirectResponse("/web/dashboard")
    return RedirectResponse("/web/login")


@app.get("/manifest.webmanifest", include_in_schema=False)
async def pwa_manifest():
    manifest_path = os.path.join(STATIC_DIR, "manifest.webmanifest")
    if os.path.exists(manifest_path):
        return FileResponse(manifest_path, media_type="application/manifest+json")
    raise HTTPException(status_code=404, detail="Manifesto PWA não encontrado.")


@app.get("/sw.js", include_in_schema=False)
async def pwa_service_worker():
    sw_path = os.path.join(STATIC_DIR, "sw.js")
    if os.path.exists(sw_path):
        return FileResponse(sw_path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="Service Worker não encontrado.")


@app.get("/web/login", response_class=HTMLResponse, include_in_schema=False)
async def web_login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "erro": ""})


@app.post("/web/login", response_class=HTMLResponse, include_in_schema=False)
async def web_login_post(
    request: Request,
    usuario: str = Form(...),
    senha: str = Form(...),
):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT senha, role FROM usuarios WHERE UPPER(usuario)=UPPER(?) LIMIT 1",
            (usuario.strip(),)
        )
        row = cur.fetchone()
    if not row or not verify_password(senha, str(row[0] or "")):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "erro": "Usuário ou senha incorretos."}
        )
    role = str(row[1] or "OPERADOR")
    token = _criar_token(usuario.strip(), role)
    response = RedirectResponse("/web/dashboard", status_code=302)
    response.set_cookie(
        "ofp_token", token,
        max_age=JWT_EXPIRE_HORAS * 3600,
        httponly=True,
        samesite="lax"
    )
    return response


@app.get("/web/logout", include_in_schema=False)
async def web_logout():
    resp = RedirectResponse("/web/login", status_code=302)
    resp.delete_cookie("ofp_token")
    return resp


@app.get("/web/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def web_dashboard(request: Request):
    payload = _checar_cookie(request)
    if not payload:
        return _redir_login()
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM clientes")
        total_clientes = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM orcamentos_aguardo WHERE status='AGUARDANDO'")
        os_abertas = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM orcamentos_aguardo WHERE status='EM ANDAMENTO'")
        os_andamento = cur.fetchone()[0]
        cur.execute(
            "SELECT COALESCE(SUM(CASE WHEN tipo='ENTRADA' THEN valor ELSE -valor END),0) "
            "FROM fluxo_caixa"
        )
        saldo = float(cur.fetchone()[0] or 0)
        cur.execute(
            "SELECT nome_oficina FROM dados_oficina WHERE id=1"
        )
        row_oficina = cur.fetchone()
        nome_oficina = row_oficina[0] if row_oficina else "Oficina de Pesca"
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "usuario": payload.get("sub", ""),
        "role": payload.get("role", ""),
        "nome_oficina": nome_oficina,
        "total_clientes": total_clientes,
        "os_abertas": os_abertas,
        "os_andamento": os_andamento,
        "saldo": f"R$ {saldo:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        "versao": APP_VERSION,
    })


@app.get("/web/clientes", response_class=HTMLResponse, include_in_schema=False)
async def web_clientes(request: Request, busca: str = ""):
    payload = _checar_cookie(request)
    if not payload:
        return _redir_login()
    with get_db_connection() as conn:
        cur = conn.cursor()
        if busca:
            cur.execute(
                "SELECT id,nome,telefone,email,cidade,estado FROM clientes "
                "WHERE nome LIKE ? OR telefone LIKE ? OR cidade LIKE ? ORDER BY nome",
                (f"%{busca}%", f"%{busca}%", f"%{busca}%")
            )
        else:
            cur.execute(
                "SELECT id,nome,telefone,email,cidade,estado FROM clientes ORDER BY nome"
            )
        clientes = cur.fetchall()
    return templates.TemplateResponse("clientes.html", {
        "request": request,
        "clientes": clientes,
        "busca": busca,
        "usuario": payload.get("sub", ""),
        "role": payload.get("role", ""),
    })


@app.get("/web/os", response_class=HTMLResponse, include_in_schema=False)
async def web_os(request: Request, status_filtro: str = ""):
    payload = _checar_cookie(request)
    if not payload:
        return _redir_login()
    with get_db_connection() as conn:
        cur = conn.cursor()
        if status_filtro:
            cur.execute(
                "SELECT id,cliente,equipamento,defeito,valor_total,sinal,saldo,status,data "
                "FROM orcamentos_aguardo WHERE status=? ORDER BY id DESC",
                (status_filtro,)
            )
        else:
            cur.execute(
                "SELECT id,cliente,equipamento,defeito,valor_total,sinal,saldo,status,data "
                "FROM orcamentos_aguardo ORDER BY id DESC LIMIT 200"
            )
        orcamentos = cur.fetchall()
    return templates.TemplateResponse("os.html", {
        "request": request,
        "orcamentos": orcamentos,
        "status_filtro": status_filtro,
        "usuario": payload.get("sub", ""),
        "role": payload.get("role", ""),
    })


@app.get("/web/financeiro", response_class=HTMLResponse, include_in_schema=False)
async def web_financeiro(request: Request):
    payload = _checar_cookie(request)
    if not payload:
        return _redir_login()
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id,data,descricao,tipo,valor,categoria,metodo_pagamento "
            "FROM fluxo_caixa ORDER BY id DESC LIMIT 200"
        )
        lancamentos = cur.fetchall()
        cur.execute(
            "SELECT COALESCE(SUM(CASE WHEN tipo='ENTRADA' THEN valor ELSE -valor END),0) "
            "FROM fluxo_caixa"
        )
        saldo = float(cur.fetchone()[0] or 0)
        cur.execute(
            "SELECT COALESCE(SUM(CASE WHEN tipo='ENTRADA' THEN valor ELSE -valor END),0) "
            "FROM fluxo_caixa WHERE tipo='ENTRADA'"
        )
        total_entradas = float(cur.fetchone()[0] or 0)
        cur.execute(
            "SELECT COALESCE(SUM(valor),0) FROM fluxo_caixa WHERE tipo='SAIDA'"
        )
        total_saidas = float(cur.fetchone()[0] or 0)

    def fmt(v):
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    return templates.TemplateResponse("financeiro.html", {
        "request": request,
        "lancamentos": lancamentos,
        "saldo": fmt(saldo),
        "total_entradas": fmt(total_entradas),
        "total_saidas": fmt(total_saidas),
        "usuario": payload.get("sub", ""),
        "role": payload.get("role", ""),
    })


# ─── STARTUP ──────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    inicializar_banco()
    host = _CFG.get("servidor", "host", fallback="0.0.0.0")
    porta = _CFG.getint("servidor", "porta", fallback=8000)
    logger.info("Servidor Oficina de Pesca v%s iniciado em %s:%s", APP_VERSION, host, porta)


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servidor Oficina de Pesca")
    parser.add_argument(
        "--host", default=_CFG.get("servidor", "host", fallback="0.0.0.0"),
        help="Endereço de escuta (padrão: 0.0.0.0 = todas as interfaces)"
    )
    parser.add_argument(
        "--porta", type=int,
        default=_CFG.getint("servidor", "porta", fallback=8000),
        help="Porta TCP (padrão: 8000)"
    )
    args = parser.parse_args()

    import socket
    try:
        ip_local = socket.gethostbyname(socket.gethostname())
    except Exception:
        ip_local = "SEU_IP"

    print("=" * 60)
    print(f"  🐟  Servidor Oficina de Pesca  v{APP_VERSION}")
    print("=" * 60)
    print(f"  🖥️  Acesso local (este PC):   http://localhost:{args.porta}")
    print(f"  🌐  Acesso na rede (outros):  http://{ip_local}:{args.porta}")
    print(f"  📱  Celular/tablet:            http://{ip_local}:{args.porta}")
    print(f"  📖  Documentação da API:       http://localhost:{args.porta}/api/docs")
    print("=" * 60)
    print("  Pressione Ctrl+C para encerrar.")
    print()

    uvicorn.run(app, host=args.host, port=args.porta, log_level="warning")
