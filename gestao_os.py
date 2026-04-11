import customtkinter as ctk
import os
from tkinter import messagebox, ttk
from datetime import datetime
from config import CAMINHO_BANCO, inicializar_banco, get_db_connection

from tela_os import FrmOS

caminho_banco = CAMINHO_BANCO

class FrmGestaoOrcamentos(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        inicializar_banco()
        self.title("CONSULTA DE ORÇAMENTOS")
        self.geometry("980x620")
        self.minsize(900, 580)
        self.configure(fg_color="#161b22")
        self.grab_set()
        self.focus_force()

        header = ctk.CTkFrame(self, fg_color="#1f2a38", corner_radius=20)
        header.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkLabel(header, text="📋 CONSULTA DE ORÇAMENTOS", font=("Arial", 22, "bold"), text_color="orange").pack(side="left", padx=20, pady=20)
        ctk.CTkButton(header, text="Atualizar", fg_color="#2980b9", width=120, command=self.buscar_os).pack(side="right", padx=20, pady=20)

        f_busca = ctk.CTkFrame(self, fg_color="#1f2a38", corner_radius=20)
        f_busca.pack(pady=10, padx=20, fill="x")
        self.ent_busca = ctk.CTkEntry(f_busca, placeholder_text="Filtrar por número, cliente, status, equipamento ou defeito", width=300)
        self.ent_busca.pack(side="left", padx=(20, 10), pady=10, fill="x", expand=True)
        ctk.CTkButton(f_busca, text="PESQUISAR", fg_color="#2980b9", width=120, command=self.buscar_os).pack(side="left", padx=(0, 20), pady=10)
        self.ent_busca.bind("<Return>", lambda _e: self.buscar_os())

        # --- BOTÕES DE AÇÃO (movidos para cima) ---
        self.f_botoes = ctk.CTkFrame(self, fg_color="#1f2a38", corner_radius=20)
        self.f_botoes.pack(pady=(0, 6), padx=20, fill="x")
        ctk.CTkButton(
            self.f_botoes, text="🔄 ALTERAR STATUS", fg_color="#7d4e00", hover_color="#a86500",
            width=180, command=self.alterar_status_orcamento
        ).pack(side="left", padx=(20, 10), pady=10)
        ctk.CTkButton(
            self.f_botoes, text="📂 ABRIR O.S.", fg_color="#2980b9", width=140,
            command=self.abrir_orcamento_selecionado
        ).pack(side="left", padx=(0, 10), pady=10)
        self.lbl_info = ctk.CTkLabel(self.f_botoes, text="Selecione um orçamento...", justify="left",
                                     font=("Arial", 12), text_color="#bdc3c7")
        self.lbl_info.pack(side="left", padx=15, pady=10)

        tabela_frame = ctk.CTkFrame(self, fg_color="#1f2a38", corner_radius=20)
        tabela_frame.pack(pady=(0, 10), padx=20, fill="both", expand=True)

        style = ttk.Style()
        style.configure("Treeview", rowheight=28, font=("Arial", 10))
        style.configure("Treeview.Heading", font=("Arial", 10, "bold"))

        self.tab = ttk.Treeview(
            tabela_frame,
            columns=("id", "id_cliente", "equipamento", "defeito", "valor_total", "sinal", "saldo", "status", "data", "descricao"),
            show="headings",
            height=12
        )
        self.tab.heading("id", text="Nº OC")
        self.tab.heading("id_cliente", text="ID / NOME")
        self.tab.heading("equipamento", text="Equipamento")
        self.tab.heading("defeito", text="Defeito")
        self.tab.heading("valor_total", text="ValorTotal")
        self.tab.heading("sinal", text="Sinal")
        self.tab.heading("saldo", text="Saldo")
        self.tab.heading("status", text="Status")
        self.tab.heading("data", text="Data")
        self.tab.heading("descricao", text="PEÇAS / SERVIÇOS")

        self.tab.column("id", width=60, anchor="center")
        self.tab.column("id_cliente", width=150, anchor="w")
        self.tab.column("equipamento", width=140)
        self.tab.column("defeito", width=140)
        self.tab.column("valor_total", width=90, anchor="e")
        self.tab.column("sinal", width=90, anchor="e")
        self.tab.column("saldo", width=90, anchor="e")
        self.tab.column("status", width=110, anchor="center")
        self.tab.column("data", width=95, anchor="center")
        self.tab.column("descricao", width=240)
        self.tab.pack(fill="both", expand=True, padx=15, pady=15)

        self.tab.tag_configure("st_amarelo", background="#3a2e00", foreground="#FFD700")
        self.tab.tag_configure("st_verde", background="#003a10", foreground="#00e676")
        self.tab.tag_configure("st_vermelho", background="#3a0000", foreground="#ff6b6b")
        self.tab.tag_configure("st_padrao", background="#1a2a3a", foreground="#ecf0f1")

        self.tab.bind("<<TreeviewSelect>>", self.selecionar_orcamento)
        self.tab.bind("<Double-1>", self.abrir_orcamento_selecionado)

        self.dados_os = None
        self.buscar_os()

    def _formatar_itens(self, itens_json):
        """Formata o JSON de itens como: M.O / 1x ROLAMENTO"""
        if not itens_json:
            return ""
        try:
            import json
            itens = json.loads(itens_json)
            partes = []
            for it in itens:
                if len(it) >= 2:
                    descricao = str(it[0])
                    qtd = str(it[1])
                    partes.append(f"{qtd}x {descricao}" if qtd != "1" else descricao)
            resultado = " / ".join(partes)
            return resultado[:80] + "..." if len(resultado) > 80 else resultado
        except Exception:
            return ""

    def alterar_status_orcamento(self):
        selecao = self.tab.selection()
        if not selecao:
            messagebox.showwarning("Aviso", "Selecione um orçamento na lista.", parent=self)
            return
        item = self.tab.item(selecao[0], "values")
        num_os = item[0]

        dialogo = ctk.CTkToplevel(self)
        dialogo.title("ALTERAR STATUS")
        dialogo.geometry("320x200")
        dialogo.resizable(False, False)
        dialogo.configure(fg_color="#161b22")
        dialogo.grab_set()
        dialogo.focus_force()

        ctk.CTkLabel(dialogo, text=f"Orçamento Nº {num_os}", font=("Arial", 14, "bold"),
                     text_color="orange").pack(pady=(18, 6))
        ctk.CTkLabel(dialogo, text="Selecione o novo status:", font=("Arial", 12),
                     text_color="#ecf0f1").pack(pady=(0, 12))

        def aplicar(novo_status):
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE orcamentos_aguardo SET status = ? WHERE id = ?", (novo_status, num_os))
                    conn.commit()
                dialogo.destroy()
                self.buscar_os()
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao alterar status: {e}", parent=dialogo)

        f_btns = ctk.CTkFrame(dialogo, fg_color="transparent")
        f_btns.pack()
        ctk.CTkButton(f_btns, text="🟡  EM ANDAMENTO", fg_color="#7d6400", hover_color="#a88700",
                      width=200, command=lambda: aplicar("EM ANDAMENTO")).pack(pady=5)
        ctk.CTkButton(f_btns, text="🟢  FINALIZADO", fg_color="#1a6b30", hover_color="#27ae60",
                      width=200, command=lambda: aplicar("FINALIZADO")).pack(pady=5)

    def buscar_os(self):
        termo = self.ent_busca.get().strip().upper()
        for item in self.tab.get_children():
            self.tab.delete(item)

        self.dados_os = None

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()

                if termo:
                    like_termo = f"%{termo}%"
                    cursor.execute(
                        """
                        SELECT oa.id, COALESCE(c.id, ''), oa.cliente, oa.equipamento, oa.defeito, oa.valor_total,
                               oa.sinal, oa.saldo, oa.status, oa.data, COALESCE(oa.itens_detalhes, '')
                        FROM orcamentos_aguardo oa
                        LEFT JOIN clientes c ON UPPER(c.nome) = UPPER(oa.cliente)
                        WHERE CAST(oa.id AS TEXT) LIKE ?
                           OR UPPER(oa.cliente) LIKE ?
                           OR UPPER(oa.status) LIKE ?
                           OR UPPER(COALESCE(oa.equipamento, '')) LIKE ?
                           OR UPPER(COALESCE(oa.defeito, '')) LIKE ?
                        ORDER BY oa.id DESC
                        """,
                        (like_termo, like_termo, like_termo, like_termo, like_termo)
                    )
                else:
                    cursor.execute(
                        """
                        SELECT oa.id, COALESCE(c.id, ''), oa.cliente, oa.equipamento, oa.defeito, oa.valor_total,
                               oa.sinal, oa.saldo, oa.status, oa.data, COALESCE(oa.itens_detalhes, '')
                        FROM orcamentos_aguardo oa
                        LEFT JOIN clientes c ON UPPER(c.nome) = UPPER(oa.cliente)
                        ORDER BY oa.id DESC
                        """
                    )

                rows = cursor.fetchall()

            for row in rows:
                id_orc, id_cli, nome_cli, equipamento, defeito, total, sinal, saldo, status, data, itens_json = row
                id_nome = f"{id_cli} - {nome_cli}" if id_cli else str(nome_cli or "")
                descricao_fmt = self._formatar_itens(itens_json)
                status_upper = (status or "").upper()
                if status_upper in ("AGUARDANDO", "EM ANDAMENTO"):
                    tag = "st_amarelo"
                elif status_upper in ("FINALIZADO", "APROVADO"):
                    tag = "st_verde"
                elif status_upper == "REPROVADO":
                    tag = "st_vermelho"
                else:
                    tag = "st_padrao"
                self.tab.insert(
                    "",
                    "end",
                    values=(
                        id_orc,
                        id_nome,
                        equipamento or "",
                        defeito or "",
                        f"R$ {float(total or 0):.2f}",
                        f"R$ {float(sinal or 0):.2f}",
                        f"R$ {float(saldo or 0):.2f}",
                        status or "",
                        data or "-",
                        descricao_fmt,
                    ),
                    tags=(tag,)
                )

            if rows:
                self.lbl_info.configure(text=f"{len(rows)} orçamento(s) encontrado(s). Dê dois cliques para abrir.")
            else:
                self.lbl_info.configure(text="Nenhum orçamento encontrado para o filtro informado.")
        except Exception as e:
            self.lbl_info.configure(text=f"Erro ao consultar orçamentos: {e}")

    def selecionar_orcamento(self, event=None):
        selecao = self.tab.selection()
        if not selecao:
            self.dados_os = None
            return

        item = self.tab.item(selecao[0], "values")
        num_os = item[0]

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, cliente, equipamento, defeito, valor_total, sinal, saldo, status, data
                    FROM orcamentos_aguardo
                    WHERE id = ?
                    """,
                    (num_os,)
                )
                self.dados_os = cursor.fetchone()

            if not self.dados_os:
                self.lbl_info.configure(text="Não foi possível carregar os detalhes do orçamento selecionado.")
                return

            status = (self.dados_os[7] or "").upper()
            resumo = (
                f"Nº {self.dados_os[0]}  |  {self.dados_os[1] or ''}  |  "
                f"{self.dados_os[2] or ''}  |  R$ {float(self.dados_os[4] or 0):.2f}  |  {status or '-'}"
            )
            self.lbl_info.configure(text=resumo)
        except Exception as e:
            self.lbl_info.configure(text=f"Erro ao carregar detalhes: {e}")

    def abrir_orcamento_selecionado(self, event=None):
        if event is not None:
            self.selecionar_orcamento()

        if not self.dados_os:
            messagebox.showwarning("Aviso", "Selecione um orçamento na lista.", parent=self)
            return

        try:
            janela = FrmOS(self.master, id_orc=self.dados_os[0])
            janela.focus_force()
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir o orçamento: {e}", parent=self)

    def aprovar_os(self):
        if not self.dados_os:
            messagebox.showwarning("Aviso", "Selecione um orçamento na lista.", parent=self)
            return
        try:
            num_os = self.dados_os[0]
            status_atual = (self.dados_os[7] or "").upper()
            janela = FrmOS(self.master, id_orc=num_os)
            janela.focus_force()
            if status_atual == "APROVADO":
                janela.gerar_documento_pdf("ORDEM DE SERVIÇO")
            else:
                messagebox.showinfo(
                    "Aprovação",
                    f"O orçamento {num_os} foi aberto na tela de O.S.\nA aprovação e o lançamento no financeiro devem ser feitos por lá.",
                    parent=self
                )
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao abrir aprovação: {e}")

    def reprovar_os(self):
        if not self.dados_os:
            messagebox.showwarning("Aviso", "Selecione um orçamento na lista.", parent=self)
            return
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE orcamentos_aguardo SET status = 'REPROVADO' WHERE id = ?", (self.dados_os[0],))
            conn.commit()
        messagebox.showwarning("Aviso", "Orçamento marcado como REPROVADO.")
        self.buscar_os()