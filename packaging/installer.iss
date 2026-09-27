; Inno Setup script: dist\Label-Printer\ -> build\installer\Label-Printer-Setup.exe
;
; Run packaging\build.ps1, which builds the manual, the app and this installer.
; Per-user install (no admin password), Danish, Start Menu entry, desktop
; shortcut and a normal uninstaller.
; Saved as UTF-8 with BOM: without it Inno Setup reads the Danish letters wrongly.

#define MyAppName "Label Printer"
; Keep in sync with __version__ in src\label_printer\__init__.py.
#define MyAppVersion "4.3"
#define MyAppExeName "Label-Printer.exe"

[Setup]
; Identifies "this program" to Windows across versions -- never change it,
; so a newer installer upgrades the existing install in place.
AppId={{4A3DD020-8DD1-412A-A387-D6C54D7F2206}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
OutputDir={#SourcePath}..\build\installer
OutputBaseFilename=Label-Printer-Setup
SetupIconFile={#SourcePath}..\src\label_printer\assets\label_printer.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
; Close a running Label Printer before upgrading it.
CloseApplications=yes

[Languages]
Name: "danish"; MessagesFile: "compiler:Languages\Danish.isl"

[Tasks]
; Checked by default: the desktop icon is how it will be started.
Name: "desktopicon"; Description: "Opret genvej på skrivebordet"; GroupDescription: "Genveje:"

[Files]
Source: "{#SourcePath}..\dist\Label-Printer\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; The manual, built by docs\manual\make_manual.py. The "? Hjælp" button in the
; app looks for it next to Label-Printer.exe.
Source: "{#SourcePath}..\build\Label-Printer-Vejledning.pdf"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
; Remove the previous version's program files first, so stale libraries from
; an older build can't linger in _internal\.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} – Vejledning"; Filename: "{app}\Label-Printer-Vejledning.pdf"
Name: "{group}\Afinstaller {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Start {#MyAppName}"; Flags: nowait postinstall skipifsilent
