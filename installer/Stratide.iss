; Stratide Windows 11 per-user installer (Issue #85).
; Built with Inno Setup 6.7.4. No administrator rights, no Windows service.

#define AppName "Stratide"
#ifndef AppVersion
  #define AppVersion "0.3.2"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\app"
#endif
#ifndef TestMode
  #define TestMode "0"
#endif

#ifndef OutputDir
  #define OutputDir "..\dist\installer"
#endif

[Setup]
AppId={{5D9E3C2A-4B71-4F0E-9C8D-2A6B7E1F4C90}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Stratide
AppPublisherURL=https://github.com/handFOOLed/Stratide
DefaultDirName={localappdata}\Programs\Stratide
DefaultGroupName=Stratide
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#OutputDir}
OutputBaseFilename=Stratide-Setup-{#AppVersion}-x64
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\stratide-launcher.exe
UninstallDisplayName={#AppName} {#AppVersion}
UsePreviousAppDir=yes
CloseApplications=no
RestartApplications=no
SetupLogging=yes
#if TestMode == "1"
Uninstallable=no
#endif
VersionInfoVersion={#AppVersion}
VersionInfoCompany=Stratide
VersionInfoDescription=Stratide Windows installer
VersionInfoProductName=Stratide
VersionInfoProductVersion={#AppVersion}

[Languages]
Name: "chinesesimp"; MessagesFile: "languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："
Name: "autostart"; Description: "登录 Windows 后自动启动 Stratide 后台（不自动打开浏览器）"; GroupDescription: "启动选项："; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

#if TestMode != "1"
[Icons]
Name: "{group}\Stratide"; Filename: "{app}\stratide-launcher.exe"; WorkingDir: "{app}"; Comment: "打开本地 Dashboard"
Name: "{group}\停止 Stratide 后台"; Filename: "{app}\stratide-launcher.exe"; Parameters: "--home ""{code:GetHomeDir}"" --stop"; WorkingDir: "{app}"
Name: "{group}\启用登录自启"; Filename: "{app}\stratide-launcher.exe"; Parameters: "--home ""{code:GetHomeDir}"" --autostart enable"; WorkingDir: "{app}"
Name: "{group}\停用登录自启"; Filename: "{app}\stratide-launcher.exe"; Parameters: "--home ""{code:GetHomeDir}"" --autostart disable"; WorkingDir: "{app}"
Name: "{group}\打开数据目录"; Filename: "{app}\stratide-launcher.exe"; Parameters: "--home ""{code:GetHomeDir}"" --open-data"; WorkingDir: "{app}"
Name: "{group}\打开日志目录"; Filename: "{app}\stratide-launcher.exe"; Parameters: "--home ""{code:GetHomeDir}"" --open-logs"; WorkingDir: "{app}"
Name: "{group}\删除本地数据…"; Filename: "{app}\stratide-launcher.exe"; Parameters: "--home ""{code:GetHomeDir}"" --delete-user-data"; WorkingDir: "{app}"
Name: "{group}\安装与升级说明"; Filename: "{app}\docs\WINDOWS_INSTALL.md"
Name: "{group}\卸载 Stratide"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Stratide"; Filename: "{app}\stratide-launcher.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\stratide-launcher.exe"; Parameters: "--home ""{code:GetHomeDir}"""; Description: "立即打开 Stratide"; Flags: nowait postinstall skipifsilent

#endif
#if TestMode != "1"
[UninstallRun]
Filename: "{app}\stratide-launcher.exe"; Parameters: "--home ""{code:GetHomeDir}"" --stop --quiet"; Flags: runhidden waituntilterminated; RunOnceId: "StopStratide"
Filename: "{app}\stratide-launcher.exe"; Parameters: "--home ""{code:GetHomeDir}"" --autostart remove --quiet"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveAutostart"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

#endif
[Code]
var
  HomeDir: String;
  DataDir: String;
  PortValue: Integer;
  Migrating: Boolean;
  DataPage: TInputDirWizardPage;
  PortPage: TInputQueryWizardPage;

function GetHomeDir(Param: String): String;
var
  EnvHome: String;
begin
  if HomeDir <> '' then
    Result := HomeDir
  else
  begin
    EnvHome := GetEnv('STRATIDE_HOME');
    if EnvHome <> '' then
      Result := EnvHome
    else
      Result := ExpandConstant('{localappdata}\Stratide');
  end;
end;

function InitializeSetup: Boolean;
var
  ParamHome: String;
  ParamData: String;
begin
  Result := True;
  DataDir := '';
  PortValue := 0;
  ParamHome := ExpandConstant('{param:HOME}');
  if (ParamHome = '') or (Pos('{param:', ParamHome) = 1) then
    ParamHome := GetEnv('STRATIDE_HOME');
  if ParamHome = '' then
    ParamHome := ExpandConstant('{localappdata}\Stratide');
  HomeDir := ParamHome;
  ParamData := ExpandConstant('{param:DATA}');
  if (ParamData <> '') and (Pos('{param:', ParamData) <> 1) then
    DataDir := ParamData;
  Migrating := FileExists(HomeDir + '\runtime.json');
  if not Migrating then
  begin
    if DataDir = '' then
      DataDir := ExpandConstant('{localappdata}\Stratide\data');
    PortValue := 8710;
  end;
end;

procedure InitializeWizard;
begin
  DataPage := CreateInputDirPage(wpSelectDir, '数据目录',
    '行情、Paper 账本、研究记录和未知费用预留保存在哪里？',
    '升级与卸载默认保留该目录；只有明确选择“删除本地数据”才会删除。', False, '');
  DataPage.Add('');
  DataPage.Values[0] := DataDir;

  PortPage := CreateInputQueryPage(wpSelectDir, '本地服务端口',
    'Dashboard 只监听 127.0.0.1。',
    '默认 8710。若端口已被其他程序占用，请在此选择另一个端口。');
  PortPage.Add('端口（1024–65535）：', False);
  PortPage.Values[0] := IntToStr(PortValue);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if Migrating and ((PageID = DataPage.ID) or (PageID = PortPage.ID)) then
    Result := True;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = DataPage.ID then
  begin
    DataDir := DataPage.Values[0];
    if (Length(DataDir) < 4) or (Pos(':', DataDir) <> 2) then
    begin
      MsgBox('请选择绝对路径的数据目录。', mbError, MB_OK);
      Result := False;
    end
    else if CompareText(DataDir, ExpandConstant('{app}')) = 0 then
    begin
      MsgBox('数据目录不能与程序目录相同；否则卸载会误删用户数据。', mbError, MB_OK);
      Result := False;
    end;
  end
  else if CurPageID = PortPage.ID then
  begin
    PortValue := StrToIntDef(PortPage.Values[0], 0);
    if (PortValue < 1024) or (PortValue > 65535) then
    begin
      MsgBox('端口必须是 1024–65535 之间的整数。', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  if FileExists(ExpandConstant('{app}\stratide-launcher.exe')) then
    Exec(ExpandConstant('{app}\stratide-launcher.exe'),
      '--home "' + GetHomeDir('') + '" --stop --quiet', '',
      SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Args: String;
  ResultCode: Integer;
begin
  Log('Stratide step=' + IntToStr(Ord(CurStep)) + ' home=' + GetHomeDir('') +
    ' data=' + DataDir + ' migrate=' + IntToStr(Ord(Migrating)));
  if CurStep <> ssPostInstall then Exit;
  if not Migrating then
  begin
    Args := '--home "' + GetHomeDir('') + '" --configure --quiet --port ' +
      IntToStr(PortValue) + ' --data-dir "' + DataDir + '"';
    if (not Exec(ExpandConstant('{app}\stratide-launcher.exe'), Args, '',
      SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
      MsgBox('Stratide 无法写入本机运行配置。程序仍可启动并生成默认配置，但所选端口/数据目录未保存。',
        mbError, MB_OK);
    Log('Stratide configure result=' + IntToStr(ResultCode));
  end;
  if WizardIsTaskSelected('autostart') then
    if (not Exec(ExpandConstant('{app}\stratide-launcher.exe'),
      '--home "' + GetHomeDir('') + '" --autostart enable --quiet', '',
      SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
      MsgBox('登录自启未能创建（任务计划程序或当前用户注册表不可用）。Stratide 仍可手动使用；请在应用“运行与安装”页重试。',
        mbError, MB_OK);
end;