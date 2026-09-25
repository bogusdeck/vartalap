; Inno Setup Compiler Script for Vartalap Windows Installer
[Setup]
AppName=Vartalap
AppVersion=0.1.0
DefaultDirName={autopf}\Vartalap
DefaultGroupName=Vartalap
OutputDir=Output
OutputBaseFilename=VartalapSetup_v0.1.0
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
ChangesEnvironment=yes

[Files]
Source: "dist\vartalap.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Vartalap CLI"; Filename: "{app}\vartalap.exe"
Name: "{commondesktop}\Vartalap"; Filename: "{app}\vartalap.exe"

[Tasks]
Name: envPath; Description: "Add Vartalap to System PATH environment variable"; Flags: unchecked

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  Path: string;
begin
  if (CurStep = ssPostInstall) and IsTaskSelected('envPath') then
  begin
    if RegQueryStringValue(HKEY_LOCAL_MACHINE, 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment', 'Path', Path) then
    begin
      if Pos(ExpandConstant('{app}'), Path) = 0 then
      begin
        Path := Path + ';' + ExpandConstant('{app}');
        RegWriteStringValue(HKEY_LOCAL_MACHINE, 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment', 'Path', Path);
      end;
    end;
  end;
end;
