import csv
import customtkinter as ctk
import sqlite3
from datetime import datetime
from tkinter import filedialog, messagebox, simpledialog, ttk

from config import CAMINHO_BANCO, inicializar_banco, verify_password, get_db_connection

caminho_banco = CAMINHO_BANCO


class FrmFinanceiro(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        inicializar_banco()
        self.title("FLUXO DE CAIXA - OFICINA DE PESCA")
        self.geometry("1280x740")
        self.minsize(1120, 700)
        self.grab_set()
        self.focus_force()
        self.configure(fg_color="#161b22")

        hoje = datetime.now()
        inicio_mes = hoje.replace(day=1)

        header = ctk.CTkFrame(self, fg_color="#1f2a38", corner_radius=20)
        header.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkLabel(header, text="MOVIMENTACOES DE CAIXA", font=("Arial", 26, "bold"), text_color="orange").pack(side="left", padx=20, pady=20)
        self.lbl_saldo = ctk.CTkLabel(header, text="SALDO GERAL EM CAIXA: R$ 0.00", font=("Arial", 18, "bold"), text_color="#2ecc71")
        self.lbl_saldo.pack(side="right", padx=20, pady=20)

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self.frame_botoes = ctk.CTkFrame(content, fg_color="#1f2a38", corner_radius=20)
        self.frame_botoes.pack(fill="x", pady=(0, 10), padx=10)
        ctk.CTkButton(self.frame_botoes, text="+ LANCAR DESPESA", fg_color="#c0392b", width=170, command=self.lancar_saida).pack(side="left", padx=8, pady=15)
        ctk.CTkButton(self.frame_botoes, text="+ LANCAR RECEITA", fg_color="#27ae60", width=170, command=self.lancar_entrada).pack(side="left", padx=8, pady=15)
        ctk.CTkButton(self.frame_botoes, text="EDITAR", fg_color="#8e44ad", width=130, command=self.editar_lancamento).pack(side="left", padx=8, pady=15)
        ctk.CTkButton(self.frame_botoes, text="ESTORNAR", fg_color="#7f8c8d", width=130, command=self.estornar_lancamento).pack(side="left", padx=8, pady=15)
        ctk.CTkButton(self.frame_botoes, text="EXPORTAR CSV", fg_color="#2980b9", width=160, command=self.exportar_csv).pack(side="left", padx=8, pady=15)
        ctk.CTkButton(self.frame_botoes, text="ATUALIZAR", fg_color="#34495e", width=140, command=self.carregar_dados).pack(side="right", padx=10, pady=15)

        filter_frame = ctk.CTkFrame(content, fg_color="#1f2a38", corner_radius=20)
        filter_frame.pack(fill="x", pady=(0, 10), padx=10)
        ctk.CTkLabel(filter_frame, text="De:", font=("Arial", 12, "bold"), text_color="#ecf0f1").pack(side="left", padx=(20, 8), pady=12)
        self.ent_data_inicio = ctk.CTkEntry(filter_frame, width=110, placeholder_text="01/04/2026")
        self.ent_data_inicio.insert(0, inicio_mes.strftime("%d/%m/%Y"))
        self.ent_data_inicio.pack(side="left", padx=5, pady=12)
        ctk.CTkLabel(filter_frame, text="Ate:", font=("Arial", 12, "bold"), text_color="#ecf0f1").pack(side="left", padx=(10, 8), pady=12)
        self.ent_data_fim = ctk.CTkEntry(filter_frame, width=110, placeholder_text="30/04/2026")
        self.ent_data_fim.insert(0, hoje.strftime("%d/%m/%Y"))
        self.ent_data_fim.pack(side="left", padx=5, pady=12)
        self.ent_busca = ctk.CTkEntry(filter_frame, placeholder_text="Buscar descricao, categoria ou pagamento", width=330)
        self.ent_busca.pack(side="left", padx=12, pady=12)
        ctk.CTkButton(filter_frame, text="Aplicar", fg_color="#2980b9", width=120, command=self.carregar_dados).pack(side="left", padx=6, pady=12)
        ctk.CTkButton(filter_frame, text="Limpar", fg_color="#7f8c8d", width=100, command=self.limpar_filtros).pack(side="left", padx=6, pady=12)

        tabela_card = ctk.CTkFrame(content, fg_color="#1f2a38", corner_radius=20)
        tabela_card.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", rowheight=30, font=("Arial", 11), background="#1f2a38", fieldbackground="#1f2a38", foreground="#ecf0f1")
        style.configure("Treeview.Heading", font=("Arial", 11, "bold"))

        self.tab_caixa = ttk.Treeview(
            tabela_card,
            columns=("id", "data", "desc", "tipo", "valor", "categoria", "metodo"),
            show="headings"
        )
        self.tab_caixa.heading("id", text="ID")
        self.tab_caixa.heading("data", text="DATA")
        self.tab_caixa.heading("desc", text="DESCRICAO")
        self.tab_caixa.heading("tipo", text="TIPO")
        self.tab_caixa.heading("valor", text="VALOR")
        self.tab_caixa.heading("categoria", text="CATEGORIA")
        self.tab_caixa.heading("metodo", text="PAGAMENTO")
        self.tab_caixa.column("id", width=60, anchor="center")
        self.tab_caixa.column("data", width=110, anchor="center")
        self.tab_caixa.column("desc", width=390)
        self.tab_caixa.column("tipo", width=90, anchor="center")
        self.tab_caixa.column("valor", width=120, anchor="e")
        self.tab_caixa.column("categoria", width=190, anchor="center")
        self.tab_caixa.column("metodo", width=150, anchor="center")
        self.tab_caixa.tag_configure("entrada", background="#0d2b18", foreground="#9ef0b2")
        self.tab_caixa.tag_configure("saida", background="#341313", foreground="#ffb3b3")
        self.tab_caixa.pack(fill="both", expand=True, padx=20, pady=20)

        self.frame_resumo = ctk.CTkFrame(content, fg_color="#1f2a38", corner_radius=20)
        self.frame_resumo.pack(fill="x", pady=(0, 10), padx=10)
        self.lbl_entradas = ctk.CTkLabel(self.frame_resumo, text="ENTRADAS FILTRADAS\nR$ 0.00", font=("Arial", 14, "bold"), text_color="#000000", fg_color="#c8f7c5", corner_radius=8, width=240, height=58)
        self.lbl_entradas.pack(side="left", padx=10, pady=15)
        self.lbl_saidas = ctk.CTkLabel(self.frame_resumo, text="SAIDAS FILTRADAS\nR$ 0.00", font=("Arial", 14, "bold"), text_color="#000000", fg_color="#ff9f9a", corner_radius=8, width=240, height=58)
        self.lbl_saidas.pack(side="left", padx=10, pady=15)
        self.lbl_saldo_resumo = ctk.CTkLabel(self.frame_resumo, text="SALDO DO FILTRO\nR$ 0.00", font=("Arial", 14, "bold"), text_color="#000000", fg_color="#b7ef8a", corner_radius=8, width=240, height=58)
        self.lbl_saldo_resumo.pack(side="left", padx=10, pady=15)
        self.lbl_saldo_receber = ctk.CTkLabel(self.frame_resumo, text="SALDO A RECEBER\nR$ 0.00", font=("Arial", 14, "bold"), text_color="#000000", fg_color="#fff36d", corner_radius=8, width=240, height=58)
        self.lbl_saldo_receber.pack(side="left", padx=10, pady=15)

        self.frame_pagamento = ctk.CTkFrame(content, fg_color="#1f2a38", corner_radius=20)
        self.frame_pagamento.pack(fill="x", pady=(0, 10), padx=10)
        ctk.CTkLabel(self.frame_pagamento, text="RECEBIMENTOS NO PERIODO POR PAGAMENTO", font=("Arial", 12, "bold"), text_color="#bdc3c7").pack(anchor="w", padx=15, pady=(8, 0))
        self.lbl_pix = ctk.CTkLabel(self.frame_pagamento, text="PIX\nR$ 0.00", font=("Arial", 13, "bold"), text_color="#000000", fg_color="#a8e6ff", corner_radius=8, width=220, height=56)
        self.lbl_pix.pack(side="left", padx=10, pady=12)
        self.lbl_dinheiro = ctk.CTkLabel(self.frame_pagamento, text="DINHEIRO\nR$ 0.00", font=("Arial", 13, "bold"), text_color="#000000", fg_color="#d2f8c8", corner_radius=8, width=220, height=56)
        self.lbl_dinheiro.pack(side="left", padx=10, pady=12)
        self.lbl_cartao = ctk.CTkLabel(self.frame_pagamento, text="CARTAO\nR$ 0.00", font=("Arial", 13, "bold"), text_color="#000000", fg_color="#f2d5ff", corner_radius=8, width=220, height=56)
        self.lbl_cartao.pack(side="left", padx=10, pady=12)

        self.carregar_dados()

    def _parse_data(self, texto):
        try:
            return datetime.strptime(texto.strip(), "%d/%m/%Y")
        except Exception:
            return None

    def _data_sql(self, coluna):
        return f"date(substr({coluna},7,4)||'-'||substr({coluna},4,2)||'-'||substr({coluna},1,2))"

    def _selecionado(self):
        selecao = self.tab_caixa.selection()
        if not selecao:
            return None
        return self.tab_caixa.item(selecao[0], "values")

    def _eh_lancamento_automatico_os(self, descricao, categoria):
        texto_desc = str(descricao or "").upper()
        texto_cat = str(categoria or "").upper()
        return ("SINAL O.S." in texto_desc) or ("ORDEM DE SERV" in texto_cat)

    def _autenticar_admin(self, acao):
        usuario = simpledialog.askstring("Autorizacao Admin", f"Usuario ADMIN para {acao}:", parent=self)
        if not usuario:
            return False
        senha = simpledialog.askstring("Autorizacao Admin", "Senha ADMIN:", show="*", parent=self)
        if not senha:
            return False
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT senha, role FROM usuarios WHERE UPPER(usuario)=UPPER(?) LIMIT 1", (usuario.strip(),))
                row = cursor.fetchone()
            if not row:
                messagebox.showwarning("Acesso negado", "Usuario ADMIN nao encontrado.", parent=self)
                return False
            senha_hash, role = row
            if str(role or "").upper() != "ADMIN":
                messagebox.showwarning("Acesso negado", "Somente ADMIN pode executar esta acao.", parent=self)
                return False
            if not verify_password(senha, str(senha_hash or "")):
                messagebox.showwarning("Acesso negado", "Senha ADMIN invalida.", parent=self)
                return False
            return True
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao validar ADMIN: {e}", parent=self)
            return False

    def _perguntar_metodo_pagamento(self, titulo="Forma de pagamento", valor_inicial=None):
        dialogo = ctk.CTkToplevel(self)
        dialogo.title(titulo)
        dialogo.geometry("300x250")
        dialogo.resizable(False, False)
        dialogo.configure(fg_color="#161b22")
        dialogo.grab_set()
        dialogo.focus_force()

        ctk.CTkLabel(dialogo, text=titulo, font=("Arial", 13, "bold"), text_color="orange", wraplength=250).pack(pady=(18, 12))
        resultado = {"metodo": valor_inicial}

        def escolher(metodo):
            resultado["metodo"] = metodo
            dialogo.destroy()

        f = ctk.CTkFrame(dialogo, fg_color="transparent")
        f.pack()
        ctk.CTkButton(f, text="DINHEIRO", fg_color="#1a6b30", hover_color="#27ae60", width=200, command=lambda: escolher("DINHEIRO")).pack(pady=5)
        ctk.CTkButton(f, text="PIX", fg_color="#1a4b6b", hover_color="#2980b9", width=200, command=lambda: escolher("PIX")).pack(pady=5)
        ctk.CTkButton(f, text="CARTAO", fg_color="#4b1a6b", hover_color="#8e44ad", width=200, command=lambda: escolher("CARTAO")).pack(pady=5)
        ctk.CTkButton(f, text="CANCELAR", fg_color="#7f8c8d", hover_color="#95a5a6", width=200, command=dialogo.destroy).pack(pady=(12, 0))

        dialogo.wait_window()
        return resultado["metodo"]

    def limpar_filtros(self):
        hoje = datetime.now()
        self.ent_data_inicio.delete(0, "end")
        self.ent_data_inicio.insert(0, hoje.replace(day=1).strftime("%d/%m/%Y"))
        self.ent_data_fim.delete(0, "end")
        self.ent_data_fim.insert(0, hoje.strftime("%d/%m/%Y"))
        self.ent_busca.delete(0, "end")
        self.carregar_dados()

    def lancar_saida(self):
        desc = simpledialog.askstring("Gasto", "Descricao do gasto:", parent=self)
        if not desc:
            return
        valor = simpledialog.askfloat("Gasto", "Valor da saida (R$):", parent=self)
        if valor is None or valor <= 0:
            messagebox.showwarning("Atencao", "Informe um valor valido para a saida.", parent=self)
            return
        categoria = simpledialog.askstring("Gasto", "Categoria da saida:", initialvalue="DESPESA OPERACIONAL", parent=self) or "DESPESA OPERACIONAL"
        metodo = self._perguntar_metodo_pagamento("Como foi paga essa despesa?")
        if not metodo:
            return
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO fluxo_caixa (data, descricao, tipo, valor, categoria, metodo_pagamento) VALUES (?, ?, 'SAIDA', ?, ?, ?)",
                    (datetime.now().strftime("%d/%m/%Y"), desc.upper(), valor, categoria.upper(), metodo)
                )
                conn.commit()
            self.carregar_dados()
            messagebox.showinfo("Sucesso", "Despesa lancada com sucesso.", parent=self)
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar gasto: {e}", parent=self)

    def lancar_entrada(self):
        descricao = simpledialog.askstring("Receita", "Descricao da receita:", parent=self)
        if not descricao:
            return
        valor = simpledialog.askfloat("Receita", "Valor da entrada (R$):", parent=self)
        if valor is None or valor <= 0:
            messagebox.showwarning("Atencao", "Informe um valor valido para a entrada.", parent=self)
            return
        categoria = simpledialog.askstring("Receita", "Categoria da entrada:", initialvalue="RECEITA AVULSA", parent=self) or "RECEITA AVULSA"
        metodo = self._perguntar_metodo_pagamento("Qual a forma de recebimento?")
        if not metodo:
            return
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO fluxo_caixa (data, descricao, tipo, valor, categoria, metodo_pagamento) VALUES (?, ?, 'ENTRADA', ?, ?, ?)",
                    (datetime.now().strftime("%d/%m/%Y"), descricao.upper(), valor, categoria.upper(), metodo)
                )
                conn.commit()
            self.carregar_dados()
            messagebox.showinfo("Sucesso", "Entrada lancada com sucesso.", parent=self)
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar entrada: {e}", parent=self)

    def editar_lancamento(self):
        item = self._selecionado()
        if not item:
            messagebox.showwarning("Atencao", "Selecione um lancamento para editar.", parent=self)
            return

        if not self._autenticar_admin("editar lancamento"):
            return

        id_mov, _data, descricao_atual, _tipo, valor_txt, categoria_atual, metodo_atual = item
        valor_base = float(str(valor_txt).replace("R$", "").strip().replace(",", "."))

        descricao = simpledialog.askstring("Editar", "Descricao:", initialvalue=descricao_atual, parent=self)
        if not descricao:
            return
        valor = simpledialog.askfloat("Editar", "Valor (R$):", initialvalue=valor_base, parent=self)
        if valor is None or valor <= 0:
            messagebox.showwarning("Atencao", "Informe um valor valido.", parent=self)
            return
        categoria = simpledialog.askstring("Editar", "Categoria:", initialvalue=categoria_atual, parent=self) or categoria_atual
        metodo = self._perguntar_metodo_pagamento("Forma de pagamento", valor_inicial=metodo_atual)
        if not metodo:
            return

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE fluxo_caixa SET descricao = ?, valor = ?, categoria = ?, metodo_pagamento = ? WHERE id = ?",
                    (descricao.upper(), valor, categoria.upper(), metodo, id_mov)
                )
                conn.commit()
            self.carregar_dados()
        except Exception as e:
            messagebox.showerror("Erro", f"Nao foi possivel editar: {e}", parent=self)

    def estornar_lancamento(self):
        item = self._selecionado()
        if not item:
            messagebox.showwarning("Atencao", "Selecione um lancamento para estornar.", parent=self)
            return

        if not self._autenticar_admin("estornar lancamento"):
            return

        id_mov, _data, descricao, tipo, valor_txt, categoria, metodo = item
        valor = float(str(valor_txt).replace("R$", "").strip().replace(",", "."))
        tipo_estorno = "SAIDA" if str(tipo).upper() == "ENTRADA" else "ENTRADA"
        descricao_estorno = f"ESTORNO REF. #{id_mov} - {descricao}"[:255]

        if not messagebox.askyesno("Estorno", f"Gerar estorno do lancamento #{id_mov}?", parent=self):
            return

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO fluxo_caixa (data, descricao, tipo, valor, categoria, metodo_pagamento) VALUES (?, ?, ?, ?, ?, ?)",
                    (datetime.now().strftime("%d/%m/%Y"), descricao_estorno.upper(), tipo_estorno, valor, f"ESTORNO {categoria}".upper(), metodo)
                )
                conn.commit()
            self.carregar_dados()
            messagebox.showinfo("Sucesso", "Estorno lancado com sucesso.", parent=self)
        except Exception as e:
            messagebox.showerror("Erro", f"Nao foi possivel estornar: {e}", parent=self)

    def exportar_csv(self):
        if not self.tab_caixa.get_children():
            messagebox.showwarning("Atencao", "Nao ha dados para exportar com o filtro atual.", parent=self)
            return
        caminho = filedialog.asksaveasfilename(
            parent=self,
            title="Exportar financeiro",
            defaultextension=".csv",
            initialfile=f"financeiro_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            filetypes=[("CSV", "*.csv")]
        )
        if not caminho:
            return
        try:
            with open(caminho, "w", newline="", encoding="utf-8-sig") as arquivo:
                writer = csv.writer(arquivo, delimiter=";")
                writer.writerow(["ID", "DATA", "DESCRICAO", "TIPO", "VALOR", "CATEGORIA", "PAGAMENTO"])
                for item_id in self.tab_caixa.get_children():
                    writer.writerow(self.tab_caixa.item(item_id, "values"))
            messagebox.showinfo("Sucesso", "CSV exportado com sucesso.", parent=self)
        except Exception as e:
            messagebox.showerror("Erro", f"Nao foi possivel exportar: {e}", parent=self)

    def carregar_dados(self):
        if not hasattr(self, "tab_caixa") or not self.tab_caixa.winfo_exists():
            return
        for item_id in self.tab_caixa.get_children():
            self.tab_caixa.delete(item_id)

        dt_ini = self._parse_data(self.ent_data_inicio.get())
        dt_fim = self._parse_data(self.ent_data_fim.get())
        if not dt_ini or not dt_fim:
            messagebox.showwarning("Atencao", "Use datas validas no formato dd/mm/aaaa.", parent=self)
            return

        d_ini = dt_ini.strftime("%Y-%m-%d")
        d_fim = dt_fim.strftime("%Y-%m-%d")
        busca = f"%{self.ent_busca.get().strip().upper()}%"

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                data_sql = self._data_sql("data")

                cursor.execute("SELECT COALESCE(SUM(CASE WHEN UPPER(tipo)='ENTRADA' THEN valor ELSE -valor END), 0) FROM fluxo_caixa")
                saldo_total = float(cursor.fetchone()[0] or 0)

                try:
                    cursor.execute("SELECT COALESCE(SUM(saldo), 0) FROM orcamentos_aguardo WHERE UPPER(status) = 'APROVADO'")
                    saldo_receber = float(cursor.fetchone()[0] or 0)
                except sqlite3.Error:
                    # Em bases antigas sem a tabela de orçamentos, mantém o financeiro funcional.
                    saldo_receber = 0.0

                cursor.execute(
                    f"""
                    SELECT id, data, descricao, tipo, valor, COALESCE(categoria, 'GERAL'), COALESCE(metodo_pagamento, '-')
                    FROM fluxo_caixa
                    WHERE {data_sql} BETWEEN ? AND ?
                        AND (
                            UPPER(descricao) LIKE ?
                            OR UPPER(COALESCE(categoria, '')) LIKE ?
                            OR UPPER(COALESCE(metodo_pagamento, '')) LIKE ?
                        )
                    ORDER BY id DESC
                    """,
                    (d_ini, d_fim, busca, busca, busca)
                )
                linhas = cursor.fetchall()

                cursor.execute(
                    f"""
                    SELECT UPPER(COALESCE(metodo_pagamento, '-')), COALESCE(SUM(valor), 0)
                    FROM fluxo_caixa
                    WHERE {data_sql} BETWEEN ? AND ?
                        AND UPPER(tipo) = 'ENTRADA'
                    GROUP BY UPPER(COALESCE(metodo_pagamento, '-'))
                    """,
                    (d_ini, d_fim)
                )
                pagamentos = cursor.fetchall()

            entradas = 0.0
            saidas = 0.0
            for row in linhas:
                id_mov, data, descricao, tipo, valor, categoria, metodo = row
                valor = float(valor or 0)
                if str(tipo).upper() == "ENTRADA":
                    entradas += valor
                    tag = "entrada"
                else:
                    saidas += valor
                    tag = "saida"
                self.tab_caixa.insert(
                    "",
                    "end",
                    values=(id_mov, data, descricao, tipo, f"R$ {valor:.2f}", categoria, metodo),
                    tags=(tag,)
                )

            saldo_filtro = entradas - saidas
            cor_saldo = "#2ecc71" if saldo_total >= 0 else "#e74c3c"
            total_pix = 0.0
            total_dinheiro = 0.0
            total_cartao = 0.0
            for metodo_pg, valor_pg in pagamentos:
                m = str(metodo_pg or "").upper()
                v = float(valor_pg or 0)
                if "PIX" in m:
                    total_pix += v
                elif "DINHEIRO" in m:
                    total_dinheiro += v
                elif "CART" in m:
                    total_cartao += v

            self.lbl_saldo.configure(text=f"SALDO GERAL EM CAIXA: R$ {saldo_total:.2f}", text_color=cor_saldo)
            self.lbl_entradas.configure(text=f"ENTRADAS FILTRADAS\nR$ {entradas:.2f}")
            self.lbl_saidas.configure(text=f"SAIDAS FILTRADAS\nR$ {saidas:.2f}")
            self.lbl_saldo_resumo.configure(text=f"SALDO DO FILTRO\nR$ {saldo_filtro:.2f}", fg_color="#b7ef8a" if saldo_filtro >= 0 else "#ff9f9a")
            self.lbl_saldo_receber.configure(text=f"SALDO A RECEBER\nR$ {saldo_receber:.2f}")
            self.lbl_pix.configure(text=f"PIX\nR$ {total_pix:.2f}")
            self.lbl_dinheiro.configure(text=f"DINHEIRO\nR$ {total_dinheiro:.2f}")
            self.lbl_cartao.configure(text=f"CARTAO\nR$ {total_cartao:.2f}")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao carregar financeiro: {e}", parent=self)


if __name__ == "__main__":
    inicializar_banco()
    app = ctk.CTk()
    app.withdraw()
    FrmFinanceiro(app)
    app.mainloop()

