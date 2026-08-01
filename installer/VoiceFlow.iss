#ifndef MyAppVersion
  #define MyAppVersion "3.1.1"
#endif

[Setup]
AppId={{6FCF9AB8-03DF-4544-949C-9F71241AACFD}
AppName=VoiceFlow
AppVersion={#MyAppVersion}
AppPublisher=VoiceFlow
DefaultDirName={autopf}\VoiceFlow
DefaultGroupName=VoiceFlow
OutputDir=..\release
OutputBaseFilename=VoiceFlow-{#MyAppVersion}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\VoiceFlow.exe

[Files]
Source: "..\dist\VoiceFlow.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\FRIEND_TESTING.md"; DestDir: "{app}"; DestName: "VoiceFlow Quick Start.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\VoiceFlow"; Filename: "{app}\VoiceFlow.exe"
Name: "{autodesktop}\VoiceFlow"; Filename: "{app}\VoiceFlow.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\VoiceFlow.exe"; Description: "Launch VoiceFlow"; Flags: nowait postinstall skipifsilent
