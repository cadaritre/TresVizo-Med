; Compilar con Inno Setup después de distribuir.ps1.
[Setup]
AppId=TresVizoMed
AppName=TresVizo Med
AppVersion=0.1.0
DefaultDirName={localappdata}\Programs\TresVizo-Med
PrivilegesRequired=lowest
DefaultGroupName=TresVizo Med
SetupIconFile=..\assets\tresvizo_medico.ico
UninstallDisplayIcon={app}\TresVizo-Med.exe
OutputDir=..\dist\installer
OutputBaseFilename=TresVizo-Med-Setup
LicenseFile=..\LICENSE

[Files]
Source: "..\dist\TresVizo-Med\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\TresVizo Med"; Filename: "{app}\TresVizo-Med.exe"
Name: "{autodesktop}\TresVizo Med"; Filename: "{app}\TresVizo-Med.exe"

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
