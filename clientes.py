import customtkinter as ctk
import sqlite3
import os
import requests
from tkinter import messagebox, ttk
from datetime import datetime
from config import CAMINHO_BANCO, inicializar_banco, get_db_connection, get_logger

logger = get_logger(__name__)

inicializar_banco()

class FrmClientes(ctk.CTkToplevel):
    def __init__(self, master, nome_inicial="", ao_salvar=None):
        super().__init__(master)
        self.ao_salvar = ao_salvar
        self.title("Ficha de Cadastro - Oficina de Pesca")
        self.geometry("860x860")
        self.minsize(840, 820)

        self.lift()
        self.focus_force()
        self.grab_set()
        self.configure(fg_color="#161b22")

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(pady=10, padx=10, fill="both", expand=True)

        self.f_header = ctk.CTkFrame(self.scroll, fg_color="#1f2a38", corner_radius=20)
        self.f_header.pack(pady=15, padx=20, fill="x")
        ctk.CTkLabel(self.f_header, text="🎣 CADASTRO DE PESCADOR", font=("Arial", 24, "bold"), text_color="orange").pack(side="left", padx=20, pady=20)
        ctk.CTkButton(self.f_header, text="🗂️ VER LISTA / HISTÓRICO", fg_color="#2980b9", width=180,
                      command=self.abrir_lista_completa).pack(side="right", padx=20, pady=20)

        self.f_dados = ctk.CTkFrame(self.scroll, fg_color="#1f2a38", corner_radius=20)
        self.f_dados.pack(pady=10, padx=20, fill="x")
        self.f_dados.grid_columnconfigure(0, weight=1)
        self.f_dados.grid_columnconfigure(1, weight=1)

        self.txt_nome = self.criar_campo("NOME COMPLETO:", 0, 0)
        self.txt_fone = self.criar_campo("TELEFONE/WHATSAPP:", 1, 0)
        self.txt_email = self.criar_campo("E-MAIL:", 2, 0)
        self.txt_cep = self.criar_campo("CEP:", 3, 0)
        self.txt_cep.bind("<FocusOut>", lambda e: self.buscar_cep())
        self.txt_cep.bind("<Return>", lambda e: self.buscar_cep())

        self.txt_rua = self.criar_campo("LOGRADOURO (Rua/Av):", 0, 1)
        self.txt_num = self.criar_campo("NÚMERO:", 1, 1)
        self.txt_bairro = self.criar_campo("BAIRRO:", 2, 1)
        self.txt_cidade = self.criar_campo("CIDADE:", 3, 1)
        self.txt_estado = self.criar_campo("ESTADO:", 4, 1)

        if nome_inicial:
            self.txt_nome.insert(0, nome_inicial.upper())
            self.txt_fone.focus_set()

        botoes_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        botoes_frame.pack(pady=20, padx=20, fill="x")
        ctk.CTkButton(botoes_frame, text="💾 SALVAR CADASTRO", fg_color="#27ae60", height=50, font=("Arial", 18, "bold"), command=self.salvar_cliente).pack(side="left", expand=True, fill="x", padx=(0,10))
        ctk.CTkButton(botoes_frame, text="🧹 LIMPAR", fg_color="#7f8c8d", height=50, font=("Arial", 18, "bold"), command=self.limpar_campos).pack(side="left", expand=True, fill="x", padx=(10,0))

    def limpar_campos(self):
        for campo in [
            self.txt_nome, self.txt_fone, self.txt_email, self.txt_cep,
            self.txt_rua, self.txt_num, self.txt_bairro, self.txt_cidade, self.txt_estado
        ]:
            campo.delete(0, 'end')
        self.txt_nome.focus_set()

    def criar_campo(self, label, linha, coluna):
        lbl = ctk.CTkLabel(self.f_dados, text=label, font=("Arial", 12, "bold"), text_color="#ecf0f1")
        lbl.grid(row=linha*2, column=coluna, padx=20, pady=(20, 5), sticky="w")
        ent = ctk.CTkEntry(self.f_dados, width=320)
        ent.grid(row=linha*2 + 1, column=coluna, padx=20, pady=(0, 10), sticky="ew")
        return ent

    def buscar_cep(self):
        # Pega o valor, remove traços e espaços
        cep = self.txt_cep.get().replace("-", "").replace(".", "").strip()
        
        # Só tenta buscar se tiver os 8 dígitos
        if len(cep) == 8:
            try:
                url = f"https://viacep.com.br/ws/{cep}/json/"
                # Timeout de 3 segundos para não travar o sistema se a internet cair
                resposta = requests.get(url, timeout=3) 
                retorno = resposta.json()
                
                if "erro" not in retorno:
                    # Limpa e preenche os campos com letras MAIÚSCULAS
                    self.txt_rua.delete(0, 'end')
                    self.txt_rua.insert(0, retorno.get('logradouro', '').upper())
                    
                    self.txt_bairro.delete(0, 'end')
                    self.txt_bairro.insert(0, retorno.get('bairro', '').upper())
                    
                    self.txt_cidade.delete(0, 'end')
                    self.txt_cidade.insert(0, retorno.get('localidade', '').upper())

                    self.txt_estado.delete(0, 'end')
                    self.txt_estado.insert(0, retorno.get('uf', '').upper())
                    
                    # Foca no campo número para agilizar o cadastro
                    self.txt_num.focus_set()
                else:
                    messagebox.showwarning("CEP", "CEP não encontrado!")
            except requests.exceptions.RequestException:
                messagebox.showerror("Erro de Conexão", "Não foi possível consultar o CEP. Verifique sua internet.")
            except Exception as e:
                logger.exception("Erro inesperado ao consultar CEP: %s", e)

    def salvar_cliente(self):
        nome = self.txt_nome.get().upper()
        if not nome:
            messagebox.showwarning("Aviso", "O nome é obrigatório!", parent=self)
            return
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""INSERT INTO clientes (nome, telefone, email, cep, rua, numero, bairro, cidade, estado, data_cadastro) 
                                  VALUES (?,?,?,?,?,?,?,?,?,?)""",
                               (nome, self.txt_fone.get(), self.txt_email.get(), self.txt_cep.get(), 
                                self.txt_rua.get(), self.txt_num.get(), self.txt_bairro.get(), self.txt_cidade.get(), 
                                self.txt_estado.get(), datetime.now().strftime("%Y-%m-%d")))
                conn.commit()
            if callable(self.ao_salvar):
                self.ao_salvar(nome)
            messagebox.showinfo("Sucesso", "Pescador cadastrado com sucesso!", parent=self)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar: {e}", parent=self)

    def abrir_lista_completa(self):
        JanelaListaClientes(self.master)

# --- CLASSE DA LISTA COM HISTÓRICO ---
class JanelaListaClientes(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Consulta e Histórico de Pescadores")
        self.geometry("1250x750")
        self.lift(); self.focus_force(); self.grab_set()
        
        ctk.CTkLabel(self, text="🔎 CONSULTA DE CLIENTES E HISTÓRICO", font=("Arial", 20, "bold"), text_color="orange").pack(pady=15)
        
        self.ent_busca = ctk.CTkEntry(self, placeholder_text="🔍 Digite o nome para pesquisar...", width=500, height=35)
        self.ent_busca.pack(pady=5)
        self.ent_busca.bind("<KeyRelease>", lambda e: self.carregar_dados())

        self.f_tab = ctk.CTkFrame(self)
        self.f_tab.pack(fill="both", expand=True, padx=20, pady=10)

        colunas = ("id", "nome", "whatsapp", "endereco", "bairro", "cidade")
        self.tabela = ttk.Treeview(self.f_tab, columns=colunas, show="headings")
        
        self.tabela.heading("id", text="ID"); self.tabela.column("id", width=40)
        self.tabela.heading("nome", text="NOME"); self.tabela.column("nome", width=250)
        self.tabela.heading("whatsapp", text="WHATSAPP"); self.tabela.column("whatsapp", width=120)
        self.tabela.heading("endereco", text="ENDEREÇO"); self.tabela.column("endereco", width=250)
        self.tabela.heading("bairro", text="BAIRRO"); self.tabela.column("bairro", width=150)
        self.tabela.heading("cidade", text="CIDADE"); self.tabela.column("cidade", width=120)

        self.tabela.pack(side="left", fill="both", expand=True)
        scrol = ttk.Scrollbar(self.f_tab, orient="vertical", command=self.tabela.yview)
        self.tabela.configure(yscroll=scrol.set); scrol.pack(side="right", fill="y")

        self.tabela.bind("<<TreeviewSelect>>", self.carregar_historico_selecionado)

        self.f_hist = ctk.CTkFrame(self, fg_color="#2c3e50")
        self.f_hist.pack(fill="x", padx=20, pady=(0, 20))
        
        ctk.CTkLabel(self.f_hist, text="📜 ÚLTIMO SERVIÇO DESTA PESSOA:", font=("Arial", 12, "bold"), text_color="white").pack(pady=5)
        self.txt_historico = ctk.CTkTextbox(self.f_hist, height=100, font=("Arial", 13), fg_color="#34495e", text_color="white")
        self.txt_historico.pack(fill="x", padx=10, pady=10)

        self.carregar_dados()

    def carregar_dados(self):
        for i in self.tabela.get_children(): self.tabela.delete(i)
        busca = f"%{self.ent_busca.get().upper()}%"
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""SELECT id, nome, telefone, (rua || ', ' || numero), bairro, cidade 
                                  FROM clientes WHERE UPPER(nome) LIKE ? ORDER BY nome""", (busca,))
                for linha in cursor.fetchall():
                    self.tabela.insert("", "end", values=linha)
        except Exception as e:
            logger.exception("Erro ao carregar lista de clientes: %s", e)

    def carregar_historico_selecionado(self, event):
        selecao = self.tabela.selection()
        if not selecao: return
        nome_cliente = self.tabela.item(selecao[0], "values")[1]
        self.txt_historico.delete("0.0", "end")
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""SELECT data, equipamento, itens_detalhes, valor_total 
                                  FROM orcamentos_aguardo WHERE cliente = ? 
                                  ORDER BY id DESC LIMIT 1""", (nome_cliente,))
                h = cursor.fetchone()
            if h:
                resumo = f"📅 DATA: {h[0]}  |  🎣 EQUIPAMENTO: {h[1]}\n🛠️ SERVIÇO: {h[2]}\n💰 VALOR: R$ {h[3]:.2f}"
                self.txt_historico.insert("0.0", resumo)
            else:
                self.txt_historico.insert("0.0", "Nenhum serviço registrado para este pescador.")
        except Exception as e:
            logger.exception("Erro ao buscar histórico do cliente: %s", e)
            self.txt_historico.insert("0.0", "Erro ao buscar histórico.")

if __name__ == "__main__":
    root = ctk.CTk()
    root.withdraw()
    app = FrmClientes(root)
    app.mainloop()