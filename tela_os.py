import customtkinter as ctk
import sqlite3
import os
import json
import re
import threading
import webbrowser
import urllib.request
from urllib.parse import quote, quote_plus, urljoin, urlparse, parse_qs, unquote
from tkinter import ttk, filedialog, messagebox, simpledialog
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from datetime import datetime

from config import CAMINHO_BANCO, inicializar_banco, DIRETORIO_RECURSOS, get_db_connection, get_logger

# --- CONFIGURACOES DE CAMINHOS ---
caminho_banco = CAMINHO_BANCO
logger = get_logger(__name__)

class FrmOS(ctk.CTkToplevel):
    def __init__(self, master, id_orc=None):
        super().__init__(master)
        inicializar_banco()
        
        self.title("SISTEMA FRS - OFICINA DE PESCA")
        self.geometry("1000x650")
        self.resizable(True, True)
        
        self.lift()
        self.grab_set() 
        self.focus_force()
        
        self.nome_oficina = "OFICINA DE PESCA"
        self.endereco_oficina = "Av: Regis, nº 378 - Cumbica - Guarulhos - SP"
        self.telefone_oficina = "11 2303-0407"
        self.chave_pix = "ribeirolispe@gmail.com"
        self.logo_oficina = ""
        self.logo_patrocinador = ""
        self.status_documento = "NOVO"
        self.tipo_documento = "ORÇAMENTO"
        self._cliente_em_validacao = False
        self._busca_vista_em_andamento = False
        self.numero_whatsapp_reposicao = "553791910037"
        self.carregar_dados_oficina()
        
        self.num_oc = self.carregar_proximo_numero() if not id_orc else id_orc

        self.check_capa = ctk.StringVar(value="NÃO")
        self.check_linha = ctk.StringVar(value="NÃO")
        self.check_manivela = ctk.StringVar(value="SIM") 
        self.check_caixa = ctk.StringVar(value="NÃO")

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        
        ctk.CTkLabel(self.sidebar, text="MENU FRS", font=("Arial", 16, "bold")).pack(pady=20)

        ctk.CTkButton(self.sidebar, text="🔍 PESQUISAR O.S.", fg_color="#2980b9", command=self.pesquisar_orcamento).pack(pady=10, padx=10, fill="x")
        self.btn_pdf = ctk.CTkButton(self.sidebar, text="📄 GERAR ORÇAMENTO", fg_color="#e67e22", command=self.finalizar_e_abrir_pdf)
        self.btn_pdf.pack(pady=10, padx=10, fill="x")
        self.btn_aprovar = ctk.CTkButton(self.sidebar, text="✅ APROVAR", fg_color="#27ae60", command=self.clicar_aprovado)
        self.btn_aprovar.pack(pady=10, padx=10, fill="x")
        self.btn_reprovar = ctk.CTkButton(self.sidebar, text="❌ REPROVAR", fg_color="#c0392b", command=self.clicar_reprovado)
        self.btn_reprovar.pack(pady=10, padx=10, fill="x")
        ctk.CTkButton(self.sidebar, text="📦 PRODUTOS", fg_color="#2980b9", command=self.abrir_estoque).pack(pady=10, padx=10, fill="x")

        self.main_area = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.main_area.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        self.setup_campos()

        if id_orc:
            self.carregar_dados_orcamento(id_orc)

    def carregar_proximo_numero(self):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'ultimo_orcamento'")
                res = cursor.fetchone()
            return (res[0] + 1) if res else 501
        except Exception as e:
            logger.exception("Erro ao carregar próximo número de orçamento: %s", e)
            return 501

    def _parse_valor(self, valor, default=0.0):
        """Converte valores monetários aceitando vírgula ou ponto."""
        try:
            texto = str(valor).strip().replace("R$", "").replace(" ", "")
            if not texto:
                return float(default)
            return float(texto.replace(",", "."))
        except (TypeError, ValueError):
            return float(default)

    def carregar_dados_oficina(self):
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT nome_oficina, endereco_oficina, telefone_oficina, chave_pix, logo_path, logo_patrocinador_path
                    FROM dados_oficina
                    WHERE id = 1
                    """
                )
                res = cursor.fetchone()
            if res:
                self.nome_oficina = res[0] or self.nome_oficina
                self.endereco_oficina = res[1] or self.endereco_oficina
                self.telefone_oficina = res[2] or self.telefone_oficina
                self.chave_pix = res[3] or self.chave_pix
                self.logo_oficina = res[4] or self.logo_oficina
                self.logo_patrocinador = (res[5] or self.logo_patrocinador) if len(res) > 5 else self.logo_patrocinador
        except Exception as e:
            logger.exception("Erro ao carregar dados da oficina: %s", e)

    def abrir_config_oficina(self):
        janela = ctk.CTkToplevel(self)
        janela.title("DADOS DA OFICINA")
        janela.geometry("560x420")
        janela.resizable(False, False)
        janela.grab_set()
        janela.focus_force()

        ctk.CTkLabel(janela, text="Configurar Layout da Oficina", font=("Arial", 20, "bold"), text_color="orange").pack(pady=(20, 12))

        form = ctk.CTkFrame(janela)
        form.pack(fill="both", expand=True, padx=20, pady=10)

        ent_nome = ctk.CTkEntry(form, placeholder_text="Nome da oficina")
        ent_nome.pack(fill="x", padx=15, pady=(15, 8))
        ent_nome.insert(0, self.nome_oficina)

        ent_endereco = ctk.CTkEntry(form, placeholder_text="Endereço")
        ent_endereco.pack(fill="x", padx=15, pady=8)
        ent_endereco.insert(0, self.endereco_oficina)

        ent_fone = ctk.CTkEntry(form, placeholder_text="Telefone")
        ent_fone.pack(fill="x", padx=15, pady=8)
        ent_fone.insert(0, self.telefone_oficina)

        ent_pix = ctk.CTkEntry(form, placeholder_text="Chave PIX")
        ent_pix.pack(fill="x", padx=15, pady=8)
        ent_pix.insert(0, self.chave_pix)

        logo_var = ctk.StringVar(value=self.logo_oficina)
        f_logo = ctk.CTkFrame(form, fg_color="transparent")
        f_logo.pack(fill="x", padx=15, pady=(8, 4))
        ent_logo = ctk.CTkEntry(f_logo, textvariable=logo_var)
        ent_logo.pack(side="left", fill="x", expand=True)

        def escolher_logo():
            caminho = filedialog.askopenfilename(
                parent=janela,
                title="Selecionar imagem da oficina",
                filetypes=[("Imagens", "*.png;*.jpg;*.jpeg;*.webp")]
            )
            if caminho:
                logo_var.set(caminho)

        ctk.CTkButton(f_logo, text="Imagem", width=90, fg_color="#2980b9", command=escolher_logo).pack(side="left", padx=(8, 0))

        def salvar():
            nome = ent_nome.get().strip()
            endereco = ent_endereco.get().strip()
            telefone = ent_fone.get().strip()
            pix = ent_pix.get().strip()
            logo = logo_var.get().strip()

            if not nome:
                messagebox.showwarning("Atenção", "Informe o nome da oficina.", parent=janela)
                return

            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        UPDATE dados_oficina
                        SET nome_oficina = ?, endereco_oficina = ?, telefone_oficina = ?, chave_pix = ?, logo_path = ?
                        WHERE id = 1
                        """,
                        (nome, endereco, telefone, pix, logo)
                    )
                    conn.commit()

                self.nome_oficina = nome
                self.endereco_oficina = endereco
                self.telefone_oficina = telefone
                self.chave_pix = pix
                self.logo_oficina = logo

                messagebox.showinfo("Sucesso", "Dados da oficina atualizados no layout.", parent=janela)
                janela.destroy()
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível salvar: {e}", parent=janela)

        ctk.CTkButton(form, text="SALVAR DADOS", fg_color="#27ae60", command=salvar).pack(pady=(12, 15))

    def atualizar_identificacao_documento(self, status=None):
        status_normalizado = (status or "").upper()
        self.status_documento = status_normalizado or "NOVO"
        self.tipo_documento = "ORDEM DE SERVIÇO" if self.status_documento == "APROVADO" else "ORÇAMENTO"

        if hasattr(self, "lbl_oc"):
            self.lbl_oc.configure(text=f"{self.tipo_documento} Nº: {self.num_oc}")

        if hasattr(self, "btn_pdf"):
            texto_botao = "📄 GERAR O.S." if self.tipo_documento == "ORDEM DE SERVIÇO" else "📄 GERAR ORÇAMENTO"
            self.btn_pdf.configure(text=texto_botao)

        # Atualizar cores e estado dos botões de aprovação
        STATUS_TRAVADO = ("APROVADO", "REPROVADO", "FINALIZADO", "EM ANDAMENTO")
        if hasattr(self, "btn_aprovar") and hasattr(self, "btn_reprovar"):
            if self.status_documento == "APROVADO":
                self.btn_aprovar.configure(
                    text="✅ APROVADO", fg_color="#1a6b30", hover_color="#1a6b30",
                    state="disabled"
                )
                self.btn_reprovar.configure(
                    text="❌ REPROVAR", fg_color="#555555", hover_color="#555555",
                    state="disabled"
                )
            elif self.status_documento == "REPROVADO":
                self.btn_reprovar.configure(
                    text="❌ REPROVADO", fg_color="#7b1a1a", hover_color="#7b1a1a",
                    state="disabled"
                )
                self.btn_aprovar.configure(
                    text="✅ APROVAR", fg_color="#555555", hover_color="#555555",
                    state="disabled"
                )
            elif self.status_documento in ("FINALIZADO", "EM ANDAMENTO"):
                self.btn_aprovar.configure(
                    text="✅ APROVADO", fg_color="#1a6b30", hover_color="#1a6b30",
                    state="disabled"
                )
                self.btn_reprovar.configure(
                    text="❌ REPROVAR", fg_color="#555555", hover_color="#555555",
                    state="disabled"
                )
            else:
                self.btn_aprovar.configure(
                    text="✅ APROVAR", fg_color="#27ae60", hover_color="#2ecc71",
                    state="normal"
                )
                self.btn_reprovar.configure(
                    text="❌ REPROVAR", fg_color="#c0392b", hover_color="#e74c3c",
                    state="normal"
                )

        # Travar/destravar campos conforme status
        travado = self.status_documento in STATUS_TRAVADO
        self.travar_campos(travado)

    def travar_campos(self, travar: bool):
        """Bloqueia ou libera todos os campos de edição do formulário."""
        if not hasattr(self, "_campos_bloqueio"):
            return
        estado = "disabled" if travar else "normal"
        for widget in self._campos_bloqueio:
            try:
                widget.configure(state=estado)
            except Exception:
                pass
        # Checkboxes
        if hasattr(self, "_chk_widgets"):
            for chk in self._chk_widgets:
                try:
                    chk.configure(state=estado)
                except Exception:
                    pass
        # Botão ADD e lupa
        for btn in [getattr(self, "btn_add", None), getattr(self, "btn_lupa", None)]:
            if btn:
                try:
                    btn.configure(state=estado)
                except Exception:
                    pass
        btn_vista = getattr(self, "btn_buscar_vista", None)
        if btn_vista:
            try:
                btn_vista.configure(state=estado)
            except Exception:
                pass

    def coletar_dados_documento(self, status=None):
        total_f = self.atualizar_total()
        status_salvar = (status or self.status_documento or "AGUARDANDO").upper()
        itens_json = json.dumps([self.tab.item(i)['values'] for i in self.tab.get_children()])
        dados_adicionais = json.dumps({
            "opcional": self._parse_valor(self.ent_opcional.get()),
            "frete": self._parse_valor(self.ent_frete.get()),
            "desconto": self._parse_valor(self.ent_desc.get()),
            "prazo": self.txt_prazo.get().strip(),
            "obs": self.txt_obs.get("1.0", "end-1c")
        })
        return {
            "cliente": self.txt_cliente.get().strip().upper(),
            "equipamento": self.txt_equip.get().strip().upper(),
            "defeito": self.txt_defeito.get().strip().upper(),
            "total": total_f,
            "sinal": total_f / 2,
            "saldo": total_f / 2,
            "status": status_salvar,
            "data": datetime.now().strftime("%d/%m/%Y"),
            "itens_json": itens_json,
            "dados_adicionais": dados_adicionais
        }

    def salvar_documento(self, status=None):
        dados = self.coletar_dados_documento(status=status)
        if not dados["cliente"]:
            raise ValueError("Informe o nome do cliente antes de salvar o documento.")

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM orcamentos_aguardo WHERE id=?", (self.num_oc,))
            registro_existente = cursor.fetchone()

            cursor.execute(
                "INSERT OR REPLACE INTO orcamentos_aguardo VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    self.num_oc,
                    dados["cliente"],
                    dados["equipamento"],
                    dados["defeito"],
                    dados["total"],
                    dados["sinal"],
                    dados["saldo"],
                    dados["status"],
                    dados["data"],
                    dados["itens_json"],
                    dados["dados_adicionais"]
                )
            )

            if not registro_existente:
                cursor.execute("UPDATE configuracoes SET valor = valor + 1 WHERE chave='ultimo_orcamento'")

            conn.commit()
        self.atualizar_identificacao_documento(dados["status"])
        return dados

    def gerar_documento_pdf(self, tipo_documento=None):
        tipo = tipo_documento or self.tipo_documento or "ORÇAMENTO"
        prefixo = "ORDEM_SERVICO" if tipo == "ORDEM DE SERVIÇO" else "ORCAMENTO"
        caminho = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile=f"{prefixo}_{self.num_oc}.pdf")
        if not caminho:
            return None

        self.gerar_pdf_fiel(caminho, tipo_documento=tipo)
        os.startfile(caminho)
        return caminho

    def _normalizar_telefone_whatsapp(self, telefone):
        """Normaliza número de cliente: adiciona +55 apenas se parecer brasileiro (10-11 dígitos).
        Números com prefixo internacional diferente são mantidos como estão.
        """
        digitos = re.sub(r"\D", "", str(telefone or ""))
        if not digitos:
            return ""
        # Já tem código de país (começa com 55 e tem 12+ dígitos)
        if digitos.startswith("55") and len(digitos) >= 12:
            return digitos
        # Parece número brasileiro sem DDI (10 = fixo com DDD, 11 = celular com DDD)
        if len(digitos) in (10, 11):
            return f"55{digitos}"
        # Número estrangeiro ou formato desconhecido — usa como está
        return digitos

    def _normalizar_telefone_fornecedor(self, telefone):
        """Normaliza número de fornecedor: sempre força prefixo Brasil (+55).
        Fornecedores são todos nacionais.
        """
        digitos = re.sub(r"\D", "", str(telefone or ""))
        if not digitos:
            return ""
        # Já tem +55
        if digitos.startswith("55") and len(digitos) >= 12:
            return digitos
        # Garante +55 independente do tamanho
        return f"55{digitos}"

    def _oferecer_envio_whatsapp(self, caminho_pdf, tipo_documento=None):
        tipo = tipo_documento or self.tipo_documento or "ORÇAMENTO"
        if tipo != "ORÇAMENTO":
            return

        if not messagebox.askyesno(
            "WhatsApp",
            "PDF gerado com sucesso. Deseja abrir o WhatsApp para enviar ao cliente?",
            parent=self,
        ):
            return

        cliente = self.txt_cliente.get().strip().upper() or "CLIENTE"
        telefone = self._normalizar_telefone_whatsapp(self.txt_fone.get())
        nome_pdf = os.path.basename(caminho_pdf)
        prazo = self.txt_prazo.get().strip() or "A combinar"
        valor_total = self.atualizar_total()

        msg = (
            f"Olá, Pescador {cliente}! Tudo bem?\n\n"
            f"Seu orçamento nº {self.num_oc} já está pronto.\n"
            f"Valor total: R$ {valor_total:.2f}\n"
            f"Prazo estimado: {prazo}\n"
            f"Arquivo PDF: {nome_pdf}\n\n"
            f"{self.nome_oficina}\n"
            f"Contato: {self.telefone_oficina}\n\n"
            "Já abri o WhatsApp para envio. Basta anexar o PDF e enviar."
        )
        texto = quote(msg)

        if telefone:
            link = f"https://wa.me/{telefone}?text={texto}"
        else:
            link = f"https://wa.me/?text={texto}"

        try:
            webbrowser.open(link)
        except Exception:
            try:
                self.clipboard_clear()
                self.clipboard_append(link)
            except Exception:
                pass
            messagebox.showinfo(
                "WhatsApp",
                "Não foi possível abrir o WhatsApp automaticamente.\nO link foi copiado para a área de transferência.",
                parent=self,
            )
            return

        copiar_link = messagebox.askyesno(
            "WhatsApp",
            "Deseja copiar o link do WhatsApp também?",
            parent=self,
        )
        if copiar_link:
            try:
                self.clipboard_clear()
                self.clipboard_append(link)
                messagebox.showinfo("WhatsApp", "Link copiado para a área de transferência.", parent=self)
            except Exception:
                pass

    def setup_campos(self):
        self.main_area.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self.main_area, fg_color="#1f2a38", corner_radius=20)
        header.pack(fill="x", padx=10, pady=(0, 3))
        self.lbl_oc = ctk.CTkLabel(header, text=f"ORÇAMENTO Nº: {self.num_oc}", font=("Arial", 24, "bold"), text_color="orange")
        self.lbl_oc.pack(side="left", padx=15, pady=15)
        ctk.CTkLabel(header, text="Preencha cliente, itens e finalize.", font=("Arial", 10), text_color="#bdc3c7").pack(side="left", padx=15)
        self.atualizar_identificacao_documento(self.status_documento)

        f_dados = ctk.CTkFrame(self.main_area, fg_color="#1f2a38", corner_radius=20)
        f_dados.pack(pady=2, padx=10, fill="x")
        f_dados.grid_columnconfigure(0, weight=3)
        f_dados.grid_columnconfigure(1, weight=1)

        self.txt_cliente = ctk.CTkEntry(f_dados, placeholder_text="NOME DO PESCADOR")
        self.txt_cliente.grid(row=0, column=0, padx=(15, 5), pady=(15, 5), sticky="ew")
        self.txt_cliente.bind("<Return>", self.buscar_cliente)
        self.txt_cliente.bind("<FocusOut>", self.buscar_cliente)

        self.btn_lupa = ctk.CTkButton(f_dados, text="🔍", width=50, fg_color="#2980b9", command=self.buscar_cliente)
        self.btn_lupa.grid(row=0, column=1, padx=(0, 15), pady=(15, 5), sticky="e")

        self.txt_fone = ctk.CTkEntry(f_dados, placeholder_text="TELEFONE")
        self.txt_fone.grid(row=0, column=2, padx=(0, 15), pady=(15, 5), sticky="ew")

        self.txt_end_cliente = ctk.CTkEntry(f_dados, placeholder_text="ENDEREÇO COMPLETO")
        self.txt_end_cliente.grid(row=1, column=0, columnspan=3, padx=15, pady=(0, 15), sticky="ew")

        f_equip = ctk.CTkFrame(self.main_area, fg_color="#1f2a38", corner_radius=20)
        f_equip.pack(pady=2, padx=10, fill="x")
        f_equip.grid_columnconfigure(0, weight=2)
        f_equip.grid_columnconfigure(1, weight=1)
        f_equip.grid_columnconfigure(2, weight=3)

        self.txt_equip = ctk.CTkEntry(f_equip, placeholder_text="EQUIPAMENTO (EX: CARRETILHA)")
        self.txt_equip.grid(row=0, column=0, padx=(15, 5), pady=8, sticky="ew")
        self.btn_buscar_vista = ctk.CTkButton(
            f_equip,
            text="🔎 BUSCAR VISTA",
            width=150,
            fg_color="#8e44ad",
            hover_color="#9b59b6",
            command=self.buscar_vista_equipamento,
        )
        self.btn_buscar_vista.grid(row=0, column=1, padx=(0, 5), pady=8, sticky="ew")
        self.txt_defeito = ctk.CTkEntry(f_equip, placeholder_text="DEFEITO RELATADO")
        self.txt_defeito.grid(row=0, column=2, padx=(0, 15), pady=8, sticky="ew")

        f_check = ctk.CTkFrame(self.main_area, fg_color="#1f2a38", corner_radius=20)
        f_check.pack(fill="x", pady=2, padx=10)
        ctk.CTkLabel(f_check, text="ACOMPANHA:", font=("Arial", 12, "bold"), text_color="#ecf0f1").pack(side="left", padx=15, pady=10)
        self._chk_widgets = []
        for text, var in [("CAPA", self.check_capa), ("LINHA", self.check_linha), ("MANIVELA", self.check_manivela), ("CAIXA", self.check_caixa)]:
            chk = ctk.CTkCheckBox(f_check, text=text, variable=var, onvalue="SIM", offvalue="NÃO", text_color="#ecf0f1")
            chk.pack(side="left", padx=6)
            self._chk_widgets.append(chk)

        f_item = ctk.CTkFrame(self.main_area, fg_color="#1f2a38", corner_radius=20)
        f_item.pack(fill="x", pady=3, padx=10)
        self.txt_serv = ctk.CTkEntry(f_item, placeholder_text="DESCRIÇÃO DA PEÇA/SERVIÇO")
        self.txt_serv.grid(row=0, column=0, padx=(15, 5), pady=10, sticky="ew")
        self.txt_serv.bind("<KeyRelease>", self.sugerir_preco)
        self.txt_serv.bind("<Return>", lambda _e: self.add_item())
        self.txt_qtd = ctk.CTkEntry(f_item, width=70)
        self.txt_qtd.insert(0, "1")
        self.txt_qtd.grid(row=0, column=1, padx=3, pady=10)
        self.txt_qtd.bind("<Return>", lambda _e: self.add_item())
        self.txt_val = ctk.CTkEntry(f_item, placeholder_text="R$ UNIT", width=100)
        self.txt_val.grid(row=0, column=2, padx=3, pady=10)
        self.txt_val.bind("<Return>", lambda _e: self.add_item())
        self.btn_add = ctk.CTkButton(f_item, text="ADD", fg_color="#27ae60", width=90, command=self.add_item)
        self.btn_add.grid(row=0, column=3, padx=(5, 15), pady=10)
        self.btn_remover = ctk.CTkButton(f_item, text="REMOVER", fg_color="#c0392b", width=90, command=self.remover_item_selecionado)
        self.btn_remover.grid(row=0, column=4, padx=(0, 15), pady=10)
        f_item.grid_columnconfigure(0, weight=1)

        self.tab = ttk.Treeview(self.main_area, columns=("d","q","u","t"), show="headings", height=6)
        self.tab.heading("d", text="DESCRIÇÃO")
        self.tab.heading("q", text="QTD")
        self.tab.heading("u", text="UNIT")
        self.tab.heading("t", text="TOTAL")
        self.tab.column("d", width=520)
        self.tab.column("q", width=80, anchor="center")
        self.tab.column("u", width=120, anchor="center")
        self.tab.column("t", width=120, anchor="center")
        
        # Estilizar a tabela
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", rowheight=30, font=("Arial", 11))
        style.configure("Treeview.Heading", font=("Arial", 11, "bold"))
        style.configure("evenrow.Treeview", background="#2c3e50")
        style.configure("oddrow.Treeview", background="#34495e")
        
        self.tab.pack(pady=(5, 10), padx=10, fill="both", expand=True)
        self.tab.bind("<Delete>", self.remover_item_selecionado)

        footer_frame = ctk.CTkFrame(self.main_area, fg_color="transparent", corner_radius=20)
        footer_frame.pack(fill="x", pady=3, padx=10)
        footer_frame.grid_columnconfigure((0,1,2,3), weight=1)

        self.ent_opcional = ctk.CTkEntry(footer_frame, placeholder_text="OPCIONAL (R$)", width=120)
        self.ent_opcional.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self.ent_opcional.bind("<KeyRelease>", lambda e: self.atualizar_total())

        self.ent_frete = ctk.CTkEntry(footer_frame, placeholder_text="FRETE (R$)", width=120)
        self.ent_frete.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        self.ent_frete.bind("<KeyRelease>", lambda e: self.atualizar_total())

        self.ent_desc = ctk.CTkEntry(footer_frame, placeholder_text="DESCONTO (R$)", width=120)
        self.ent_desc.grid(row=0, column=2, padx=10, pady=10, sticky="ew")
        self.ent_desc.bind("<KeyRelease>", lambda e: self.atualizar_total())

        self.lbl_total = ctk.CTkLabel(footer_frame, text="TOTAL GERAL: R$ 0.00", font=("Arial", 14, "bold"), text_color="#2ecc71")
        self.lbl_total.grid(row=1, column=0, columnspan=4, padx=10, pady=(0,10), sticky="w")

        self.txt_prazo = ctk.CTkEntry(footer_frame, placeholder_text="PRAZO DE ENTREGA")
        self.txt_prazo.grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")
        self.txt_prazo.insert(0, "7 dias úteis")

        self.txt_obs = ctk.CTkTextbox(footer_frame, height=50, wrap="word")
        self.txt_obs.grid(row=2, column=2, columnspan=2, padx=10, pady=(0, 10), sticky="ew")

        # Lista de todos os campos editáveis para controle de travamento
        self._campos_bloqueio = [
            self.txt_cliente, self.txt_fone, self.txt_end_cliente,
            self.txt_equip, self.txt_defeito,
            self.txt_serv, self.txt_qtd, self.txt_val,
            self.ent_opcional, self.ent_frete, self.ent_desc,
            self.txt_prazo, self.txt_obs,
        ]

    def carregar_dados_orcamento(self, id_orc):
        """Carrega dados do orçamento para a tela O.S."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT cliente, equipamento, defeito, valor_total, sinal, saldo, status, itens_detalhes, dados_adicionais FROM orcamentos_aguardo WHERE id=?", (id_orc,))
                res = cursor.fetchone()
            if res:
                self.num_oc = id_orc
                self.atualizar_identificacao_documento(res[6])
                for item in self.tab.get_children():
                    self.tab.delete(item)
                for campo in [self.ent_opcional, self.ent_frete, self.ent_desc]:
                    campo.delete(0, 'end')
                self.txt_prazo.delete(0, 'end')
                self.txt_prazo.insert(0, '7 dias úteis')
                self.txt_obs.delete('1.0', 'end')
                self.txt_obs.insert('1.0', '')
                self.txt_cliente.delete(0, 'end'); self.txt_cliente.insert(0, res[0])
                self.buscar_cliente(abrir_cadastro=False)
                self.txt_equip.delete(0, 'end'); self.txt_equip.insert(0, res[1])
                self.txt_defeito.delete(0, 'end'); self.txt_defeito.insert(0, res[2])
                # Carregar itens da tabela
                if res[7]:  # itens_detalhes
                    try:
                        conteudo = res[7].strip()
                        if conteudo.startswith('['):
                            itens = json.loads(conteudo)
                            for item in itens:
                                # Garantir que os valores sejam strings para display correto
                                item_str = [str(v) for v in item]
                                self.tab.insert("", "end", values=item_str)
                        else:
                            messagebox.showwarning("Aviso de Dados", "O formato dos itens detalhados para este orçamento está incorreto e não pôde ser carregado.", parent=self)
                    except Exception as e:
                        logger.exception("Erro ao carregar itens detalhados: %s", e)
                        messagebox.showwarning("Aviso de Dados", f"Erro ao carregar itens detalhados: {e}. O formato pode estar incorreto.", parent=self)
                # Carregar dados adicionais
                if res[8]:  # dados_adicionais
                    try:
                        dados = json.loads(res[8])
                        self.ent_opcional.delete(0, 'end'); self.ent_opcional.insert(0, dados.get('opcional', 0))
                        self.ent_frete.delete(0, 'end'); self.ent_frete.insert(0, dados.get('frete', 0))
                        self.ent_desc.delete(0, 'end'); self.ent_desc.insert(0, dados.get('desconto', 0))
                        self.txt_prazo.delete(0, 'end'); self.txt_prazo.insert(0, dados.get('prazo', '7 dias úteis'))
                        self.txt_obs.delete('1.0', 'end'); self.txt_obs.insert('1.0', dados.get('obs', ''))
                    except Exception as e:
                        logger.exception("Erro ao carregar dados adicionais: %s", e)
                self.atualizar_total()
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao carregar orçamento: {e}")

    # --- FUNÇÃO DE SUGESTÃO DE PREÇO (Corrigida) ---
    def sugerir_preco(self, event):
        texto = self.txt_serv.get().strip()
        if len(texto) < 3: return
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                # Busca no banco de dados um produto com nome parecido
                cursor.execute("SELECT preco_venda FROM produtos WHERE nome LIKE ?", (f'%{texto}%',))
                res = cursor.fetchone()
            if res:
                self.txt_val.delete(0, 'end')
                self.txt_val.insert(0, f"{res[0]:.2f}")
        except Exception as e:
            logger.exception("Erro ao sugerir preço: %s", e)

    # --- FUNÇÃO QUE A JANELA DE PRODUTOS CHAMA (Com a janelinha de quantidade) ---
    def adicionar_item_ao_orcamento(self, descricao, valor_unitario):
        # Traz a tela de OS para frente para a janelinha aparecer no lugar certo
        self.lift()
        self.focus_force()
        
        # Abre a janelinha de quantidade que você pediu
        qtd = simpledialog.askinteger("Quantidade", f"Quantos(as) '{descricao}'?", initialvalue=1, parent=self)
        
        if qtd and qtd > 0:
            subtotal = qtd * valor_unitario
            # USANDO 'self.tab' QUE É O NOME DA SUA TABELA
            self.tab.insert("", "end", values=(descricao.upper(), qtd, f"{valor_unitario:.2f}", f"{subtotal:.2f}"))
            self.atualizar_total()
            
    # --- FUNÇÃO DO BOTÃO "ADD" (Para digitar manual) ---
    def add_item(self):
        try:
            d = self.txt_serv.get().upper()
            q = int(self.txt_qtd.get())
            v = self._parse_valor(self.txt_val.get())
            if not d.strip() or q <= 0 or v <= 0:
                raise ValueError("Dados inválidos para item")

            produto_info = self._consultar_produto_por_nome(d)
            if produto_info:
                _, estoque_atual = produto_info
                if int(estoque_atual or 0) <= 0:
                    self._oferecer_whatsapp_sem_estoque(d)

            # Adicionar linha com cor alternada
            row_count = len(self.tab.get_children())
            tag = 'evenrow' if row_count % 2 == 0 else 'oddrow'
            self.tab.insert("", "end", values=(d, q, f"{v:.2f}", f"{q*v:.2f}"), tags=(tag,))
            self.atualizar_total()
            # Limpa os campos e volta o cursor para o nome do serviço
            self.txt_serv.delete(0, 'end')
            self.txt_val.delete(0, 'end')
            self.txt_serv.focus()
        except (ValueError, TypeError):
            messagebox.showwarning("Erro", "Preencha Descrição, Qtd e Valor corretamente!")

    def remover_item_selecionado(self, _event=None):
        selecionado = self.tab.selection()
        if not selecionado:
            return
        if not messagebox.askyesno("Remover item", "Deseja remover o item selecionado?", parent=self):
            return
        for item_id in selecionado:
            self.tab.delete(item_id)
        self.atualizar_total()

    def _consultar_produto_por_nome(self, nome_produto: str):
        nome = str(nome_produto or "").strip().upper()
        if not nome:
            return None
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, estoque FROM produtos WHERE UPPER(nome)=? LIMIT 1",
                    (nome,),
                )
                return cursor.fetchone()
        except Exception:
            return None

    def _oferecer_whatsapp_sem_estoque(self, nome_produto: str):
        enviar = messagebox.askyesno(
            "Produto sem estoque",
            f"{nome_produto} está sem estoque.\n\nDeseja abrir o WhatsApp para solicitar reposição?",
            parent=self,
        )
        if not enviar:
            return

        arquivo_ref = self._buscar_vista_ja_baixada(nome_produto)
        texto = (
            "Olá! Solicitação de reposição de peça.\n"
            f"Produto: {nome_produto}\n"
            f"O.S.: {self.num_oc}\n"
            "Favor confirmar disponibilidade e prazo."
        )
        # Fornecedores são sempre Brasil → força +55
        numero = self._normalizar_telefone_fornecedor(self.numero_whatsapp_reposicao)
        link = f"https://wa.me/{numero}?text={quote(texto)}"

        try:
            webbrowser.open(link)
        except Exception:
            messagebox.showwarning(
                "WhatsApp",
                "Não foi possível abrir o WhatsApp automaticamente.",
                parent=self,
            )
            return

        if arquivo_ref and os.path.exists(arquivo_ref):
            anexar = messagebox.askyesno(
                "Anexar arquivo",
                "Existe PDF/imagem baixado desta peça. Deseja abrir a pasta para anexar no WhatsApp?",
                parent=self,
            )
            if anexar:
                try:
                    os.startfile(os.path.dirname(arquivo_ref))
                except Exception:
                    pass

    # --- FUNÇÃO DE SOMAR TUDO ---
    def atualizar_total(self):
        try:
            soma = sum(self._parse_valor(self.tab.item(i)['values'][3]) for i in self.tab.get_children())
            
            v_opc = self._parse_valor(self.ent_opcional.get())
            v_fre = self._parse_valor(self.ent_frete.get())
            v_desc = self._parse_valor(self.ent_desc.get())
            
            total = (soma + v_opc + v_fre) - v_desc
            self.lbl_total.configure(text=f"TOTAL GERAL: R$ {total:.2f}")
            return total
        except Exception as e:
            logger.exception("Erro ao atualizar total: %s", e)
            return 0

    def _baixar_estoque_aprovacao(self):
        """Baixa estoque dos produtos conforme itens aprovados na O.S."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                for item_id in self.tab.get_children():
                    val = self.tab.item(item_id).get('values', [])
                    if len(val) < 2:
                        continue
                    descricao = str(val[0]).strip().upper()
                    try:
                        qtd = int(float(str(val[1]).replace(",", ".")))
                    except Exception:
                        qtd = 0
                    if not descricao or qtd <= 0:
                        continue

                    cursor.execute(
                        "SELECT id, estoque FROM produtos WHERE UPPER(nome) = ? LIMIT 1",
                        (descricao,)
                    )
                    prod = cursor.fetchone()
                    if not prod:
                        continue

                    id_prod, estoque_atual = prod
                    estoque_atual = int(estoque_atual or 0)
                    novo_estoque = max(0, estoque_atual - qtd)
                    cursor.execute("UPDATE produtos SET estoque = ? WHERE id = ?", (novo_estoque, id_prod))

                conn.commit()
        except Exception:
            logger.exception("Erro ao baixar estoque após aprovação.")

    def _consultar_cliente(self, nome):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT nome, telefone, rua, numero, bairro, cidade, estado FROM clientes WHERE UPPER(nome) = ? LIMIT 1",
                (nome,)
            )
            return cursor.fetchone()

    def _preencher_cliente(self, dados_cliente):
        nome, telefone, rua, numero, bairro, cidade, estado = dados_cliente
        self.txt_cliente.delete(0, 'end')
        self.txt_cliente.insert(0, str(nome or ""))
        self.txt_fone.delete(0, 'end')
        self.txt_fone.insert(0, str(telefone or ""))
        end = f"{rua or ''}, {numero or ''} - {bairro or ''} - {cidade or ''}/{estado or ''}".upper()
        self.txt_end_cliente.delete(0, 'end')
        self.txt_end_cliente.insert(0, end)

    def _abrir_cadastro_cliente(self, nome):
        from clientes import FrmClientes

        def apos_salvar(nome_salvo):
            self.txt_cliente.delete(0, 'end')
            self.txt_cliente.insert(0, nome_salvo)
            self.buscar_cliente(abrir_cadastro=False)

        janela = FrmClientes(self, nome_inicial=nome, ao_salvar=apos_salvar)
        janela.focus_force()

    def buscar_cliente(self, event=None, abrir_cadastro=True):
        nome = self.txt_cliente.get().strip().upper()
        if not nome or self._cliente_em_validacao:
            return
        try:
            self._cliente_em_validacao = True
            res = self._consultar_cliente(nome)
            if res:
                self._preencher_cliente(res)
            else:
                self.txt_fone.delete(0, 'end')
                self.txt_end_cliente.delete(0, 'end')
                if abrir_cadastro and messagebox.askyesno("Cliente não cadastrado", f"{nome} não está cadastrado. Deseja abrir o cadastro agora?", parent=self):
                    self._abrir_cadastro_cliente(nome)
        except Exception as e:
            messagebox.showerror("Erro", f"Erro: {e}", parent=self)
        finally:
            self._cliente_em_validacao = False

    def _extrair_links_html(self, html: str, base_url: str) -> list[str]:
        links = []
        padrao = re.compile(r'(?:href|src)=["\']([^"\']+)["\']', re.IGNORECASE)
        for raw in padrao.findall(html or ""):
            link = (raw or "").strip()
            if not link:
                continue
            if link.startswith("//"):
                link = "https:" + link
            elif link.startswith("/"):
                link = urljoin(base_url, link)
            if not link.lower().startswith(("http://", "https://")):
                continue
            links.append(link)
        return links

    def _normalizar_link_resultado(self, link: str) -> str:
        link = (link or "").strip()
        if not link:
            return ""
        parsed = urlparse(link)
        if "duckduckgo.com" in parsed.netloc.lower() and parsed.path.startswith("/l/"):
            uddg = parse_qs(parsed.query).get("uddg", [""])[0]
            if uddg:
                return unquote(uddg)
        return link

    def _pontuar_link_vista(self, link: str, equipamento: str, dom_prioritarios: tuple[str, ...]) -> int:
        texto = (link or "").lower()
        score = 0
        if any(dom in texto for dom in dom_prioritarios):
            score += 50
        if any(ext in texto for ext in (".pdf", ".png", ".jpg", ".jpeg", ".webp")):
            score += 30
        for k in ("manual", "schematic", "schema", "diagrama", "exploded", "vista", "peca", "peças"):
            if k in texto:
                score += 8
        for token in re.findall(r"[a-z0-9]+", equipamento.lower()):
            if len(token) >= 3 and token in texto:
                score += 4
        return score

    def _chave_cache_equipamento(self, equipamento: str) -> str:
        base = (equipamento or "").strip().lower()
        base = re.sub(r"\s+", " ", base)
        return re.sub(r"[^a-z0-9 ]+", "", base).strip()

    def _pasta_download_vistas(self) -> str:
        pasta = os.path.join(os.path.dirname(CAMINHO_BANCO), "downloads_vistas")
        os.makedirs(pasta, exist_ok=True)
        return pasta

    def _caminho_indice_vistas(self) -> str:
        return os.path.join(self._pasta_download_vistas(), "index_vistas.json")

    def _ler_indice_vistas(self) -> dict:
        caminho = self._caminho_indice_vistas()
        if not os.path.exists(caminho):
            return {}
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _gravar_indice_vistas(self, data: dict):
        caminho = self._caminho_indice_vistas()
        try:
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=True, indent=2)
        except Exception:
            pass

    def _registrar_vista_baixada(self, equipamento: str, caminho_arquivo: str):
        chave = self._chave_cache_equipamento(equipamento)
        if not chave:
            return
        data = self._ler_indice_vistas()
        data[chave] = {
            "arquivo": caminho_arquivo,
            "atualizado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._gravar_indice_vistas(data)

    def _buscar_vista_ja_baixada(self, equipamento: str) -> str:
        chave = self._chave_cache_equipamento(equipamento)
        if not chave:
            return ""

        data = self._ler_indice_vistas()
        item = data.get(chave, {}) if isinstance(data, dict) else {}
        caminho = str(item.get("arquivo", "")).strip()
        if caminho and os.path.exists(caminho):
            return caminho

        # Fallback para instalações antigas sem índice
        pasta = self._pasta_download_vistas()
        token = re.sub(r"[^a-z0-9]+", "_", chave)
        candidatos = []
        for nome in os.listdir(pasta):
            nome_low = nome.lower()
            if token and token in re.sub(r"[^a-z0-9]+", "_", nome_low):
                caminho_nome = os.path.join(pasta, nome)
                if os.path.isfile(caminho_nome):
                    candidatos.append(caminho_nome)
        if not candidatos:
            return ""
        candidatos.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return candidatos[0]

    def _baixar_arquivo_vista(self, url_arquivo: str, equipamento: str) -> str:
        pasta = self._pasta_download_vistas()

        parsed = urlparse(url_arquivo)
        nome = os.path.basename(parsed.path) or "vista_equipamento"
        nome = re.sub(r'[^a-zA-Z0-9._-]+', '_', nome)
        if "." not in nome:
            equip = re.sub(r'[^a-zA-Z0-9_-]+', '_', equipamento.lower())
            nome = f"{equip}.pdf"

        destino = os.path.join(pasta, nome)
        req = urllib.request.Request(
            url_arquivo,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp, open(destino, "wb") as f:
            f.write(resp.read())
        self._registrar_vista_baixada(equipamento, destino)
        return destino

    def _buscar_links_sites_prioritarios(self, equipamento: str) -> list[str]:
        buscas = [
            f"https://www.reelschematic.com/?s={quote_plus(equipamento)}",
            f"https://www.reelschematic.com/search/{quote_plus(equipamento)}",
            f"https://marurifishing.com.py/?s={quote_plus(equipamento)}",
            "https://marurifishing.com.py/categoria/manutencao",
            "https://marurifishing.com.py/categoria/pecas-carretilha",
            f"https://www.marinefishing.com.br/?s={quote_plus(equipamento)}",
            "https://www.marinefishing.com.br/manuais",
        ]
        links = []
        for url in buscas:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                links.extend(self._extrair_links_html(html, url))
            except Exception:
                continue
        return links

    def _buscar_links_internet(self, equipamento: str) -> list[str]:
        consulta = (
            f'"{equipamento}" (manual OR schematic OR diagrama OR vista explodida OR peças) '
            "(filetype:pdf OR filetype:png OR filetype:jpg OR filetype:jpeg)"
        )
        url = f"https://duckduckgo.com/html/?q={quote_plus(consulta)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        return [self._normalizar_link_resultado(l) for l in self._extrair_links_html(html, url)]

    def _achar_vista_equipamento(self, equipamento: str) -> tuple[bool, str]:
        dom_prioritarios = ("reelschematic.com", "marurifishing.com.py", "marinefishing.com.br")
        ext_ok = (".pdf", ".png", ".jpg", ".jpeg", ".webp")

        candidatos = []
        candidatos.extend(self._buscar_links_sites_prioritarios(equipamento))
        try:
            candidatos.extend(self._buscar_links_internet(equipamento))
        except Exception:
            pass

        vistos = set()
        unicos = []
        for c in candidatos:
            c = self._normalizar_link_resultado(c)
            if not c or c in vistos:
                continue
            vistos.add(c)
            unicos.append(c)

        ordenados = sorted(
            unicos,
            key=lambda l: self._pontuar_link_vista(l, equipamento, dom_prioritarios),
            reverse=True,
        )

        for link in ordenados[:35]:
            try:
                alvo = link.split("?")[0].lower()
                if alvo.endswith(ext_ok):
                    return True, self._baixar_arquivo_vista(link, equipamento)

                req = urllib.request.Request(link, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    content_type = str(resp.headers.get("Content-Type", "")).lower()
                    dados = resp.read()

                if "pdf" in content_type or "image" in content_type:
                    nome_ext = ".pdf" if "pdf" in content_type else ".jpg"
                    link_download = link if link.split("?")[0].lower().endswith(ext_ok) else f"{link}{nome_ext}"
                    return True, self._baixar_arquivo_vista(link_download, equipamento)

                html = dados.decode("utf-8", errors="ignore")
                for s in self._extrair_links_html(html, link):
                    if s.lower().split("?")[0].endswith(ext_ok):
                        return True, self._baixar_arquivo_vista(s, equipamento)
            except Exception:
                continue

        return False, "Não encontrado."

    def buscar_vista_equipamento(self):
        equipamento = self.txt_equip.get().strip()
        if not equipamento:
            messagebox.showwarning("Atenção", "Informe o equipamento antes de buscar a vista.", parent=self)
            return
        caminho_cache = self._buscar_vista_ja_baixada(equipamento)
        if caminho_cache:
            try:
                os.startfile(caminho_cache)
            except Exception:
                pass
            messagebox.showinfo("Vista encontrada", f"Arquivo já baixado encontrado:\n{caminho_cache}", parent=self)
            return
        if self._busca_vista_em_andamento:
            return

        self._busca_vista_em_andamento = True
        self.btn_buscar_vista.configure(text="BUSCANDO...", state="disabled")

        def worker():
            try:
                ok, resultado = self._achar_vista_equipamento(equipamento)

                def concluir():
                    self._busca_vista_em_andamento = False
                    self.btn_buscar_vista.configure(text="🔎 BUSCAR VISTA", state="normal")
                    if ok:
                        try:
                            os.startfile(resultado)
                        except Exception:
                            pass
                        messagebox.showinfo("Vista encontrada", f"Arquivo baixado em:\n{resultado}", parent=self)
                    else:
                        messagebox.showinfo(
                            "Não encontrado",
                            "Não foi encontrada vista técnica (PDF/imagem) para este equipamento.",
                            parent=self,
                        )

                self.after(0, concluir)
            except Exception as e:
                logger.exception("Erro ao buscar vista de equipamento: %s", e)

                def erro():
                    self._busca_vista_em_andamento = False
                    self.btn_buscar_vista.configure(text="🔎 BUSCAR VISTA", state="normal")
                    messagebox.showwarning("Busca de vista", f"Falha na busca: {e}", parent=self)

                self.after(0, erro)

        threading.Thread(target=worker, daemon=True).start()

    def clicar_aprovado(self):
        try:
            total = self.atualizar_total()
            sinal = total / 2
            cliente = self.txt_cliente.get().strip().upper()
            if not cliente:
                messagebox.showwarning("Atenção", "Informe o nome do cliente antes de aprovar.", parent=self)
                return

            if self.status_documento == "APROVADO":
                if self.gerar_documento_pdf("ORDEM DE SERVIÇO"):
                    messagebox.showinfo("Sucesso", f"Ordem de serviço {self.num_oc} gerada novamente.", parent=self)
                return

            if not messagebox.askyesno("Aprovar", f"Aprovar O.S. {self.num_oc}?\nSinal: R$ {sinal:.2f}", parent=self):
                return

            # --- Diálogo de tipo de pagamento ---
            metodo_selecionado = self._perguntar_tipo_pagamento()
            if not metodo_selecionado:
                return

            caminho_pdf = filedialog.asksaveasfilename(defaultextension=".pdf", initialfile=f"ORDEM_SERVICO_{self.num_oc}.pdf")
            if not caminho_pdf:
                return

            dados = self.salvar_documento(status="APROVADO")
            self._baixar_estoque_aprovacao()
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO fluxo_caixa (data, descricao, tipo, valor, categoria, metodo_pagamento) VALUES (?,?,?,?,?,?)",
                    (datetime.now().strftime("%d/%m/%Y"), f"SINAL O.S. {self.num_oc} - {cliente}", "ENTRADA", dados["sinal"], "ORDEM DE SERVIÇO", metodo_selecionado)
                )
                conn.commit()

            self.gerar_pdf_fiel(caminho_pdf, tipo_documento="ORDEM DE SERVIÇO")
            os.startfile(caminho_pdf)
            self.atualizar_identificacao_documento("APROVADO")
            messagebox.showinfo("Sucesso", f"Ordem de serviço {self.num_oc} aprovada!\nPagamento via {metodo_selecionado} lançado no financeiro.", parent=self)
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def _perguntar_tipo_pagamento(self):
        """Abre diálogo para selecionar tipo de pagamento. Retorna o método ou None se cancelado."""
        dialogo = ctk.CTkToplevel(self)
        dialogo.title("TIPO DE PAGAMENTO")
        dialogo.geometry("300x230")
        dialogo.resizable(False, False)
        dialogo.configure(fg_color="#161b22")
        dialogo.grab_set()
        dialogo.focus_force()
        dialogo.lift()

        ctk.CTkLabel(dialogo, text="Como será o pagamento do SINAL?",
                     font=("Arial", 13, "bold"), text_color="orange",
                     wraplength=260).pack(pady=(18, 12))

        resultado = {"metodo": None}

        def escolher(metodo):
            resultado["metodo"] = metodo
            dialogo.destroy()

        f = ctk.CTkFrame(dialogo, fg_color="transparent")
        f.pack()
        ctk.CTkButton(f, text="💰  DINHEIRO", fg_color="#1a6b30", hover_color="#27ae60",
                      width=200, command=lambda: escolher("DINHEIRO")).pack(pady=5)
        ctk.CTkButton(f, text="📱  PIX", fg_color="#1a4b6b", hover_color="#2980b9",
                      width=200, command=lambda: escolher("PIX")).pack(pady=5)
        ctk.CTkButton(f, text="💳  CARTÃO", fg_color="#4b1a6b", hover_color="#8e44ad",
                      width=200, command=lambda: escolher("CARTÃO")).pack(pady=5)

        dialogo.wait_window()
        return resultado["metodo"]

    def clicar_reprovado(self):
        if messagebox.askyesno("Reprovar", "Marcar como REPROVADO?", parent=self):
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE orcamentos_aguardo SET status='REPROVADO' WHERE id=?", (self.num_oc,))
                conn.commit()
            self.atualizar_identificacao_documento("REPROVADO")
            messagebox.showinfo("FRS", "Orçamento marcado como REPROVADO.", parent=self)

    def pesquisar_orcamento(self):
        num = simpledialog.askinteger("Pesquisa", "Nº Orçamento:", parent=self)
        if not num: return
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM orcamentos_aguardo WHERE id=?", (num,))
                res = cursor.fetchone()
            if res:
                self.carregar_dados_orcamento(num)
                messagebox.showinfo("Busca", f"O.S. {num} carregada!")
            else: messagebox.showerror("Erro", "Não encontrado.")
        except Exception as e: messagebox.showerror("Erro", str(e))

    def abrir_estoque(self):
        try:
            from menu import FrmProdutos
            FrmProdutos(self)
        except Exception as e: messagebox.showerror("Erro", f"Erro: {e}")

    def finalizar_e_abrir_pdf(self):
        cliente = self.txt_cliente.get().strip().upper()
        if not cliente:
            messagebox.showwarning("Atenção", "Informe o nome do cliente antes de gerar o documento.", parent=self)
            return
        try:
            status_salvar = "APROVADO" if self.status_documento == "APROVADO" else "AGUARDANDO"
            self.salvar_documento(status=status_salvar)
            caminho_pdf = self.gerar_documento_pdf(self.tipo_documento)
            if caminho_pdf:
                self._oferecer_envio_whatsapp(caminho_pdf, self.tipo_documento)
                self.destroy()
        except Exception as e:
            messagebox.showerror("Erro", str(e), parent=self)

    def gerar_pdf_fiel(self, caminho, tipo_documento=None):
        c = canvas.Canvas(caminho, pagesize=A4)
        largura, altura = A4
        data_atual = datetime.now().strftime("%d/%m/%Y")
        tipo = tipo_documento or self.tipo_documento or "ORÇAMENTO"
        eh_os = tipo == "ORDEM DE SERVIÇO"
        cor_banner = (0.15, 0.55, 0.32) if eh_os else (0.90, 0.48, 0.13)
        titulo_secundario = "DOCUMENTO DE ENTRADA E EXECUÇÃO" if eh_os else "PROPOSTA COMERCIAL PARA APROVAÇÃO"

        # --- IMAGENS NO TOPO (configuráveis) ---
        try:
            logo_path = self.logo_oficina if os.path.isabs(self.logo_oficina) else os.path.join(DIRETORIO_RECURSOS, self.logo_oficina)
            patr_path = self.logo_patrocinador if os.path.isabs(self.logo_patrocinador) else os.path.join(DIRETORIO_RECURSOS, self.logo_patrocinador)
            if self.logo_oficina and os.path.exists(logo_path):
                c.drawImage(logo_path, 45, altura - 88, width=145, height=72, preserveAspectRatio=True, mask='auto')
            if self.logo_patrocinador and os.path.exists(patr_path):
                c.drawImage(patr_path, largura - 170, altura - 82, width=120, height=60, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass  # Se a imagem não existir, continua sem ela

        # --- CABEÇALHO ---
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, altura - 102, (self.nome_oficina or "OFICINA").upper())
        c.setFont("Helvetica", 10)
        c.drawString(50, altura - 117, self.telefone_oficina)
        c.drawString(50, altura - 132, self.endereco_oficina.upper())

        c.saveState()
        if eh_os:
            c.setFillColorRGB(0.84, 0.92, 0.87)
        else:
            c.setFillColorRGB(0.98, 0.91, 0.84)
        c.setFont("Helvetica-Bold", 52)
        c.translate(largura / 2, altura / 2)
        c.rotate(35)
        marca = "ORDEM DE SERVIÇO" if eh_os else "ORÇAMENTO"
        c.drawCentredString(0, 0, marca)
        c.restoreState()

        # Número do Documento à Direita
        c.setFillColorRGB(*cor_banner)
        c.setFont("Helvetica-Bold", 14)
        c.drawRightString(largura - 50, altura - 128, tipo)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 24)
        c.drawRightString(largura - 50, altura - 148, str(self.num_oc))
        c.setFont("Helvetica-Oblique", 8.8)
        c.drawRightString(largura - 50, altura - 178, titulo_secundario)
        
        c.setLineWidth(1.2)
        c.setStrokeColorRGB(*cor_banner)
        c.line(50, altura - 166, largura - 50, altura - 166)
        c.setStrokeColorRGB(0, 0, 0)

        # --- DADOS DO CLIENTE E EQUIPAMENTO ---
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, altura - 182, f"DATA: {data_atual}")
        c.drawString(50, altura - 197, f"CLIENTE: {self.txt_cliente.get().upper()}")
        c.drawString(50, altura - 212, f"TELEFONE: {self.txt_fone.get()}")
        c.drawString(50, altura - 227, f"ENDEREÇO: {self.txt_end_cliente.get().upper()}")
        
        c.line(50, altura - 237, largura - 50, altura - 237)
        
        c.drawString(50, altura - 252, f"EQUIPAMENTO: {self.txt_equip.get().upper()}")
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(50, altura - 267, f"DEFEITO RELATADO: {self.txt_defeito.get().upper()}")

        # --- CHECKLIST DE ENTRADA ---
        txt_acompanha = f"ACOMPANHA:  Capa: {self.check_capa.get()}  |  Linha: {self.check_linha.get()}  |  Manivela: {self.check_manivela.get()}  |  Caixa: {self.check_caixa.get()}"
        c.setFont("Helvetica-Bold", 9)
        c.drawString(50, altura - 282, txt_acompanha)
        
        c.setLineWidth(1)
        c.line(50, altura - 292, largura - 50, altura - 292)

        # --- TABELA DE ITENS ---
        y = altura - 312
        c.setFont("Helvetica-Bold", 10)
        c.drawString(55, y, "ITEM")
        c.drawString(90, y, "DESCRIÇÃO DOS SERVIÇOS / PEÇAS")
        c.drawString(350, y, "QTD")
        c.drawString(410, y, "V. UNIT")
        c.drawRightString(largura - 55, y, "V. TOTAL")
        
        y -= 5
        c.line(50, y, largura - 50, y)
        
        y -= 20
        c.setFont("Helvetica", 9)
        soma_itens = 0
        
        for i, item in enumerate(self.tab.get_children(), 1):
            if y < 150:
                c.showPage()
                y = altura - 50
                c.setFont("Helvetica", 9)
            
            val = self.tab.item(item)['values']
            c.drawString(55, y, str(i))
            c.drawString(90, y, str(val[0]))
            c.drawString(350, y, str(val[1]))
            c.drawString(410, y, f"R$ {val[2]}")
            c.drawRightString(largura - 55, y, f"R$ {val[3]}")
            
            soma_itens += self._parse_valor(val[3])
            
            c.setDash(1, 2)
            c.setLineWidth(0.5)
            c.line(50, y - 5, largura - 50, y - 5)
            c.setDash([])
            y -= 20

        # --- RESUMO FINANCEIRO ---
        y_fin = y - 20
        if y_fin < 180:
            c.showPage()
            y_fin = altura - 100

        c.setLineWidth(1)
        c.line(largura - 250, y_fin + 15, largura - 50, y_fin + 15)

        v_opc = self._parse_valor(self.ent_opcional.get())
        v_fre = self._parse_valor(self.ent_frete.get())
        v_desc = self._parse_valor(self.ent_desc.get())
            
        total_geral = (soma_itens + v_opc + v_fre) - v_desc

        c.setFont("Helvetica", 10)
        financeiro = [
            ("SUBTOTAL ITENS:", soma_itens),
            ("OPCIONAL:", v_opc),
            ("FRETE / LOGÍSTICA:", v_fre),
            ("DESCONTO:", v_desc)
        ]

        for label, valor in financeiro:
            c.drawRightString(largura - 150, y_fin, label)
            c.drawRightString(largura - 55, y_fin, f"R$ {valor:.2f}")
            y_fin -= 15

        y_fin -= 5
        c.setFont("Helvetica-Bold", 12)
        c.drawRightString(largura - 150, y_fin, "TOTAL GERAL:")
        c.drawRightString(largura - 55, y_fin, f"R$ {total_geral:.2f}")

        # --- INFORMAÇÕES DE PAGAMENTO ---
        y_pag = y_fin - 40
        c.setFont("Helvetica-Bold", 10)
        if eh_os:
            data_aprovacao = datetime.now().strftime("%d/%m/%Y")
            c.drawString(50, y_pag, "CONDIÇÕES DA ORDEM DE SERVIÇO:")
            c.setFont("Helvetica", 9)
            c.drawString(50, y_pag - 15, f"SINAL RECEBIDO: R$ {total_geral/2:.2f}")
            c.drawString(50, y_pag - 30, f"DATA DA APROVAÇÃO: {data_aprovacao}")
            c.drawString(50, y_pag - 45, f"SALDO PENDENTE NA ENTREGA: R$ {total_geral/2:.2f}")
            c.drawString(50, y_pag - 60, f"CHAVE PIX / RECEBIMENTO: {self.chave_pix}")
            c.drawRightString(largura - 50, y_pag - 15, "PRAZO:")
            c.setFont("Helvetica-Bold", 10)
            c.drawRightString(largura - 50, y_pag - 30, self.txt_prazo.get().strip())
        else:
            obs_texto = self.txt_obs.get("1.0", "end-1c").strip()
            prazo_texto = self.txt_prazo.get().strip()
            # Observação acima das condições
            c.setFont("Helvetica-Bold", 10)
            c.drawString(50, y_pag + 15, "OBSERVAÇÃO:")
            c.setFont("Helvetica", 9)
            c.drawString(50, y_pag, obs_texto)
            # Prazo à direita
            c.drawRightString(largura - 50, y_pag + 15, "PRAZO:")
            c.setFont("Helvetica-Bold", 10)
            c.drawRightString(largura - 50, y_pag, prazo_texto)
            # Condições do orçamento
            y_pag = y_pag - 20
            c.setFont("Helvetica-Bold", 10)
            c.drawString(50, y_pag, "CONDIÇÕES DO ORÇAMENTO:")
            c.setFont("Helvetica", 9)
            c.drawString(50, y_pag - 15, f"ENTRADA (50%): R$ {total_geral/2:.2f}")
            c.drawString(50, y_pag - 30, f"SALDO NA ENTREGA: R$ {total_geral/2:.2f}")
            c.drawString(50, y_pag - 45, f"CHAVE PIX: {self.chave_pix}")
            c.drawString(50, y_pag - 60, "Aceitamos Cartões de Crédito e Débito (taxas por conta do cliente).")

        # --- TERMOS E RODAPÉ ---
        y_termo = y_pag - (95 if eh_os else 80)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(50, y_termo, "TERMO DE GARANTIA E CONDIÇÕES:" if eh_os else "TERMOS GERAIS:")
        c.setFont("Helvetica", 7.5)
        if eh_os:
            termos = [
                "1. GARANTIA: 90 dias conforme Art. 26 do CDC para serviços e peças substituídas.",
                "2. MAU USO: A garantia não cobre danos por quedas, humidade ou abertura por terceiros.",
                "3. ABANDONO: Equipamentos não retirados em 90 dias serão vendidos para custear despesas.",
                "4. PAGAMENTO: Aceitamos Cartões de Crédito/Débito (Taxas da operadora por conta do cliente)."
            ]
        else:
            termos = [
                "1. VALIDADE: Este orçamento pode ser revisto caso haja alteração de peças ou serviços necessários.",
                "2. APROVAÇÃO: A execução do serviço começa após confirmação do cliente.",
                "3. ABANDONO: Equipamentos não retirados em 90 dias serão vendidos para custear despesas.",
                "4. GARANTIA: 90 dias conforme Art. 26 do CDC após aprovação e execução do serviço.",
            ]
        for linha in termos:
            y_termo -= 10
            c.drawString(50, y_termo, linha)

        y_ass = max(78, y_termo - 42)
        c.setLineWidth(1)
        c.line(70, y_ass, 240, y_ass)
        c.line(largura - 240, y_ass, largura - 70, y_ass)
        c.setFont("Helvetica", 8)
        c.drawCentredString(155, y_ass - 12, "ASSINATURA DO CLIENTE")
        c.drawCentredString(largura - 155, y_ass - 12, "ASSINATURA DA OFICINA")

        c.setFont("Helvetica-BoldOblique", 8)
        rodape = "ORDEM DE SERVIÇO GERADA E AUTORIZADA PARA EXECUÇÃO." if eh_os else "ORÇAMENTO SUJEITO À APROVAÇÃO DO CLIENTE."
        c.drawCentredString(largura/2, 42, rodape)
        c.drawCentredString(largura/2, 30, "OBRIGADO PELA PREFERÊNCIA! A SUA CONFIANÇA É A NOSSA MELHOR ISCA.")
        
        c.save()

if __name__ == "__main__":
    inicializar_banco() # <--- Garante a criação da tabela configuracoes
    app = ctk.CTk()
    app.withdraw()
    FrmOS(app)
    app.mainloop()