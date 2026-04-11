from PIL import Image
import os

# Nome do arquivo da imagem enviada (ajuste se necessário)
img_path = "play_store_512.png"  # Coloque o nome correto do arquivo aqui
img = Image.open(img_path)

sizes = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}

base_dir = r"android_apk/app/src/main/res"

for folder, size in sizes.items():
    out_dir = os.path.join(base_dir, folder)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "ic_launcher.png")
    img.resize((size, size), Image.LANCZOS).save(out_path)
    print(f"Salvo: {out_path}")
