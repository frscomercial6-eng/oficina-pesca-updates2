from PIL import Image

# Nome do arquivo PNG de entrada
input_file = "icone_app_chave_anzol.png"  # Altere se necessário

# Nome do arquivo ICO de saída
output_file = "icone_oficina.ico"

# Tamanhos recomendados para ícone do Windows
sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]

img = Image.open(input_file)
img.save(output_file, format='ICO', sizes=sizes)

print(f"Ícone gerado: {output_file}")
