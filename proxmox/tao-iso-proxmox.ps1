# =====================================================================================================
#  cloudblue-iso-proxmox   (ban 26.11b)
#  GHEP 1 FILE ISO "PROXMOX TU CAI" cho MAY CHU VPS ao hoa:
#     ISO Proxmox VE goc (ban chinh thuc)  +  tra loi tu cai  +  phan mem CloudBlue (cbhost)  +  cac ISO may mau Windows (CloudBlue-MayMau-*.iso)
#  Ghi ISO nay ra USB (Rufus, che do DD), khoi dong may chu tu USB la TU DONG HET: cai Proxmox VE, tu len web CloudBlue (cho admin bam DUYET),
#  tu chep ISO may mau tu USB, tu dung may mau Windows. May dang co Windows / da co Proxmox thi ISO KHONG tu cai (tranh xoa nham).
#
#  Chay trong Windows PowerShell tren may Windows 10 / 11 (khong can quyen Admin):
#     -Iso "D:\proxmox-ve_9.3-1.iso"     ISO Proxmox VE goc (bo trong = tu tim proxmox-ve_*.iso trong Downloads / Desktop / Documents / cac o dia; khong co thi tu tai)
#     -MayMau "E:\a.iso,E:\b.iso"        cac ISO may mau (bo trong = tu tim moi file CloudBlue-MayMau-*.iso);  -KhongMau = khong kem may mau
#     -Ten cbvps                         ten may chu (chu thuong, so, dau -)        -O nvme0n1   ten o dia cai (bo trong = o dia dau tien, khong tinh USB)
#     -Ip 192.168.1.50/24 -Gateway 192.168.1.1 -Dns 8.8.8.8      IP tinh (bo trong = may chu tu nhan IP qua DHCP luc cai roi giu IP do)
#     -Out "E:\CloudBlue-Proxmox.iso"    -Work "E:\cb-maymau"    -TatMay (cai xong tat may thay vi khoi dong lai)
#     -KhongHoi (khong hoi gi; mat khau root lay tu bien moi truong CB_PVE_PW_HASH = ma bam)   -Nhanh main   -Nguon <thu muc kho cloudblue tai san>
#  Lenh hoi MAT KHAU root cua Proxmox (go 2 lan, khong hien) - chi luu ma bam vao ISO. ISO khong chua khoa bi mat nao cua CloudBlue.
# =====================================================================================================
param(
  [string]$Iso = "",
  [string]$MayMau = "",
  [string]$Out = "",
  [string]$Work = "",
  [string]$Ten = "cbvps",
  [string]$O = "",
  [string]$Ip = "",
  [string]$Gateway = "",
  [string]$Dns = "",
  [string]$Nhanh = "main",
  [string]$Nguon = "",
  [switch]$KhongMau,
  [switch]$TatMay,
  [switch]$KhongHoi
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$VER = "26.11b"
$OwnerRepo = "lvhien205hn-eng/cloudblue"
$RawBase = "https://raw.githubusercontent.com/" + $OwnerRepo
$PYURL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
$UA = "cloudblue-iso-proxmox/" + $VER
$ToolFiles = @("proxmox/vm/pve_iso.py", "proxmox/vm/cb_nap.py", "proxmox/vm/pve_firstboot.sh", "proxmox/cbhost.py")
$Notes = New-Object System.Collections.ArrayList
$GetFileErr = ""
$Rev = "local"

function Say([string]$m, [string]$c = "Gray") { Write-Host $m -ForegroundColor $c }
function Step([string]$m) { Write-Host ""; Write-Host ("== " + $m) -ForegroundColor Cyan }
function Note([string]$m) { [void]$Notes.Add($m); Write-Host ("   (!) " + $m) -ForegroundColor Yellow }

function Stop-Build([string]$m) {
  Write-Host ""
  Write-Host ("!! DUNG: " + $m) -ForegroundColor Red
  Write-Host "   Chup / chep phan chu tu dong '== ' gan nhat toi day gui ho tro." -ForegroundColor Red
  throw "cb-stop"
}

function Step([string]$m) { Write-Host ""; Write-Host ("== " + $m) -ForegroundColor Cyan }
function Note([string]$m) { [void]$Notes.Add($m); Write-Host ("   (!) " + $m) -ForegroundColor Yellow }

function Stop-Build([string]$m) {
  Write-Host ""
  Write-Host ("!! DUNG: " + $m) -ForegroundColor Red
  Write-Host "   Chup / chep phan chu tu dong '== ' gan nhat toi day gui ho tro." -ForegroundColor Red
  throw "cb-stop"
}

function Note([string]$m) { [void]$Notes.Add($m); Write-Host ("   (!) " + $m) -ForegroundColor Yellow }

function Stop-Build([string]$m) {
  Write-Host ""
  Write-Host ("!! DUNG: " + $m) -ForegroundColor Red
  Write-Host "   Chup / chep phan chu tu dong '== ' gan nhat toi day gui ho tro." -ForegroundColor Red
  throw "cb-stop"
}

function Stop-Build([string]$m) {
  Write-Host ""
  Write-Host ("!! DUNG: " + $m) -ForegroundColor Red
  Write-Host "   Chup / chep phan chu tu dong '== ' gan nhat toi day gui ho tro." -ForegroundColor Red
  throw "cb-stop"
}

function Get-Sha([string]$p) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLower() }
function Clean-Path([string]$p) { return ("" + $p).Trim().Trim('"').Trim("'").Trim() }
function Test-Link([string]$t) { return [bool]((("" + $t).Trim().Trim('"')) -match '^https?://') }

function Test-There([string]$p) {
  if (-not $p) { return $false }
  try { return [bool](Test-Path -LiteralPath $p) } catch { return $false }
}

function Clean-Path([string]$p) { return ("" + $p).Trim().Trim('"').Trim("'").Trim() }
function Test-Link([string]$t) { return [bool]((("" + $t).Trim().Trim('"')) -match '^https?://') }

function Test-There([string]$p) {
  if (-not $p) { return $false }
  try { return [bool](Test-Path -LiteralPath $p) } catch { return $false }
}

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
  Write-Host ("  CloudBlue - TAO ISO PROXMOX TU CAI cho may chu VPS ao hoa (ban " + $VER + ")") -ForegroundColor Green
  Write-Host "  1 file ISO: Proxmox VE + CloudBlue + ISO may mau Windows. Khoi dong may chu tu no la tu cai, tu len web, tu dung may mau." -ForegroundColor Green
  Write-Host "  ======================================================" -ForegroundColor Green
  if ($PSVersionTable.PSVersion.Major -lt 5) { Stop-Build "Can Windows PowerShell 5.1 (Windows 10 / 11)." }
  if (-not [Environment]::Is64BitOperatingSystem) { Stop-Build "Can Windows 64-bit." }

  # ---------------------------------------------------------------- thu muc lam viec (dung chung voi lenh ghep ISO may mau: da co Python thi khoi tai lai)
  Step "A  Thu muc lam viec + cong cu"
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
  $Tool = Join-Path $Work "tool-pve"
  $PyDir = Join-Path $Work "py"
  New-Item -ItemType Directory -Force $Dl | Out-Null
  Say ("   Thu muc lam viec: " + $Work) "DarkGray"

  if (-not $Nguon) { $Rev = Get-Rev }
  if (Test-Path -LiteralPath $Tool) { Remove-Item -LiteralPath $Tool -Recurse -Force }
  New-Item -ItemType Directory -Force $Tool | Out-Null
  foreach ($f in $ToolFiles) { Get-Repo $f (Join-Path $Tool ($f -replace "/", "\")) }
  $PveIso = Join-Path $Tool "proxmox\vm\pve_iso.py"
  if (-not (Select-String -LiteralPath $PveIso -Pattern "GHEP ISO PROXMOX TU CAI" -SimpleMatch -Quiet)) { Stop-Build "pve_iso.py tai ve khong dung - cho 5 phut roi chay lai lenh." }
  if (-not (Select-String -LiteralPath (Join-Path $Tool "proxmox\cbhost.py") -Pattern "CBHOST_VER = " -SimpleMatch -Quiet)) { Stop-Build "cbhost.py tai ve khong dung - cho 5 phut roi chay lai lenh." }
  if (-not (Select-String -LiteralPath (Join-Path $Tool "proxmox\cbhost.py") -Pattern "auto_tpl" -SimpleMatch -Quiet)) { Stop-Build "cbhost.py tai ve la ban cu (chua co tu dung may mau) - cho 5 phut roi chay lai lenh." }
  if (-not (Select-String -LiteralPath (Join-Path $Tool "proxmox\cbhost.py") -Pattern "def net_heal" -SimpleMatch -Quiet)) { Stop-Build "cbhost.py tai ve la ban cu (chua co tu sua mang) - cho 5 phut roi chay lai lenh." }
  $CbVer = ""
  $mv = Select-String -LiteralPath (Join-Path $Tool "proxmox\cbhost.py") -Pattern '^CBHOST_VER = "([^"]+)"' | Select-Object -First 1
  if ($mv) { $CbVer = $mv.Matches[0].Groups[1].Value }
  Say ("   bo ghep ISO Proxmox + cbhost " + $CbVer + " (tu sua mang: CO) - nguon " + $(if ($Nguon) { $Nguon } else { "GitHub " + $Rev.Substring(0, [Math]::Min(12, $Rev.Length)) })) "DarkGray"

  $PyExe = Join-Path $PyDir "python.exe"
  $pyOk = $false
  if (Test-There $PyExe) { if (-not (Test-Signed $PyExe "Python Software Foundation")) { $pyOk = $true } }
  if (-not $pyOk) {
    $zip = Join-Path $Dl "python-embed.zip"
    if ((-not (Test-There $zip)) -or ((Get-Item -LiteralPath $zip).Length -lt 5MB)) {
      Say "   tai Python nhung 3.12 (python.org, ~11 MB) ..." "DarkGray"
      if (-not (Get-File $PYURL $zip)) { Stop-Build ("Khong tai duoc Python tu python.org (" + $GetFileErr + ").") }
    }
    if (Test-Path -LiteralPath $PyDir) { Remove-Item -LiteralPath $PyDir -Recurse -Force }
    Expand-Archive -Force -LiteralPath $zip -DestinationPath $PyDir
    if (-not (Test-There $PyExe)) { Stop-Build "Giai nen Python loi (thieu python.exe) - xoa thu muc lam viec roi chay lai." }
    $why = Test-Signed $PyExe "Python Software Foundation"
    if ($why) { Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue; Stop-Build ("python.exe tai ve khong co chu ky hop le cua Python Software Foundation (" + $why + ").") }
  }
  Say "   python.exe: chu ky Python Software Foundation hop le" "DarkGray"

  # ---------------------------------------------------------------- ghep (pve_iso.py lam het: tim file, hoi mat khau root, ghep, tu kiem)
  $a = @("-I", "-B", $PveIso, "--work", $Work, "--ten", $Ten)
  if ($Iso) { $a += @("--iso", (Clean-Path $Iso)) }
  if ($MayMau) { $a += @("--mau", $MayMau) }
  if ($KhongMau) { $a += "--khong-mau" }
  if ($Out) { $a += @("--out", (Clean-Path $Out)) }
  if ($O) { $a += @("--o", $O) }
  if ($Ip) { $a += @("--ip", $Ip) }
  if ($Gateway) { $a += @("--gateway", $Gateway) }
  if ($Dns) { $a += @("--dns", $Dns) }
  if ($TatMay) { $a += "--tat-may" }
  if ($KhongHoi) { $a += "--khong-hoi" }
  Write-Host ""
  $old = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  & $PyExe @a
  $rc = $LASTEXITCODE
  $ErrorActionPreference = $old
  if ($rc -ne 0) {
    Write-Host ""
    Write-Host "   Chup / chep phan chu tu dong '== ' gan nhat toi day gui ho tro." -ForegroundColor Red
  }
  foreach ($n in $Notes) { Say ("   (!) " + $n) "Yellow" }
} catch {
  if (("" + $_) -ne "cb-stop") {
    Write-Host ""
    Write-Host ("!! LOI KHONG NGO: " + $_) -ForegroundColor Red
    Write-Host ("   " + $_.InvocationInfo.PositionMessage) -ForegroundColor DarkGray
  }
}
