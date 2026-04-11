# -*- mode: python ; coding: utf-8 -*-
# ==============================================================
#  PyInstaller spec - Oficina de Pesca
#  Gerar o executável:
#    pyinstaller oficina.spec
#  Saída: dist\Oficina_Pesca\Oficina_Pesca.exe
#  Licença: OFP_LICENCA_SECRET é lido em runtime via variável de ambiente
#  (definida no instalador instalar.iss).
# ==============================================================

block_cipher = None

# Recursos de dados que devem ir junto com o exe
dados = [
    ('fundomenu.png',         '.'),
    ('LOGO.bmp',              '.'),
    ('config.cfg',            '.'),
]

# Remove arquivos que NÃO devem ir para o cliente
# (gerador_licenca.py é ferramenta interna do desenvolvedor)

a = Analysis(
    ['login.py'],
    pathex=[],
    binaries=[],
    datas=dados,
    hiddenimports=[
        'customtkinter',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'PIL._tkinter_finder',
        'reportlab',
        'reportlab.graphics',
        'reportlab.graphics.shapes',
        'reportlab.platypus',
        'reportlab.lib.pagesizes',
        'reportlab.pdfgen.canvas',
        'config',
        'menu',
        'clientes',
        'tela_os',
        'gestao_os',
        'tela_financeiro',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['gerador_licenca'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Oficina_Pesca',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # Sem janela de console (app de janela)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Oficina_Pesca',
)
