# =====================================================================================================
#  cloudblue-tao-iso   (ban 20.11a)
#  TAO FILE ISO "CloudBlue-PC.iso": bo cai Windows TU DONG cho may PC cho thue.
#
#  Chay trong Windows PowerShell (Admin) tren 1 may Windows 10/11 dang co file ISO Windows goc:
#     - nhan 1 hoac nhieu ISO goc (vi du 22H2 + 1511)  ->  1 ISO duy nhat chua ca hai ban
#     - khoi dong may tu ISO / USB do: tu chon o, dem nguoc 30 giay, XOA va cai Windows, tao phan vung cuu ho,
#       cai phan mem CloudBlue, may tu hien len trang quan tri
#  Script KHONG sua file ISO goc, KHONG dung gi toi o dia cua may dang chay (chi tao thu muc lam viec + file ISO moi).
#
#  Tham so (deu co the bo trong - script se hoi):
#     -Iso  "D:\Win10_22H2.iso","D:\Win10_1511.iso"     duong dan ISO goc (hoac thu muc da giai nen)
#     -Out  "D:\CloudBlue-PC.iso"                       noi ghi ISO moi
#     -Work "D:\cb-work"                                thu muc lam viec (can trong ~2 lan tong dung luong ISO, KHONG co dau cach)
#     -TaiKhoan PC  -MatKhau ""                         tai khoan Windows tao san tren may cho thue
#     -GiuWork                                          giu thu muc lam viec sau khi xong
#     -Them "D:\cb-them"                                thu muc THEM vao bo cai (bo trong: tu tim thu muc ten cb-them nam canh file ISO, khong co thi hoi):
#                                                         drivers\            driver cho MOI ban Windows (thu muc co file .inf, hoac goi .zip / .exe)
#                                                         drivers\1511\       driver chi cho ban 1511   (tuong tu: drivers\22h2\ ...)
#                                                         firstboot.d\        file .cmd .bat .ps1 chay 1 lan o lan dang nhap dau (firstboot.d\1511\ = chi ban 1511)
#                                                         wallpaper.jpg       anh nen rieng (khong co thi dung anh nen CloudBlue)
#     -KhongIso                                         chi dung cay thu muc, khong dong ISO
#     -KhoaChung / -KhongKhoaChung                      khoa CAI DAT chung cua Microsoft (khong kich hoat ban quyen), chi de man hinh
#                                                       cai lan dau khong dung lai hoi key. Mac dinh: chi dien cho ban cu hon 1703 (vd 1511).
#  MA DANG KY (cbpc_...): script HOI khi chay - dung dan vao dong lenh, dung gui cho ai.
# =====================================================================================================
param(
  [string[]]$Iso = @(),
  [string]$Out = "",
  [string]$Work = "",
  [string]$TaiKhoan = "PC",
  [string]$MatKhau = "",
  [string]$Nhanh = "main",
  [string]$Nguon = "",
  [string]$MaDangKy = "",
  [switch]$GiuWork,
  [string]$Them = "",
  [switch]$KhongIso,
  [switch]$KhoaChung,
  [switch]$KhongKhoaChung
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$VER = "20.11a"
$REPO = "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue"
$PYURL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
$TOOLFILES = @("lib/cbsys.py", "lib/cbcore.py", "lib/cbrec.py", "pe/cb_pe.py", "pe/start.cmd", "boot/winpeshl.ini",
               "os/cb_provision.py", "os/provision.cmd", "os/cb_stage.py", "os/unattend.tpl.xml", "os/wallpaper.jpg",
               "agent/pcagent.py", "agent/watch.cmd", "agent/cbpc.cmd", "CAI-DAT.cmd", "cb_build.py")
$T0 = Get-Date
$Mounted = New-Object System.Collections.ArrayList
$Notes = New-Object System.Collections.ArrayList
$DrvInfo = New-Object System.Collections.ArrayList
$MountDir = ""

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
  # Chay 1 chuong trinh ngoai, in thang ra man hinh, tra ma thoat (khong de chu loi cua no lam dung script).
  $old = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try { & $exe @a 2>&1 | ForEach-Object { Write-Host ("   " + $_) } } catch { Write-Host ("   " + $_) }
  $rc = $LASTEXITCODE
  $ErrorActionPreference = $old
  return $rc
}

function Get-File([string]$url, [string]$dst, [string]$agent = "") {
  $dir = Split-Path -Parent $dst
  if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
  if (Test-Path $dst) { Remove-Item -Force $dst }
  $curl = Join-Path $env:SystemRoot "System32\curl.exe"
  if (Test-Path $curl) {
    $a = @("-fsSL", "--retry", "3", "--connect-timeout", "20", "-o", $dst)
    if ($agent) { $a += @("-A", $agent) }
    $a += $url
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    & $curl @a 2>$null | Out-Null
    $ErrorActionPreference = $old
    if ($LASTEXITCODE -eq 0 -and (Test-Path $dst) -and ((Get-Item $dst).Length -gt 0)) { return $true }
  }
  try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $h = @{}
    if ($agent) { $h["User-Agent"] = $agent }
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $dst -Headers $h
    return ((Test-Path $dst) -and ((Get-Item $dst).Length -gt 0))
  } catch { return $false }
}

function Run-Quiet([string]$exe, [string[]]$a) {
  # Chay 1 chuong trinh ngoai, KHONG in gi ra man hinh, tra ma thoat.
  $old = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $rc = 1
  try { & $exe @a 2>&1 | Out-Null; $rc = $LASTEXITCODE } catch { $rc = 1 }
  $ErrorActionPreference = $old
  return $rc
}

function Expand-DriverPacks([string]$dir) {
  # Goi driver de nguyen file .zip / .exe (tu giai nen) nam ngay trong cb\drivers hoac trong thu muc con cap 1 (vi du drivers\1511)
  #   ->  giai nen ra thu muc cung ten de lay file .inf (bo cai chi nap duoc driver dang .inf).
  # File .exe can 7-Zip da cai tren may nay; khong co thi ghi chu va bo qua. Thu muc da co san file .inf thi khong dung toi.
  # Goi VGA NVIDIA (ten kieu 466.77-notebook-...exe) KHONG giai nen o day: cb_build.py chuyen no sang firstboot.d de cai im lang o lan dang nhap dau.
  $seven = ""
  $cands = @((Join-Path $env:ProgramFiles "7-Zip\7z.exe"))
  $pf86 = ${env:ProgramFiles(x86)}
  if ($pf86) { $cands += (Join-Path $pf86 "7-Zip\7z.exe") }
  foreach ($c in $cands) { if ((-not $seven) -and (Test-Path $c)) { $seven = $c } }
  $tops = @($dir)
  foreach ($d in @(Get-ChildItem $dir -Directory)) { $tops += $d.FullName }
  foreach ($t in $tops) {
    if (@(Get-ChildItem $t -File -Filter *.inf).Count -gt 0) { continue }
    $packs = @(Get-ChildItem $t -File | Where-Object { ($_.Extension -eq ".zip") -or (($_.Extension -eq ".exe") -and ($_.Length -gt 5MB)) })
    foreach ($f in $packs) {
      if ($f.Name -match '^\d{3}\.\d{2}-(notebook|desktop)-') { continue }
      $to = Join-Path $t ($f.BaseName -replace '[^A-Za-z0-9_.-]', '_')
      if (Test-Path $to) { $to = $to + "_x" }
      $okx = $false
      if ($f.Extension -eq ".zip") {
        try { Expand-Archive -Force -Path $f.FullName -DestinationPath $to; $okx = $true } catch { $okx = $false }
      } elseif ($seven) {
        $rcx = Run-Quiet $seven @("x", "-y", ("-o" + $to), $f.FullName)
        $okx = ($rcx -eq 0)
      } else {
        Note ("Goi driver " + $f.Name + " la file .exe ma may nay chua cai 7-Zip nen khong tu giai nen duoc. Giai nen bang tay (chuot phai > Extract) cho ra thu muc co file .inf roi chay lai.")
        continue
      }
      $ninf = 0
      if (Test-Path $to) { $ninf = @(Get-ChildItem $to -Recurse -File -Filter *.inf).Count }
      if ($okx -and ($ninf -gt 0)) {
        Remove-Item -Force $f.FullName
        Say ("   da giai nen goi driver " + $f.Name + " (" + $ninf + " file .inf)") "DarkGray"
      } else {
        if (Test-Path $to) { Remove-Item -Recurse -Force $to -ErrorAction SilentlyContinue }
        Note ("Goi driver " + $f.Name + ": giai nen khong ra file .inf nao - se KHONG nap duoc kieu driver (neu la bo cai .exe thi dung lenh chay lan dau trong firstboot.d).")
      }
    }
  }
}

function Get-Sha([string]$p) { return (Get-FileHash -Algorithm SHA256 -Path $p).Hash.ToLower() }

function Clean-Path([string]$p) { return $p.Trim().Trim('"').Trim("'").Trim() }

function Get-ImageList([string]$file) {
  # Tra danh sach ban (index) trong 1 file install.wim / .esd: Index, Name, Edition, Version, Lang, Arch
  $res = @()
  try {
    $list = @(Get-WindowsImage -ImagePath $file)
    foreach ($it in $list) {
      $d = Get-WindowsImage -ImagePath $file -Index $it.ImageIndex
      $iv = "" + $d.Version
      if ($d.SPBuild -and ($iv.Split(".").Count -lt 4)) { $iv = $iv + "." + $d.SPBuild }
      $lang = "en-US"
      try { if ($d.Languages -and $d.Languages.Count -gt 0) { $lang = "" + $d.Languages[[int]$d.DefaultLanguageIndex] } } catch { }
      $res += [pscustomobject]@{ Index = [int]$it.ImageIndex; Name = "" + $d.ImageName; Edition = "" + $d.EditionId; Version = $iv; Lang = $lang; Arch = [int]$d.Architecture }
    }
    return $res
  } catch {
    Say ("   (Get-WindowsImage loi: " + $_.Exception.Message + " -> doc bang dism)") "DarkGray"
    $res = @()
  }
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
    $res += [pscustomobject]@{ Index = $i; Name = (& $g "Name"); Edition = (& $g "Edition"); Version = $iv; Lang = $lang; Arch = $arch }
  }
  return $res
}

function Find-Oscdimg([string]$dl) {
  $c = @()
  $pf = ${env:ProgramFiles(x86)}
  if ($pf) { $c += (Join-Path $pf "Windows Kits\10\Assessment and Deployment Kit\Deployment Tools\amd64\Oscdimg\oscdimg.exe") }
  if ($PSScriptRoot) { $c += (Join-Path $PSScriptRoot "oscdimg.exe") }
  $c += (Join-Path $dl "oscdimg.exe")
  foreach ($p in $c) { if (Test-Path $p) { return $p } }
  Say "   tai oscdimg.exe (cong cu dong ISO cua Microsoft, ~150KB) tu may chu Microsoft..." "DarkGray"
  $dst = Join-Path $dl "oscdimg.exe"
  foreach ($id in @("688CABB065000", "3D44737265000")) {
    $ok = Get-File ("https://msdl.microsoft.com/download/symbols/oscdimg.exe/" + $id + "/oscdimg.exe") $dst "Microsoft-Symbol-Server/10.0.0.0"
    if ($ok) {
      $sig = Get-AuthenticodeSignature $dst
      if ($sig.Status -eq "Valid" -and $sig.SignerCertificate.Subject -match "Microsoft") { return $dst }
      Remove-Item -Force $dst -ErrorAction SilentlyContinue
    }
  }
  return ""
}

# ----------------------------------------------------------------------------------------------------- bat dau
try {
  Write-Host ""
  Write-Host ("  CloudBlue PC - TAO ISO CAI WINDOWS TU DONG (ban " + $VER + ")") -ForegroundColor Green
  Write-Host "  ======================================================" -ForegroundColor Green

  $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
  if (-not $isAdmin) { Stop-Build "Can mo Windows PowerShell bang quyen Admin (chuot phai nut Start > Windows PowerShell (Admin) / Terminal (Admin))." }
  if ($PSVersionTable.PSVersion.Major -lt 5) { Stop-Build "Can Windows PowerShell 5.1 (Windows 10 / 11)." }
  if (-not [Environment]::Is64BitOperatingSystem) { Stop-Build "Can Windows 64-bit." }

  # ---------------------------------------------------------------- 1. ISO goc
  Step "1/8  File ISO Windows goc"
  if ($Iso.Count -eq 0) {
    Say "   Keo tha tung file ISO vao cua so nay roi bam Enter (hoac dan duong dan). Xong thi bam Enter trong." "White"
    while ($true) {
      $p = Clean-Path (Read-Host ("   ISO thu " + ($Iso.Count + 1) + " (Enter trong = het)"))
      if (-not $p) { break }
      if (-not (Test-Path $p)) { Say ("   khong thay: " + $p) "Yellow"; continue }
      $Iso += $p
    }
  }
  $Iso = @($Iso | ForEach-Object { Clean-Path $_ } | Where-Object { $_ })
  if ($Iso.Count -eq 0) { Stop-Build "Chua co file ISO nao." }
  foreach ($p in $Iso) { if (-not (Test-Path $p)) { Stop-Build ("Khong thay: " + $p) } }

  # ---------------------------------------------------------------- thu muc THEM (driver, lenh chay lan dau, anh nen rieng)
  if (-not $Them) {
    foreach ($p in $Iso) {
      $par = Split-Path -Parent (Get-Item $p).FullName
      if ($par -and (-not $Them)) {
        $c = Join-Path $par "cb-them"
        if (Test-Path $c) { $Them = $c }
      }
    }
    if ($Them) { Say ("   Thu muc them (tu tim thay canh file ISO): " + $Them) "White" }
    else {
      Say "   Thu muc THEM (driver, lenh chay lan dau, anh nen rieng): keo tha thu muc vao day roi Enter. Khong co thi Enter trong." "White"
      $Them = Clean-Path ("" + (Read-Host "   Thu muc them"))
    }
  }
  if ($Them) {
    $Them = Clean-Path $Them
    if (-not (Test-Path $Them)) { Stop-Build ("Khong thay thu muc them: " + $Them) }
  }

  # ---------------------------------------------------------------- thu muc lam viec
  $totalIso = 0
  foreach ($p in $Iso) { $it = Get-Item $p; if (-not $it.PSIsContainer) { $totalIso += $it.Length } else { $totalIso += 6GB } }
  if (-not $Work) {
    $best = Get-Volume | Where-Object { $_.DriveType -eq "Fixed" -and $_.DriveLetter } | Sort-Object SizeRemaining -Descending | Select-Object -First 1
    if (-not $best) { Stop-Build "Khong tim thay o cung nao de lam viec - dung tham so -Work D:\cb-work" }
    $Work = "" + $best.DriveLetter + ":\cb-work"
  }
  $Work = Clean-Path $Work
  if ($Work -match '\s') { Stop-Build ("Thu muc lam viec khong duoc co dau cach: " + $Work + "  (vi du dung -Work D:\cb-work)") }
  if (-not $Out) { $Out = Join-Path (Split-Path -Qualifier $Work) "\CloudBlue-PC.iso" }
  $Out = Clean-Path $Out
  if ($Out -match '\s') { Stop-Build ("Duong dan ISO moi khong duoc co dau cach: " + $Out) }
  New-Item -ItemType Directory -Force $Work | Out-Null
  $wdrive = (Split-Path -Qualifier $Work).TrimEnd(":")
  $free = (Get-PSDrive $wdrive).Free
  $need = [int64]($totalIso * 2.2 + 3GB)
  Say ("   Thu muc lam viec: " + $Work + "   ISO moi: " + $Out) "DarkGray"
  Say ("   O " + $wdrive + ": con trong " + [math]::Round($free / 1GB, 1) + " GB - can khoang " + [math]::Round($need / 1GB, 1) + " GB") "DarkGray"
  if ($free -lt $need) { Stop-Build ("O " + $wdrive + ": khong du cho trong. Don bot hoac dung -Work <o khac>:\cb-work") }
  $IsoRoot = Join-Path $Work "iso"
  $Tool = Join-Path $Work "tool"
  $PyDir = Join-Path $Work "py"
  $Dl = Join-Path $Work "dl"
  $MountDir = Join-Path $Work "mnt"
  foreach ($d in @($Dl)) { New-Item -ItemType Directory -Force $d | Out-Null }

  # don dep lan chay truoc bi do
  if (Test-Path $MountDir) {
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    & dism.exe /English /Unmount-Image "/MountDir:$MountDir" /Discard 2>$null | Out-Null
    & dism.exe /English /Cleanup-Wim 2>$null | Out-Null
    $ErrorActionPreference = $old
    Remove-Item -Recurse -Force $MountDir -ErrorAction SilentlyContinue
  }
  foreach ($d in @($IsoRoot, $Tool, $PyDir)) { if (Test-Path $d) { Remove-Item -Recurse -Force $d } }

  # ---------------------------------------------------------------- 2. phan mem CloudBlue
  Step "2/8  Tai phan mem CloudBlue PC"
  if ($Nguon) {
    $Nguon = Clean-Path $Nguon
    foreach ($f in $TOOLFILES) {
      $src = Join-Path $Nguon ($f -replace "/", "\")
      if (-not (Test-Path $src)) { Stop-Build ("Thu muc nguon thieu file " + $f) }
      $dst = Join-Path $Tool ($f -replace "/", "\")
      New-Item -ItemType Directory -Force (Split-Path -Parent $dst) | Out-Null
      Copy-Item -Force $src $dst
    }
    Say ("   lay tu thu muc " + $Nguon) "DarkGray"
  } else {
    $base = $REPO + "/" + $Nhanh + "/winpc"
    $man = Join-Path $Dl "manifest.json"
    if (-not (Get-File ($base + "/manifest.json?t=" + (Get-Random)) $man)) { Stop-Build "Khong tai duoc manifest.json tu GitHub (kiem tra mang)." }
    $mj = Get-Content -Raw -Encoding UTF8 $man | ConvertFrom-Json
    foreach ($f in $TOOLFILES) {
      $dst = Join-Path $Tool ($f -replace "/", "\")
      if (-not (Get-File ($base + "/" + $f + "?t=" + (Get-Random)) $dst)) { Stop-Build ("Khong tai duoc " + $f) }
      $want = $mj.sha256.$f
      if (-not $want) { Stop-Build ("manifest.json khong co ma kiem cua " + $f) }
      if ((Get-Sha $dst) -ne $want) { Stop-Build ("File " + $f + " tai ve khong khop ma kiem (GitHub chua cap nhat xong?) - cho 5 phut roi chay lai lenh.") }
    }
    Say ("   " + $TOOLFILES.Count + " file, ban " + $mj.ver + ", khop ma kiem") "DarkGray"
  }

  # ---------------------------------------------------------------- 3. Python nhung + chung chi
  Step "3/8  Tai Python nhung 3.12 (python.org) + bo chung chi"
  $zip = Join-Path $Dl "python-embed.zip"
  if (-not (Test-Path $zip) -or ((Get-Item $zip).Length -lt 5MB)) {
    if (-not (Get-File $PYURL $zip)) { Stop-Build "Khong tai duoc Python tu python.org (kiem tra mang)." }
  }
  Expand-Archive -Force -Path $zip -DestinationPath $PyDir
  $PyExe = Join-Path $PyDir "python.exe"
  if (-not (Test-Path $PyExe)) { Stop-Build "Giai nen Python loi (thieu python.exe) - xoa thu muc lam viec roi chay lai." }
  $sig = Get-AuthenticodeSignature $PyExe
  if ($sig.Status -ne "Valid" -or -not ($sig.SignerCertificate.Subject -match "Python Software Foundation")) {
    Remove-Item -Force $zip -ErrorAction SilentlyContinue
    Stop-Build ("python.exe tai ve khong co chu ky hop le cua Python Software Foundation (trang thai: " + $sig.Status + ").")
  }
  Say "   python.exe: chu ky Python Software Foundation hop le" "DarkGray"
  $ca = Join-Path $Tool "os\cacert.pem"
  if ((Get-File "https://curl.se/ca/cacert.pem" $ca) -and ((Get-Item $ca).Length -gt 100KB) -and (Select-String -Path $ca -Pattern "BEGIN CERTIFICATE" -Quiet)) {
    Say "   bo chung chi goc (curl.se): co" "DarkGray"
  } else {
    Remove-Item -Force $ca -ErrorAction SilentlyContinue
    Note "Khong tai duoc bo chung chi (cacert.pem) - agent se dung chung chi cua Windows."
  }

  # ---------------------------------------------------------------- 4. dia chi may chu + ma dang ky
  Step "4/8  Dia chi he thong + MA DANG KY"
  $cfgjs = Join-Path $Dl "config.js"
  if (-not (Get-File ($REPO + "/" + $Nhanh + "/blueroblox-site/config.js?t=" + (Get-Random)) $cfgjs)) { Stop-Build "Khong tai duoc config.js cua web tu GitHub." }
  $cj = Get-Content -Raw -Encoding UTF8 $cfgjs
  $SbUrl = ""; $SbKey = ""
  if ($cj -match 'supabaseUrl\s*:\s*"([^"]+)"') { $SbUrl = $Matches[1] }
  if ($cj -match 'supabaseAnonKey\s*:\s*"([^"]+)"') { $SbKey = $Matches[1] }
  if (-not ($SbUrl -match '^https://[a-z0-9]+\.supabase\.co/?$') -or -not $SbKey) { Stop-Build "Khong doc duoc dia chi Supabase trong config.js." }
  Say ("   may chu: " + $SbUrl) "DarkGray"
  if (-not $MaDangKy) {
    Say "   Vao web > Bang quan tri > May PC > 'Tao ma dang ky' > Copy, roi dan vao day (chuot phai = dan). Ma KHONG hien khi dan." "White"
    $sec = Read-Host "   MA DANG KY (Enter trong = may cai xong se KHONG tu len web)" -AsSecureString
    $MaDangKy = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
  }
  $MaDangKy = ("" + $MaDangKy).Trim()
  if ($MaDangKy -and -not ($MaDangKy -match '^cbpc_[0-9a-f]{40}$')) { Stop-Build "Ma dang ky sai dang (phai la cbpc_ + 40 ky tu). Copy lai tu trang quan tri." }
  if ($MaDangKy) { Say "   ma dang ky: da nhan (khong in ra)" "DarkGray" } else { Note "Khong co ma dang ky: may cai tu ISO nay se khong tu hien len web." }

  # ---------------------------------------------------------------- 5. mo ISO goc, doc cac ban Windows
  Step "5/8  Doc cac ban Windows trong ISO goc"
  $src = @()
  foreach ($p in $Iso) {
    $it = Get-Item $p
    if ($it.PSIsContainer) { $root = $it.FullName.TrimEnd("\") + "\" }
    else {
      $m = Mount-DiskImage -ImagePath $it.FullName -PassThru
      [void]$Mounted.Add($it.FullName)
      Start-Sleep -Milliseconds 800
      $vol = $m | Get-Volume
      if (-not $vol -or -not $vol.DriveLetter) { Start-Sleep 2; $vol = Get-DiskImage -ImagePath $it.FullName | Get-Volume }
      if (-not $vol -or -not $vol.DriveLetter) { Stop-Build ("Khong mo duoc ISO: " + $p) }
      $root = "" + $vol.DriveLetter + ":\"
    }
    # bo cai chuan: \sources\install.wim|esd   ;   ISO 2 kien truc (x86 + x64): \x64\sources\install.wim|esd
    $img = $null
    $std = $false
    foreach ($sub in @("sources", "x64\sources")) {
      foreach ($n in @("install.wim", "install.esd")) {
        $c = Join-Path $root ($sub + "\" + $n)
        if ((-not $img) -and (Test-Path $c)) { $img = $c; $std = ($sub -eq "sources") }
      }
    }
    if (-not $img) {
      Say ("   Noi dung " + $root + ":") "Yellow"
      Get-ChildItem $root | Select-Object -First 25 | ForEach-Object { Say ("      " + $_.Name) "Yellow" }
      $sdir = Join-Path $root "sources"
      if (Test-Path $sdir) {
        Get-ChildItem $sdir -File | Sort-Object Length -Descending | Select-Object -First 6 | ForEach-Object { Say ("      sources\" + $_.Name + "   " + [math]::Round($_.Length / 1MB) + " MB") "Yellow" }
        if (Test-Path (Join-Path $sdir "install.swm")) { Stop-Build ("ISO nay dung anh Windows bi cat nho (install.swm) - ban nay chua ho tro: " + $p) }
      }
      Stop-Build ("ISO nay khong phai bo cai Windows chuan (khong thay sources\install.wim / install.esd): " + $p)
    }
    if ($std) { $std = ((Test-Path (Join-Path $root "sources\boot.wim")) -and (Test-Path (Join-Path $root "boot\boot.sdi")) -and (Test-Path (Join-Path $root "efi\microsoft\boot\efisys.bin"))) }
    $list = @(Get-ImageList $img)
    if ($list.Count -eq 0) { Stop-Build ("Khong doc duoc danh sach ban trong " + $img) }
    $x64 = @($list | Where-Object { $_.Arch -eq 9 })
    if ($x64.Count -eq 0) { Stop-Build ("Chi ho tro Windows 64-bit (x64) - ISO nay khong co ban x64 nao: " + $p) }
    $pick = $x64 | Where-Object { $_.Edition -eq "Professional" } | Select-Object -First 1
    if (-not $pick) { $pick = $x64 | Select-Object -First 1 }
    $bytes = (Get-Item $img).Length
    Say ("   " + (Split-Path -Leaf $p) + ":") "White"
    foreach ($x in $list) {
      $mk = ""
      if ($x.Arch -ne 9) { $mk = "   (32-bit - khong dung)" } elseif ($x.Index -eq $pick.Index) { $mk = "   <-- mac dinh" }
      Say ("      ban so " + $x.Index + ": " + $x.Name + "  (" + $x.Edition + ", " + $x.Version + ")" + $mk) "DarkGray"
    }
    if ($x64.Count -gt 1) {
      $ans = ("" + (Read-Host ("   Dung ban so nao? (Enter = " + $pick.Index + ")"))).Trim()
      if ($ans) {
        $sel = $x64 | Where-Object { ("" + $_.Index) -eq $ans } | Select-Object -First 1
        if (-not $sel) { Stop-Build ("ISO nay khong co ban x64 so '" + $ans + "'.") }
        $pick = $sel
      }
    }
    if (-not $std) { Say "      (ISO nay khong co du bo khoi dong chuan o goc - chi lay ban Windows, khong dung lam moi truong cai dat)" "DarkGray" }
    # ISO tuy bien hay kem file rieng cua nguoi lam: ghi lai de in vao khung TOM TAT (bo cai CloudBlue KHONG dung cac file nay)
    $extra = @()
    foreach ($n in @("autounattend.xml", "sources\pid.txt", "sources\ei.cfg")) { if (Test-Path (Join-Path $root $n)) { $extra += $n } }
    $oemDir = Join-Path $root 'sources\$OEM$'
    if (Test-Path -LiteralPath $oemDir) {
      $oemFiles = @(Get-ChildItem -LiteralPath $oemDir -Recurse -File)
      $extra += ('$OEM$ (' + $oemFiles.Count + ' file: ' + ((@($oemFiles | Select-Object -First 8 | ForEach-Object { $_.Name })) -join ', ') + ')')
    }
    $src += [pscustomobject]@{ Root = $root; Image = $img; Pick = $pick; Bytes = $bytes; Path = $p; Std = $std; Extra = ($extra -join ' ; ') }
  }
  $stdSrc = @($src | Where-Object { $_.Std })
  if ($stdSrc.Count -eq 0) { Stop-Build "Khong ISO nao co du bo khoi dong chuan o goc (sources\boot.wim + boot\boot.sdi + efi\microsoft\boot\efisys.bin). ISO 2 kien truc (x86 + x64) chi dung duoc lam ban Windows phu - can them 1 ISO Windows 64-bit chuan." }
  $baseSrc = $stdSrc | Sort-Object { try { [version]$_.Pick.Version } catch { [version]"0.0" } } -Descending | Select-Object -First 1
  Say ("   Bo cai goc (moi truong cai dat): " + (Split-Path -Leaf $baseSrc.Path) + "  [" + $baseSrc.Pick.Version + "]") "DarkGray"

  # ---------------------------------------------------------------- 6. dung cay ISO
  Step "6/8  Chep bo cai goc + ghep phan mem CloudBlue (vai phut)"
  $rc = Run-Exe "robocopy.exe" @(($baseSrc.Root.TrimEnd("\") + "\."), $IsoRoot, "/E", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
  if ($rc -ge 8) { Stop-Build ("Chep ISO goc loi (robocopy ma " + $rc + ").") }
  $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
  & attrib.exe -R (Join-Path $IsoRoot "*") /S /D 2>$null | Out-Null
  $ErrorActionPreference = $old
  $wpSrc = ""
  if ($Them) {
    $nThem = 0
    foreach ($pair in @(@("drivers", "cb\drivers"), @("firstboot.d", "cb\os\firstboot.d"))) {
      $from = Join-Path $Them $pair[0]
      if (Test-Path $from) {
        $r3 = Run-Exe "robocopy.exe" @($from, (Join-Path $IsoRoot $pair[1]), "/E", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
        if ($r3 -ge 8) { Stop-Build ("Chep " + $from + " loi (robocopy ma " + $r3 + ").") }
        $nThem += @(Get-ChildItem $from -Recurse -File).Count
      }
    }
    foreach ($n in @("wallpaper.jpg", "wallpaper.jpeg", "wallpaper.png", "wallpaper.bmp")) {
      $c = Join-Path $Them $n
      if ((-not $wpSrc) -and (Test-Path $c)) { $wpSrc = $c }
    }
    if (($nThem -eq 0) -and (-not $wpSrc)) { Note ("Thu muc them khong co drivers\ , firstboot.d\ hay wallpaper.jpg nao: " + $Them) } else { Say ("   them " + $nThem + " file tu " + $Them + " (drivers / firstboot.d)") "DarkGray" }
    $ddir = Join-Path $IsoRoot "cb\drivers"
    if (Test-Path $ddir) {
      try { Expand-DriverPacks $ddir } catch { Note ("Giai nen goi driver loi: " + $_.Exception.Message) }
      $loose = @(Get-ChildItem $ddir -File -Filter *.inf).Count
      if ($loose -gt 0) { [void]$DrvInfo.Add("DRIVER (file le, moi ban): " + $loose + " file .inf") }
      foreach ($sd in @(Get-ChildItem $ddir -Directory)) {
        $ninf = @(Get-ChildItem $sd.FullName -Recurse -File -Filter *.inf).Count
        $nvga = @(Get-ChildItem $sd.FullName -File | Where-Object { $_.Name -match '^\d{3}\.\d{2}-(notebook|desktop)-' }).Count
        $line = "DRIVER " + $sd.Name + ": " + $ninf + " file .inf"
        if ($nvga -gt 0) { $line = $line + " + " + $nvga + " goi VGA NVIDIA (.exe)" }
        [void]$DrvInfo.Add($line)
        if (($ninf -eq 0) -and ($nvga -eq 0)) { Note ("Thu muc driver '" + $sd.Name + "' khong co file .inf nao - se KHONG nap duoc. Driver dang .exe phai giai nen ra (7-Zip / WinRAR) de co file .inf.") }
      }
    }
  }
  $images = @()
  foreach ($s in $src) {
    $isBase = ($s.Path -eq $baseSrc.Path)
    $ipath = $s.Image
    if ($isBase) { $ipath = Join-Path $IsoRoot ("sources\" + (Split-Path -Leaf $s.Image)) }
    $images += @{ src = $ipath; base = $isBase; index = $s.Pick.Index; name = $s.Pick.Name; edition = $s.Pick.Edition; version = $s.Pick.Version; lang = $s.Pick.Lang; arch = $s.Pick.Arch }
  }
  $defIdx = -1
  if ($images.Count -gt 1) {
    Say "   Ban Windows MAC DINH khi cai tu USB / ISO (luc dem nguoc 30 giay van doi duoc bang phim so):" "White"
    for ($i = 0; $i -lt $images.Count; $i++) { Say ("      " + ($i + 1) + " = " + $images[$i].name + "  [" + $images[$i].version + "]") "DarkGray" }
    $ans = ("" + (Read-Host "   Go so roi Enter (Enter trong = ban moi nhat)")).Trim()
    if ($ans) {
      $k = 0
      if ([int]::TryParse($ans, [ref]$k) -and ($k -ge 1) -and ($k -le $images.Count)) { $defIdx = $k - 1 } else { Stop-Build ("Lua chon ban mac dinh khong hop le: " + $ans) }
    }
  }
  $gk = "auto"
  if ($KhoaChung) { $gk = "on" }
  if ($KhongKhoaChung) { $gk = "off" }
  $infoFile = Join-Path $Dl "build-info.txt"
  Remove-Item -Force $infoFile -ErrorAction SilentlyContinue
  $params = @{ out = $IsoRoot; tool = $Tool; py = $PyDir; images = $images; user = $TaiKhoan; password = $MatKhau; sb_url = $SbUrl; sb_key = $SbKey; enroll_key = $MaDangKy; generic_key = $gk; info = $infoFile; wallpaper = $wpSrc; default_index = $defIdx }
  $pj = Join-Path $Dl "params.json"
  [IO.File]::WriteAllText($pj, ($params | ConvertTo-Json -Depth 6), (New-Object Text.UTF8Encoding($false)))
  $rc = Run-Exe $PyExe @("-I", "-B", (Join-Path $Tool "cb_build.py"), "layout", $pj)
  Remove-Item -Force $pj -ErrorAction SilentlyContinue
  if ($rc -ne 0) { Stop-Build ("Sap xep bo cai loi (cb_build ma " + $rc + ").") }

  # ---------------------------------------------------------------- 7. chen bo cai vao boot.wim
  Step "7/8  Chen bo cai CloudBlue vao moi truong cai dat (boot.wim)"
  $wim = Join-Path $IsoRoot "sources\boot.wim"
  $cnt = @(Get-ImageList $wim).Count
  $bidx = 1
  if ($cnt -ge 2) { $bidx = 2 }
  New-Item -ItemType Directory -Force $MountDir | Out-Null
  $rc = Run-Exe "dism.exe" @("/English", "/Mount-Image", "/ImageFile:$wim", "/Index:$bidx", "/MountDir:$MountDir")
  if ($rc -ne 0) { Stop-Build ("Khong mo duoc boot.wim (dism ma " + $rc + "). Tat phan mem diet virus roi chay lai.") }
  $okPatch = $false
  try {
    $cbm = Join-Path $MountDir "cb"
    foreach ($sub in @("py", "lib", "pe")) {
      $r2 = Run-Exe "robocopy.exe" @((Join-Path $IsoRoot ("cb\" + $sub)), (Join-Path $cbm $sub), "/E", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
      if ($r2 -ge 8) { throw ("chep " + $sub + " loi") }
    }
    $ini = Join-Path $MountDir "Windows\System32\winpeshl.ini"
    if (Test-Path $ini) { Copy-Item -Force $ini ($ini + ".goc"); Note "boot.wim goc da co san winpeshl.ini (ban ISO tuy bien) - da thay bang cua CloudBlue, ban cu luu thanh winpeshl.ini.goc." }
    Copy-Item -Force (Join-Path $Tool "boot\winpeshl.ini") $ini
    if (-not (Test-Path (Join-Path $cbm "py\python.exe")) -or -not (Test-Path (Join-Path $cbm "pe\cb_pe.py"))) { throw "thieu file sau khi chep" }
    $okPatch = $true
  } catch {
    Say ("   loi: " + $_) "Red"
  }
  if ($okPatch) {
    $rc = Run-Exe "dism.exe" @("/English", "/Unmount-Image", "/MountDir:$MountDir", "/Commit")
    if ($rc -ne 0) { $okPatch = $false }
  }
  if (-not $okPatch) {
    Run-Exe "dism.exe" @("/English", "/Unmount-Image", "/MountDir:$MountDir", "/Discard") | Out-Null
    Stop-Build "Chen boot.wim that bai."
  }
  Remove-Item -Recurse -Force $MountDir -ErrorAction SilentlyContinue
  $rc = Run-Exe $PyExe @("-I", "-B", (Join-Path $Tool "cb_build.py"), "check", $IsoRoot)
  if ($rc -ne 0) { Stop-Build "Cay ISO thieu file (xem cac dong THIEU o tren)." }

  # ---------------------------------------------------------------- tu kiem tren may nay (CHI DOC, khong doi gi)
  Step "Tu kiem tren may nay (chi doc o dia, KHONG doi gi)"
  $t1 = Run-Exe $PyExe @("-I", "-B", (Join-Path $IsoRoot "cb\lib\cbsys.py"), "--selftest")
  Write-Host ""
  $t2 = Run-Exe $PyExe @("-I", "-B", "-u", (Join-Path $IsoRoot "cb\pe\cb_pe.py"), "--dry-run", $IsoRoot)
  $selfOk = (($t1 -eq 0) -and ($t2 -eq 0))
  if (-not $selfOk) { Note ("Tu kiem chua dat (doc o dia: ma " + $t1 + ", chay thu bo cai: ma " + $t2 + ") - gui phan chu o tren cho ho tro TRUOC khi dung ISO.") }

  # ---------------------------------------------------------------- 8. dong ISO
  $isoDone = $false
  if (-not $KhongIso) {
    Step "8/8  Dong file ISO (vai phut)"
    $osc = Find-Oscdimg $Dl
    if (-not $osc) {
      Note "Khong co oscdimg.exe (khong tai duoc tu Microsoft). Cay bo cai da dung xong o thu muc iso - xem huong dan de dong ISO sau."
    } else {
      if (Test-Path $Out) { Remove-Item -Force $Out }
      $bios = Join-Path $IsoRoot "boot\etfsboot.com"
      $efi = Join-Path $IsoRoot "efi\microsoft\boot\efisys.bin"
      if (-not (Test-Path $efi)) { Stop-Build "Bo cai goc thieu efi\microsoft\boot\efisys.bin." }
      if (Test-Path $bios) { $bd = "-bootdata:2#p0,e,b" + $bios + "#pEF,e,b" + $efi } else { $bd = "-bootdata:1#pEF,e,b" + $efi }
      $rc = Run-Exe $osc @("-m", "-o", "-u2", "-udfver102", $bd, "-lCLOUDBLUE_PC", $IsoRoot, $Out)
      if ($rc -ne 0 -or -not (Test-Path $Out)) { Stop-Build ("Dong ISO loi (oscdimg ma " + $rc + ").") }
      $isoDone = $true
    }
  }

  # ---------------------------------------------------------------- tom tat
  $mins = [math]::Round(((Get-Date) - $T0).TotalMinutes, 1)
  Write-Host ""
  Write-Host "================= TOM TAT (chep ca khung nay gui ho tro) =================" -ForegroundColor Green
  Write-Host ("tao-iso " + $VER + " - xong sau " + $mins + " phut")
  foreach ($s in $src) {
    Write-Host ("  ISO goc: " + (Split-Path -Leaf $s.Path) + " -> " + $s.Pick.Name + " [" + $s.Pick.Edition + " " + $s.Pick.Version + "] ban so " + $s.Pick.Index + ", " + [math]::Round($s.Bytes / 1GB, 2) + " GB")
    if ($s.Extra) { Write-Host ("     file rieng cua ISO nay (khong dung toi): " + $s.Extra) }
  }
  if (Test-Path $infoFile) { Get-Content -Encoding UTF8 $infoFile | ForEach-Object { Write-Host ("  " + $_) } }
  foreach ($n in $DrvInfo) { Write-Host ("  " + $n) }
  Write-Host ("  Chen boot.wim (ban so " + $bidx + "): OK")
  Write-Host ("  Tu kiem: doc o dia = " + $(if ($t1 -eq 0) { "DAT" } else { "CHUA DAT (" + $t1 + ")" }) + " ; chay thu bo cai = " + $(if ($t2 -eq 0) { "DAT" } else { "CHUA DAT (" + $t2 + ")" }))
  Write-Host ("  Ma dang ky: " + $(if ($MaDangKy) { "CO" } else { "KHONG" }))
  if ($isoDone) { Write-Host ("  ISO: " + $Out + "  (" + [math]::Round((Get-Item $Out).Length / 1GB, 2) + " GB)") -ForegroundColor Green }
  else { Write-Host ("  ISO: CHUA dong - cay bo cai o " + $IsoRoot) -ForegroundColor Yellow }
  foreach ($n in $Notes) { Write-Host ("  (!) " + $n) -ForegroundColor Yellow }
  Write-Host "==========================================================================" -ForegroundColor Green
  if ($isoDone -and $selfOk) {
    Write-Host ""
    Write-Host "  BUOC KE: thu tren 1 MAY THU / may ao truoc (may do se bi XOA SACH):" -ForegroundColor White
    Write-Host "    - ghi ISO ra USB bang Rufus (hoac chep vao USB Ventoy), cam vao may, khoi dong tu USB"
    Write-Host "    - man hinh dem nguoc 30 giay ghi ro o nao se bi xoa; bam X de huy"
  }
  if ($isoDone -and -not $GiuWork) {
    foreach ($d in @($IsoRoot, $PyDir, $Tool)) { Remove-Item -Recurse -Force $d -ErrorAction SilentlyContinue }
  }
} catch {
  if ("" + $_.Exception.Message -ne "cb-stop") {
    Write-Host ""
    Write-Host ("!! LOI KHONG NGO: " + $_.Exception.Message) -ForegroundColor Red
    Write-Host ("   dong " + $_.InvocationInfo.ScriptLineNumber + ": " + ("" + $_.InvocationInfo.Line).Trim()) -ForegroundColor Red
    Write-Host "   Chup man hinh nay gui ho tro." -ForegroundColor Red
  }
} finally {
  if ($MountDir -and (Test-Path $MountDir) -and (Test-Path (Join-Path $MountDir "Windows"))) {
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    & dism.exe /English /Unmount-Image "/MountDir:$MountDir" /Discard 2>$null | Out-Null
    $ErrorActionPreference = $old
  }
  foreach ($m in $Mounted) { try { Dismount-DiskImage -ImagePath $m | Out-Null } catch { } }
}
