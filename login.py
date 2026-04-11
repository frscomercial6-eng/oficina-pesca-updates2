import customtkinter as ctk
import sqlite3
import threading
import os
import sys
import webbrowser
import json
import configparser
import urllib.request
import urllib.error
import subprocess
from urllib.parse import quote_plus
from tkinter import simpledialog, messagebox
from menu import FrmMenu 
from config import (
    hash_password,
    validate_password,
    verify_password,
    inicializar_banco,
    existe_algum_usuario,
    get_db_connection,
    obter_status_trial,
    obter_status_licenca,
    ativar_licenca,
    get_logger,
    verificar_nova_versao,
    obter_info_nova_versao,
    eh_versao_mais_nova,
    obter_politica_atualizacao,
    executar_atualizacao,
    APP_VERSION,
    VALOR_ATUALIZACAO_NAO_PERMANENTE,
    INTERVALO_DIAS_CHECK_VERSAO,
    URL_CHECK_LICENCAS,
    validar_licenca_remota,
    deve_verificar_atualizacao,
    obter_tipo_licenca,
    obter_chave_licenca_ativa,
    INFINITEPAY_LINK_PAGAMENTO,
    INFINITEPAY_API_CHECKOUT_URL,
    INFINITEPAY_API_TOKEN,
    INFINITEPAY_HANDLE,
    WHATSAPP_ADMIN_DESTINO,
)

logger = get_logger(__name__)
_INFINITEPAY_DEBUG_LOGGED = False
_PAGAMENTO_EXPIRADO_JA_EXIBIDO = False
VALOR_LICENCA_PERMANENTE = 599.90
VALOR_LICENCA_MENSAL = 149.90
VALOR_LICENCA_TRIMESTRAL = 249.90


def _obter_cfg_promo_runtime() -> tuple[bool, str, float, str]:
    """Lê a configuração da promoção de lançamento em tempo real."""
    try:
        base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
        caminhos_cfg = [
            os.path.join(base_dir, "config.cfg"),
            os.path.join(os.getcwd(), "config.cfg"),
            os.path.join(os.path.dirname(base_dir), "config.cfg"),
        ]

        cfg = configparser.ConfigParser()
        for caminho in caminhos_cfg:
            if os.path.exists(caminho):
                cfg.read(caminho, encoding="utf-8")
                break

        ativo = cfg.getboolean("pagamento", "promo_lancamento_ativo", fallback=False)
        nome = cfg.get("pagamento", "promo_lancamento_nome", fallback="PROMO LANÇAMENTO").strip() or "PROMO LANÇAMENTO"
        valor = cfg.getfloat("pagamento", "promo_lancamento_valor", fallback=99.90)
        link = cfg.get("pagamento", "infinitepay_link_promo_lancamento", fallback="").strip()
        return ativo, nome, max(float(valor), 0.0), link
    except Exception as e:
        logger.info("Falha ao ler configuração da promoção de lançamento: %s", e)
        return False, "PROMO LANÇAMENTO", 99.90, ""


def _obter_cfg_pagamento_runtime() -> tuple[str, str, str, str, str, str, str, str]:
    """Relê config.cfg em tempo real para não exigir reinício ao alterar pagamento."""
    try:
        base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
        caminhos_cfg = [
            os.path.join(base_dir, "config.cfg"),
            os.path.join(os.getcwd(), "config.cfg"),
            os.path.join(os.path.dirname(base_dir), "config.cfg"),
        ]

        cfg = configparser.ConfigParser()
        cfg_path_usado = ""
        for caminho in caminhos_cfg:
            if os.path.exists(caminho):
                cfg.read(caminho, encoding="utf-8")
                cfg_path_usado = caminho
                break

        if not cfg_path_usado:
            logger.info("config.cfg não encontrado em runtime nos caminhos esperados de pagamento.")

        link = cfg.get("pagamento", "infinitepay_link", fallback=INFINITEPAY_LINK_PAGAMENTO).strip()
        link_permanente = cfg.get("pagamento", "infinitepay_link_permanente", fallback=link).strip()
        link_mensal = cfg.get("pagamento", "infinitepay_link_mensal", fallback=link).strip()
        link_trimestral = cfg.get("pagamento", "infinitepay_link_trimestral", fallback=link_mensal or link).strip()
        link_atualizacao = cfg.get("pagamento", "infinitepay_link_atualizacao", fallback=link).strip()
        handle = cfg.get("pagamento", "infinitepay_handle", fallback=INFINITEPAY_HANDLE).strip()
        checkout_url = cfg.get("pagamento", "infinitepay_checkout_url", fallback=INFINITEPAY_API_CHECKOUT_URL).strip()
        token = cfg.get("pagamento", "infinitepay_api_token", fallback=INFINITEPAY_API_TOKEN).strip()
        return link, link_permanente, link_mensal, link_trimestral, link_atualizacao, handle, checkout_url, token
    except Exception as e:
        logger.info("Falha ao reler config.cfg em runtime: %s", e)
        return (
            INFINITEPAY_LINK_PAGAMENTO,
            INFINITEPAY_LINK_PAGAMENTO,
            INFINITEPAY_LINK_PAGAMENTO,
            INFINITEPAY_LINK_PAGAMENTO,
            INFINITEPAY_LINK_PAGAMENTO,
            INFINITEPAY_HANDLE,
            INFINITEPAY_API_CHECKOUT_URL,
            INFINITEPAY_API_TOKEN,
        )


def _texto_pagamento_infinitepay(tipo: str, valor_reais: float = 0.0) -> str:
    base = f"Pagamento {tipo} pela InfinitePay.\nVocê pode pagar por PIX ou cartão."
    if valor_reais > 0:
        valor = f"{valor_reais:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        base += f"\n\nValor: R$ {valor}"
    return base


def _obter_numero_whatsapp_admin() -> str:
    numero = "".join(ch for ch in str(WHATSAPP_ADMIN_DESTINO or "") if ch.isdigit())
    if numero and not numero.startswith("55"):
        numero = "55" + numero
    return numero


def _enviar_mensagem_pagamento_whatsapp_admin(tipo_pagamento: str):
    numero_admin = _obter_numero_whatsapp_admin()
    if not numero_admin:
        messagebox.showwarning(
            "WhatsApp",
            "Número do administrador não configurado em config.cfg (app.whatsapp_admin).",
            parent=janela_login,
        )
        return

    usuario = (entry_user.get().strip() if 'entry_user' in globals() else "") or "Cliente"
    texto = (
        f"Olá, sou {usuario}. Acabei de realizar o pagamento ({tipo_pagamento}) no sistema Oficina de Pesca. "
        "Pode verificar e liberar, por favor?"
    )
    link = f"https://wa.me/{numero_admin}?text={quote_plus(texto)}"

    try:
        abriu = bool(webbrowser.open(link, new=2))
        if abriu:
            return
    except Exception as e:
        logger.info("Falha ao abrir WhatsApp com webbrowser: %s", e)

    try:
        if hasattr(os, "startfile"):
            os.startfile(link)  # type: ignore[attr-defined]
            return
    except Exception as e:
        logger.info("Falha ao abrir WhatsApp com os.startfile: %s", e)

    messagebox.showwarning(
        "WhatsApp",
        "Não foi possível abrir o WhatsApp automaticamente.",
        parent=janela_login,
    )


def _oferecer_envio_whatsapp_admin(tipo_pagamento: str):
    enviar = messagebox.askyesno(
        "Avisar Administrador",
        "Deseja enviar agora uma mensagem ao administrador no WhatsApp para confirmar o pagamento?",
        parent=janela_login,
    )
    if enviar:
        _enviar_mensagem_pagamento_whatsapp_admin(tipo_pagamento)


def _obter_link_checkout_por_handle(handle: str = "") -> str:
    handle = str(handle or INFINITEPAY_HANDLE or "").strip().lstrip("@")
    if not handle:
        return ""
    return f"https://checkout.infinitepay.io/{handle}"


def _criar_link_checkout_infinitepay(
    valor_reais: float,
    descricao: str,
    referencia: str = "",
    item_descricao: str = "Atualização",
) -> str:
    """Tenta criar checkout dinâmico na InfinitePay e retorna URL vazia em falha."""
    global _INFINITEPAY_DEBUG_LOGGED
    _link_cfg, _link_perm_cfg, _link_mensal_cfg, _link_tri_cfg, _link_atual_cfg, handle_cfg, checkout_url_cfg, token_cfg = _obter_cfg_pagamento_runtime()

    debug_ativo = not _INFINITEPAY_DEBUG_LOGGED
    if debug_ativo:
        _INFINITEPAY_DEBUG_LOGGED = True

    if not token_cfg:
        if debug_ativo:
            logger.info(
                "InfinitePay debug (primeira tentativa): Token não configurado em config.cfg (pagamento.infinitepay_api_token)."
            )
        return ""

    url = checkout_url_cfg or "https://api.infinitepay.io/invoices/public/checkout/links"
    valor_centavos = max(int(round(float(valor_reais) * 100)), 1)
    item_descricao = str(item_descricao or "Atualização").strip() or "Atualização"

    payload = {
        "handle": handle_cfg or "frsoficinadepesca",
        "items": [
            {
                "quantity": 1,
                "price": valor_centavos,
                "description": item_descricao,
            }
        ],
    }
    if referencia:
        payload["external_reference"] = referencia

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token_cfg}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        },
    )

    token_mascarado = f"***{token_cfg[-4:]}" if len(token_cfg) >= 4 else "***"
    if debug_ativo:
        logger.info(
            "InfinitePay debug (primeira tentativa): POST %s | payload=%s | token=%s",
            url,
            payload,
            token_mascarado,
        )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            bruto = resp.read().decode("utf-8", errors="replace")
            if debug_ativo:
                logger.info(
                    "InfinitePay debug (primeira tentativa): HTTP %s | resposta=%s",
                    getattr(resp, "status", "200"),
                    bruto[:1200],
                )
            data = json.loads(bruto)
    except urllib.error.HTTPError as e:
        try:
            erro_bruto = e.read().decode("utf-8", errors="replace")
        except Exception:
            erro_bruto = str(e)
        if debug_ativo:
            logger.info(
                "InfinitePay debug (primeira tentativa): HTTPError %s | resposta=%s",
                getattr(e, "code", "N/A"),
                erro_bruto[:1200],
            )
        logger.info("Falha ao criar checkout InfinitePay: %s", e)
        return ""
    except Exception as e:
        if debug_ativo:
            logger.info("InfinitePay debug (primeira tentativa): Erro inesperado: %s", e)
        logger.info("Falha ao criar checkout InfinitePay: %s", e)
        return ""

    if isinstance(data, dict):
        for chave in ("checkout_url", "payment_url", "url", "link", "short_url"):
            valor = str(data.get(chave, "")).strip()
            if valor.startswith("http"):
                return valor

        nested = data.get("data")
        if isinstance(nested, dict):
            for chave in ("checkout_url", "payment_url", "url", "link", "short_url"):
                valor = str(nested.get(chave, "")).strip()
                if valor.startswith("http"):
                    return valor
    return ""


def _abrir_link_infinitepay_se_configurado(
    valor_reais: float = 0.0,
    descricao: str = "",
    referencia: str = "",
    item_descricao: str = "Atualização",
    link_forcado: str = "",
):
    link_cfg, link_perm_cfg, link_mensal_cfg, link_tri_cfg, link_atual_cfg, _handle_cfg, _checkout_url_cfg, _token_cfg = _obter_cfg_pagamento_runtime()
    link_pagamento = ""
    if valor_reais > 0:
        link_pagamento = _criar_link_checkout_infinitepay(
            valor_reais,
            descricao or "Atualização de versão",
            referencia,
            item_descricao,
        )

    if not link_pagamento:
        if link_forcado:
            link_pagamento = link_forcado

    if not link_pagamento:
        item_norm = str(item_descricao or "").strip().lower()
        if "permanente" in item_norm:
            link_pagamento = link_perm_cfg or link_cfg
        elif "trimestral" in item_norm:
            link_pagamento = link_tri_cfg or link_mensal_cfg or link_cfg
        elif "mensal" in item_norm and "atualiza" not in item_norm:
            link_pagamento = link_mensal_cfg or link_cfg
        else:
            link_pagamento = link_atual_cfg or link_cfg

    if not link_pagamento:
        messagebox.showwarning(
            "InfinitePay",
            "Não foi possível obter o link de pagamento.\n\n"
            "Preencha no config.cfg:\n"
            "- pagamento.infinitepay_link (link real criado no app InfinitePay)\n"
            "- pagamento.infinitepay_link_permanente\n"
            "- pagamento.infinitepay_link_mensal\n"
            "- pagamento.infinitepay_link_trimestral\n"
            "- pagamento.infinitepay_link_atualizacao\n"
            "ou\n"
            "- pagamento.infinitepay_api_token (para geração automática)",
            parent=janela_login,
        )
        return

    abrir = messagebox.askyesno(
        "InfinitePay",
        "Deseja abrir o link de pagamento da InfinitePay agora?",
        parent=janela_login,
    )
    if not abrir:
        return

    try:
        abriu = bool(webbrowser.open(link_pagamento, new=2))
        if abriu:
            return
    except Exception as e:
        logger.info("Falha ao abrir link com webbrowser: %s", e)

    try:
        if hasattr(os, "startfile"):
            os.startfile(link_pagamento)  # type: ignore[attr-defined]
            return
    except Exception as e:
        logger.info("Falha ao abrir link com os.startfile: %s", e)

    try:
        subprocess.run(["cmd", "/c", "start", "", link_pagamento], check=False)
        return
    except Exception as e:
        logger.info("Falha ao abrir link com cmd start: %s", e)

    try:
        janela_login.clipboard_clear()
        janela_login.clipboard_append(link_pagamento)
    except Exception:
        pass

    messagebox.showwarning(
        "InfinitePay",
        "Não foi possível abrir o link automaticamente.\n\n"
        f"Link: {link_pagamento}\n\n"
        "O link foi copiado para a área de transferência (quando disponível).",
        parent=janela_login,
    )


def abrir_tela_cadastro():
    jan_cad = ctk.CTkToplevel(janela_login)
    jan_cad.geometry("320x360")
    jan_cad.title("Novo Acesso")
    jan_cad.attributes("-topmost", True)
    
    ctk.CTkLabel(jan_cad, text="CADASTRAR", font=("Arial", 18, "bold")).pack(pady=20)
    u_new = ctk.CTkEntry(jan_cad, placeholder_text="Novo Usuário")
    u_new.pack(pady=10)
    s_new = ctk.CTkEntry(jan_cad, placeholder_text="Nova Senha", show="*")
    s_new.pack(pady=10)
    s_confirm = ctk.CTkEntry(jan_cad, placeholder_text="Confirmar Senha", show="*")
    s_confirm.pack(pady=10)
    ctk.CTkLabel(
        jan_cad,
        text="Novos cadastros criados nesta tela entram como OPERADOR.",
        text_color="#95a5a6",
        wraplength=260,
        justify="center"
    ).pack(pady=(0, 10))
    
    def salvar():
        u, s, sc = u_new.get().strip(), s_new.get().strip(), s_confirm.get().strip()
        role = "OPERADOR"
        if u and s and sc:
            if s != sc:
                label_status.configure(text="❌ Senhas não coincidem!", text_color="red")
                return
            valid, mensagem = validate_password(s)
            if not valid:
                label_status.configure(text=f"❌ {mensagem}", text_color="red")
                return
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO usuarios (usuario, senha, role) VALUES (?, ?, ?)", (u, hash_password(s), role))
                    conn.commit()
                jan_cad.destroy()
                label_status.configure(text=f"✅ Usuário {u} criado!", text_color="green")
            except sqlite3.IntegrityError:
                label_status.configure(text="❌ Usuário já existe!", text_color="red")
            except Exception:
                label_status.configure(text="❌ Erro ao criar usuário!", text_color="red")
        else:
            label_status.configure(text="❌ Preencha todos os campos!", text_color="red")

    ctk.CTkButton(jan_cad, text="SALVAR", fg_color="#27ae60", command=salvar).pack(pady=20)


def abrir_tela_primeiro_admin():
    # Evita abrir duplicado se já existe uma janela de criação aberta
    for w in janela_login.winfo_children():
        if isinstance(w, ctk.CTkToplevel) and w.winfo_exists():
            try:
                if w.title() == "Primeiro Acesso":
                    w.focus_force()
                    return
            except Exception:
                pass

    jan_admin = ctk.CTkToplevel(janela_login)
    jan_admin.geometry("360x380")
    jan_admin.title("Primeiro Acesso")
    jan_admin.attributes("-topmost", True)
    jan_admin.grab_set()
    jan_admin.focus_force()

    ctk.CTkLabel(jan_admin, text="CRIAR ADMIN", font=("Arial", 18, "bold")).pack(pady=20)
    ctk.CTkLabel(
        jan_admin,
        text="Nenhum usuário encontrado.\nCrie agora o ADMIN inicial.",
        text_color="#f1c40f",
        justify="center"
    ).pack(pady=(0, 12))

    u_new = ctk.CTkEntry(jan_admin, placeholder_text="Usuário ADMIN")
    u_new.pack(pady=8)
    s_new = ctk.CTkEntry(jan_admin, placeholder_text="Senha", show="*")
    s_new.pack(pady=8)
    s_confirm = ctk.CTkEntry(jan_admin, placeholder_text="Confirmar Senha", show="*")
    s_confirm.pack(pady=8)

    lbl_local = ctk.CTkLabel(jan_admin, text="", text_color="red")
    lbl_local.pack(pady=(8, 0))

    def salvar_admin():
        u = u_new.get().strip()
        s = s_new.get().strip()
        sc = s_confirm.get().strip()

        if not u or not s or not sc:
            lbl_local.configure(text="Preencha todos os campos.")
            return
        if s != sc:
            lbl_local.configure(text="As senhas não coincidem.")
            return

        valid, mensagem = validate_password(s)
        if not valid:
            lbl_local.configure(text=mensagem)
            return

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO usuarios (usuario, senha, role) VALUES (?, ?, 'ADMIN')",
                    (u, hash_password(s))
                )
                conn.commit()
            jan_admin.destroy()
            atualizar_status_trial_tela()
            label_status.configure(text="✅ ADMIN inicial criado. Faça login.", text_color="green")
            atualizar_status_primeiro_acesso()
        except sqlite3.IntegrityError:
            lbl_local.configure(text="Usuário já existe.")
        except Exception as e:
            lbl_local.configure(text=f"Erro ao criar ADMIN: {e}")

    ctk.CTkButton(jan_admin, text="CRIAR ADMIN", fg_color="#27ae60", command=salvar_admin).pack(pady=18)

def verificar_login():
    label_status.configure(text="", text_color="red")

    if not existe_algum_usuario():
        label_status.configure(text="⚠️ Crie o ADMIN inicial para continuar.", text_color="#f1c40f")
        abrir_tela_primeiro_admin()
        return

    u = entry_user.get().strip()
    s = entry_pass.get().strip()

    if not u or not s:
        label_status.configure(text="❌ Informe usuário e senha.", text_color="red")
        return

    lic_ativa, _msg_lic, _cliente_lic, _validade_lic = obter_status_licenca()
    trial_ativo, _, _ = obter_status_trial()
    if not lic_ativa and not trial_ativo:
        label_status.configure(text="❌ Trial expirado. Ative a licenca.", text_color="red")
        janela_login.after(120, _oferecer_pagamento_quando_expirar)
        return
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, usuario, senha, role FROM usuarios WHERE UPPER(usuario)=UPPER(?) LIMIT 1",
                (u,)
            )
            user = cursor.fetchone()

            if user:
                stored_password = user[2]
                if verify_password(s, stored_password):
                    role = user[3] if len(user) > 3 else "OPERADOR"
                    janela_login.destroy()
                    app_menu = FrmMenu(usuario=u, role=role, senha_login=s)
                    app_menu.mainloop()
                    return
    except Exception as e:
        logger.exception("Erro no login: %s", e)

    label_status.configure(text="❌ Usuário ou senha inválidos.", text_color="red")
    try:
        messagebox.showerror("Login", "Usuário ou senha inválidos.", parent=janela_login)
    except Exception:
        pass


def abrir_tela_ativacao():
    chave = simpledialog.askstring("Ativacao", "Informe a chave de ativacao:", parent=janela_login)
    if not chave:
        abrir_pagamento = messagebox.askyesno(
            "Compra permanente",
            _texto_pagamento_infinitepay("da licença permanente"),
            parent=janela_login,
        )
        if abrir_pagamento:
            _abrir_link_infinitepay_se_configurado(
                valor_reais=VALOR_LICENCA_PERMANENTE,
                descricao="Licença permanente Oficina de Pesca",
                referencia="LICENCA_PERMANENTE",
                item_descricao="Permanente",
            )
            _oferecer_envio_whatsapp_admin("Licença permanente")
        return

    ok, msg = ativar_licenca(chave)
    if ok:
        messagebox.showinfo("Licenca", msg, parent=janela_login)
        atualizar_status_trial_tela()
        atualizar_status_primeiro_acesso()
    else:
        messagebox.showerror("Licenca", msg, parent=janela_login)


def abrir_central_pagamentos():
    promo_ativo, promo_nome, promo_valor, _promo_link = _obter_cfg_promo_runtime()

    janela_pag = ctk.CTkToplevel(janela_login)
    janela_pag.title("Central de Pagamentos")
    altura = 390 if promo_ativo else 340
    janela_pag.geometry(f"380x{altura}")
    janela_pag.resizable(False, False)
    janela_pag.attributes("-topmost", True)
    janela_pag.grab_set()
    janela_pag.focus_force()

    ctk.CTkLabel(
        janela_pag,
        text="Escolha o tipo de cobrança",
        font=("Arial", 18, "bold"),
    ).pack(pady=(18, 8))

    ctk.CTkLabel(
        janela_pag,
        text="Os links são gerados pela InfinitePay",
        text_color="#bdc3c7",
    ).pack(pady=(0, 14))

    def cobrar_licenca_mensal():
        janela_pag.destroy()
        _fluxo_pagamento_licenca_mensal()

    def cobrar_licenca_trimestral():
        janela_pag.destroy()
        _fluxo_pagamento_licenca_trimestral()

    def cobrar_licenca_permanente():
        janela_pag.destroy()
        messagebox.showinfo(
            "Pagamento",
            _texto_pagamento_infinitepay("da licença permanente", VALOR_LICENCA_PERMANENTE),
            parent=janela_login,
        )
        _abrir_link_infinitepay_se_configurado(
            valor_reais=VALOR_LICENCA_PERMANENTE,
            descricao="Licença permanente Oficina de Pesca",
            referencia="LICENCA_PERMANENTE",
            item_descricao="Permanente",
        )
        _oferecer_envio_whatsapp_admin("Licença permanente")

    def cobrar_atualizacao():
        janela_pag.destroy()
        _fluxo_pagamento_atualizacao_mensal()

    def cobrar_promo_lancamento():
        janela_pag.destroy()
        _fluxo_pagamento_promo_lancamento()

    if promo_ativo:
        valor_fmt = f"{promo_valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        ctk.CTkButton(
            janela_pag,
            text=f"{promo_nome.upper()} - R$ {valor_fmt}",
            width=300,
            fg_color="#e84393",
            hover_color="#d63074",
            command=cobrar_promo_lancamento,
        ).pack(pady=6)

    ctk.CTkButton(
        janela_pag,
        text="LICENÇA MENSAL - R$ 149,90",
        width=300,
        fg_color="#16a085",
        hover_color="#138d75",
        command=cobrar_licenca_mensal,
    ).pack(pady=6)

    ctk.CTkButton(
        janela_pag,
        text="LICENÇA TRIMESTRAL - R$ 249,90",
        width=300,
        fg_color="#1abc9c",
        hover_color="#17a589",
        command=cobrar_licenca_trimestral,
    ).pack(pady=6)

    ctk.CTkButton(
        janela_pag,
        text="LICENÇA PERMANENTE - R$ 599,90",
        width=300,
        fg_color="#2980b9",
        hover_color="#2471a3",
        command=cobrar_licenca_permanente,
    ).pack(pady=6)

    ctk.CTkButton(
        janela_pag,
        text="ATUALIZAÇÃO - R$ 50,00",
        width=300,
        fg_color="#e67e22",
        hover_color="#ca6f1e",
        command=cobrar_atualizacao,
    ).pack(pady=6)

    ctk.CTkButton(
        janela_pag,
        text="FECHAR",
        width=300,
        fg_color="#7f8c8d",
        hover_color="#707b7c",
        command=janela_pag.destroy,
    ).pack(pady=(10, 0))


def _oferecer_pagamento_quando_expirar():
    global _PAGAMENTO_EXPIRADO_JA_EXIBIDO
    if _PAGAMENTO_EXPIRADO_JA_EXIBIDO:
        return

    _PAGAMENTO_EXPIRADO_JA_EXIBIDO = True
    abrir_central_pagamentos()


def atualizar_status_primeiro_acesso():
    if existe_algum_usuario():
        # Garante campos habilitados caso tenham sido desabilitados antes
        entry_user.configure(state="normal")
        entry_pass.configure(state="normal")
        btn_entrar.configure(state="normal", fg_color="#27ae60", hover_color="#219a52")
        return
    entry_user.configure(state="disabled")
    entry_pass.configure(state="disabled")
    btn_entrar.configure(state="disabled", fg_color="#7f8c8d", hover_color="#7f8c8d")
    label_status.configure(
        text="⚠️ Primeiro acesso: crie o usuário ADMIN inicial.",
        text_color="#f1c40f"
    )
    # Abre automaticamente a tela de criar admin após um pequeno delay
    janela_login.after(600, abrir_tela_primeiro_admin)

# Interface Login
inicializar_banco()
ctk.set_appearance_mode("dark")
janela_login = ctk.CTk()
janela_login.title("Login Oficina")
janela_login.geometry("420x540")
janela_login.resizable(False, False)

# Centralizar
x = (janela_login.winfo_screenwidth() // 2) - 210
y = (janela_login.winfo_screenheight() // 2) - 270
janela_login.geometry(f"420x540+{x}+{y}")

main_frame = ctk.CTkFrame(janela_login, corner_radius=20, fg_color="#252525")
main_frame.pack(expand=True, fill="both", padx=20, pady=20)

ctk.CTkLabel(main_frame, text="🎣 OFICINA DE PESCA", font=("Arial", 28, "bold"), text_color="orange").pack(pady=(30, 8))
ctk.CTkLabel(main_frame, text="Acesse o sistema para gerenciar ordens e finanças.", text_color="#bdc3c7").pack(pady=(0, 25))
ctk.CTkLabel(main_frame, text="Preencha usuário e senha para entrar no sistema.", text_color="#95a5a6").pack(pady=(0, 10))

ctk.CTkLabel(main_frame, text="Usuário de acesso", text_color="#dfe6e9", anchor="w").pack(padx=50, pady=(0, 4), fill="x")
entry_user = ctk.CTkEntry(main_frame, placeholder_text="Usuário", width=320, height=44)
entry_user.pack(pady=(0, 10))

ctk.CTkLabel(main_frame, text="Senha de acesso", text_color="#dfe6e9", anchor="w").pack(padx=50, pady=(0, 4), fill="x")
entry_pass = ctk.CTkEntry(main_frame, placeholder_text="Senha", show="*", width=320, height=44)
entry_pass.pack(pady=(0, 10))

btn_entrar = ctk.CTkButton(main_frame, text="🔐 ENTRAR", command=verificar_login, width=320, height=48, fg_color="#27ae60", hover_color="#2ecc71")
btn_entrar.pack(pady=(20, 15))

btn_ativar = ctk.CTkButton(
    main_frame,
    text="ATIVAR LICENCA",
    command=abrir_tela_ativacao,
    width=320,
    height=40,
    fg_color="#2980b9",
    hover_color="#3498db"
)
btn_ativar.pack(pady=(0, 10))

btn_pagamento = ctk.CTkButton(
    main_frame,
    text="COMPRAR LICENÇA",
    command=abrir_central_pagamentos,
    width=320,
    height=38,
    fg_color="#8e44ad",
    hover_color="#7d3c98"
)
btn_pagamento.pack(pady=(0, 10))

ctk.CTkLabel(main_frame, text="Cadastro de usuários disponível apenas no menu do ADMIN.", text_color="#95a5a6", wraplength=300, justify="center").pack(pady=(0, 10))

label_trial = ctk.CTkLabel(main_frame, text="", text_color="#f1c40f", wraplength=320, justify="center")
label_trial.pack(pady=(0, 6))

label_status = ctk.CTkLabel(main_frame, text="", text_color="red")
label_status.pack(pady=(8, 12))

_url_update_disponivel = ""
_auto_update_liberado = False
_mensagem_politica_update = ""


def _executar_instalacao_update():
    if not _url_update_disponivel:
        messagebox.showwarning("Atualização", "Link de atualização indisponível no momento.", parent=janela_login)
        return

    confirmar = messagebox.askyesno(
        "Atualização",
        "Deseja baixar e instalar a nova versão agora?\n\n"
        "O sistema será fechado para concluir a atualização.",
        parent=janela_login,
    )
    if not confirmar:
        return

    ok, msg = executar_atualizacao(
        _url_update_disponivel,
        app_executavel=sys.executable,
        processo_pid=os.getpid(),
        silenciosa=True,
    )
    if ok:
        messagebox.showinfo("Atualização", msg, parent=janela_login)
        janela_login.destroy()
    else:
        messagebox.showerror("Atualização", msg, parent=janela_login)


def _fluxo_pagamento_atualizacao_mensal():
    prosseguir = messagebox.askyesno(
        "Pagamento da atualização",
        _texto_pagamento_infinitepay("da atualização mensal", VALOR_ATUALIZACAO_NAO_PERMANENTE),
        parent=janela_login,
    )
    if not prosseguir:
        return

    _abrir_link_infinitepay_se_configurado(
        valor_reais=VALOR_ATUALIZACAO_NAO_PERMANENTE,
        descricao="Atualização mensal Oficina de Pesca",
        referencia="ATUALIZACAO_MENSAL",
        item_descricao="Atualização",
    )
    _oferecer_envio_whatsapp_admin("Atualização")

    confirmou = messagebox.askyesno(
        "Confirmação de pagamento",
        "Pagamento realizado?\n\nSe sim, clique em 'Sim' para liberar a atualização agora.",
        parent=janela_login,
    )
    if not confirmou:
        return

    _executar_instalacao_update()


def _fluxo_pagamento_licenca_mensal():
    prosseguir = messagebox.askyesno(
        "Pagamento da licença mensal",
        _texto_pagamento_infinitepay("da licença mensal", VALOR_LICENCA_MENSAL),
        parent=janela_login,
    )
    if not prosseguir:
        return

    _abrir_link_infinitepay_se_configurado(
        valor_reais=VALOR_LICENCA_MENSAL,
        descricao="Licença mensal Oficina de Pesca",
        referencia="LICENCA_MENSAL",
        item_descricao="Mensal",
    )
    _oferecer_envio_whatsapp_admin("Licença mensal")


def _fluxo_pagamento_licenca_trimestral():
    prosseguir = messagebox.askyesno(
        "Pagamento da licença trimestral",
        _texto_pagamento_infinitepay("da licença trimestral", VALOR_LICENCA_TRIMESTRAL)
        + "\n\nInclui atualizações por 90 dias sem custo adicional.",
        parent=janela_login,
    )
    if not prosseguir:
        return

    _abrir_link_infinitepay_se_configurado(
        valor_reais=VALOR_LICENCA_TRIMESTRAL,
        descricao="Licença trimestral Oficina de Pesca",
        referencia="LICENCA_TRIMESTRAL",
        item_descricao="Trimestral",
    )
    _oferecer_envio_whatsapp_admin("Licença trimestral")


def _fluxo_pagamento_promo_lancamento():
    promo_ativo, promo_nome, promo_valor, promo_link = _obter_cfg_promo_runtime()
    if not promo_ativo:
        return

    prosseguir = messagebox.askyesno(
        "Promoção de lançamento",
        _texto_pagamento_infinitepay(f"da promoção {promo_nome}", promo_valor),
        parent=janela_login,
    )
    if not prosseguir:
        return

    _abrir_link_infinitepay_se_configurado(
        valor_reais=promo_valor,
        descricao=f"Promoção de lançamento - {promo_nome}",
        referencia="PROMO_LANCAMENTO",
        item_descricao="Promoção",
        link_forcado=promo_link,
    )
    _oferecer_envio_whatsapp_admin(f"Promoção de lançamento ({promo_nome})")


def atualizar_agora():
    global _url_update_disponivel, _auto_update_liberado, _mensagem_politica_update
    if not _auto_update_liberado:
        _fluxo_pagamento_atualizacao_mensal()
        return

    _executar_instalacao_update()


btn_atualizar = ctk.CTkButton(
    main_frame,
    text="ATUALIZAR AGORA",
    command=atualizar_agora,
    width=320,
    height=36,
    fg_color="#2ecc71",
    hover_color="#27ae60",
    state="disabled",
)
btn_atualizar.pack(pady=(0, 8))


def atualizar_status_trial_tela():
    global _PAGAMENTO_EXPIRADO_JA_EXIBIDO
    lic_ativa, _msg_lic, cliente_lic, validade_lic = obter_status_licenca()
    if lic_ativa:
        _PAGAMENTO_EXPIRADO_JA_EXIBIDO = False
        texto_validade = "PERMANENTE" if str(validade_lic).upper() == "PERMANENTE" else str(validade_lic)
        label_trial.configure(
            text=f"LICENCA ATIVA ({cliente_lic}) - validade: {texto_validade}",
            text_color="#2ecc71"
        )
        entry_user.configure(state="normal")
        entry_pass.configure(state="normal")
        btn_entrar.configure(state="normal", fg_color="#27ae60", hover_color="#2ecc71")
        btn_ativar.configure(
            state="disabled",
            text="LICENCA ATIVA",
            width=180,
            height=32,
            fg_color="#1f7a45",
            hover_color="#1f7a45"
        )
        return

    ativo, dias_restantes, data_limite = obter_status_trial()
    if ativo:
        _PAGAMENTO_EXPIRADO_JA_EXIBIDO = False
        label_trial.configure(
            text=f"VERSAO TRIAL: {dias_restantes} dia(s) restante(s). Valido ate {data_limite}.",
            text_color="#f1c40f"
        )
        entry_user.configure(state="normal")
        entry_pass.configure(state="normal")
        btn_entrar.configure(state="normal", fg_color="#27ae60", hover_color="#2ecc71")
        btn_ativar.configure(
            state="normal",
            text="ATIVAR LICENCA",
            width=320,
            height=40,
            fg_color="#2980b9",
            hover_color="#3498db"
        )
        return

    label_trial.configure(
        text=f"TRIAL EXPIRADO em {data_limite}. Contate o suporte para ativacao.",
        text_color="#e74c3c"
    )
    entry_user.configure(state="disabled")
    entry_pass.configure(state="disabled")
    btn_entrar.configure(state="disabled", fg_color="#7f8c8d", hover_color="#7f8c8d")
    btn_ativar.configure(
        state="normal",
        text="ATIVAR LICENCA",
        width=320,
        height=40,
        fg_color="#2980b9",
        hover_color="#3498db"
    )
    label_status.configure(text="❌ Trial expirado. Login bloqueado ate ativacao.", text_color="red")
    janela_login.after(200, _oferecer_pagamento_quando_expirar)


atualizar_status_trial_tela()
atualizar_status_primeiro_acesso()

# ─── Verificação de nova versão (em background, não bloqueia o login) ────────
label_versao = ctk.CTkLabel(
    main_frame,
    text=f"v{APP_VERSION}",
    text_color="#555555",
    font=("Arial", 10),
)
label_versao.pack(pady=(0, 4))

def _checar_versao_bg():
    global _url_update_disponivel, _auto_update_liberado, _mensagem_politica_update
    if not deve_verificar_atualizacao(INTERVALO_DIAS_CHECK_VERSAO):
        return

    info_versao = obter_info_nova_versao()
    versao_nova = str(info_versao.get("versao", "")).strip()
    novidades = str(info_versao.get("novidades", "")).strip()
    url_download = str(info_versao.get("url_download", "")).strip()
    disponivel = bool(versao_nova and eh_versao_mais_nova(versao_nova, APP_VERSION))

    if disponivel:
        lic_ativa, _msg_lic, _cliente_lic, validade_lic = obter_status_licenca()
        tipo_licenca = obter_tipo_licenca()
        chave_ativa = obter_chave_licenca_ativa()

        remoto_ok = True
        msg_remota = ""
        tipo_remoto = ""
        if URL_CHECK_LICENCAS and chave_ativa:
            remoto_ok, msg_remota, tipo_remoto = validar_licenca_remota(URL_CHECK_LICENCAS, chave_ativa)
            if tipo_remoto:
                tipo_licenca = tipo_remoto

        if URL_CHECK_LICENCAS and not remoto_ok:
            auto_update_liberado = False
            msg_politica = f"Licença sem liberação online: {msg_remota}"
        else:
            auto_update_liberado, msg_politica = obter_politica_atualizacao(
                lic_ativa,
                validade_lic,
                tipo_licenca,
            )

        def _mostrar():
            global _url_update_disponivel, _auto_update_liberado, _mensagem_politica_update
            _auto_update_liberado = auto_update_liberado
            _mensagem_politica_update = msg_politica
            tipo_txt = tipo_licenca.title() if tipo_licenca else "Licença"
            if auto_update_liberado:
                texto_update = f"🔔 Nova versão {versao_nova} disponível ({tipo_txt}). {msg_politica}"
                cor = "#2ecc71"
                if url_download:
                    _url_update_disponivel = url_download
                    btn_atualizar.configure(state="normal")
                else:
                    btn_atualizar.configure(state="disabled")
            else:
                texto_update = f"🔔 Nova versão {versao_nova} disponível ({tipo_txt}). {msg_politica}"
                cor = "#f39c12"
                btn_atualizar.configure(
                    text="RENOVAR PARA ATUALIZAR",
                    state="normal",
                    fg_color="#f39c12",
                    hover_color="#d68910",
                )

            if auto_update_liberado:
                btn_atualizar.configure(
                    text="ATUALIZAR AGORA",
                    fg_color="#2ecc71",
                    hover_color="#27ae60",
                )

            if novidades:
                texto_update = f"{texto_update} {novidades}".strip()

            label_versao.configure(
                text=texto_update,
                text_color=cor,
                font=("Arial", 11, "bold"),
            )
            janela_login.geometry("420x570")
        janela_login.after(0, _mostrar)

threading.Thread(target=_checar_versao_bg, daemon=True).start()

janela_login.mainloop()