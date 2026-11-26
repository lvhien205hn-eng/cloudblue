# =====================================================================================================
#  cloudblue-iso-may-mau   (ban 26.11b)
#  TAO 1 FILE ISO "MAY MAU" cho VPS ao hoa (Proxmox): Windows goc + driver VirtIO + QEMU guest agent + phan mem CloudBlue PC.
#  Cai ISO nay len 1 may ao moi tren Proxmox la TU DONG HET: chia o, cai Windows, driver, QEMU guest agent, tai khoan khach VPS
#  (Admin, khong mat khau, tu dang nhap), phan mem CloudBlue (CHUA dang ky). Xong may de chay cho -> bang dieu khien may mau tren web
#  (hoac Shutdown + Convert to template).
#
#  Chay trong Windows PowerShell (Admin) tren may Windows 10 / 11 co file ISO Windows goc:
#     -Iso    "D:\Win2012R2.iso"        ISO Windows goc (Server 2012 R2 / 2016 / 2019 / 2022, Windows 10 LTSC) - duong dan hoac link tai thang
#     -Virtio "D:\virtio-win-0.1.215.iso"   ISO driver virtio-win (bo trong = tu tai dung ban: 2012 R2 -> 0.1.215, ban khac -> 0.1.271)
#     -Ban 2                            so thu tu ban Windows trong ISO (bo trong = tu chon ban Server co giao dien / Win10 LTSC)
#     -Out "D:\CloudBlue-MayMau-win2012r2.iso"   -Work "D:\cb-maymau"   -TaiKhoan VPS   -Key XXXXX-...(ISO khong phai ban dung thu)
#     -KhongHoi  -GiuWork  -KhongFfmpeg  -Nhanh main  -Nguon <thu muc kho cloudblue tai san>
#  ISO nay KHONG chua khoa bi mat nao (khong ma dang ky, khong khoa Supabase bi mat). XOA SACH o dia 0 cua may cai no.
# =====================================================================================================
param(
  [string]$Iso = "",
  [string]$Virtio = "",
  [string]$Out = "",
  [string]$Work = "",
  [string]$TaiKhoan = "VPS",
  [int]$Ban = 0,
  [string]$Key = "",
  [string]$Nhanh = "main",
  [string]$Nguon = "",
  [switch]$KhongHoi,
  [switch]$GiuWork,
  [switch]$KhongFfmpeg
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$VER = "26.11b"
$OwnerRepo = "lvhien205hn-eng/cloudblue"
$RawBase = "https://raw.githubusercontent.com/" + $OwnerRepo
$PYURL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
$UCRTURL = "https://download.microsoft.com/download/9/6/f/96fd0525-3ddf-423d-8845-5f92f4a6883e/Windows8.1-KB2999226-x64.msu"
$VIRTIOURL = "https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/archive-virtio/virtio-win-{0}-1/virtio-win-{0}.iso"
$UA = "cloudblue-iso-may-mau/" + $VER
$OSC_SHA = "2000160b2c5044691b2f9a0ac308e5207f273d4880a572457af16d05886ba861"
$WinpcFiles = @("lib/cbsys.py", "lib/cbcore.py", "lib/cbrec.py", "os/cb_provision.py", "os/provision.cmd", "os/cb_stage.py", "os/unattend.tpl.xml",
                "os/wallpaper.jpg", "agent/pcagent.py", "agent/pcremote.py", "agent/watch.cmd", "agent/cbpc.cmd")
$VmFiles = @("proxmox/vm/vm_build.py", "proxmox/vm/maymau.ps1", "proxmox/vm/SetupComplete.cmd", "proxmox/vm/pe.cmd")
$T0 = Get-Date
$Mounted = New-Object System.Collections.ArrayList
$Notes = New-Object System.Collections.ArrayList
$GetFileErr = ""
$OscInfo = ""
$OscWhy = New-Object System.Collections.ArrayList
$IsoRoot = ""

function Say([string]$m, [string]$c = "Gray") { Write-Host $m -ForegroundColor $c }
function Step([string]$m) { Write-Host ""; Write-Host ("== " + $m) -ForegroundColor Cyan }
function Note([string]$m) { [void]$Notes.Add($m); Write-Host ("   (!) " + $m) -ForegroundColor Yellow }

function Stop-Build([string]$m) {
  Write-Host ""
  Write-Host ("!! DUNG: " + $m) -ForegroundColor Red
  Write-Host "   Chup / chep phan chu tu dong '== ' gan nhat toi day gui ho tro." -ForegroundColor Red
  throw "cb-stop"
}

function Run-Exe([string]$exe, [string[]]$a) {
  $old = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $rc = 9009
  try {
    & $exe @a 2>&1 | ForEach-Object {
      # dong chu tren kenh loi cua chuong trinh ngoai (oscdimg in tien do o do): lay dung noi dung; dong trong thi bo (khong in "...RemoteException")
      $t = ""
      if ($_ -is [System.Management.Automation.ErrorRecord]) { if ($_.Exception) { $t = "" + $_.Exception.Message } } else { $t = "" + $_ }
      if ($t.Trim() -and ($t -notmatch '^System\.Management\.Automation\.RemoteException$')) { Write-Host ("   " + $t) }
    }
    $rc = $LASTEXITCODE
  } catch { Write-Host ("   " + $_) }
  $ErrorActionPreference = $old
  return $rc
}

function Get-Sha([string]$p) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLower() }
function Clean-Path([string]$p) { return ("" + $p).Trim().Trim('"').Trim("'").Trim() }
function Test-Link([string]$t) { return [bool]((("" + $t).Trim().Trim('"')) -match '^https?://') }

function Test-There([string]$p) {
  if (-not $p) { return $false }
  try { return [bool](Test-Path -LiteralPath $p) } catch { return $false }
}

function Get-File([string]$url, [string]$dst, [string]$agent = "") {
  # Tai 1 file (curl.exe cua Windows truoc, khong duoc thi Invoke-WebRequest). Loi thi ly do nam o $script:GetFileErr.
  $script:GetFileErr = ""
  $dir = Split-Path -Parent $dst
  if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
  if (Test-Path -LiteralPath $dst) { Remove-Item -LiteralPath $dst -Force }
  $curl = Join-Path $env:SystemRoot "System32\curl.exe"
  if (Test-Path -LiteralPath $curl) {
    $a = @("-fsSL", "--retry", "3", "--connect-timeout", "20", "-o", $dst)
    if ($agent) { $a += @("-A", $agent) }
    $a += $url
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    & $curl @a 2>$null | Out-Null
    $crc = $LASTEXITCODE
    $ErrorActionPreference = $old
    if (($crc -eq 0) -and (Test-Path -LiteralPath $dst) -and ((Get-Item -LiteralPath $dst).Length -gt 0)) { return $true }
    $script:GetFileErr = "curl ma " + $crc
  }
  try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $iw = @{ UseBasicParsing = $true; Uri = $url; OutFile = $dst }
    if ($agent) { $iw["UserAgent"] = $agent }
    Invoke-WebRequest @iw
    if ((Test-Path -LiteralPath $dst) -and ((Get-Item -LiteralPath $dst).Length -gt 0)) { return $true }
    $script:GetFileErr = ($script:GetFileErr + " ; tai ve file rong").Trim(" ;")
    return $false
  } catch {
    $script:GetFileErr = ($script:GetFileErr + " ; " + $_.Exception.Message).Trim(" ;")
    return $false
  }
}

function Test-FileLocked([string]$p) {
  if (-not $p) { return $false }
  if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { return $false }
  try {
    $fs = [System.IO.File]::Open($p, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
    $fs.Close()
    return $false
  } catch {
    $ex = $_.Exception
    while ($ex) {
      if ($ex -is [System.IO.IOException]) { return $true }
      $ex = $ex.InnerException
    }
    return $false
  }
}

function Get-FreeOut([string]$p) {
  # File ISO dich dang bi giu (may ao dang gan?) -> <ten>-2.iso, <ten>-3.iso ...
  if (-not (Test-FileLocked $p)) { return $p }
  $dir = Split-Path -Parent $p
  $stem = [System.IO.Path]::GetFileNameWithoutExtension($p)
  $ext = [System.IO.Path]::GetExtension($p)
  for ($i = 2; $i -le 21; $i++) {
    $c = Join-Path $dir ($stem + "-" + $i + $ext)
    if (-not (Test-FileLocked $c)) { return $c }
  }
  return ""
}

function Test-Pe([string]$p) {
  try {
    $it = Get-Item -LiteralPath $p
    if (($it.Length -lt 16KB) -or ($it.Length -gt 32MB)) { return $false }
    $fs = [IO.File]::OpenRead($it.FullName)
    try { $b0 = $fs.ReadByte(); $b1 = $fs.ReadByte() } finally { $fs.Close() }
    return [bool](($b0 -eq 77) -and ($b1 -eq 90))
  } catch { return $false }
}

function Find-Oscdimg([string]$dl) {
  # oscdimg.exe (cong cu dong ISO cua Microsoft): bo ADK da cai -> ban da tai lan truoc -> tai tu may chu ky hieu cua Microsoft (kiem ma SHA-256 da ghim).
  $c = @()
  foreach ($pf in @(${env:ProgramFiles(x86)}, $env:ProgramFiles)) {
    if ($pf) { foreach ($arch in @("amd64", "x86")) { $c += (Join-Path $pf ("Windows Kits\10\Assessment and Deployment Kit\Deployment Tools\" + $arch + "\Oscdimg\oscdimg.exe")) } }
  }
  foreach ($p in $c) { if ((Test-There $p) -and (Test-Pe $p)) { $script:OscInfo = "co san tren may: " + $p; return $p } }
  $dst = Join-Path $dl "oscdimg.exe"
  if ((Test-There $dst) -and (Test-Pe $dst)) { $script:OscInfo = "ban da tai lan truoc"; return $dst }
  Say "   tai oscdimg.exe (cong cu dong ISO cua Microsoft, ~150KB) ..." "DarkGray"
  foreach ($s in @(@("688CABB065000", $OSC_SHA), @("3D44737265000", ""))) {
    $url = "https://msdl.microsoft.com/download/symbols/oscdimg.exe/" + $s[0] + "/oscdimg.exe"
    $ok = Get-File $url $dst "Microsoft-Symbol-Server/10.0.0.0"
    if (-not $ok) { $ok = Get-File $url $dst }
    if (-not $ok) { [void]$script:OscWhy.Add($s[0] + ": tai loi (" + $script:GetFileErr + ")"); continue }
    $h = Get-Sha $dst
    if ($s[1] -and ($h -ne $s[1])) { [void]$script:OscWhy.Add($s[0] + ": ma kiem khac ban da ghim"); Remove-Item -LiteralPath $dst -Force -ErrorAction SilentlyContinue; continue }
    if ((-not $s[1]) -and (-not (Test-Pe $dst))) { [void]$script:OscWhy.Add($s[0] + ": khong phai chuong trinh Windows"); Remove-Item -LiteralPath $dst -Force -ErrorAction SilentlyContinue; continue }
    $script:OscInfo = "tai tu msdl.microsoft.com/" + $s[0] + $(if ($s[1]) { " (khop ma kiem da ghim)" } else { " (ban du phong)" })
    return $dst
  }
  return ""
}

function Mount-Iso([string]$path) {
  # Mo 1 file ISO -> "E:\". ISO dang mo san (bam dup trong Explorer) thi dung luon, khong thao ra khi xong.
  $full = (Get-Item -LiteralPath $path).FullName
  $di = $null
  try { $di = Get-DiskImage -ImagePath $full -ErrorAction Stop } catch { $di = $null }
  if (-not ($di -and $di.Attached)) {
    Mount-DiskImage -ImagePath $full | Out-Null
    [void]$script:Mounted.Add($full)
  }
  $letter = ""
  for ($i = 0; $i -lt 15; $i++) {
    try { $vols = @(Get-DiskImage -ImagePath $full | Get-Volume) } catch { $vols = @() }
    foreach ($v in $vols) { if ((-not $letter) -and $v.DriveLetter) { $letter = "" + $v.DriveLetter } }
    if ($letter) { break }
    Start-Sleep -Milliseconds 700
  }
  if (-not $letter) { Stop-Build ("Khong mo duoc file ISO: " + $path) }
  return ($letter + ":\")
}

function Get-IsoLabel([string]$root) {
  try { return ("" + (Get-Volume -DriveLetter $root.Substring(0, 1)).FileSystemLabel) } catch { return "" }
}

function Get-ImageList([string]$file) {
  # Cac ban trong install.wim / .esd: index, name, edition, version, itype (Server / Server Core / Client), lang, arch
  $res = @()
  try {
    foreach ($it in @(Get-WindowsImage -ImagePath $file)) {
      $d = Get-WindowsImage -ImagePath $file -Index $it.ImageIndex
      $iv = "" + $d.Version
      if ($d.SPBuild -and ($iv.Split(".").Count -lt 4)) { $iv = $iv + "." + $d.SPBuild }
      $lang = "en-US"
      try { if ($d.Languages -and $d.Languages.Count -gt 0) { $lang = "" + $d.Languages[[int]$d.DefaultLanguageIndex] } } catch { }
      $res += [pscustomobject]@{ index = [int]$it.ImageIndex; name = "" + $d.ImageName; edition = "" + $d.EditionId; version = $iv
                                 itype = "" + $d.InstallationType; lang = $lang; arch = [int]$d.Architecture }
    }
    return $res
  } catch { Say ("   (Get-WindowsImage loi: " + $_.Exception.Message + " -> doc bang dism)") "DarkGray" }
  $res = @()
  $txt = & dism.exe /English /Get-WimInfo "/WimFile:$file" 2>$null
  $idx = @($txt | Where-Object { $_ -match '^Index : (\d+)' } | ForEach-Object { [int]($_ -replace '^Index : ', '') })
  foreach ($i in $idx) {
    $t = & dism.exe /English /Get-WimInfo "/WimFile:$file" "/Index:$i" 2>$null
    $g = { param($k) $l = $t | Where-Object { $_ -match ("^" + $k + " : ") } | Select-Object -First 1; if ($l) { ($l -replace ("^" + $k + " : "), "").Trim() } else { "" } }
    $iv = & $g "Version"
    $spb = & $g "ServicePack Build"
    if ($spb -and ($iv.Split(".").Count -lt 4)) { $iv = $iv + "." + $spb }
    $arch = 0
    if ((& $g "Architecture") -eq "x64") { $arch = 9 }
    $lang = "en-US"
    $ll = $t | Where-Object { $_ -match '\(Default\)' } | Select-Object -First 1
    if ($ll) { $lang = ($ll -replace '\(Default\)', '').Trim() }
    $res += [pscustomobject]@{ index = $i; name = (& $g "Name"); edition = (& $g "Edition"); version = $iv; itype = (& $g "Installation"); lang = $lang; arch = $arch }
  }
  return $res
}

function Get-Input([string]$what, [string]$hint) {
  # Hoi 1 file: keo tha vao cua so (hoac dan duong dan / link tai thang). Enter trong -> "".
  Say ("   " + $hint) "White"
  $line = Clean-Path (Read-Host ("   " + $what))
  return $line
}

function Get-LinkFile([string]$url, [string]$name, [string]$alt = "") {
  # Link tai thang (http / https) -> <work>\dl\<ten>. Da tai roi (cung link) thi dung lai. $alt = link du phong (cung file, ten khac).
  $sha = [BitConverter]::ToString((New-Object Security.Cryptography.SHA256Managed).ComputeHash([Text.Encoding]::UTF8.GetBytes($url))).Replace("-", "").Substring(0, 12).ToLower()
  $dst = Join-Path $script:Dl ($name + "-" + $sha + ".iso")
  if ((Test-There $dst) -and ((Get-Item -LiteralPath $dst).Length -gt 100MB)) { Say ("   da tai link nay lan truoc: " + $dst) "DarkGray"; return $dst }
  Say ("   dang tai tu link (file lon, co the vai chuc phut): " + $url) "DarkGray"
  if (-not (Get-File $url ($dst + ".part") $UA)) {
    $e1 = $script:GetFileErr
    if ((-not $alt) -or (-not (Get-File $alt ($dst + ".part") $UA))) { Stop-Build ("Tai link loi: " + $e1 + ". Tai file do bang Chrome roi chay lai lenh: " + $url) }
  }
  Move-Item -LiteralPath ($dst + ".part") -Destination $dst -Force
  return $dst
}

function Get-Repo([string]$rel, [string]$dst) {
  # 1 file cua kho cloudblue: tu -Nguon (thu muc tai san) hoac GitHub (dung 1 ban commit cho moi file)
  if ($Nguon) {
    $src = Join-Path $Nguon ($rel -replace "/", "\")
    if (-not (Test-There $src)) { Stop-Build ("Thu muc nguon thieu file " + $rel) }
    New-Item -ItemType Directory -Force (Split-Path -Parent $dst) | Out-Null
    Copy-Item -LiteralPath $src -Destination $dst -Force
    return
  }
  if (-not (Get-File ($RawBase + "/" + $script:Rev + "/" + $rel) $dst $UA)) { Stop-Build ("Khong tai duoc " + $rel + " tu GitHub (" + $script:GetFileErr + ")") }
}

function Get-Rev {
  # Ma commit moi nhat cua nhanh -> tai moi file tu DUNG 1 ban (khong lan file cu / moi khi GitHub dang cap nhat). Khong hoi duoc -> ten nhanh.
  try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $r = Invoke-RestMethod -UserAgent $UA -Uri ("https://api.github.com/repos/" + $OwnerRepo + "/commits/" + $Nhanh) -TimeoutSec 20
    if (("" + $r.sha) -match '^[0-9a-f]{40}$') { return ("" + $r.sha) }
  } catch { }
  return $Nhanh
}

function Test-Signed([string]$p, [string]$who) {
  # Chu ky so hop le cua $who? -> "" (dat) hoac ly do
  try {
    $sg = Get-AuthenticodeSignature -LiteralPath $p
    if ($sg.Status -ne "Valid") { return ("chu ky so: " + $sg.Status) }
    if (-not (("" + $sg.SignerCertificate.Subject) -match $who)) { return ("ky boi " + $sg.SignerCertificate.Subject) }
    return ""
  } catch { return ("khong doc duoc chu ky so: " + $_.Exception.Message) }
}

# ----------------------------------------------------------------------------------------------------- bat dau
try {
  Write-Host ""
  Write-Host ("  CloudBlue - TAO ISO MAY MAU VPS AO HOA (ban " + $VER + ")") -ForegroundColor Green
  Write-Host "  1 file ISO: Windows + driver VirtIO + QEMU guest agent + phan mem CloudBlue. Cai len may ao Proxmox la tu xong het." -ForegroundColor Green
  Write-Host "  ======================================================" -ForegroundColor Green
  $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
  if (-not $isAdmin) { Stop-Build "Can mo Windows PowerShell bang quyen Admin (chuot phai nut Start > Windows PowerShell (Admin) / Terminal (Admin))." }
  if ($PSVersionTable.PSVersion.Major -lt 5) { Stop-Build "Can Windows PowerShell 5.1 (Windows 10 / 11)." }
  if (-not [Environment]::Is64BitOperatingSystem) { Stop-Build "Can Windows 64-bit." }
  if ($TaiKhoan -notmatch '^[A-Za-z][A-Za-z0-9_-]{0,19}$') { Stop-Build ("Ten tai khoan khach chi gom chu, so, - _ (toi da 20 ky tu): " + $TaiKhoan) }
  $Key = ("" + $Key).Trim().ToUpper()
  if ($Key -and ($Key -notmatch '^[0-9A-Z]{5}(-[0-9A-Z]{5}){4}$')) { Stop-Build "-Key phai co dang XXXXX-XXXXX-XXXXX-XXXXX-XXXXX" }

  # ---------------------------------------------------------------- 1. file ISO Windows
  Step "1/7  File ISO Windows goc"
  if ((-not $Iso) -and (-not $KhongHoi)) {
    $Iso = Get-Input "ISO Windows" "Keo tha file ISO Windows (Server 2012 R2 / 2016 / 2019 / 2022 hoac Windows 10 LTSC) vao cua so nay roi bam Enter (hoac dan link tai thang)."
  }
  $Iso = Clean-Path $Iso
  if (-not $Iso) { Stop-Build "Chua co file ISO Windows." }
  if ((-not (Test-Link $Iso)) -and (-not (Test-There $Iso))) { Stop-Build ("Khong thay file: " + $Iso) }
  if ((-not (Test-Link $Iso)) -and ($Iso -notmatch '\.iso$')) { Stop-Build ("Day khong phai file .iso: " + $Iso) }

  # ---------------------------------------------------------------- thu muc lam viec
  if (-not $Work) {
    $vols = @(Get-Volume | Where-Object { ($_.DriveType -eq "Fixed") -and $_.DriveLetter } | Sort-Object SizeRemaining -Descending)
    if ($vols.Count -eq 0) { Stop-Build "Khong tim thay o cung nao de lam viec - dung -Work D:\cb-maymau" }
    $Work = "" + $vols[0].DriveLetter + ":\cb-maymau"
    foreach ($v in $vols) { $prev = "" + $v.DriveLetter + ":\cb-maymau"; if (Test-Path -LiteralPath (Join-Path $prev "dl")) { $Work = $prev; break } }
  }
  $Work = Clean-Path $Work
  if ($Work -match '\s') { Stop-Build ("Thu muc lam viec khong duoc co dau cach: " + $Work) }
  New-Item -ItemType Directory -Force $Work | Out-Null
  $Dl = Join-Path $Work "dl"
  $Tool = Join-Path $Work "tool"
  $PyDir = Join-Path $Work "py"
  $IsoRoot = Join-Path $Work "iso"
  New-Item -ItemType Directory -Force $Dl | Out-Null
  Say ("   Thu muc lam viec: " + $Work) "DarkGray"
  if (Test-Link $Iso) { $Iso = Get-LinkFile $Iso "windows" }
  $Iso = (Get-Item -LiteralPath $Iso).FullName

  # ---------------------------------------------------------------- 2. phan mem CloudBlue + Python nhung
  Step "2/7  Tai phan mem CloudBlue + Python nhung 3.12"
  $Rev = "local"
  if (-not $Nguon) { $Rev = Get-Rev }
  if (Test-Path -LiteralPath $Tool) { Remove-Item -LiteralPath $Tool -Recurse -Force }
  New-Item -ItemType Directory -Force $Tool | Out-Null
  $man = Join-Path $Tool "winpc\manifest.json"
  Get-Repo "winpc/manifest.json" $man
  $mj = Get-Content -Raw -Encoding UTF8 -LiteralPath $man | ConvertFrom-Json
  foreach ($f in $WinpcFiles) {
    $dst = Join-Path $Tool ("winpc\" + ($f -replace "/", "\"))
    Get-Repo ("winpc/" + $f) $dst
    $want = "" + $mj.sha256.$f
    if (-not $want) { Stop-Build ("manifest.json khong co ma kiem cua " + $f) }
    if ((Get-Sha $dst) -ne $want) { Stop-Build ("File " + $f + " khong khop ma kiem (GitHub chua cap nhat xong?) - cho 5 phut roi chay lai lenh.") }
  }
  foreach ($f in $VmFiles) { Get-Repo $f (Join-Path $Tool ($f -replace "/", "\")) }
  $VmBuild = Join-Path $Tool "proxmox\vm\vm_build.py"
  if (-not (Select-String -LiteralPath $VmBuild -Pattern "cloudblue vm_build" -SimpleMatch -Quiet)) { Stop-Build "vm_build.py tai ve khong dung." }
  if (-not (Select-String -LiteralPath (Join-Path $Tool "proxmox\vm\maymau.ps1") -Pattern "cloudblue-may-mau" -SimpleMatch -Quiet)) { Stop-Build "maymau.ps1 tai ve khong dung." }
  Say ("   phan mem CloudBlue PC ban " + $mj.ver + " (" + $WinpcFiles.Count + " file khop ma kiem) + bo cai may mau - nguon " + $(if ($Nguon) { $Nguon } else { "GitHub " + $Rev.Substring(0, [Math]::Min(12, $Rev.Length)) })) "DarkGray"
  $cfgjs = Join-Path $Tool "config.js"
  Get-Repo "blueroblox-site/config.js" $cfgjs
  $cj = Get-Content -Raw -LiteralPath $cfgjs
  $SbUrl = ""; $SbKey = ""
  if ($cj -match 'supabaseUrl\s*:\s*"([^"]+)"') { $SbUrl = $Matches[1] }
  if ($cj -match 'supabaseAnonKey\s*:\s*"([^"]+)"') { $SbKey = $Matches[1] }
  if ((-not $SbUrl) -or (-not $SbKey)) { Stop-Build "Khong doc duoc dia chi he thong trong config.js cua web." }
  Say ("   dia chi he thong: " + $SbUrl + " (khoa CONG KHAI cua web)") "DarkGray"
  $zip = Join-Path $Dl "python-embed.zip"
  if ((-not (Test-There $zip)) -or ((Get-Item -LiteralPath $zip).Length -lt 5MB)) {
    if (-not (Get-File $PYURL $zip)) { Stop-Build ("Khong tai duoc Python tu python.org (" + $GetFileErr + ").") }
  }
  if (Test-Path -LiteralPath $PyDir) { Remove-Item -LiteralPath $PyDir -Recurse -Force }
  Expand-Archive -Force -LiteralPath $zip -DestinationPath $PyDir
  $PyExe = Join-Path $PyDir "python.exe"
  if (-not (Test-There $PyExe)) { Stop-Build "Giai nen Python loi (thieu python.exe) - xoa thu muc lam viec roi chay lai." }
  $why = Test-Signed $PyExe "Python Software Foundation"
  if ($why) { Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue; Stop-Build ("python.exe tai ve khong co chu ky hop le cua Python Software Foundation (" + $why + ").") }
  Say "   python.exe: chu ky Python Software Foundation hop le" "DarkGray"
  $CaPath = Join-Path $Dl "cacert.pem"
  if ((Get-File "https://curl.se/ca/cacert.pem" $CaPath) -and ((Get-Item -LiteralPath $CaPath).Length -gt 100KB) -and (Select-String -LiteralPath $CaPath -Pattern "BEGIN CERTIFICATE" -SimpleMatch -Quiet)) {
    Say "   bo chung chi goc (curl.se): co" "DarkGray"
  } else { Remove-Item -LiteralPath $CaPath -Force -ErrorAction SilentlyContinue; $CaPath = ""; Note "Khong tai duoc bo chung chi (cacert.pem) - agent se dung chung chi cua Windows." }

  # ---------------------------------------------------------------- 3. doc ISO Windows
  Step "3/7  Doc cac ban Windows trong ISO"
  $WinRoot = Mount-Iso $Iso
  $img = ""
  foreach ($n in @("install.wim", "install.esd")) { $c = Join-Path $WinRoot ("sources\" + $n); if ((-not $img) -and (Test-There $c)) { $img = $c } }
  if (-not $img) { Stop-Build ("ISO nay khong phai bo cai Windows chuan (khong thay sources\install.wim / install.esd): " + $Iso) }
  foreach ($n in @("sources\boot.wim", "boot\etfsboot.com", "efi\microsoft\boot\efisys.bin")) {
    if (-not (Test-There (Join-Path $WinRoot $n))) { Stop-Build ("ISO Windows thieu " + $n + " (can ISO bo cai Windows 64-bit khoi dong duoc).") }
  }
  $imgs = @(Get-ImageList $img)
  if ($imgs.Count -eq 0) { Stop-Build ("Khong doc duoc danh sach ban trong " + $img) }
  $ij = Join-Path $Work "images.json"
  $pj = Join-Path $Work "pick.json"
  Set-Content -LiteralPath $ij -Value (ConvertTo-Json -InputObject @($imgs) -Depth 4) -Encoding UTF8
  [void](Run-Exe $PyExe @("-I", "-B", $VmBuild, "pick", $ij, $pj))
  if (-not (Test-There $pj)) { Stop-Build "Khong chon duoc ban Windows (vm_build pick loi)." }
  $pick = Get-Content -Raw -LiteralPath $pj | ConvertFrom-Json
  $okIdx = @($pick.images | Where-Object { $_.ok } | ForEach-Object { [int]$_.index })
  if ($okIdx.Count -eq 0) { Stop-Build "ISO nay khong co ban Windows nao dung duoc cho may mau (xem ly do tung ban o tren)." }
  $sel = [int]$pick.default
  if ($Ban -gt 0) { $sel = $Ban }
  elseif ((-not $KhongHoi) -and ($okIdx.Count -gt 1)) {
    $a = ("" + (Read-Host ("   Chon so thu tu ban Windows (Enter = " + $sel + ")"))).Trim()
    if ($a -match '^\d+$') { $sel = [int]$a }
  }
  if ($okIdx -notcontains $sel) { Stop-Build ("Ban so " + $sel + " khong dung duoc cho may mau (chon 1 trong: " + ($okIdx -join ", ") + ").") }
  $S = $pick.images | Where-Object { [int]$_.index -eq $sel } | Select-Object -First 1
  Say ("   -> ban so " + $sel + ": " + $S.name + " (" + $S.version + ") -> may mau tpl-" + $S.tag) "White"
  if ((-not $Key) -and (("" + $S.edition + " " + $S.name) -notmatch 'Eval')) {
    Note "Ban Windows nay khong phai ban dung thu (Evaluation): neu bo cai hoi khoa (product key) thi go tay o man hinh may ao, hoac tao lai ISO voi -Key."
  }

  # ---------------------------------------------------------------- 4. driver VirtIO
  Step "4/7  Driver VirtIO (ISO virtio-win)"
  $want = "" + $S.virtio
  if ((-not $Virtio) -and (-not $KhongHoi)) {
    $Virtio = Get-Input "ISO virtio-win (Enter = tu tai)" ("Keo tha file ISO virtio-win vao day roi Enter - hoac bam Enter de TU TAI ban " + $want + " (" + $S.os + ", ~600 MB).")
  }
  $Virtio = Clean-Path $Virtio
  if (-not $Virtio) { if ("" + $S.virtio_url) { $Virtio = "" + $S.virtio_url } else { $Virtio = $VIRTIOURL -f $want } }
  if (Test-Link $Virtio) {
    $vname = "virtio-win"
    if ($Virtio -match 'virtio-win-(\d+\.\d+\.\d+)\.iso') { $vname = "virtio-win-" + $Matches[1] }
    $valt = ""
    if ($Virtio -match '^(https://fedorapeople\.org/.+/archive-virtio/virtio-win-[0-9.]+-\d+/)virtio-win-[0-9.]+\.iso$') { $valt = $Matches[1] + "virtio-win.iso" }
    $Virtio = Get-LinkFile $Virtio $vname $valt
  }
  if (-not (Test-There $Virtio)) { Stop-Build ("Khong thay file ISO virtio-win: " + $Virtio) }
  $VRoot = Mount-Iso $Virtio
  $VVer = ""
  foreach ($t in @((Get-IsoLabel $VRoot), (Split-Path -Leaf $Virtio))) { if ((-not $VVer) -and ($t -match '(\d+\.\d+\.\d+)')) { $VVer = $Matches[1] } }
  $miss = @()
  foreach ($d in @("vioscsi", "viostor", "NetKVM", "vioserial")) {
    $dd = Join-Path $VRoot ($d + "\" + $S.os + "\amd64")
    if (-not (@(Get-ChildItem -LiteralPath $dd -Filter "*.inf" -ErrorAction SilentlyContinue).Count -gt 0)) { $miss += $d }
  }
  if ($miss.Count -gt 0) {
    Stop-Build ("ISO virtio-win " + $VVer + " khong co driver " + ($miss -join ", ") + " cho " + $S.os + ". Dung virtio-win " + $want + ".")
  }
  # ban virtio QUA MOI cho ban Windows nay (2012 R2: tu 0.1.217 Windows khong nhan chu ky so cua driver o dia -> bo cai khong thay o dia) -> dung, khong ghep ISO hong
  $vmax = "" + $S.virtio_max
  if ($vmax -and ($VVer -match '^\d+\.\d+\.\d+$') -and ([version]$VVer -gt [version]$vmax)) {
    Stop-Build ("virtio-win " + $VVer + " QUA MOI cho " + $S.name + ": Windows nay khong nhan chu ky so cua driver o dia ban do, bo cai se bao khong thay o dia. Dung virtio-win " + $vmax + " - tai bang Chrome: " + $S.virtio_url + " roi chay lai lenh (hoac bo -Virtio de lenh tu tai).")
  }
  $GaMsi = Join-Path $VRoot "guest-agent\qemu-ga-x86_64.msi"
  if (-not (Test-There $GaMsi)) { Stop-Build "ISO virtio-win thieu guest-agent\qemu-ga-x86_64.msi (QEMU guest agent)." }
  $why = Test-Signed $GaMsi "Red Hat"
  if ($why -match "HashMismatch") { Stop-Build ("qemu-ga-x86_64.msi bi sua (chu ky so khong khop) - tai lai ISO virtio-win.") }
  if ($why -match "NotSigned") { Say "   qemu-ga-x86_64.msi khong co chu ky so (binh thuong voi ISO virtio-win)" "DarkGray" }
  elseif ($why) { Note ("qemu-ga-x86_64.msi: " + $why) }
  Say ("   virtio-win " + $VVer + " - driver " + $S.os + " du (o dia VirtIO SCSI / Block, mang VirtIO, cong noi QEMU agent) + QEMU guest agent") "DarkGray"
  if ($VVer -and ($VVer -ne $want)) {
    Note ("Dang dung virtio-win " + $VVer + " - CloudBlue chi kiem ky ban " + $want + " cho " + $S.os + " (0.1.285 loi o dia / mang; 0.1.302 loi sao luu VSS cua QEMU agent). Nen tao lai ISO, o buoc 4 bam Enter de tu tai ban " + $want + ".")
  }

  # ---------------------------------------------------------------- 5. ffmpeg + ban va
  Step "5/7  ffmpeg (dieu khien tu xa) + ban va Windows can them"
  $FfExe = ""
  if (-not $KhongFfmpeg) {
    $ffDir = Join-Path $Work "ffmpeg"
    $rc = Run-Exe $PyExe @("-I", "-B", $VmBuild, "ffmpeg", (Join-Path $Tool "winpc\agent\pcremote.py"), $ffDir, $Dl)
    if (($rc -eq 0) -and (Test-There (Join-Path $ffDir "ffmpeg.exe"))) { $FfExe = Join-Path $ffDir "ffmpeg.exe" }
    else { Note "Chua kem duoc ffmpeg - moi VPS se tu tai (~84 MB) lan dau dieu khien." }
  }
  $UcrtPath = ""
  if ($S.os -eq "2k12R2") {
    $UcrtPath = Join-Path $Dl "Windows8.1-KB2999226-x64.msu"
    if ((-not (Test-There $UcrtPath)) -or (Test-Signed $UcrtPath "Microsoft Corporation")) {
      Say "   tai ban va Universal C Runtime (KB2999226, ~1 MB) tu Microsoft - 2012 R2 can de chay Python ..." "DarkGray"
      if (-not (Get-File $UCRTURL $UcrtPath)) { Stop-Build ("Khong tai duoc ban va KB2999226 tu download.microsoft.com (" + $GetFileErr + ").") }
    }
    $why = Test-Signed $UcrtPath "Microsoft Corporation"
    if ($why) { Remove-Item -LiteralPath $UcrtPath -Force -ErrorAction SilentlyContinue; Stop-Build ("Ban va KB2999226 tai ve khong co chu ky hop le cua Microsoft (" + $why + ").") }
    Say "   ban va KB2999226: chu ky Microsoft hop le" "DarkGray"
  }

  # ---------------------------------------------------------------- 6. chep bo cai + ghep
  Step "6/7  Chep bo cai Windows + ghep phan mem CloudBlue"
  if (-not $Out) { $Out = Join-Path (Split-Path -Qualifier $Work) ("CloudBlue-MayMau-" + $S.tag + ".iso") }
  $Out = Clean-Path $Out
  if ($Out -match '\s') { Stop-Build ("Duong dan ISO moi khong duoc co dau cach: " + $Out) }
  $o2 = Get-FreeOut $Out
  if (-not $o2) { Stop-Build ("File ISO cu dang bi chuong trinh khac giu: " + $Out + " - dung -Out <duong dan khac>.") }
  if ($o2 -ne $Out) { Note ("File " + $Out + " dang bi giu -> ghi ra " + $o2); $Out = $o2 }
  $isoBytes = (Get-Item -LiteralPath $Iso).Length
  $need = [int64]($isoBytes * 2.2) + 2GB
  $drv = Get-PSDrive -Name ((Split-Path -Qualifier $Work).TrimEnd(":")) -ErrorAction SilentlyContinue
  if ($drv -and ($drv.Free -lt $need)) { Stop-Build ("O " + (Split-Path -Qualifier $Work) + " con " + [math]::Round($drv.Free / 1GB, 1) + " GB - can khoang " + [math]::Round($need / 1GB, 1) + " GB. Dung -Work <o khac>:\cb-maymau") }
  if (Test-Path -LiteralPath $IsoRoot) { Remove-Item -LiteralPath $IsoRoot -Recurse -Force }
  $rc = Run-Exe "robocopy.exe" @(($WinRoot.TrimEnd("\") + "\."), $IsoRoot, "/E", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
  if ($rc -ge 8) { Stop-Build ("Chep ISO goc loi (robocopy ma " + $rc + ").") }
  & attrib.exe -R (Join-Path $IsoRoot "*") /S /D 2>$null | Out-Null
  $P = [ordered]@{
    iso_root = $IsoRoot; tool = $Tool; py_dir = $PyDir; os = "" + $S.os; tag = "" + $S.tag; server = [bool]$S.server; user = $TaiKhoan
    image = [ordered]@{ index = [int]$S.index; name = "" + $S.name; edition = "" + $S.edition; version = "" + $S.version; lang = "" + $S.lang }
    virtio_root = $VRoot; virtio_ver = $VVer; ga_msi = $GaMsi; ucrt = $UcrtPath; ffmpeg = $FfExe; cacert = $CaPath
    sb_url = $SbUrl; sb_key = $SbKey; key = $Key; built = (Get-Date -Format "yyyy-MM-dd HH:mm:ss"); update_base = "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/"
  }
  $paramsJ = Join-Path $Work "params.json"
  Set-Content -LiteralPath $paramsJ -Value (ConvertTo-Json -InputObject $P -Depth 5) -Encoding UTF8
  $rc = Run-Exe $PyExe @("-I", "-B", $VmBuild, "layout", $paramsJ)
  Remove-Item -LiteralPath $paramsJ -Force -ErrorAction SilentlyContinue
  if ($rc -ne 0) { Stop-Build "Ghep phan mem CloudBlue vao bo cai loi (xem dong LOI o tren)." }
  $rc = Run-Exe $PyExe @("-I", "-B", $VmBuild, "check", $IsoRoot)
  if ($rc -ne 0) { Stop-Build "Cay bo cai thieu file (xem cac dong THIEU o tren)." }

  # ---------------------------------------------------------------- 7. dong ISO
  Step "7/7  Dong file ISO"
  $osc = Find-Oscdimg $Dl
  if (-not $osc) { Stop-Build ("Khong co oscdimg.exe (cong cu dong ISO): " + ($OscWhy -join " | ") + ". Cai Windows ADK (Deployment Tools) roi chay lai.") }
  Say ("   oscdimg: " + $OscInfo) "DarkGray"
  $bios = Join-Path $IsoRoot "boot\etfsboot.com"
  $efi = Join-Path $IsoRoot "efi\microsoft\boot\efisys_noprompt.bin"
  if (-not (Test-There $efi)) { $efi = Join-Path $IsoRoot "efi\microsoft\boot\efisys.bin"; Note "ISO goc khong co efisys_noprompt.bin: may ao UEFI (OVMF) se hien 'Press any key to boot from CD' - bam 1 phim trong o Console." }
  $bd = "-bootdata:2#p0,e,b" + $bios + "#pEF,e,b" + $efi
  $lbl = "CB_MAYMAU_" + ("" + $S.tag).ToUpper()
  if ($lbl.Length -gt 32) { $lbl = $lbl.Substring(0, 32) }
  if (Test-Path -LiteralPath $Out) { Remove-Item -LiteralPath $Out -Force }
  $rc = Run-Exe $osc @("-m", "-o", "-u2", "-udfver102", $bd, ("-l" + $lbl), $IsoRoot, $Out)
  if (($rc -ne 0) -or (-not (Test-There $Out))) { Stop-Build ("oscdimg loi (ma " + $rc + ").") }
  $gb = [math]::Round((Get-Item -LiteralPath $Out).Length / 1GB, 2)
  $mins = [math]::Round(((Get-Date) - $T0).TotalMinutes, 1)

  Write-Host ""
  Write-Host "  ======================================================" -ForegroundColor Green
  Write-Host ("  XONG (" + $mins + " phut): " + $Out + "  (" + $gb + " GB)") -ForegroundColor Green
  Write-Host ("  May mau: tpl-" + $S.tag + " | " + $S.name + " | tai khoan khach " + $TaiKhoan + " (Admin, khong mat khau, tu dang nhap) | virtio " + $VVer) -ForegroundColor Green
  Write-Host "  ======================================================" -ForegroundColor Green
  Say "  Buoc tiep (TU DONG): chay lenh ghep ISO Proxmox tu cai (tao-iso-proxmox.ps1 - HUONG-DAN muc 0). Lenh do tu lay file nay;" "White"
  Say "   may chu cai tu ISO do se TU cai Proxmox, tu len web va TU dung may mau - khong phai lam 4 buoc tay ben duoi." "White"
  Say "  Chi khi may chu Proxmox da cai san tu truoc moi lam tay:" "DarkGray"
  Say "   1. Dua file ISO nay len Proxmox: trang Proxmox > Datacenter > ten may > local > ISO Images > Upload." "DarkGray"
  Say ("   2. Create VM: Name tpl-" + $S.tag + ", OS: chon ISO nay, System: Qemu Agent (tich), Disk: SCSI 20 GB (VirtIO SCSI single, Discard), CPU 2 (type host), RAM 2048, Network: VirtIO.") "DarkGray"
  Say "   3. Start: may TU cai het (20-40 phut, tu khoi dong lai 1-2 lan). Xong man hinh hien 'MAY MAU DA XONG'." "DarkGray"
  Say "   4. Chinh them tuy y (cai phan mem...) roi: Shutdown > Hardware > CD/DVD Drive > Do not use any media > chuot phai > Convert to template." "DarkGray"
  Say "   ISO nay XOA SACH o dia 0 cua may cai no - chi gan vao may ao mau moi tao. Khong chua khoa bi mat nao." "Yellow"
  foreach ($n in $Notes) { Say ("   (!) " + $n) "Yellow" }
} catch {
  if (("" + $_) -ne "cb-stop") {
    Write-Host ""
    Write-Host ("!! LOI KHONG NGO: " + $_) -ForegroundColor Red
    Write-Host ("   " + $_.InvocationInfo.PositionMessage) -ForegroundColor DarkGray
  }
} finally {
  foreach ($m in $Mounted) { try { Dismount-DiskImage -ImagePath $m | Out-Null } catch { } }
  if ($IsoRoot -and (-not $GiuWork) -and (Test-Path -LiteralPath $IsoRoot)) { Remove-Item -LiteralPath $IsoRoot -Recurse -Force -ErrorAction SilentlyContinue }
}
