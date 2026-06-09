; Inno Setup Script — Music DL Installer
; Telechargez Inno Setup : https://jrsoftware.org/isinfo.php
; Puis lancez : build.bat

#define AppName      "Music DL"
#define AppVersion   "1.0.0"
#define AppPublisher "Music DL"
#define AppURL       "http://localhost:5000"
#define AppExeName   "MusicDL.exe"
#define AppDataDir   "{localappdata}\MusicDL"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=installer_output
OutputBaseFilename=MusicDL_Setup_v{#AppVersion}
SetupIconFile=icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Pas besoin de droits admin — installe dans Program Files de l'utilisateur
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; Exige Windows 10 minimum
MinVersion=10.0

[Languages]
Name: "french";    MessagesFile: "compiler:Languages\French.isl"
Name: "english";   MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";    Description: "Cr&eer un raccourci sur le Bureau";    GroupDescription: "Raccourcis :"; Flags: unchecked
Name: "startuprun";     Description: "Lancer {#AppName} au d&emarrage de Windows"; GroupDescription: "Options :"; Flags: unchecked

[Files]
; Dossier complet genere par PyInstaller
Source: "dist\MusicDL\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Menu Demarrer
Name: "{group}\{#AppName}";             Filename: "{app}\{#AppExeName}"
Name: "{group}\Desinstaller {#AppName}"; Filename: "{uninstallexe}"
; Bureau (si option cochee)
Name: "{autodesktop}\{#AppName}";       Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; Lancement au demarrage Windows (si option cochee)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "{#AppName}"; \
  ValueData: """{app}\{#AppExeName}"""; \
  Flags: uninsdeletevalue; Tasks: startuprun

[Run]
; Lancer l'app a la fin de l'installation
Filename: "{app}\{#AppExeName}"; \
  Description: "Lancer {#AppName} maintenant"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Supprimer les fichiers temporaires (PAS les donnees utilisateur dans AppData)
Type: filesandordirs; Name: "{app}"

[Code]
procedure InitializeWizard();
begin
  WizardForm.WelcomeLabel2.Caption :=
    'Music DL va etre installe sur votre PC.' + #13#10 + #13#10 +
    'Vos musiques et playlists seront stockees dans :' + #13#10 +
    ExpandConstant('{localappdata}') + '\MusicDL' + #13#10 + #13#10 +
    'Ce dossier est personnel a votre compte Windows.' + #13#10 +
    'Il ne sera PAS supprime lors de la desinstallation.';
end;
