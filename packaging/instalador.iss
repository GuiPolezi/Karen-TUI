; Instalador do CMD ALL-IN-ONE (Inno Setup 6).
;
; Instala por usuário, em %LOCALAPPDATA%\Programs\CMD ALL-IN-ONE, sem UAC. Os dados do
; usuário (.env, logs, notas, prefs.json, perfil do Chromium) ficam em
; %LOCALAPPDATA%\CMD-ALL-IN-ONE e NUNCA são tocados aqui: atualizar ou desinstalar não
; apaga configuração.
;
; Os atalhos abrem o Windows Terminal (cores e fonte do ciclo 3); sem ele, caem no
; executável direto (conhost).
;
; Compilar:  iscc /DAppVersion=0.1.0 packaging\instalador.iss
; A atualização automática chama este instalador com
;   /SILENT /SUPPRESSMSGBOXES /NORESTART /FORCECLOSEAPPLICATIONS /RESTARTAPPLICATIONS

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "CMD ALL-IN-ONE"
#define AppExe "CMD-ALL-IN-ONE.exe"
#define AppPublisher "Sino Informática"

[Setup]
AppId={{7F3A9C21-6B54-4E1D-9F0A-2C8D5E4B1A77}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
; sem ArchitecturesAllowed de propósito: "x64compatible" só existe do Inno 6.3 para cima e
; o compilador da máquina de build pode ser mais antigo. O executável é x64 e roda por
; emulação no ARM64; numa máquina 32 bits ele simplesmente não abriria.
OutputDir=..\dist
OutputBaseFilename=CMD-ALL-IN-ONE-Setup-{#AppVersion}
SetupIconFile=cmd-all-in-one.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; a atualização roda com o programa aberto: o Restart Manager fecha e reabre
CloseApplications=force
RestartApplications=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar um atalho na área de trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "..\dist\CMD-ALL-IN-ONE\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; com Windows Terminal: abre nele, já na pasta do programa
Name: "{group}\{#AppName}"; Filename: "{code:WtPath}"; \
    Parameters: "-d ""{app}"" ""{app}\{#AppExe}"""; WorkingDir: "{app}"; \
    IconFilename: "{app}\{#AppExe}"; Check: TemWindowsTerminal
Name: "{userdesktop}\{#AppName}"; Filename: "{code:WtPath}"; \
    Parameters: "-d ""{app}"" ""{app}\{#AppExe}"""; WorkingDir: "{app}"; \
    IconFilename: "{app}\{#AppExe}"; Tasks: desktopicon; Check: TemWindowsTerminal
; sem Windows Terminal: o executável direto
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; \
    Check: not TemWindowsTerminal
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; \
    Tasks: desktopicon; Check: not TemWindowsTerminal

[Run]
; depois de instalar na mão, abre o programa (a atualização silenciosa reabre sozinha)
Filename: "{code:WtPath}"; Parameters: "-d ""{app}"" ""{app}\{#AppExe}"""; \
    Description: "Abrir o {#AppName}"; WorkingDir: "{app}"; \
    Flags: nowait postinstall skipifsilent; Check: TemWindowsTerminal
Filename: "{app}\{#AppExe}"; Description: "Abrir o {#AppName}"; WorkingDir: "{app}"; \
    Flags: nowait postinstall skipifsilent; Check: not TemWindowsTerminal

[Code]
function CaminhoWt(): String;
begin
  { alias de execução do Windows Terminal, instalado por usuário ou pela Store }
  Result := ExpandConstant('{localappdata}\Microsoft\WindowsApps\wt.exe');
  if not FileExists(Result) then
    Result := '';
end;

function TemWindowsTerminal(): Boolean;
begin
  Result := CaminhoWt() <> '';
end;

function WtPath(Param: String): String;
begin
  Result := CaminhoWt();
  if Result = '' then
    Result := ExpandConstant('{app}\{#AppExe}');
end;
