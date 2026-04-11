from config import gerar_chave_licenca, gerar_hash_publico_licenca


def main():
    print("=== GERADOR DE CHAVE - OFICINA DE PESCA ===")
    cliente = input("Nome do cliente: ").strip()
    if not cliente:
        cliente = "CLIENTE"

    print("\nTipo de licença:")
    print("1 - PERMANENTE")
    print("2 - MENSAL (30 dias)")
    print("3 - TRIMESTRAL (90 dias)")
    opcao = input("Escolha (1/2/3, ENTER = 1): ").strip() or "1"

    tipo = "PERMANENTE"
    dias = None
    if opcao == "2":
        tipo = "MENSAL"
        dias = 30
    elif opcao == "3":
        tipo = "TRIMESTRAL"
        dias = 90

    dias_txt = input("Dias customizados (ENTER mantém padrão): ").strip()
    if dias_txt:
        try:
            dias_custom = int(dias_txt)
            if dias_custom > 0:
                dias = dias_custom
                if dias_custom >= 90:
                    tipo = "TRIMESTRAL"
                elif dias_custom >= 30:
                    tipo = "MENSAL"
        except ValueError:
            pass

    chave = gerar_chave_licenca(cliente, dias, tipo_licenca=tipo)
    print("\nCHAVE GERADA:")
    print(chave)
    print(f"TIPO: {tipo}")
    print(f"HASH PÚBLICO (GitHost): {gerar_hash_publico_licenca(chave)}")
    print("\nCopie e envie para o cliente.")


if __name__ == "__main__":
    main()
