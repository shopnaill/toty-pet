; ============================================================
;  Toty Desktop Pet — Inno Setup Installer Script
;
;  Requirements:
;    1. Build with PyInstaller first:  pyinstaller toty.spec
;    2. Then compile this .iss with Inno Setup 6+
;       or from CLI:  iscc installer.iss
; ============================================================

#define MyAppName "Toty"
#define MyAppVersion "15.0.0"
#define MyAppPublisher "mfoud5391"
#define MyAppURL "https://github.com/mfoud5391/toty"
#define MyAppExeName "Toty.exe"
#define OutputDir "dist"

[Setup]
AppId={{A7C3E2D1-4F8B-4A2E-9D6C-1B3E5F7A9C0D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=
OutputDir={#OutputDir}
OutputBaseFilename=TotySetup-v{#MyAppVersion}
SetupIconFile=assets\toty_archive.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Modern look
WizardImageFile=assets\toty_idle.png
WizardSmallImageFile=assets\toty_archive.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startupicon"; Description: "Start Toty with Windows"; GroupDescription: "Startup:"

[Files]
; Include all files from PyInstaller dist/Toty/ output
Source: "dist\Toty\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Optional: run on Windows startup
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Toty"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
