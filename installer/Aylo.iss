#ifndef MyAppVersion
  #define MyAppVersion "3.1.1"
#endif

[Setup]
AppId={{6FCF9AB8-03DF-4544-949C-9F71241AACFD}
AppName=Aylo
AppVersion={#MyAppVersion}
AppPublisher=Aylo
DefaultDirName={autopf}\Aylo
DefaultGroupName=Aylo
OutputDir=..\release
OutputBaseFilename=Aylo-{#MyAppVersion}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\Aylo.exe

[Files]
Source: "..\dist\Aylo.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\FRIEND_TESTING.md"; DestDir: "{app}"; DestName: "Aylo Quick Start.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Aylo"; Filename: "{app}\Aylo.exe"
Name: "{autodesktop}\Aylo"; Filename: "{app}\Aylo.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\Aylo.exe"; Description: "Launch Aylo"; Flags: nowait postinstall skipifsilent
