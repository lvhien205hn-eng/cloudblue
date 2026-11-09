# =====================================================================
#  setup.ps1 — Cài CloudBlue Cloud Phone lên MÁY WINDOWS (LDPlayer 9 · MuMu · MEmu) — 1 LỆNH làm hết phần tự động được
#  MÁY CHỦ MỚI: mở PowerShell bằng "Run as administrator", dán 1 dòng (đổi win4 / phone4 theo số máy):
#     New-Item -ItemType Directory -Force C:\blue | Out-Null; Remove-Item C:\blue\setup.ps1 -ErrorAction SilentlyContinue; curl.exe -fsSL -H "Accept: application/vnd.github.raw" -o C:\blue\setup.ps1 "https://api.github.com/repos/lvhien205hn-eng/cloudblue/contents/windows/setup.ps1"; if (-not (Test-Path C:\blue\setup.ps1) -or (Get-Item C:\blue\setup.ps1).Length -lt 5000) { curl.exe -fsSL -o C:\blue\setup.ps1 "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main/windows/setup.ps1?t=$(Get-Random)" }; Set-ExecutionPolicy -Scope Process Bypass -Force; & C:\blue\setup.ps1 -Node win4 -PubHost phone4.cloudblue.vn
#     (xoá bản cũ trước khi tải → tải hỏng thì báo lỗi, không lỡ chạy lại bản cũ; api.github.com hết lượt → lấy raw.githubusercontent)
#  Tự làm: giờ máy · tắt Hyper-V · Python · Node.js · adb (Google) · cloudflared · ws-scrcpy (trình phát hình) · tải phonectl/cloudphoned/cpapi
#          · cloudphone.conf (giả lập, phoneN/streamN, cổng 8188+N) · tường lửa · tự chạy khi bật máy · mở bảng CloudBlue (quyền Admin)
#  Cuối cùng in DANH SÁCH VIỆC LÀM TAY còn lại (giả lập, khoá Supabase, Cloudflare, cổng modem…) + lưu ở C:\blue\logs\viec-lam-tay.txt.
#  Chạy lại bao nhiêu lần cũng được — phần đã xong tự bỏ qua. winget hỏng / không có → tự tải thẳng bộ cài chính thức.
#  KHÔNG có -Node thì không tạo cloudphone.conf mới (tránh máy mới tự nhận là win1). Máy đã có conf: tên máy / tên miền lấy theo conf
#  (bảng CloudBlue chạy bộ cài không kèm tham số); -Node khác NODE_ID trong conf → dừng, không đụng gì.
# =====================================================================
param([string]$Node = "win1", [string]$PubHost = "phone.cloudblue.vn")
$SETUP_VER = "2026-11-08e"
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Windows PowerShell 5.1: thanh tiến độ làm Invoke-WebRequest / Expand-Archive chậm gấp nhiều lần
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12   # Windows cũ mặc định TLS 1.0 → GitHub/Google từ chối
$B = "C:\blue"
$RAW = "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main"   # thêm ?t=… để luôn lấy bản mới nhất (không bị giới hạn lượt như api.github.com)
function Ok($m)   { Write-Host "  [OK] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  [!] $m" -ForegroundColor Yellow }
function Step($m) { Write-Host "`n== $m ==" -ForegroundColor Cyan }
function Get($url, $out) {
  $ErrorActionPreference = "Continue"   # bảng CloudBlue chạy bộ cài kèm *>&1 → dòng lỗi của curl không được làm dừng cả bộ cài (throw dưới vẫn dừng)
  # File của BlueRoblox: lấy qua api.github.com TRƯỚC (luôn là bản mới nhất — raw.githubusercontent hay trả bản cũ vài phút),
  # api hết lượt (60 lần/giờ) thì dùng raw.githubusercontent
  if ($url -like "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main/*") {
    $api = $url -replace "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main", "https://api.github.com/repos/lvhien205hn-eng/cloudblue/contents"
    & curl.exe -fsL -H "Accept: application/vnd.github.raw" -H "User-Agent: BlueRoblox-setup" -o $out $api   # hết lượt (403) → im lặng, lấy raw
    if ($LASTEXITCODE -eq 0) { return }
    $url = $url + "?t=" + [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() }
  & curl.exe -fsSL -H "Cache-Control: no-cache" -o $out $url
  if ($LASTEXITCODE -ne 0) { throw "Tải lỗi: $url" } }

Write-Host "CloudBlue setup $SETUP_VER" -ForegroundColor DarkGray
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Host "Hay mo PowerShell bang Run as administrator." -ForegroundColor Red; exit 1 }
New-Item -ItemType Directory -Force -Path $B, "$B\redroid", "$B\wstmp", "$B\apk-cai-san", "$B\logs" | Out-Null
Set-Location $B
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
function Dl($url, $out) { Invoke-WebRequest -UseBasicParsing -UserAgent "BlueRoblox-setup" -Uri $url -OutFile $out }
function RefreshPath { $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User") }
function ConfVal($k) {   # đọc 1 dòng KHOÁ=giá trị trong cloudphone.conf ("" nếu chưa có)
  if (-not (Test-Path "$B\cloudphone.conf")) { return "" }
  foreach ($l in (Get-Content "$B\cloudphone.conf" -Encoding UTF8)) { if ($l -match "^\s*$k\s*=\s*(.*)$") { return $Matches[1].Trim() } }
  return "" }
# DNS Cloudflare + Google (IPv4 + IPv6): DNS của modem/nhà mạng hay nhớ "không có tên" → tên miền phoneN.cloudblue.vn mới tạo không vào được
try { Get-NetAdapter | Where-Object Status -eq Up | ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ServerAddresses ("1.1.1.1","8.8.8.8","2606:4700:4700::1111","2001:4860:4860::8888") }; ipconfig /flushdns | Out-Null } catch {}
$WG = [bool](Get-Command winget -ErrorAction SilentlyContinue)   # Windows 10 bản cũ / Server không có winget → tải thẳng bộ cài chính thức
# winget có mà HỎNG (máy mới cài: App Installer cũ / đang tự cập nhật, nguồn lỗi…) → in vài dòng lỗi, bước đó tự tải thẳng bộ cài chính thức
function WgInstall($id) {
  if (-not $WG) { return }
  $ErrorActionPreference = "Continue"   # Windows PowerShell 5.1: dòng lỗi của winget không được làm dừng cả bộ cài
  Write-Host "  winget: dang cai $id (co the dung yen vai phut - dung bam Ctrl+C)" -ForegroundColor DarkGray
  $o = & winget install -e --id $id --scope machine --accept-source-agreements --accept-package-agreements 2>&1 | ForEach-Object { "$_" }
  $rc = $LASTEXITCODE
  RefreshPath
  if ($rc -ne 0) {
    Write-Host "  [!] winget $id loi (ma $rc) -> tai thang bo cai chinh thuc" -ForegroundColor Yellow
    $o | ForEach-Object { ("$_" -split "`r")[-1].Trim() } | Where-Object { $_ -match '[A-Za-z]{3}' } | Select-Object -Last 3 | ForEach-Object { Write-Host "      $_" -ForegroundColor DarkGray } } }
function Npm {   # npm in "npm WARN …" ra luồng lỗi → không để dừng bộ cài; trả mã thoát của npm (chữ của npm vẫn hiện + vào nhật ký của bảng)
  $ErrorActionPreference = "Continue"
  & npm.cmd @args | ForEach-Object { Write-Host $_ }
  $LASTEXITCODE }

# Tên máy chủ → tên miền + cổng: win4 → phone4.cloudblue.vn (cổng bảo vệ cpapi) · stream4.cloudblue.vn (phát hình dự phòng) · cổng phát hình 8192
# Máy đã cài (có cloudphone.conf) → lấy theo conf (bộ cài không sửa conf đã có)
$CONF0 = Test-Path "$B\cloudphone.conf"
$KNOWN = $CONF0 -or $PSBoundParameters.ContainsKey("Node")
if ($CONF0) {
  $cn = ConfVal "NODE_ID"
  if ($PSBoundParameters.ContainsKey("Node") -and $cn -and ($cn -ne $Node)) {
    throw "C:\blue\cloudphone.conf dang ghi NODE_ID=$cn, KHAC -Node $Node - chua lam gi ca. Kiem tra lai may nay la may nao. Neu dung la $Node (conf cu chep tu may khac) thi doi ten file conf:  Rename-Item C:\blue\cloudphone.conf cloudphone.conf.cu  roi chay lai lenh cai." }
  if ($cn) { $Node = $cn }
  $cp = ((ConfVal "PUBLIC_BASE") -replace '^https?://', '') -replace '[/:].*$', ''
  if ($cp) {
    if ($PSBoundParameters.ContainsKey("PubHost") -and ($PubHost.Trim().ToLower() -ne $cp.ToLower())) { Write-Host "  [!] cloudphone.conf dang ghi $cp (khac -PubHost $PubHost) - giu theo conf" -ForegroundColor Yellow }
    $PubHost = $cp } }
$NUM = [int]("0" + ($Node -replace '[^0-9]', ''))
if (-not $CONF0 -and -not $PSBoundParameters.ContainsKey("PubHost")) { $PubHost = if ($NUM -ge 2) { "phone$NUM.cloudblue.vn" } else { "phone.cloudblue.vn" } }
$PubHost = $PubHost.Trim().ToLower()
$SUB, $DOM = $PubHost -split '\.', 2
if (-not $DOM) { throw "Ten mien sai: $PubHost (dung dang phone4.cloudblue.vn)" }
$EXP = if ($NUM -ge 2) { "phone$NUM" } else { "phone" }
if (-not $CONF0 -and $PSBoundParameters.ContainsKey("Node") -and ($SUB -ne $EXP)) { throw "Ten mien $PubHost khong khop -Node $Node (may $Node dung $EXP.$DOM) - sua lai lenh cai" }
$SSUB = if ($SUB -like "phone*") { "stream" + $SUB.Substring(5) } else { "stream-" + $SUB }
$SHOST = "$SSUB.$DOM"
$SPORT = if ($NUM -ge 2) { 8188 + $NUM } else { 8189 }
if ($CONF0) {
  $cs = ((ConfVal "STREAM_WS") -replace '^wss?://', '') -replace '[/:].*$', ''
  if ($cs) { $SHOST = $cs; $SSUB = ($cs -split '\.', 2)[0] }
  $cport = ConfVal "STREAM_PORT"; if ($cport) { $SPORT = $cport } }
$PY = "C:\Program Files\Python312\python.exe"
$PYW = "C:\Program Files\Python312\pythonw.exe"

# Giả lập: LDPlayer 9 (Android 9) · MuMu (Android 12 + 15) · MEmu (Android 7)
# MuMu: file lệnh (mumu-cli.exe / MuMuManager.exe) nằm ở shell\ · nx_main\ · thư mục gốc · hoặc SÂU hơn (MuMu mới: nx_device\<bản>\shell\)
# → tìm giống phonectl: các chỗ hay gặp + conf MUMU_DIR + redroid\mumu_dir.txt + khoá gỡ cài đặt + chương trình MuMu đang chạy + thư mục Netease/MuMu ở mọi ổ cứng, sâu ≤ 3 cấp
function MuMuExe($d) {
  if (-not $d) { return "" }
  $d = "$d".Trim().TrimEnd("\")
  if (-not $d -or -not (Test-Path -LiteralPath $d -PathType Container)) { return "" }
  foreach ($r in "nx_main\mumu-cli.exe", "shell\MuMuManager.exe", "nx_main\MuMuManager.exe", "MuMuManager.exe", "mumu-cli.exe") {
    if (Test-Path -LiteralPath (Join-Path $d $r) -PathType Leaf) { return (Join-Path $d $r) } }
  $f = Get-ChildItem -LiteralPath $d -Recurse -Depth 3 -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq "mumu-cli.exe" -or $_.Name -eq "MuMuManager.exe" } | Select-Object -First 1
  if ($f) { return $f.FullName }
  return "" }
function MuMuRoot($f) { $d = Split-Path $f -Parent; if ((Split-Path $d -Leaf) -match '^(shell|nx_main)$') { $d = Split-Path $d -Parent }; $d }
function FindEmu {
  # giống phonectl / bảng: thư mục khai trong conf (LD_DIR / MEMU_DIR / MUMU_DIR) + chỗ MuMu dò được lần trước (redroid\mumu_dir.txt) + chỗ cài hay gặp
  $ldp = @((ConfVal "LD_DIR"), "C:\LDPlayer\LDPlayer9", "D:\LDPlayer\LDPlayer9", "C:\Program Files\LDPlayer\LDPlayer9", "C:\leidian\LDPlayer9", "D:\leidian\LDPlayer9") |
    Where-Object { $_ -and (Test-Path "$_\ldconsole.exe") } | Select-Object -First 1
  $memu = @((ConfVal "MEMU_DIR"), "C:\Program Files\Microvirt\MEmu", "D:\Program Files\Microvirt\MEmu", "C:\Microvirt\MEmu", "D:\Microvirt\MEmu", "C:\Program Files (x86)\Microvirt\MEmu") |
    Where-Object { $_ -and (Test-Path "$_\memuc.exe") } | Select-Object -First 1
  $mc = ""; try { if (Test-Path "$B\redroid\mumu_dir.txt") { $mc = "$(Get-Content "$B\redroid\mumu_dir.txt" -Raw -Encoding UTF8)".Trim() } } catch {}
  $cand = @((ConfVal "MUMU_DIR"), $mc, "C:\Program Files\Netease\MuMuPlayer", "D:\Program Files\Netease\MuMuPlayer", "C:\Program Files\Netease\MuMuPlayer-12.0", "D:\Program Files\Netease\MuMuPlayer-12.0",
            "C:\Program Files\Netease\MuMu Player 12", "D:\Program Files\Netease\MuMu Player 12", "C:\Program Files\Netease\MuMu", "D:\Program Files\Netease\MuMu",
            "C:\Program Files\Netease\MuMuPlayerGlobal-12.0", "C:\Program Files\MuMuPlayerGlobal-12.0", "D:\Program Files\MuMuPlayerGlobal-12.0")
  $mf = ""; foreach ($c in $cand) { $mf = MuMuExe $c; if ($mf) { break } }
  if (-not $mf) {   # MuMu cài ở ổ / thư mục khác
    $more = @()
    try {   # khoá gỡ cài đặt của MuMu
      $more += Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*", "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
                                "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*" -ErrorAction SilentlyContinue |
        Where-Object { "$($_.DisplayName) $($_.PSChildName)" -match "mumu" } |
        ForEach-Object { $_.InstallLocation; $_.InstallDir
          foreach ($v in $_.DisplayIcon, $_.UninstallString) { if ($v) { $x = (("$v" -replace '^"([^"]+)".*$', '$1') -replace ',\d+$', '').Trim(); if ($x -match '\.(exe|ico|dll)$') { $x = Split-Path $x -Parent }; $x; Split-Path $x -Parent } } } } catch {}
    try {   # chương trình MuMu đang chạy
      $more += Get-Process -ErrorAction SilentlyContinue | Where-Object { "$($_.Path)" -match 'mumu' } | ForEach-Object { $p = Split-Path $_.Path -Parent; $p; Split-Path $p -Parent } } catch {}
    try {   # thư mục Netease / MuMu ở mọi ổ cứng
      foreach ($dr in @((Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" -ErrorAction Stop).DeviceID)) {
        foreach ($pat in "\Program Files\Netease\*", "\Program Files (x86)\Netease\*", "\Netease\*", "\Program Files\MuMu*", "\Program Files (x86)\MuMu*", "\MuMu*") {
          $more += Get-Item -Path ($dr + $pat) -ErrorAction SilentlyContinue | Where-Object { $_.PSIsContainer } | ForEach-Object { $_.FullName } } } } catch {}
    foreach ($c in ($more | Where-Object { $_ } | Select-Object -Unique)) { try { $mf = MuMuExe $c } catch { $mf = "" }; if ($mf) { break } } }
  $mu = if ($mf) { MuMuRoot $mf } else { $null }
  if (-not $mu) {   # dự phòng: chỗ cài ghi trong khoá gỡ cài đặt của MuMu, có thư mục nx_main / shell
    try { $mu = @(Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*", "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
                                   "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*" -ErrorAction SilentlyContinue |
            Where-Object { "$($_.DisplayName) $($_.PSChildName)" -match "mumu" } | ForEach-Object { "$($_.InstallLocation)".Trim().TrimEnd("\") } |
            Where-Object { $_ -and ([IO.Directory]::Exists("$_\nx_main") -or [IO.Directory]::Exists("$_\shell")) })[0] } catch {} }
  [pscustomobject]@{ LDP = $ldp; MEMU = $memu; MUMU = $mu } }
function EmuDiag {   # không thấy giả lập → ghi lại đã tìm ở đâu, thấy gì (gửi hỗ trợ)
  try {
    $L = @("setup $SETUP_VER  $(Get-Date -Format s)  PowerShell $($PSVersionTable.PSVersion)")
    foreach ($d in @("C:\Program Files\Netease\MuMuPlayer", (ConfVal "MUMU_DIR")) | Where-Object { $_ } | Select-Object -Unique) {
      $L += "$d | thu muc=$([IO.Directory]::Exists($d)) | nx_main\mumu-cli=$([IO.File]::Exists("$d\nx_main\mumu-cli.exe")) | nx_main\MuMuManager=$([IO.File]::Exists("$d\nx_main\MuMuManager.exe")) | Test-Path=$(Test-Path -LiteralPath "$d\nx_main\mumu-cli.exe") | MuMuExe=[$(MuMuExe $d)]" }
    $L += @(Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*", "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
                             "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*" -ErrorAction SilentlyContinue |
            Where-Object { "$($_.DisplayName)" -match "mumu|ldplayer|memu" } | ForEach-Object { "go cai dat: $($_.DisplayName) $($_.DisplayVersion) | $($_.InstallLocation)" })
    $L | Set-Content -Encoding UTF8 "$B\logs\tim-gia-lap.txt"
    Write-Host "  (da ghi nhat ky do gia lap: C:\blue\logs\tim-gia-lap.txt - gui ho tro neu gia lap da cai ma van bao chua thay)" -ForegroundColor DarkGray
  } catch {} }

Step "0/8 Windows: gio may, Hyper-V, ao hoa"
& tzutil /s "SE Asia Standard Time"
[TimeZoneInfo]::ClearCachedData()   # PowerShell nhớ múi giờ CŨ → không xoá thì Set-Date ghi giờ lệch đúng bằng chênh lệch 2 múi giờ
try {   # giờ máy sai → web báo máy chủ "Mất kết nối" (win3 từng lệch 7 tiếng; w32tm /resync hay treo → lấy giờ theo Google)
  $hd = [string](Invoke-WebRequest -UseBasicParsing -Method Head -TimeoutSec 20 -Uri "https://www.google.com").Headers["Date"]
  $gu = [DateTime]::Parse($hd, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AdjustToUniversal)   # giờ UTC của Google
  $off = ([DateTime]::UtcNow - $gu).TotalSeconds
  if ([Math]::Abs($off) -gt 60) { Set-Date $gu.ToLocalTime() | Out-Null; Ok ("Da chinh gio may (truoc do lech " + [int]$off + " giay)") } else { Ok "Gio may dung" }
} catch { Warn "Chua kiem duoc gio may (khong vao duoc google.com)" }
# Hyper-V bật → giả lập chạy chậm / không chạy. Tắt rồi phải KHỞI ĐỘNG LẠI máy mới có tác dụng.
$HVOFF = @(); $HVFAIL = @()
foreach ($f in "Microsoft-Hyper-V-All", "VirtualMachinePlatform", "HypervisorPlatform") {
  $st = ""
  try { $st = "$((Get-WindowsOptionalFeature -Online -FeatureName $f -ErrorAction Stop).State)" } catch {}   # Windows Home: không có Hyper-V → bỏ qua
  if ($st -like "Enable*") {
    Write-Host "  dang tat $f (1-2 phut)..." -ForegroundColor DarkGray
    try { Disable-WindowsOptionalFeature -Online -FeatureName $f -NoRestart -ErrorAction Stop | Out-Null; $HVOFF += $f }
    catch { $HVFAIL += $f; Warn "Chua tat duoc ${f}: $($_.Exception.Message)" } }
  elseif ($st -eq "DisablePending") { $HVOFF += $f } }
if ($HVOFF.Count) { Warn "Vua tat $($HVOFF -join ', ') - can KHOI DONG LAI may" } elseif (-not $HVFAIL.Count) { Ok "Hyper-V da tat" }
$VBS = $false; $VTOFF = $false
try { $VBS = @((Get-CimInstance -Namespace "root\Microsoft\Windows\DeviceGuard" -ClassName Win32_DeviceGuard -ErrorAction Stop).SecurityServicesRunning) -contains 2 } catch {}   # 2 = Memory integrity đang chạy
try { $VTOFF = (-not (Get-CimInstance Win32_ComputerSystem).HypervisorPresent) -and ((Get-CimInstance Win32_Processor | Select-Object -First 1).VirtualizationFirmwareEnabled -eq $false) } catch {}
if ($VTOFF) { Warn "Ao hoa (VT-x / SVM) dang TAT trong BIOS - gia lap se khong chay" }
$EM = FindEmu; $LDP = $EM.LDP; $MEMU = $EM.MEMU; $MUMU = $EM.MUMU
$EMUS = @($LDP, $MEMU, $MUMU) | Where-Object { $_ } | Select-Object -Unique
if ($EMUS) { Ok "Gia lap: $EMUS" }
else { Warn "Chua thay gia lap. Trong luc cho cai: cai MuMu Player (trang chinh thuc mumuplayer.com) + tao 2 may mau tpl_a12, tpl_a15 - gan cuoi bo cai se kiem lai" }

Step "1/8 Python"
# Python 3.12 (64-bit) đã cài CHỖ KHÁC (win4: C:\Python312; hoặc cài riêng cho tài khoản) → bộ cài python.org thấy "đã có" nên thoát mã 0
# mà không cài vào C:\Program Files\Python312 → chép nguyên thư mục đó sang (Python chạy được ở thư mục bất kỳ; KHÔNG gỡ bản gốc)
function Is64($dir) { $o = & (Join-Path $dir "python.exe") -c "import struct; print(struct.calcsize('P') * 8)"; "$o".Trim() -eq "64" }
function FindPy312 {
  $c = @()
  foreach ($k in "HKLM:\SOFTWARE\Python\PythonCore\3.12\InstallPath", "HKCU:\Software\Python\PythonCore\3.12\InstallPath") { try { $c += (Get-ItemProperty $k -ErrorAction Stop).'(default)' } catch {} }
  $c += "C:\Python312", "$env:LOCALAPPDATA\Programs\Python\Python312"
  $c | Where-Object { $_ -and (Test-Path (Join-Path $_ "python.exe")) } | ForEach-Object { "$_".TrimEnd("\") } |
    Where-Object { ($_ -ne "C:\Program Files\Python312") -and (Is64 $_) } | Select-Object -First 1 }
if (-not (Test-Path $PY) -and -not (FindPy312)) { WgInstall "Python.Python.3.12" }
if (-not (Test-Path $PY) -and -not (FindPy312)) {   # 3.12.10 = bản 3.12 cuối cùng có bộ cài Windows
  Write-Host "  tai Python 3.12.10 tu python.org (1-3 phut)..." -ForegroundColor DarkGray
  Get "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe" "$B\py-setup.exe"
  $rc = (Start-Process -Wait -PassThru "$B\py-setup.exe" -ArgumentList '/quiet InstallAllUsers=1 PrependPath=1 Include_test=0 TargetDir="C:\Program Files\Python312" /log C:\blue\logs\py-setup.log').ExitCode
  Remove-Item "$B\py-setup.exe" -ErrorAction SilentlyContinue; RefreshPath }
if (-not (Test-Path $PY)) {
  $op = FindPy312
  if ($op) { Write-Host "  may da co Python 3.12 o $op -> chep sang C:\Program Files\Python312" -ForegroundColor DarkGray
             & robocopy $op "C:\Program Files\Python312" /E /NFL /NDL /NJH /NJS /NP /R:1 /W:1 | Out-Null } }
if (-not (Test-Path $PY)) { throw "Chua cai duoc Python 3.12 (ma $rc; 1618 = Windows dang cai thu khac, cho 10 phut roi chay lai). Nhat ky: C:\blue\logs\py-setup*.log" }
Ok $PY

Step "2/8 Node.js (de chay trinh phat hinh ws-scrcpy)"
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { WgInstall "OpenJS.NodeJS.LTS" }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {   # Node 22 LTS mới nhất (tên file đọc từ nodejs.org); đọc không được → 22.12.0
  $nv = "22.12.0"
  try { $s = (& curl.exe -fsSL "https://nodejs.org/dist/latest-v22.x/SHASUMS256.txt") -join "`n"; if ($s -match 'node-v(22\.\d+\.\d+)-x64\.msi') { $nv = $Matches[1] } } catch {}
  Write-Host "  tai Node.js $nv tu nodejs.org..." -ForegroundColor DarkGray
  Get "https://nodejs.org/dist/v$nv/node-v$nv-x64.msi" "$B\node.msi"
  $rc = (Start-Process -Wait -PassThru msiexec.exe -ArgumentList "/i `"$B\node.msi`" /qn /norestart /l*v `"$B\logs\node-setup.log`"").ExitCode
  Remove-Item "$B\node.msi" -ErrorAction SilentlyContinue; RefreshPath
  if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw "Chua cai duoc Node.js (ma $rc). Nhat ky: C:\blue\logs\node-setup.log" } }
$NODEEXE = (Get-Command node).Source; Ok "node $(node --version)"   # KHÔNG đặt tên $NODE — PowerShell không phân biệt hoa/thường, sẽ ghi đè tham số -Node

Step "3/8 adb (Google platform-tools)"
if (-not (Test-Path "$B\platform-tools\adb.exe")) {
  Get "https://dl.google.com/android/repository/platform-tools-latest-windows.zip" "$B\pt.zip"
  Expand-Archive -Force "$B\pt.zip" $B; Remove-Item "$B\pt.zip" }
[Environment]::SetEnvironmentVariable("ADB_LOCAL_TRANSPORT_MAX_PORT", "5553", "Machine"); $env:ADB_LOCAL_TRANSPORT_MAX_PORT = "5553"   # adb không tự dò emulator-55xx (LDPlayer hiện mỗi máy 2 lần)
Ok "$B\platform-tools\adb.exe"

Step ("4/8 cloudflared" + $(if ($KNOWN) { " (duong ham $PubHost)" } else { "" }))
$CFX = "C:\Program Files (x86)\cloudflared\cloudflared.exe"   # nơi bộ cài .msi chính thức đặt cloudflared (bảng CloudBlue tìm ở đây nếu PATH không có)
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue) -and -not (Test-Path $CFX)) { WgInstall "Cloudflare.cloudflared" }
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue) -and -not (Test-Path $CFX)) {
  Write-Host "  tai cloudflared tu GitHub (Cloudflare)..." -ForegroundColor DarkGray
  Get "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.msi" "$B\cf.msi"
  $rc = (Start-Process -Wait -PassThru msiexec.exe -ArgumentList "/i `"$B\cf.msi`" /qn /norestart /l*v `"$B\logs\cf-setup.log`"").ExitCode
  Remove-Item "$B\cf.msi" -ErrorAction SilentlyContinue; RefreshPath
  if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue) -and -not (Test-Path $CFX)) { throw "Chua cai duoc cloudflared (ma $rc). Nhat ky: C:\blue\logs\cf-setup.log" } }
Ok "cloudflared da cai"

Step "5/8 ws-scrcpy (trinh phat hinh may len web) — 3-8 phut"
if (-not (Test-Path "$B\ws-scrcpy\dist\index.js")) {
  Get "https://codeload.github.com/NetrisTV/ws-scrcpy/zip/refs/heads/master" "$B\ws.zip"
  if (Test-Path "$B\ws-src") { Remove-Item -Recurse -Force "$B\ws-src" }
  Expand-Archive -Force "$B\ws.zip" "$B\ws-src"; Remove-Item "$B\ws.zip"
  $src = (Get-ChildItem "$B\ws-src" -Directory | Select-Object -First 1).FullName
  Push-Location $src
  # bỏ các phần cần biên dịch C++ (shell, iOS) — không dùng tới
  & node -e "const f='package.json',d=JSON.parse(require('fs').readFileSync(f));delete d.optionalDependencies;delete d.scripts.postinstall;['node-pty','ios-device-lib','node-mjpeg-proxy'].forEach(k=>delete d.dependencies[k]);require('fs').writeFileSync(f,JSON.stringify(d,null,2))"
  # chỉ dịch TypeScript, bỏ kiểm tra kiểu (các file iOS/shell không dùng tới làm báo lỗi)
  (Get-Content webpack\ws-scrcpy.common.ts -Raw) -replace "\{ loader: 'ts-loader' \}", "{ loader: 'ts-loader', options: { transpileOnly: true } }" | Set-Content -Encoding utf8 webpack\ws-scrcpy.common.ts
  Set-Content -Encoding ascii build.config.override.json '{"INCLUDE_ADB_SHELL": false, "INCLUDE_APPL": false, "USE_QVH_SERVER": false, "USE_WDA_MJPEG_SERVER": false}'
  if (Test-Path package-lock.json) { Remove-Item package-lock.json }
  if ((Npm "install" "--ignore-scripts" "--no-audit" "--no-fund") -ne 0) { throw "npm install loi - chay lai lenh cai" }
  if ((Npm "run" "dist") -ne 0) { throw "build ws-scrcpy loi - chay lai lenh cai" }
  Pop-Location
  if (Test-Path "$B\ws-scrcpy") { Remove-Item -Recurse -Force "$B\ws-scrcpy" }
  New-Item -ItemType Directory -Force "$B\ws-scrcpy" | Out-Null
  Copy-Item -Recurse "$src\dist" "$B\ws-scrcpy\dist"
  Push-Location "$B\ws-scrcpy\dist"; $rc = Npm "install" "--omit=dev" "--ignore-scripts" "--no-audit" "--no-fund"; Pop-Location
  if ($rc -ne 0) { Remove-Item -Recurse -Force "$B\ws-scrcpy" -ErrorAction SilentlyContinue; throw "npm install (ban chay) loi (ma $rc) - chay lai lenh cai" }   # xoá → lần sau dựng lại, không bỏ qua bản thiếu thư viện
  Remove-Item -Recurse -Force "$B\ws-src" }
Ok "$B\ws-scrcpy\dist"
# Trình phát hình trên trình duyệt mặc định GIỮ tới 100ms khung hình chờ vẽ (maxFps/10 khung) → hình chạy theo sau tay.
# Sửa: chỉ giữ khung MỚI NHẤT (vẽ ngay khung mới, bỏ khung cũ) → bớt tới ~100ms trễ.
Get-ChildItem "$B\ws-scrcpy\dist" -Recurse -Filter *.js -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch '\\node_modules\\' } | ForEach-Object {
  $t = [IO.File]::ReadAllText($_.FullName)
  if ($t -match 'videoSettings\.maxFps\s*/\s*10') { [IO.File]::WriteAllText($_.FullName, ($t -replace 'videoSettings\.maxFps\s*/\s*10', 'videoSettings.maxFps*0')); Ok "it tre: $($_.Name)" } }   # giữ "this." phía trước → vẫn đúng cú pháp
# chặn máy khác trong mạng vào thẳng cổng 8000 (chỉ đi qua cpapi 8010 + Cloudflare)
netsh advfirewall firewall delete rule name="BlueRoblox chan 8000" | Out-Null
netsh advfirewall firewall add rule name="BlueRoblox chan 8000" dir=in action=block protocol=TCP localport=8000,8010 remoteip=localsubnet | Out-Null

Step "6/8 Tai chuong trinh CloudBlue"
Write-Host "  cai thu vien Python (1-2 phut)..." -ForegroundColor DarkGray
& { $ErrorActionPreference = "Continue"; & $PY -m pip install --quiet --disable-pip-version-check pillow windows-capture numpy cryptography 2>&1 | Out-Null }   # phát hình app: quay cửa sổ + chứng chỉ TLS
if ($LASTEXITCODE -ne 0) { Warn "pip chua cai du thu vien (ma $LASTEXITCODE) - chay lai lenh cai sau it phut" }
foreach ($f in "cloudphoned.py", "cpapi.py") { Get "$RAW/$f" "$B\$f" }
foreach ($f in "phonectl.py", "run.py", "remake.py", "keep.bat", "start-blue.bat", "panel.py", "wallpaper.png", "donweb.py", "kiemtra.py", "suachua.ps1", "bluestream.py", "doi-ten-mien.py", "baomat.py") { Get "$RAW/windows/$f" "$B\$f" }
Ok "Da tai phonectl / cloudphoned / cpapi / bluestream / bang dieu khien"

Step ("7/8 Gia lap + cau hinh may chu" + $(if ($KNOWN) { " ($Node - $PubHost)" } else { "" }))
$EM = FindEmu; $LDP = $EM.LDP; $MEMU = $EM.MEMU; $MUMU = $EM.MUMU
$EMUS = @($LDP, $MEMU, $MUMU) | Where-Object { $_ } | Select-Object -Unique
$EMUOK = [bool]$EMUS
if (-not $EMUOK) { EmuDiag }
if ($EMUOK) {
  # Giả lập kèm adb.exe cũ → 2 bản adb tranh nhau làm rớt máy → thay bằng bản của Google (giữ bản cũ .bak)
  $ADBD = @()
  if ($LDP) { $ADBD += $LDP } elseif ($MEMU) { $ADBD += $MEMU }
  if ($MUMU) { $MR = $MUMU -replace '\\nx_device\\.*$', ''   # MuMu mới: thư mục gốc nằm trên nx_device\<bản>
              $ADBD += @(Get-ChildItem -LiteralPath $MR -Recurse -Depth 3 -File -Filter adb.exe -ErrorAction SilentlyContinue | ForEach-Object { $_.DirectoryName } | Select-Object -Unique) }
  Get-Process adb -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  foreach ($D in $ADBD) {
    foreach ($f in "adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll") {
      try {
        if ((Test-Path "$D\$f") -and -not (Test-Path "$D\$f.bak")) { Copy-Item "$D\$f" "$D\$f.bak" }
        Copy-Item -Force "$B\platform-tools\$f" "$D\$f"
      } catch { Warn "Chua thay duoc $D\$f (gia lap dang mo?) - tat gia lap roi chay lai neu may hay rot" } } }
  Ok "Gia lap: $EMUS (da dung chung adb cua Google)" }
else { Warn "Chua thay gia lap (LDPlayer 9 / MuMu / MEmu) - chua tao cau hinh" }
$NEEDNODE = $false; $CONFNEW = $false
if (-not (Test-Path "$B\cloudphone.conf") -and $EMUOK) {
  if (-not $PSBoundParameters.ContainsKey("Node")) { $NEEDNODE = $true; Warn "Chua tao cloudphone.conf: lenh cai thieu ten may chu (-Node winN)" }
  else {
$PRI = if ($Node -eq "win1") { "1" } else { "0" }
$ISMUMU = (-not $LDP) -and $MUMU -and (-not $MEMU)
$MAXR = if ($LDP) { "8" } else { "16" }     # 1 máy tối đa: Android 9 (LDPlayer 9) = 8GB · 8 nhân · MuMu (Android 12 / 15) = 16GB · 32 nhân · MEmu = 16 · 16
$MAXC = if ($LDP) { "8" } elseif ($ISMUMU) { "32" } else { "16" }
# MuMu: bán Android 12 + 15 (cần máy mẫu tpl_a12 / tpl_a15), không dựng máy sẵn, hình lấy thẳng từ Android (MuMu ẩn cửa sổ thì ngừng vẽ → không quay cửa sổ được)
$EMUL = if ($LDP) { "EMU=ld`nANDROIDS=9" } elseif ($ISMUMU) { "EMU=mumu`nANDROIDS=12,15`nCAPTURE=scrcpy" } else { "EMU=memu`nANDROIDS=7" }
$POOL = if ($ISMUMU) { "0" } else { "1" }
# PUBLIC_BASE / STREAM_WS / CPAPI_ORIGINS / NOTIFY_URL: giống doi-ten-mien.py <tên miền> <phoneN>
@"
# CloudBlue — cấu hình máy chủ (KHÔNG đưa file này lên GitHub)
SUPABASE_URL=https://nprftgodswlpzomcttal.supabase.co
SUPABASE_SERVICE_KEY=DAN_SERVICE_ROLE_KEY_VAO_DAY
PUBLIC_BASE=https://$PubHost
STREAM_WS=wss://$SHOST/v2/stream
CPAPI_ORIGINS=https://$DOM,https://www.$DOM
NOTIFY_URL=https://$DOM/api/notify-admin
NODE_ID=$Node
PRIMARY=$PRI
LIMIT_PCT=90
RAM_OVER=1
CPU_OVER=1.8
WIN_VCPU_OVER=1.8
WIN_RAM_RESERVE=3
RAM_BUSY_PCT=98
$EMUL
MEMU_MAX_RAM=$MAXR
MEMU_MAX_CPU=$MAXC
MEMU_RENDER=1
MEMU_GMEM_OPT=1
POOL_SIZE=$POOL
STREAM_PORT=$SPORT
"@ | Set-Content -Encoding utf8 "$B\cloudphone.conf"
    $CONFNEW = $true; Ok "Da tao cloudphone.conf" } }
$CONFOK = Test-Path "$B\cloudphone.conf"
if ($CONFOK) {
  $nl = (Get-Content "$B\cloudphone.conf" -Encoding UTF8 | Where-Object { $_ -match '^(NODE_ID|PUBLIC_BASE|EMU|ANDROIDS|STREAM_PORT)=' }) -join "  "
  Ok "$B\cloudphone.conf  ($nl)" }

Step "8/8 Tuong lua + tu chay khi bat may"
# Windows hỏi "cho Python dùng mạng?" mà bấm Cancel → Windows tạo luật CHẶN Python → app không vào thẳng được máy (đã gặp ở win3)
try {
  $blk = @(Get-NetFirewallApplicationFilter -ErrorAction Stop | Where-Object { "$($_.Program)" -match '\\pythonw?\.exe$' } |
           Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object { "$($_.Action)" -eq "Block" -and "$($_.Direction)" -eq "Inbound" })
  if ($blk.Count) { $blk | Remove-NetFirewallRule -ErrorAction SilentlyContinue; Ok "Da go $($blk.Count) luat tuong lua CHAN Python" } } catch {}
foreach ($p in $PY, $PYW) {   # cho phép sẵn → Windows khỏi hỏi (giống bấm "Allow access")
  $fn = "CloudBlue " + (Split-Path $p -Leaf)
  netsh advfirewall firewall delete rule name="$fn" | Out-Null
  netsh advfirewall firewall add rule name="$fn" dir=in action=allow program="$p" enable=yes | Out-Null }
$SP = ConfVal "STREAM_PORT"; if (-not $SP) { $SP = "$SPORT" }
netsh advfirewall firewall delete rule name="BlueRoblox Stream TCP" | Out-Null
netsh advfirewall firewall add rule name="BlueRoblox Stream TCP" dir=in action=allow protocol=TCP "localport=$SP" | Out-Null
Ok "Tuong lua: mo cong TCP $SP (phat hinh), Python khong bi chan"
if ($CONFOK) {
  $lnk = "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp\BlueRoblox.lnk"
  $ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut($lnk)
  if (Get-ScheduledTask -TaskName "BlueRoblox" -ErrorAction SilentlyContinue) { Remove-Item $lnk -ErrorAction SilentlyContinue }   # đã có tự chạy quyền Admin (nút 🔑)
  else { $s.TargetPath = $PYW; $s.Arguments = "`"$B\panel.py`" --auto"; $s.WorkingDirectory = $B; $s.Save() }
  $d = $ws.CreateShortcut("$env:Public\Desktop\CloudBlue.lnk"); $d.TargetPath = $PYW; $d.Arguments = "`"$B\panel.py`""; $d.WorkingDirectory = $B; $d.Save()
  Remove-Item "$env:Public\Desktop\BlueRoblox.lnk" -ErrorAction SilentlyContinue
  Ok "Bat may Windows -> tu chay CloudBlue (bieu tuong CloudBlue tren Desktop)"
  # mở bảng CloudBlue bằng quyền Admin (chỉ 1 bảng mỗi máy — đang mở thì thôi)
  $pan = @(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe' OR Name='BlueRobloxServer.exe'" -ErrorAction SilentlyContinue |
           Where-Object { "$($_.Name)" -eq "BlueRobloxServer.exe" -or "$($_.CommandLine)" -match 'panel\.py' })   # bảng chạy bằng Python hoặc bằng BlueRobloxServer.exe
  if ($pan.Count) { Ok "Bang CloudBlue dang mo san" }
  else { Start-Process -FilePath $PYW -ArgumentList "`"$B\panel.py`"" -WorkingDirectory $B; Ok "Da mo bang CloudBlue (quyen Admin)" } }

# ===================== VIỆC LÀM TAY còn lại (đúng thứ tự nên làm) =====================
$TODO = New-Object System.Collections.ArrayList
function Todo($m) { [void]$TODO.Add($m) }
$RERUN = "Set-ExecutionPolicy -Scope Process Bypass -Force; & C:\blue\setup.ps1 -Node $(if ($KNOWN) { $Node } else { 'winN' })"
if ($VTOFF) { Todo "Bat ao hoa trong BIOS (Intel: Virtualization Technology / VT-x - AMD: SVM Mode), luu BIOS roi khoi dong lai" }
try { if (@(Get-CimInstance Win32_VideoController -ErrorAction Stop | Where-Object { "$($_.Name)" -match 'Basic Display' }).Count) {   # "Microsoft Basic Display Adapter" = card chưa có driver
        Todo "Cai driver card do hoa: Device Manager > Display adapters dang co 'Microsoft Basic Display Adapter' (chua co driver). NVIDIA: nvidia.com > Drivers, chon dung ten card, Windows 64-bit; cai xong khoi dong lai - thieu driver thi may khach man den" } } catch {}
if ($HVFAIL.Count) { Todo "Tat tay: Control Panel > Programs > Turn Windows features on or off > bo chon Hyper-V, Virtual Machine Platform, Windows Hypervisor Platform > OK (bo cai chua tat duoc: $($HVFAIL -join ', '))" }
if ($VBS) { Todo "Tat Memory integrity: Windows Security > Device security > Core isolation details > Memory integrity = Off (gia lap chay nhanh hon)" }
if ($HVOFF.Count -or $HVFAIL.Count -or $VBS) { Todo "KHOI DONG LAI may - xong mo PowerShell Admin, chay lai lenh cai de kiem tra:   $RERUN" }
if (-not $EMUOK -and -not $CONFOK) {
  Todo "Cai MuMu Player tu trang chinh thuc mumuplayer.com -> mo MuMu Multi-instance -> tao 1 may Android 12 + 1 may Android 15 -> doi ten thanh tpl_a12 va tpl_a15 -> de TAT ca 2"
  Todo "Chay lai lenh cai (tu tao cau hinh, tu chay, mo bang):   $RERUN" }
elseif ($NEEDNODE) { Todo "Chay lai lenh cai KEM TEN MAY CHU (N = so may):   Set-ExecutionPolicy -Scope Process Bypass -Force; & C:\blue\setup.ps1 -Node winN -PubHost phoneN.cloudblue.vn" }
else {
  $FRESH = $CONFNEW
  if (-not $EMUOK) { Todo "Bo cai khong tim thay thu muc gia lap (cloudphone.conf ghi EMU=$(ConfVal 'EMU')). Gia lap cai o cho khac: trong bang bam 'Chon gia lap' de chi dung thu muc" }
  else {
    try {   # máy mẫu còn thiếu (phonectl engine: chỉ tính bản Android tạo được thật)
      $ej = & { $ErrorActionPreference = "Continue"; & $PY "$B\phonectl.py" engine 2>$null } | Select-Object -Last 1 | ConvertFrom-Json
      foreach ($t in @($ej.missing_tpl)) { if ($t) { $v = "$t" -replace '\D', ''; $FRESH = $true; Todo "Tao may mau ${t}: trong MuMu Multi-instance tao 1 may Android $v, doi ten thanh $t, de TAT (thieu may mau thi web khong ban Android $v o may nay)" } } } catch {} }
  if ((ConfVal "SUPABASE_SERVICE_KEY").Length -lt 30) { $FRESH = $true
    Todo "Bang CloudBlue (da mo san): bam '2 Dan khoa Supabase' -> dan khoa service_role (Supabase > Project Settings > API Keys). KHONG gui khoa nay cho ai" }
  if (-not ((& sc.exe query cloudflared | Out-String) -match "SERVICE_NAME")) { $FRESH = $true
    Todo "Cloudflare: dash.cloudflare.com > Zero Trust > Networks > Tunnels > Create a tunnel > Cloudflared > dat ten $SUB > chon Windows > copy CA lenh (co chu eyJ...) > trong bang bam '3 Noi Cloudflare' > dan vao. KHONG gui lenh nay cho ai" }
  $dnsok = $true
  foreach ($h in $PubHost, $SHOST) { try { [void][System.Net.Dns]::GetHostAddresses($h) } catch { $dnsok = $false } }
  if (-not $dnsok) { $FRESH = $true
    Todo "Cloudflare, trong tunnel cua $Node them 2 dia chi (Public hostname / Add route): $PubHost -> http://localhost:8010  va  $SHOST -> http://localhost:8020. Xong vao DNS kiem tra co du 2 ban ghi CNAME $SUB va $SSUB (may cam)" }
  $LAN = ""
  try { $LAN = "$(@((Get-NetIPConfiguration -ErrorAction SilentlyContinue | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } | Select-Object -First 1).IPv4Address)[0].IPAddress)" } catch {}
  if (-not $LAN) { $LAN = "IP LAN cua may nay (go ipconfig)" }
  Todo "Modem/router (neu chua lam): gan IP co dinh $LAN cho may nay (theo dia chi MAC) + mo cong NAT / Port Forwarding TCP $SPORT -> $LAN (chi mo dung cong nay) - app noi thang vao may, it tre hon"
  if (-not (Get-ScheduledTask -TaskName "BlueRoblox" -ErrorAction SilentlyContinue)) { $FRESH = $true
    Todo "Bang CloudBlue: bam 'Tu dang nhap + tu chay' (go mat khau Windows NGAY TRONG BANG) - bat may la bang tu chay quyen Admin" }
  if ($FRESH) {
    Todo "Bang CloudBlue: bam 'Toi uu Windows', 'An cua so gia lap', roi 'TU DONG A->Z' -> phai ra 'XONG: moi thu da chay'"
    Todo "Web quan tri > danh sach may chu: $Node phai hien 'Dang chay'; nut cua no ghi 'Nhan may lai' thi bam de bat dau nhan don" } }

Set-Location $B
Write-Host "`n==================== XONG phan cai dat tu dong ====================" -ForegroundColor Yellow
if ($TODO.Count) {
  Write-Host "CON LAI LAM TAY - lam lan luot tu tren xuong:" -ForegroundColor Yellow
  for ($i = 0; $i -lt $TODO.Count; $i++) { Write-Host ("  {0}. {1}" -f ($i + 1), $TODO[$i]) }
  try { $TODO | Set-Content -Encoding UTF8 "$B\logs\viec-lam-tay.txt"; Write-Host "  (danh sach nay luu o C:\blue\logs\viec-lam-tay.txt)" -ForegroundColor DarkGray } catch {} }
else { Remove-Item "$B\logs\viec-lam-tay.txt" -ErrorAction SilentlyContinue; Write-Host "Khong con viec gi phai lam tay." -ForegroundColor Green }
