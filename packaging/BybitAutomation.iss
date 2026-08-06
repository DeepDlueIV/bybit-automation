#define MyAppName "Bybit Automation"
#ifndef MyAppVersion
#define MyAppVersion "0.1.0"
#endif
#define MyAppExeName "BybitAutomation.exe"

[Setup]
AppId={{B85D05D6-1A63-4DC5-8BD1-9F0782B49D8A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Bybit Automation
DefaultDirName={localappdata}\BybitAutomation
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=BybitAutomation-Setup-{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupLogging=yes
CloseApplications=force
RestartApplications=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные ярлыки:"; Flags: unchecked

[Files]
Source: "..\dist\BybitAutomation\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\sound\Alarm09.wav"; DestDir: "{app}\sound"; Flags: ignoreversion
Source: "..\запуск.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Bybit Automation"; Filename: "{app}\BybitAutomation.exe"; WorkingDir: "{app}"
Name: "{autoprograms}\Открыть папку Bybit Automation"; Filename: "{app}"
Name: "{autodesktop}\Bybit Automation"; Filename: "{app}\BybitAutomation.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\BybitAutomation.exe"; Description: "Запустить Bybit Automation"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\data"
Type: files; Name: "{app}\ГДЕ_НАХОДЯТСЯ_ФАЙЛЫ.txt"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  Guide: TArrayOfString;
begin
  if CurStep = ssPostInstall then
  begin
    SetArrayLength(Guide, 7);
    Guide[0] := 'BYBIT AUTOMATION: РАСПОЛОЖЕНИЕ ФАЙЛОВ';
    Guide[1] := '';
    Guide[2] := 'Папка установки: ' + ExpandConstant('{app}');
    Guide[3] := 'Настройки и данные: ' + ExpandConstant('{app}\data');
    Guide[4] := 'Лог программы: ' + ExpandConstant('{app}\data\app.log');
    Guide[5] := 'Профиль Portable Chrome: ' + ExpandConstant('{app}\data\portable-chrome-profile');
    Guide[6] := 'Portable Chrome: ' + ExpandConstant('{app}\runtime\chrome-for-testing\chrome-win64\chrome.exe');
    SaveStringsToUTF8File(
      ExpandConstant('{app}\ГДЕ_НАХОДЯТСЯ_ФАЙЛЫ.txt'),
      Guide,
      False
    );
  end;
end;
