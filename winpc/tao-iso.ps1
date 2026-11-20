# =====================================================================================================
#  cloudblue-tao-iso   (ban 21.11a)
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
#     -TaiKhoan PC  -MatKhau ""                         tai khoan Windows tao san tren may cho thue. Mac dinh la tai khoan THUONG (khong co quyen Admin):
#                                                       khach khong go / sua duoc phan mem CloudBlue, khong dung duoc phan vung cuu ho; tren may khong con
#                                                       tai khoan quan tri nao dung duoc (moi viec quan tri di qua web).
#     -KhachAdmin                                       de tai khoan khach co quyen Admin (khach tu cai duoc moi phan mem, nhung pha duoc phan mem quan ly)
#     -GiuWork                                          giu thu muc lam viec sau khi xong
#     -Driver "2=D:\drv\lan.zip","2=D:\drv\vga.exe"     driver RIENG cho ban Windows cua ISO thu 2: file .exe .zip .7z .rar .cab hoac thu muc co file .inf.
#                                                       Khong dung tham so nay thi script HOI rieng cho tung ban (keo tha file / thu muc vao cua so).
#     -KhongHoi                                         khong hoi gi (chay tu dong): moi lua chon lay mac dinh; ma dang ky lay tu -MaDangKy / lan chay truoc
#     -Them "D:\cb-them"                                thu muc THEM vao bo cai (bo trong: tu tim thu muc ten cb-them nam canh file ISO):
#                                                         drivers\            driver cho MOI ban Windows (thu muc co file .inf, hoac goi .zip / .exe)
#                                                         drivers\1511\       driver chi cho ban 1511   (tuong tu: drivers\22h2\ ...)
#                                                         firstboot.d\        file .cmd .bat .ps1 chay 1 lan o lan dang nhap dau (firstboot.d\1511\ = chi ban 1511)
#                                                         wallpaper.jpg       anh nen rieng (khong co thi dung anh nen CloudBlue)
#     -KhongIso                                         chi dung cay thu muc, khong dong ISO
#     -KhongKiemMa                                      khong hoi may chu xem ma dang ky con hieu luc khong (mac dinh CO hoi: ma cu thi dung lai ngay,
#                                                       khoi mat cong tao ISO + cai may roi may khong hien len web)
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
  [string[]]$Driver = @(),
  [switch]$KhongHoi,
  [switch]$KhachAdmin,
  [switch]$KhongIso,
  [switch]$KhongKiemMa,
  [switch]$KhoaChung,
  [switch]$KhongKhoaChung
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$VER = "21.11a"
$REPO = "https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue"
$PYURL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
$TOOLFILES = @("lib/cbsys.py", "lib/cbcore.py", "lib/cbrec.py", "pe/cb_pe.py", "pe/start.cmd", "boot/winpeshl.ini",
               "os/cb_provision.py", "os/provision.cmd", "os/cb_stage.py", "os/unattend.tpl.xml", "os/wallpaper.jpg",
               "agent/pcagent.py", "agent/watch.cmd", "agent/cbpc.cmd", "CAI-DAT.cmd", "cb_build.py")
$T0 = Get-Date
$Mounted = New-Object System.Collections.ArrayList
$Notes = New-Object System.Collections.ArrayList
$MountDir = ""
# oscdimg.exe 2.56 tren may chu ky hieu cua Microsoft (cung dia chi + ma kiem ma goi winget Microsoft.OSCDIMG dung)
$OSC_SHA = "2000160b2c5044691b2f9a0ac308e5207f273d4880a572457af16d05886ba861"
$OscInfo = ""
$OscWhy = New-Object System.Collections.ArrayList
$GetFileErr = ""
$PACKEXT = @(".exe", ".zip", ".7z", ".rar", ".cab")

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
  # Chay 1 chuong trinh ngoai, in thang ra man hinh, tra ma thoat (khong de chu loi cua no lam dung script). Khong chay duoc -> 9009.
  $old = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $rc = 9009
  try { & $exe @a 2>&1 | ForEach-Object { Write-Host ("   " + $_) }; $rc = $LASTEXITCODE } catch { Write-Host ("   " + $_) }
  $ErrorActionPreference = $old
  return $rc
}

function Test-EnrollKey([string]$url, [string]$anon, [string]$key) {
  # Hoi may chu (ham pc_key_check, SQL v42): ma dang ky nay con dung duoc khong?
  # Tra:  "ok" = con hieu luc ; "bad" = ma cu / sai ; "nokey" = tren web dang tat ma ; "" = khong hoi duoc (mat mang, may chu chua co ham nay...)
  try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $h = @{ apikey = $anon; Authorization = ("Bearer " + $anon) }
    $body = '{"p_key":"' + $key + '"}'
    $r = Invoke-RestMethod -Method Post -Uri ($url.TrimEnd("/") + "/rest/v1/rpc/pc_key_check") -Headers $h -ContentType "application/json" -Body $body -TimeoutSec 20
    if ($r.ok -eq $true) { return "ok" }
    if (("" + $r.err) -eq "BAD_KEY") { return "bad" }
    if (("" + $r.err) -eq "NO_KEY") { return "nokey" }
    return ""
  } catch { return "" }
}

function Get-File([string]$url, [string]$dst, [string]$agent = "") {
  # Tai 1 file (curl.exe cua Windows truoc, khong duoc thi Invoke-WebRequest). Loi thi ly do nam o $script:GetFileErr.
  $script:GetFileErr = ""
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
    $crc = $LASTEXITCODE
    $ErrorActionPreference = $old
    if ($crc -eq 0 -and (Test-Path $dst) -and ((Get-Item $dst).Length -gt 0)) { return $true }
    $script:GetFileErr = "curl ma " + $crc
  }
  try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $iw = @{ UseBasicParsing = $true; Uri = $url; OutFile = $dst }
    if ($agent) { $iw["UserAgent"] = $agent }
    Invoke-WebRequest @iw
    if ((Test-Path $dst) -and ((Get-Item $dst).Length -gt 0)) { return $true }
    $script:GetFileErr = ($script:GetFileErr + " ; tai ve file rong").Trim(" ;")
    return $false
  } catch {
    $script:GetFileErr = ($script:GetFileErr + " ; " + $_.Exception.Message).Trim(" ;")
    return $false
  }
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

function Test-There([string]$p) {
  # Test-Path khong nem loi khi duong dan co ky tu la (nguoi dung dan nham).
  if (-not $p) { return $false }
  try { return [bool](Test-Path -LiteralPath $p) } catch { return $false }
}

function Test-IsoPath([string]$p) {
  # File .iso, hoac thu muc (bo cai da giai nen).
  try { if (Test-Path -LiteralPath $p -PathType Container) { return $true } } catch { return $false }
  return [bool]($p -match '\.iso$')
}

function Split-Paths([string]$line) {
  # 1 dong nguoi dung dan / keo tha -> cac duong dan. Keo nhieu file 1 luc thi cac duong dan cach nhau bang dau cach,
  # cai nao co dau cach thi nam trong nhay kep.
  $t = ("" + $line).Trim()
  if (-not $t) { return }
  $one = Clean-Path $t
  if (Test-There $one) { return $one }
  foreach ($mm in [regex]::Matches($t, '"([^"]+)"|(\S+)')) {
    $v = ("" + $mm.Groups[1].Value + $mm.Groups[2].Value).Trim()
    if ($v) { $v }
  }
}

function Test-NvidiaName([string]$n) {
  # Goi cai VGA NVIDIA (466.77-notebook-win10-64bit-international-whql.exe ...) hoac file script da danh dau nvidia-vga-...
  return [bool](($n -match '^\d{3}\.\d{2}-(notebook|desktop)-.*\.exe$') -or ($n -match '^nvidia-vga-.*\.exe$'))
}

function Count-Inf([string]$dir) {
  if (-not (Test-There $dir)) { return 0 }
  return @(Get-ChildItem -LiteralPath $dir -Recurse -File -Filter *.inf -ErrorAction SilentlyContinue).Count
}

function Test-DriverDrop([string]$p) {
  # Thu nguoi dung keo tha lam driver co dung duoc khong: "" = duoc, con lai = ly do tu choi.
  if (-not (Test-There $p)) { return ("khong thay " + $p) }
  $it = Get-Item -LiteralPath $p
  if ($it.PSIsContainer) {
    if ($it.FullName.TrimEnd("\").Length -le 3) { return ("day la ca o dia - hay keo dung thu muc driver: " + $p) }
    $hit = @(Get-ChildItem -LiteralPath $it.FullName -Recurse -File -ErrorAction SilentlyContinue | Where-Object { ($_.Extension -eq ".inf") -or ($PACKEXT -contains $_.Extension.ToLower()) } | Select-Object -First 1).Count
    if ($hit -eq 0) { return ("thu muc nay khong co file .inf / .exe / .zip nao: " + $p) }
    return ""
  }
  $ext = $it.Extension.ToLower()
  if ($ext -eq ".iso") { return ("day la file ISO, khong phai driver: " + $p) }
  if ($ext -eq ".inf") { return ("file .inf phai di cung cac file khac cua driver - hay keo CA THU MUC chua no: " + $p) }
  if (-not ($PACKEXT -contains $ext)) { return ("chi nhan file .exe .zip .7z .rar .cab hoac thu muc driver: " + $p) }
  return ""
}

function Get-DropText([string]$p) {
  $it = Get-Item -LiteralPath $p
  if ($it.PSIsContainer) { return ($it.Name + "  (thu muc, " + (Count-Inf $it.FullName) + " file .inf)") }
  return ($it.Name + "  (" + [math]::Round($it.Length / 1MB, 1) + " MB)")
}

function Get-DropName([IO.FileInfo]$f) {
  # Ten file khi chep vao bo cai. Goi VGA NVIDIA da bi doi ten (khong con dang 466.77-notebook-...) -> them tien to nvidia-vga-
  # de cb_build.py van nhan ra va cho cai im lang o lan dang nhap dau.
  $n = $f.Name
  if (($f.Extension -eq ".exe") -and (-not (Test-NvidiaName $n))) {
    $co = ""
    try { $co = "" + $f.VersionInfo.CompanyName } catch { $co = "" }
    if ($co -match "NVIDIA") { $n = "nvidia-vga-" + $n }
  }
  return $n
}

function Free-Name([string]$dir, [string]$name) {
  # Duong dan chua co ai dung trong $dir cho ten $name (ten chi giu chu / so / _ . - de cong cu nao cung doc duoc).
  $n = ($name -replace '[^A-Za-z0-9_.-]', '_')
  if (-not $n.Trim("._")) { $n = "driver" }
  $bn = [IO.Path]::GetFileNameWithoutExtension($n)
  $ex = [IO.Path]::GetExtension($n)
  $c = Join-Path $dir $n
  $i = 1
  while (Test-Path -LiteralPath $c) { $i++; $c = Join-Path $dir ($bn + "_" + $i + $ex) }
  return $c
}

function Get-OsTag([string]$osver) {
  # "10.0.19045.4291" -> "22H2" ; "10.0.10586.0" -> "1511"  (chi de hien cho nguoi dung de nhin)
  $b = 0
  if (("" + $osver) -match '^\d+\.\d+\.(\d+)') { $b = [int]$Matches[1] }
  $map = @{ 10240 = "1507"; 10586 = "1511"; 14393 = "1607"; 15063 = "1703"; 16299 = "1709"; 17134 = "1803"; 17763 = "1809"; 18362 = "1903"; 18363 = "1909"; 19041 = "2004"; 19042 = "20H2"; 19043 = "21H1"; 19044 = "21H2"; 19045 = "22H2"; 22000 = "11-21H2"; 22621 = "11-22H2"; 22631 = "11-23H2"; 26100 = "11-24H2"; 26200 = "11-25H2" }
  if ($map.ContainsKey($b)) { return ("" + $map[$b]) }
  return ("build " + $b)
}

function Expand-One([string]$file, [string]$to, [string]$seven) {
  # Giai nen 1 goi driver ra thu muc $to, thu lan luot cac cong cu co tren may. Tra so file .inf lay duoc (0 = khong duoc).
  $ext = [IO.Path]::GetExtension($file).ToLower()
  $tar = Join-Path $env:SystemRoot "System32\tar.exe"
  $exp = Join-Path $env:SystemRoot "System32\expand.exe"
  $rar = ""
  foreach ($pf in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
    if ($pf -and (-not $rar) -and (Test-Path (Join-Path $pf "WinRAR\WinRAR.exe"))) { $rar = Join-Path $pf "WinRAR\WinRAR.exe" }
  }
  foreach ($way in @("zip", "cab", "7z", "rar", "tar")) {
    if (($way -eq "zip") -and ($ext -ne ".zip")) { continue }
    if (($way -eq "cab") -and ($ext -ne ".cab")) { continue }
    if (($way -eq "7z") -and (-not $seven)) { continue }
    if (($way -eq "rar") -and (-not $rar)) { continue }
    if (($way -eq "tar") -and (-not (Test-Path $tar))) { continue }
    New-Item -ItemType Directory -Force $to | Out-Null
    if ($way -eq "zip") { try { Expand-Archive -Force -LiteralPath $file -DestinationPath $to } catch { } }
    elseif ($way -eq "cab") { [void](Run-Quiet $exp @("-F:*", $file, $to)) }
    elseif ($way -eq "7z") { [void](Run-Quiet $seven @("x", "-y", ("-o" + $to), $file)) }
    elseif ($way -eq "rar") { [void](Run-Quiet $rar @("x", "-ibck", "-inul", "-y", "-o+", $file, ($to.TrimEnd("\") + "\"))) }
    else { [void](Run-Quiet $tar @("-xf", $file, "-C", $to)) }
    $n = Count-Inf $to
    if ($n -gt 0) { return $n }
  }
  return 0
}

function Expand-DriverPacks([string]$dir) {
  # Goi driver de nguyen file (.zip .cab .7z .rar, hoac .exe tu giai nen) nam ngay trong cb\drivers hoac trong thu muc con cap 1
  # (vi du drivers\1511, hoac _img2 = driver nguoi dung keo tha cho ban Windows cua ISO thu 2)
  #   ->  giai nen ra thu muc cung ten de lay file .inf (bo cai chi nap duoc driver dang .inf).
  # Cong cu: Expand-Archive (.zip), expand.exe (.cab), 7-Zip / WinRAR neu may nay co cai, tar.exe cua Windows.
  # Thu muc da co san file .inf ngay trong no thi khong dung toi (tru thu muc _img: moi file trong do deu la goi nguoi dung dua).
  # Goi VGA NVIDIA KHONG giai nen o day: cb_build.py chuyen no sang firstboot.d de cai im lang o lan dang nhap dau.
  $seven = ""
  $cands = @((Join-Path $env:ProgramFiles "7-Zip\7z.exe"))
  $pf86 = ${env:ProgramFiles(x86)}
  if ($pf86) { $cands += (Join-Path $pf86 "7-Zip\7z.exe") }
  foreach ($c in $cands) { if ((-not $seven) -and (Test-Path $c)) { $seven = $c } }
  $tops = @($dir)
  foreach ($d in @(Get-ChildItem -LiteralPath $dir -Directory)) { $tops += $d.FullName }
  foreach ($t in $tops) {
    $staged = [bool]((Split-Path -Leaf $t) -match '^_img\d+$')
    if ((-not $staged) -and (@(Get-ChildItem -LiteralPath $t -File -Filter *.inf).Count -gt 0)) { continue }
    $packs = @(Get-ChildItem -LiteralPath $t -File | Where-Object { ($PACKEXT -contains $_.Extension.ToLower()) -and ($staged -or ($_.Extension -ne ".exe") -or ($_.Length -gt 1MB)) })
    foreach ($f in $packs) {
      if (Test-NvidiaName $f.Name) { continue }
      $to = Join-Path $t ($f.BaseName -replace '[^A-Za-z0-9_.-]', '_')
      if (Test-Path -LiteralPath $to) { $to = $to + "_x" }
      $ninf = Expand-One $f.FullName $to $seven
      if ($ninf -gt 0) {
        Remove-Item -LiteralPath $f.FullName -Force
        Say ("   da giai nen goi driver " + $f.Name + " (" + $ninf + " file .inf)") "DarkGray"
      } else {
        if (Test-Path -LiteralPath $to) { Remove-Item -LiteralPath $to -Recurse -Force -ErrorAction SilentlyContinue }
        $hint = ""
        if ((-not $seven) -and ($f.Extension -ne ".zip")) { $hint = " (may nay chua cai 7-Zip: cai 7-Zip tu 7-zip.org roi chay lai co the giai nen duoc)" }
        if ($staged) {
          Remove-Item -LiteralPath $f.FullName -Force -ErrorAction SilentlyContinue
          Note ("Goi driver " + $f.Name + ": khong lay ra duoc file .inf nao" + $hint + " -> KHONG dua vao bo cai. Cach chac an: tren 1 may dang chay tot ban Windows do (da du driver), mo PowerShell (Admin) chay   dism /online /export-driver /destination:D:\drv   roi keo thu muc D:\drv vao buoc hoi driver.")
        } else {
          Note ("Goi driver " + $f.Name + ": giai nen khong ra file .inf nao" + $hint + " - se KHONG nap duoc kieu driver (neu la bo cai .exe thi dung lenh chay lan dau trong firstboot.d).")
        }
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

function Test-Pe([string]$p) {
  # File chuong trinh Windows (bat dau bang "MZ") va co co hop ly cho oscdimg.exe?
  try {
    $it = Get-Item -LiteralPath $p
    if (($it.Length -lt 16KB) -or ($it.Length -gt 32MB)) { return $false }
    $fs = [IO.File]::OpenRead($it.FullName)
    try { $b0 = $fs.ReadByte(); $b1 = $fs.ReadByte() } finally { $fs.Close() }
    return [bool](($b0 -eq 77) -and ($b1 -eq 90))
  } catch { return $false }
}

function Find-Oscdimg([string]$dl, [string[]]$near) {
  # Tim oscdimg.exe (cong cu dong ISO cua Microsoft): bo ADK da cai -> canh script / canh file ISO -> ban da tai lan truoc -> tai tu may chu Microsoft.
  # Ban tai ve duoc kiem bang ma kiem SHA-256 da ghim (file tren may chu ky hieu cua Microsoft KHONG kem chu ky so nen khong kiem chu ky duoc).
  # Ket qua: duong dan ("" = khong co). $script:OscInfo = lay tu dau ; $script:OscWhy = cac ly do that bai.
  $c = @()
  foreach ($pf in @(${env:ProgramFiles(x86)}, $env:ProgramFiles)) {
    if ($pf) {
      foreach ($arch in @("amd64", "x86")) { $c += (Join-Path $pf ("Windows Kits\10\Assessment and Deployment Kit\Deployment Tools\" + $arch + "\Oscdimg\oscdimg.exe")) }
    }
  }
  if ($PSScriptRoot) { $c += (Join-Path $PSScriptRoot "oscdimg.exe") }
  foreach ($n in $near) { if ($n) { $c += (Join-Path $n "oscdimg.exe") } }
  foreach ($p in $c) {
    if ((Test-There $p) -and (Test-Pe $p)) { $script:OscInfo = "co san tren may: " + $p; return $p }
  }
  $dst = Join-Path $dl "oscdimg.exe"
  if ((Test-There $dst) -and (Test-Pe $dst)) {
    $h = Get-Sha $dst
    $script:OscInfo = "ban da tai lan truoc, ma kiem " + $h.Substring(0, 16) + $(if ($h -eq $OSC_SHA) { " (khop ban Microsoft 2.56)" } else { " (khong phai ban da ghim)" })
    return $dst
  }
  Say "   tai oscdimg.exe (cong cu dong ISO cua Microsoft, ~150KB) tu may chu Microsoft..." "DarkGray"
  foreach ($s in @(@("688CABB065000", $OSC_SHA), @("3D44737265000", ""))) {
    $url = "https://msdl.microsoft.com/download/symbols/oscdimg.exe/" + $s[0] + "/oscdimg.exe"
    $ok = Get-File $url $dst "Microsoft-Symbol-Server/10.0.0.0"
    if (-not $ok) {
      $e1 = $script:GetFileErr
      $ok = Get-File $url $dst
      if (-not $ok) { [void]$script:OscWhy.Add($s[0] + ": tai loi (" + $e1 + " | " + $script:GetFileErr + ")"); continue }
    }
    $len = (Get-Item -LiteralPath $dst).Length
    $h = Get-Sha $dst
    if ($s[1] -and ($h -ne $s[1])) {
      [void]$script:OscWhy.Add($s[0] + ": ma kiem khac ban da ghim (" + $h.Substring(0, 16) + ", " + $len + " byte)")
      Remove-Item -LiteralPath $dst -Force -ErrorAction SilentlyContinue
      continue
    }
    if ((-not $s[1]) -and (-not (Test-Pe $dst))) {
      [void]$script:OscWhy.Add($s[0] + ": file tai ve khong phai chuong trinh Windows (" + $len + " byte)")
      Remove-Item -LiteralPath $dst -Force -ErrorAction SilentlyContinue
      continue
    }
    $sg = "?"
    try { $sg = "" + (Get-AuthenticodeSignature -LiteralPath $dst).Status } catch { $sg = "?" }
    $script:OscInfo = "tai tu msdl.microsoft.com/" + $s[0] + ", " + $len + " byte, ma kiem " + $h.Substring(0, 16) + $(if ($s[1]) { " KHOP ban da ghim" } else { " (ban du phong, khong ghim)" }) + ", chu ky so: " + $sg
    return $dst
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
  if (($Iso.Count -eq 0) -and (-not $KhongHoi)) {
    Say "   Keo tha tung file ISO vao cua so nay roi bam Enter (hoac dan duong dan). Xong thi bam Enter trong." "White"
    Say "   (CHI file .iso o buoc nay - driver se duoc hoi rieng cho tung ban Windows o buoc 5.)" "DarkGray"
    while ($true) {
      $line = "" + (Read-Host ("   ISO thu " + ($Iso.Count + 1) + " (Enter trong = het)"))
      if (-not $line.Trim()) { break }
      foreach ($p in @(Split-Paths $line)) {
        if (-not (Test-There $p)) { Say ("   khong thay: " + $p) "Yellow"; continue }
        if (-not (Test-IsoPath $p)) { Say ("   day KHONG phai file .iso (driver se duoc hoi rieng o buoc 5): " + $p) "Yellow"; continue }
        $Iso += $p
      }
    }
  }
  $Iso = @($Iso | ForEach-Object { Clean-Path $_ } | Where-Object { $_ })
  if ($Iso.Count -eq 0) { Stop-Build "Chua co file ISO nao." }
  foreach ($p in $Iso) {
    if (-not (Test-There $p)) { Stop-Build ("Khong thay: " + $p) }
    if (-not (Test-IsoPath $p)) { Stop-Build ("Day khong phai file .iso (hoac thu muc bo cai da giai nen): " + $p) }
  }

  # ---------------------------------------------------------------- thu muc THEM (driver chung, lenh chay lan dau, anh nen rieng)
  if (-not $Them) {
    foreach ($p in $Iso) {
      $par = Split-Path -Parent (Get-Item -LiteralPath $p).FullName
      if ($par -and (-not $Them)) {
        $c = Join-Path $par "cb-them"
        if (Test-Path -LiteralPath $c -PathType Container) { $Them = $c }
      }
    }
    if ($Them) { Say ("   Thu muc them (tu tim thay canh file ISO): " + $Them) "White" }
  }
  if ($Them) {
    $Them = Clean-Path $Them
    if (-not (Test-There $Them)) { Stop-Build ("Khong thay thu muc them: " + $Them) }
    if (-not (Test-Path -LiteralPath $Them -PathType Container)) { Stop-Build ("-Them phai la THU MUC (ben trong co drivers\ , firstboot.d\ , wallpaper.jpg), khong phai file: " + $Them + "   Driver dang file .exe / .zip thi script se hoi rieng cho tung ban Windows o buoc 5.") }
  }

  # ---------------------------------------------------------------- driver rieng tung ban Windows dua bang tham so -Driver "<so thu tu ISO>=<duong dan>"
  $DrvArg = @{}
  foreach ($d in $Driver) {
    if (-not (("" + $d) -match '^\s*(\d+)\s*=\s*(.+)$')) { Stop-Build ("-Driver phai co dang  <so thu tu ISO>=<duong dan>  (vi du  2=D:\drv\lan.zip): " + $d) }
    $dk = [int]$Matches[1]
    $dv = Clean-Path $Matches[2]
    if (($dk -lt 1) -or ($dk -gt $Iso.Count)) { Stop-Build ("-Driver: khong co ISO thu " + $dk + " (chi co " + $Iso.Count + " ISO).") }
    $why = Test-DriverDrop $dv
    if ($why) { Stop-Build ("-Driver: " + $why) }
    if (-not $DrvArg.ContainsKey($dk)) { $DrvArg[$dk] = @() }
    $DrvArg[$dk] += $dv
  }

  # ---------------------------------------------------------------- thu muc lam viec
  $totalIso = 0
  foreach ($p in $Iso) { $it = Get-Item -LiteralPath $p; if (-not $it.PSIsContainer) { $totalIso += $it.Length } else { $totalIso += 6GB } }
  if (-not $Work) {
    $vols = @(Get-Volume | Where-Object { $_.DriveType -eq "Fixed" -and $_.DriveLetter } | Sort-Object SizeRemaining -Descending)
    if ($vols.Count -eq 0) { Stop-Build "Khong tim thay o cung nao de lam viec - dung tham so -Work D:\cb-work" }
    $Work = "" + $vols[0].DriveLetter + ":\cb-work"
    # uu tien thu muc lam viec cua lan chay truoc (con giu phan da tai + ma dang ky; cay bo cai cu se duoc don di)
    foreach ($v in $vols) {
      $prev = "" + $v.DriveLetter + ":\cb-work"
      if (Test-Path -LiteralPath (Join-Path $prev "dl")) { $Work = $prev; break }
    }
  }
  $Work = Clean-Path $Work
  if ($Work -match '\s') { Stop-Build ("Thu muc lam viec khong duoc co dau cach: " + $Work + "  (vi du dung -Work D:\cb-work)") }
  if (-not $Out) { $Out = Join-Path (Split-Path -Qualifier $Work) "\CloudBlue-PC.iso" }
  $Out = Clean-Path $Out
  if ($Out -match '\s') { Stop-Build ("Duong dan ISO moi khong duoc co dau cach: " + $Out) }
  New-Item -ItemType Directory -Force $Work | Out-Null
  $wdrive = (Split-Path -Qualifier $Work).TrimEnd(":")
  Say ("   Thu muc lam viec: " + $Work + "   ISO moi: " + $Out) "DarkGray"
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
  # ma dang ky cua lan chay truoc (de bam Enter la dung lai): ban ma hoa DPAPI trong thu muc dl (chi tai khoan Windows nay giai duoc),
  # hoac file enroll.key cua cay bo cai lan truoc con de lai. Doc TRUOC khi don.
  $KeyFile = Join-Path $Dl "ma-dang-ky.dpapi"
  $OldKey = ""
  if (Test-Path -LiteralPath $KeyFile) {
    try {
      $sec0 = ConvertTo-SecureString (("" + (Get-Content -LiteralPath $KeyFile -TotalCount 1)).Trim())
      $OldKey = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec0))
    } catch { $OldKey = "" }
  }
  if (-not (("" + $OldKey) -match '^cbpc_[0-9a-f]{40}$')) {
    $OldKey = ""
    $kf = Join-Path $IsoRoot "cb\enroll.key"
    if (Test-Path -LiteralPath $kf) {
      try {
        $kline = ("" + (Get-Content -LiteralPath $kf -TotalCount 1)).Trim()
        if ($kline -match '^cbpc_[0-9a-f]{40}$') { $OldKey = $kline }
      } catch { $OldKey = "" }
    }
  }
  foreach ($d in @($IsoRoot, $Tool, $PyDir)) { if (Test-Path $d) { Remove-Item -Recurse -Force $d } }
  # cho trong: tinh SAU khi da don cay bo cai cua lan chay truoc
  $free = (Get-PSDrive $wdrive).Free
  $need = [int64]($totalIso * 2.2 + 3GB)
  Say ("   O " + $wdrive + ": con trong " + [math]::Round($free / 1GB, 1) + " GB - can khoang " + [math]::Round($need / 1GB, 1) + " GB") "DarkGray"
  if ($free -lt $need) { Stop-Build ("O " + $wdrive + ": khong du cho trong. Don bot hoac dung -Work <o khac>:\cb-work") }

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
  $KeyFrom = "tham so"
  if (-not $MaDangKy) {
    $KeyFrom = ""
    if (-not $KhongHoi) {
      $q = "   MA DANG KY (Enter trong = may cai xong se KHONG tu len web)"
      if ($OldKey) {
        Say "   May nay con giu MA DANG KY cua lan chay truoc: bam Enter de DUNG LAI ma do." "White"
        Say "   (Neu sau lan do ban da bam 'Tao ma dang ky' lan nua tren web thi ma cu HET hieu luc - khi do dan ma moi vao day.)" "DarkGray"
        $q = "   MA DANG KY moi (Enter trong = dung lai ma lan truoc)"
      } else {
        Say "   Vao web > Bang quan tri > May PC > 'Tao ma dang ky' > Copy, roi dan vao day (chuot phai = dan). Ma KHONG hien khi dan." "White"
      }
      $sec = Read-Host $q -AsSecureString
      $MaDangKy = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
      if (("" + $MaDangKy).Trim()) { $KeyFrom = "moi nhap" }
    }
    if ((-not ("" + $MaDangKy).Trim()) -and $OldKey) { $MaDangKy = $OldKey; $KeyFrom = "dung lai cua lan chay truoc" }
  }
  $MaDangKy = ("" + $MaDangKy).Trim()
  if ($MaDangKy -and -not ($MaDangKy -match '^cbpc_[0-9a-f]{40}$')) { Stop-Build "Ma dang ky sai dang (phai la cbpc_ + 40 ky tu). Copy lai tu trang quan tri." }
  # hoi may chu: ma nay con hieu luc khong? (tren web bam 'Tao ma dang ky' lan nua la ma cu het dung - ISO tao bang ma cu thi may cai xong khong len web)
  $KeyState = ""
  if ($MaDangKy -and (-not $KhongKiemMa)) {
    $kTries = 0
    while ($true) {
      $KeyState = Test-EnrollKey $SbUrl $SbKey $MaDangKy
      if ($KeyState -eq "ok") { Say "   ma dang ky: may chu xac nhan CON HIEU LUC" "Green"; break }
      if ($KeyState -eq "") { Say "   (chua hoi duoc may chu ve ma dang ky - bo qua buoc kiem)" "DarkGray"; break }
      $kWhy = "Ma dang ky nay KHONG con hieu luc (tren web da bam 'Tao ma dang ky' lan nua sau khi lay ma nay)."
      if ($KeyState -eq "nokey") { $kWhy = "Tren web dang TAT ma dang ky (chua co ma nao dang mo)." }
      Write-Host ""
      Say ("   !! " + $kWhy) "Red"
      Say "      ISO tao bang ma nay thi may cai xong se KHONG hien len web." "Red"
      $kTries++
      if ($KhongHoi -or ($kTries -ge 3)) { Stop-Build ($kWhy + " Vao web > Bang quan tri > May PC > 'Tao ma dang ky' > Copy, roi chay lai lenh va dan ma moi.") }
      Say "      Vao web > Bang quan tri > May PC > 'Tao ma dang ky' > Copy, roi dan ma MOI vao day (chuot phai = dan). Ma KHONG hien khi dan." "White"
      $sec2 = Read-Host "   MA DANG KY moi" -AsSecureString
      $MaDangKy = ("" + [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec2))).Trim()
      if (-not ($MaDangKy -match '^cbpc_[0-9a-f]{40}$')) { Stop-Build "Ma dang ky sai dang (phai la cbpc_ + 40 ky tu). Copy lai tu trang quan tri." }
      $KeyFrom = "moi nhap"
    }
  }
  if ($MaDangKy) {
    Say ("   ma dang ky: da nhan - " + $KeyFrom + " (khong in ra)") "DarkGray"
    try {
      $enc = ConvertTo-SecureString $MaDangKy -AsPlainText -Force | ConvertFrom-SecureString
      [IO.File]::WriteAllText($KeyFile, ("" + $enc), [Text.Encoding]::ASCII)
    } catch { Say "   (khong luu duoc ma cho lan sau - khong sao)" "DarkGray" }
  } else { Note "Khong co ma dang ky: may cai tu ISO nay se khong tu hien len web." }

  # ---------------------------------------------------------------- 5. mo ISO goc, doc cac ban Windows
  Step "5/8  Doc cac ban Windows trong ISO goc"
  $src = @()
  foreach ($p in $Iso) {
    $it = Get-Item -LiteralPath $p
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
    if (($x64.Count -gt 1) -and (-not $KhongHoi)) {
      $ans = ("" + (Read-Host ("   Dung ban so nao? (Enter = " + $pick.Index + ")"))).Trim()
      if ($ans) {
        $sel = $x64 | Where-Object { ("" + $_.Index) -eq $ans } | Select-Object -First 1
        if (-not $sel) { Stop-Build ("ISO nay khong co ban x64 so '" + $ans + "'.") }
        $pick = $sel
      }
    }
    if (-not $std) { Say "      (ISO nay khong co du bo khoi dong chuan o goc - chi lay ban Windows, khong dung lam moi truong cai dat)" "DarkGray" }
    # driver RIENG cho ban Windows nay: tu tham so -Driver, va / hoac nguoi dung keo tha vao cua so
    $isoNo = $src.Count + 1
    $osTag = Get-OsTag $pick.Version
    $drops = @()
    if ($DrvArg.ContainsKey($isoNo)) { $drops += $DrvArg[$isoNo] }
    if (-not $KhongHoi) {
      Say ("   DRIVER rieng cho ban WINDOWS " + $osTag + " nay (" + (Split-Path -Leaf $p) + ") - vi du card mang, VGA:") "White"
      Say "      keo tha FILE driver (.exe .zip) hoac THU MUC driver vao cua so nay roi Enter; con cai nua thi keo tiep." "White"
      Say "      Ban nay khong can driver rieng / da keo het thi bam Enter trong." "White"
      while ($true) {
        $line = "" + (Read-Host ("   Driver thu " + ($drops.Count + 1) + " cho ban " + $osTag + " (Enter trong = het)"))
        if (-not $line.Trim()) { break }
        foreach ($dp in @(Split-Paths $line)) {
          $why = Test-DriverDrop $dp
          if ($why) { Say ("      KHONG nhan: " + $why) "Yellow"; continue }
          if ($drops -contains $dp) { continue }
          $drops += $dp
          Say ("      + " + (Get-DropText $dp)) "DarkGray"
        }
      }
    }
    if ($drops.Count -gt 0) { Say ("      driver rieng cho ban " + $osTag + ": " + $drops.Count + " muc") "DarkGray" }
    # ISO tuy bien hay kem file rieng cua nguoi lam: ghi lai de in vao khung TOM TAT (bo cai CloudBlue KHONG dung cac file nay)
    $extra = @()
    foreach ($n in @("autounattend.xml", "sources\pid.txt", "sources\ei.cfg")) { if (Test-Path (Join-Path $root $n)) { $extra += $n } }
    $oemDir = Join-Path $root 'sources\$OEM$'
    if (Test-Path -LiteralPath $oemDir) {
      $oemFiles = @(Get-ChildItem -LiteralPath $oemDir -Recurse -File)
      $extra += ('$OEM$ (' + $oemFiles.Count + ' file: ' + ((@($oemFiles | Select-Object -First 8 | ForEach-Object { $_.Name })) -join ', ') + ')')
    }
    $src += [pscustomobject]@{ Root = $root; Image = $img; Pick = $pick; Bytes = $bytes; Path = $p; Std = $std; Extra = ($extra -join ' ; '); Drops = $drops; Tag = $osTag }
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
  }
  # driver nguoi dung dua rieng cho tung ban Windows -> cb\drivers\_img<so thu tu ISO> ; cb_build.py doi thanh ten ban (1511, 22h2...)
  $isoNo = 0
  foreach ($s in $src) {
    $isoNo++
    $dlist = @($s.Drops)
    if ($dlist.Count -eq 0) { continue }
    $stage = Join-Path $IsoRoot ("cb\drivers\_img" + $isoNo)
    New-Item -ItemType Directory -Force $stage | Out-Null
    foreach ($dp in $dlist) {
      $it = Get-Item -LiteralPath $dp
      if ($it.PSIsContainer) {
        if ((Count-Inf $it.FullName) -gt 0) {
          $r3 = Run-Exe "robocopy.exe" @($it.FullName, (Free-Name $stage $it.Name), "/E", "/XF", "*.iso", "*.wim", "*.esd", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
          if ($r3 -ge 8) { Stop-Build ("Chep thu muc driver " + $it.FullName + " loi (robocopy ma " + $r3 + ").") }
        } else {
          # thu muc chi chua cac goi .exe / .zip: lay tung goi nam ngay trong no
          foreach ($f in @(Get-ChildItem -LiteralPath $it.FullName -File | Where-Object { $PACKEXT -contains $_.Extension.ToLower() })) {
            Copy-Item -LiteralPath $f.FullName -Destination (Free-Name $stage (Get-DropName $f)) -Force
          }
        }
      } else {
        Copy-Item -LiteralPath $it.FullName -Destination (Free-Name $stage (Get-DropName $it)) -Force
      }
    }
    Say ("   da chep " + $dlist.Count + " muc driver rieng cho ban " + $s.Tag) "DarkGray"
  }
  $ddir = Join-Path $IsoRoot "cb\drivers"
  if (Test-Path -LiteralPath $ddir) {
    try { Expand-DriverPacks $ddir } catch { Note ("Giai nen goi driver loi: " + $_.Exception.Message) }
  }
  $images = @()
  foreach ($s in $src) {
    $isBase = ($s.Path -eq $baseSrc.Path)
    $ipath = $s.Image
    if ($isBase) { $ipath = Join-Path $IsoRoot ("sources\" + (Split-Path -Leaf $s.Image)) }
    $images += @{ src = $ipath; base = $isBase; index = $s.Pick.Index; name = $s.Pick.Name; edition = $s.Pick.Edition; version = $s.Pick.Version; lang = $s.Pick.Lang; arch = $s.Pick.Arch }
  }
  $defIdx = -1
  if (($images.Count -gt 1) -and (-not $KhongHoi)) {
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
  $params = @{ out = $IsoRoot; tool = $Tool; py = $PyDir; images = $images; user = $TaiKhoan; password = $MatKhau; sb_url = $SbUrl; sb_key = $SbKey; enroll_key = $MaDangKy; generic_key = $gk; info = $infoFile; wallpaper = $wpSrc; default_index = $defIdx; user_admin = [bool]$KhachAdmin }
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
    $near = @()
    foreach ($p in $Iso) { try { $near += (Split-Path -Parent (Get-Item -LiteralPath $p).FullName) } catch { } }
    if ($Them) { $near += $Them }
    $osc = Find-Oscdimg $Dl $near
    if (-not $osc) {
      Note ("Khong lay duoc oscdimg.exe (cong cu dong ISO): " + ((@($OscWhy) | ForEach-Object { "" + $_ }) -join " ; ") + ". Cay bo cai da dung xong o thu muc iso - gui khung nay cho ho tro.")
    } else {
      Say ("   oscdimg: " + $OscInfo) "DarkGray"
      if (Test-Path $Out) { Remove-Item -Force $Out }
      $bios = Join-Path $IsoRoot "boot\etfsboot.com"
      $efi = Join-Path $IsoRoot "efi\microsoft\boot\efisys.bin"
      if (-not (Test-Path $efi)) { Stop-Build "Bo cai goc thieu efi\microsoft\boot\efisys.bin." }
      if (Test-Path $bios) { $bd = "-bootdata:2#p0,e,b" + $bios + "#pEF,e,b" + $efi } else { $bd = "-bootdata:1#pEF,e,b" + $efi }
      $rc = Run-Exe $osc @("-m", "-o", "-u2", "-udfver102", $bd, "-lCLOUDBLUE_PC", $IsoRoot, $Out)
      if ($rc -ne 0 -or -not (Test-Path $Out)) { Stop-Build ("Dong ISO loi (oscdimg ma " + $rc + "). oscdimg: " + $OscInfo) }
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
  if (Test-Path $infoFile) {
    Get-Content -Encoding UTF8 $infoFile | ForEach-Object { if (("" + $_) -match '^\(!\)') { Write-Host ("  " + $_) -ForegroundColor Yellow } else { Write-Host ("  " + $_) } }
  }
  Write-Host ("  Chen boot.wim (ban so " + $bidx + "): OK")
  Write-Host ("  Tu kiem: doc o dia = " + $(if ($t1 -eq 0) { "DAT" } else { "CHUA DAT (" + $t1 + ")" }) + " ; chay thu bo cai = " + $(if ($t2 -eq 0) { "DAT" } else { "CHUA DAT (" + $t2 + ")" }))
  Write-Host ("  Ma dang ky: " + $(if ($MaDangKy) { "CO (" + $KeyFrom + ")" + $(if ($KeyState -eq "ok") { " - may chu xac nhan con hieu luc" } else { " - CHUA kiem duoc voi may chu" }) } else { "KHONG" }))
  if ($OscInfo) { Write-Host ("  oscdimg: " + $OscInfo) }
  if (@($OscWhy).Count -gt 0) { Write-Host ("  oscdimg (cach thu khong duoc): " + ((@($OscWhy) | ForEach-Object { "" + $_ }) -join " ; ")) }
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
