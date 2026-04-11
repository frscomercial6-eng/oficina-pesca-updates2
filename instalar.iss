; ==============================================================
;  Inno Setup Script - Oficina de Pesca
;  Requisito: Inno Setup 6+ (https://jrsoftware.org/isinfo.php)
;
;  Como usar:
;    1. Execute: pyinstaller oficina.spec
;    2. Abra este arquivo no Inno Setup Compiler (ou ISCC.exe)
;    3. Pressione F9 para compilar
;    4. O instalador sera gerado em: INSTALADOR_FINAL\Setup_OficinaPesca.exe
; ==============================================================

#define AppName      "Oficina de Pesca"
#define AppVersion   "1.0.0"
#define AppPublisher "FRS Solucoes"
#define AppExeName   "Oficina_Pesca.exe"
#define SourceDir    "e:\PROGRAMA CONTROLE OFICINA DE PESCA\PROGRAMA OFICINA\dist\Oficina_Pesca"
#define LicenseSecret "ALTERAR-EM-PRODUCAO"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\OficinaPesca
DefaultGroupName={#AppName}
AllowNoIcons=yes

OutputDir=INSTALADOR_FINAL
OutputBaseFilename=Setup_OficinaPesca
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ChangesEnvironment=yes
SetupIconFile=icone_oficina.ico

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar ícone na Área de Trabalho"; GroupDescription: "Ícones adicionais:"

[Files]
; Todos os arquivos gerados pelo PyInstaller
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Imagens de fundo do menu
Source: "fundomenu.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "LOGO.bmp";     DestDir: "{app}"; Flags: ignoreversion
; Servidor web (acesso por celular/rede)
Source: "servidor.py";          DestDir: "{app}"; Flags: ignoreversion
Source: "config.py";            DestDir: "{app}"; Flags: ignoreversion
Source: "config.cfg";           DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist
Source: "versao.json";          DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist
Source: "iniciar_servidor.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "templates\*";          DestDir: "{app}\templates"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "static\*";             DestDir: "{app}\static";    Flags: ignoreversion recursesubdirs createallsubdirs
; APK do app mobile
Source: "android_apk\app\build\outputs\apk\debug\app-debug.apk"; DestDir: "{app}"; DestName: "app-oficina-pesca.apk"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";           Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\icone_oficina.ico"
Name: "{group}\Iniciar Servidor Web"; Filename: "{app}\iniciar_servidor.bat"; Comment: "Inicia o servidor para acesso via rede e celular"
Name: "{group}\Desinstalar";          Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}";     Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Environment"; ValueType: string; ValueName: "OFP_LICENCA_SECRET"; ValueData: "{#LicenseSecret}"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExeName}";        Description: "Abrir {#AppName} agora"; Flags: nowait postinstall skipifsilent
