; Inno Setup Script for Video-to-Text Transcriber
#define MyAppName "Video-to-Text Transcriber"
#define MyAppVersion "3.0.0"
#define MyAppPublisher "Chrispin Kabuya"
#define MyAppExeName "VideoToText.exe"

[Setup]
; AppId is a unique identifier for your app. Do not change this for future updates.
AppId={{8A9F5C2D-4B3E-4A1D-9F2B-7C6D5E4F3A2B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\VideoToText
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
; Tells the installer to ask for admin rights (needed for Program Files)
PrivilegesRequired=admin
; Compression settings
Compression=lzma2
SolidCompression=yes
; Look and feel
WizardStyle=modern

[Tasks]
; Optionally create a desktop icon
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Copies everything from the PyInstaller dist folder
Source: "dist\VideoToText\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Creates Start Menu and Desktop shortcuts
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Option to launch the app immediately after installation
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent