; CloudBlue PC — BỘ CÀI 1 FILE cho khách (Inno Setup 6). GitHub Actions biên dịch:  ISCC /DAppVer=1.120 installer.iss
;   → dist\CloudBluePC-Setup.exe : khách tải về, bấm mở → tự cài (không cần quyền Admin, không phải giải nén) → tự mở app + có biểu tượng ngoài Desktop.
;   App cài vào %LOCALAPPDATA%\Programs\CloudBlue\CloudBluePC — thư mục này CHỈ chứa CloudBluePC.exe + _internal (app tự cập nhật cần vậy),
;   nên file gỡ cài đặt (unins*.exe) nằm ở thư mục khác (UninstallFilesDir).
#ifndef AppVer
#define AppVer "1.0"
#endif

[Setup]
AppId={{B7C2D6A4-5E0F-4C1B-9A63-CB0017110A01}
AppName=CloudBlue PC
AppVersion={#AppVer}
AppVerName=CloudBlue PC {#AppVer}
AppPublisher=CloudBlue
AppPublisherURL=https://cloudblue.vn
AppSupportURL=https://cloudblue.vn
VersionInfoVersion={#AppVer}
DefaultDirName={localappdata}\Programs\CloudBlue\CloudBluePC
UninstallFilesDir={localappdata}\Programs\CloudBlue\go-cai-dat
DefaultGroupName=CloudBlue
PrivilegesRequired=lowest
DisableWelcomePage=yes
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableFinishedPage=yes
OutputDir=dist
OutputBaseFilename=CloudBluePC-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\CloudBluePC.exe
UninstallDisplayName=CloudBlue PC
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
CloseApplications=yes
RestartApplications=no

[Messages]
SetupAppTitle=Cài đặt
SetupWindowTitle=Cài đặt %1
ButtonInstall=&Cài đặt
ButtonCancel=Huỷ
ButtonNext=&Tiếp >
ButtonBack=< &Quay lại
WizardReady=Sẵn sàng cài đặt
ReadyLabel1=Bấm Cài đặt để cài [name] vào máy tính (không cần quyền Admin).
ReadyLabel2a=Bấm Cài đặt để tiếp tục.
ReadyLabel2b=Bấm Cài đặt để tiếp tục.
WizardInstalling=Đang cài đặt
InstallingLabel=Vui lòng chờ ít giây — đang cài [name]. Cài xong app tự mở.
ExitSetupTitle=Thoát cài đặt
ExitSetupMessage=Chưa cài xong. Thoát bây giờ thì app chưa được cài.%n%nThoát cài đặt?
ConfirmUninstall=Gỡ %1 khỏi máy tính này?
UninstalledAll=Đã gỡ %1 khỏi máy tính.

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\CloudBluePC\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autodesktop}\CloudBlue PC"; Filename: "{app}\CloudBluePC.exe"
Name: "{autoprograms}\CloudBlue PC"; Filename: "{app}\CloudBluePC.exe"

[Run]
Filename: "{app}\CloudBluePC.exe"; Flags: nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
