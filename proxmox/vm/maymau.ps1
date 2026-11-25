# =====================================================================================================
#  cloudblue-may-mau  (ban 24.11a) - chay TRONG may mau VPS ao hoa (Windows Server 2012 R2 / 2016 / 2019 / 2022, Windows 10 LTSC).
#  ISO may mau (proxmox/tao-iso-may-mau.ps1) chep file nay vao C:\CloudBluePC\vm\ . Windows PowerShell 4.0 tro len.
#
#  Buoc 1 - SetupComplete.cmd goi (SYSTEM, Windows vua cai xong, truoc man hinh dang nhap):
#     driver virtio, QEMU guest agent, (2012 R2) ban va Universal C Runtime, tai khoan khach (Admin, khong mat khau),
#     tu dang nhap, mui gio, chinh cho Server, tac vu "CloudBlue May Mau" chay buoc 2.
#  Buoc 2 - tac vu "CloudBlue May Mau" goi (SYSTEM: luc tai khoan khach dang nhap / bat may / 4 phut sau buoc 1):
#     Python chua chay (2012 R2 vua cai ban va) -> khoi dong lai (toi da 3 lan). Roi cai phan mem CloudBlue (cb_provision.py specialize + system),
#     khoa moi tai khoan khac (mat khau ngau nhien + tat), kiem, don, go tac vu, bat agent (CHUA dang ky - cho may chu dua ve).
#  Xong: may de chay cho -> web > VPS ao hoa > Ban Windows (bang dieu khien may mau) hoac Shutdown + Convert to template.
#  Nhat ky: C:\CloudBluePC\logs\maymau.log . Khong in mat khau nao.
# =====================================================================================================
param([int]$Buoc = 1, [switch]$Thu)      # -Thu: chay thu tren may CI (khong khoa tai khoan khac, khong bat agent, khong hop bao)

$ErrorActionPreference = "Continue"
$VER = "24.11a"
$Base = "C:\CloudBluePC"
$VmDir = Join-Path $Base "vm"
$LogDir = Join-Path $Base "logs"
$LogF = Join-Path $LogDir "maymau.log"
$DoneF = Join-Path $VmDir "maymau.done"
$TaskName = "CloudBlue May Mau"
$Py = Join-Path $Base "py\python.exe"
$Ps = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$Info = $null
$User = "VPS"

function Log([string]$m) {
  $line = (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + " [" + $Buoc + "] " + $m
  try {
    if (-not (Test-Path -LiteralPath $LogDir)) { New-Item -ItemType Directory -Force $LogDir | Out-Null }
    Add-Content -LiteralPath $LogF -Value $line -Encoding ASCII
  } catch { }
  Write-Host $line
}

function Short([string]$t, [int]$n = 300) {
  $s = (("" + $t) -replace "\s+", " ").Trim()
  if ($s.Length -gt $n) { $s = "..." + $s.Substring($s.Length - $n) }
  return $s
}

function Run([string]$exe, [string[]]$a, [string]$what) {
  # Chay 1 lenh (cho xong), ghi ket qua vao nhat ky, tra ma thoat. Khong chay duoc -> 9009.
  $out = ""
  $rc = 9009
  try { $out = (& $exe @a 2>&1 | Out-String); $rc = $LASTEXITCODE } catch { $out = "" + $_ }
  if ($rc -eq 0) { Log ("ok  " + $what) } else { Log ("LOI(" + $rc + ") " + $what + " :: " + (Short $out)) }
  return $rc
}

function Run-Quiet([string]$exe, [string[]]$a) {
  $rc = 9009
  try { & $exe @a 2>&1 | Out-Null; $rc = $LASTEXITCODE } catch { $rc = 9009 }
  return $rc
}

function Run-Wait([string]$exe, [string]$argline, [string]$what, [int]$sec = 1800) {
  # Chuong trinh kieu cua so (msiexec, wusa): PowerShell khong tu cho -> Start-Process + cho toi da $sec giay.
  try {
    $p = Start-Process -FilePath $exe -ArgumentList $argline -PassThru
    [void]$p.Handle                                                          # giu handle de doc duoc ma thoat sau khi chuong trinh ket thuc
    if (-not $p.WaitForExit($sec * 1000)) { try { $p.Kill() } catch { }; Log ("LOI " + $what + " :: qua " + $sec + " giay chua xong"); return 9008 }
    $rc = [int]$p.ExitCode
    if ($rc -eq 0) { Log ("ok  " + $what) } else { Log ("ma " + $rc + " " + $what) }
    return $rc
  } catch { Log ("LOI " + $what + " :: " + (Short ("" + $_))); return 9009 }
}

function Set-Reg([string]$key, [string]$name, $val, [string]$type = "String") {
  try {
    if (-not (Test-Path -LiteralPath $key)) { New-Item -Path $key -Force | Out-Null }
    New-ItemProperty -LiteralPath $key -Name $name -Value $val -PropertyType $type -Force | Out-Null
    return $true
  } catch { Log ("LOI ghi registry " + $key + " " + $name + " :: " + (Short ("" + $_))); return $false }
}

function Tell([string]$m, [int]$sec = 600) {
  # Hop bao tren man hinh (SYSTEM gui toi moi phien dang nhap). Khong co msg.exe thi thoi.
  if ($Thu) { return }
  try { & msg.exe * ("/time:" + $sec) $m 2>&1 | Out-Null } catch { }
}

function Touch-Mark([string]$name) {
  # Moc kieu cb_provision.py: C:\CloudBluePC\logs\<ten> chua so giay UTC luc dat moc
  $p = Join-Path $LogDir $name
  if (Test-Path -LiteralPath $p) { return }
  $epoch = New-Object DateTime 1970, 1, 1, 0, 0, 0, ([DateTimeKind]::Utc)
  $t = [int64](([DateTime]::UtcNow - $epoch).TotalSeconds)
  try { [IO.File]::WriteAllText($p, ("" + $t)) } catch { Log ("LOI ghi moc " + $name) }
}

function Get-GroupName([string]$sid, [string]$dflt) {
  try { return ((New-Object Security.Principal.SecurityIdentifier($sid)).Translate([Security.Principal.NTAccount]).Value.Split("\")[-1]) } catch { return $dflt }
}

function Test-Member([string]$group, [string]$u) {
  $lines = @()
  try { $lines = @(& net.exe localgroup $group 2>$null) } catch { $lines = @() }
  foreach ($l in $lines) { if (("" + $l).Trim() -eq $u) { return $true } }
  return $false
}

function New-RandomPw {
  $chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789".ToCharArray()
  $rng = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
  $b = New-Object byte[] 24
  $rng.GetBytes($b)
  $s = "Cb"
  foreach ($x in $b) { $s += $chars[[int]$x % $chars.Length] }
  return ($s + "!7x")
}

function Read-Info {
  try { $script:Info = Get-Content -Raw -LiteralPath (Join-Path $VmDir "maymau.json") | ConvertFrom-Json } catch { $script:Info = $null }
  if ($script:Info -and ("" + $script:Info.user) -match '^[A-Za-z][A-Za-z0-9_-]{0,19}$') { $script:User = "" + $script:Info.user }
}

function Is-Server { return [bool]($script:Info -and $script:Info.server) }

function Get-Tag { if ($script:Info -and $script:Info.tag) { return ("" + $script:Info.tag) } else { return "?" } }

# ------------------------------------------------------------------------------------------------ buoc 1
function Install-Drivers {
  $infs = @(Get-ChildItem -Path (Join-Path $VmDir "drivers") -Recurse -Filter "*.inf" -ErrorAction SilentlyContinue)
  if ($infs.Count -eq 0) { Log 'khong co driver virtio kem theo (bo cai da nap tu $WinPEDriver$)'; return }
  foreach ($f in $infs) { [void](Run "pnputil.exe" @("-i", "-a", $f.FullName) ("driver " + $f.Directory.Name + "\" + $f.Name)) }
}

function Install-Ga {
  $ga = Get-Service -Name "QEMU-GA" -ErrorAction SilentlyContinue
  if (-not $ga) {
    $msi = Join-Path $VmDir "qemu-ga-x86_64.msi"
    if (Test-Path -LiteralPath $msi) {
      [void](Run-Wait "msiexec.exe" ('/i "' + $msi + '" /qn /norestart /l*v "' + (Join-Path $LogDir "qemu-ga-msi.log") + '"') "cai QEMU guest agent")
    } else { Log "LOI thieu qemu-ga-x86_64.msi" }
    $ga = Get-Service -Name "QEMU-GA" -ErrorAction SilentlyContinue
  }
  if (-not $ga) { Log "LOI chua cai duoc QEMU guest agent (may chu se khong dua duoc ve dang ky vao may VPS)"; return }
  try { Set-Service -Name "QEMU-GA" -StartupType Automatic -ErrorAction Stop } catch { Log ("LOI dat QEMU-GA tu chay :: " + (Short ("" + $_))) }
  try { Start-Service -Name "QEMU-GA" -ErrorAction Stop; Log "ok  QEMU guest agent dang chay" }
  catch { Log "QEMU guest agent chua chay (may mau chua bat Qemu Agent o Options) - may VPS nhan ban se tu bat" }
}

function Install-Ucrt {
  if (Test-Path -LiteralPath (Join-Path $env:SystemRoot "System32\ucrtbase.dll")) { return }
  $msu = Join-Path $VmDir "ucrt.msu"
  if (-not (Test-Path -LiteralPath $msu)) { Log "LOI thieu ucrtbase.dll (Universal C Runtime) va khong co ucrt.msu - Python se khong chay"; return }
  $rc = Run-Wait "wusa.exe" ('"' + $msu + '" /quiet /norestart') "cai ban va Universal C Runtime (KB2999226)"
  if (@(0, 3010, 2359302) -contains $rc) { return }
  # wusa khong duoc -> giai nen goi .cab, cai bang DISM
  $x = Join-Path $env:TEMP "cb-ucrt"
  Remove-Item -LiteralPath $x -Recurse -Force -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force $x | Out-Null
  [void](Run "expand.exe" @("-F:*", $msu, $x) "giai nen ban va UCRT")
  $cab = Get-ChildItem -LiteralPath $x -Filter "*KB2999226*.cab" -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($cab) { [void](Run "dism.exe" @("/online", "/add-package", ("/packagepath:" + $cab.FullName), "/quiet", "/norestart") "cai ban va UCRT bang DISM") }
  else { Log "LOI khong thay goi .cab trong ucrt.msu" }
}

function Set-PwPolicy {
  # Windows Server bat "mat khau phuc tap" -> khong tao duoc tai khoan khach khong mat khau. Tat luat nay (khach van tu dat mat khau duoc).
  $inf = Join-Path $env:TEMP "cb-pw.inf"
  $sdb = Join-Path $env:TEMP "cb-pw.sdb"
  Remove-Item -LiteralPath $sdb -Force -ErrorAction SilentlyContinue
  $lines = @("[Unicode]", "Unicode=yes", "[System Access]", "PasswordComplexity = 0", "MinimumPasswordLength = 0", "[Version]", 'signature="$CHICAGO$"', "Revision=1")
  Set-Content -LiteralPath $inf -Value $lines -Encoding Unicode
  [void](Run "secedit.exe" @("/configure", "/db", $sdb, "/cfg", $inf, "/areas", "SECURITYPOLICY", "/quiet") "tat luat mat khau phuc tap / do dai toi thieu (Server)")
}

function Ensure-User {
  $adm = Get-GroupName "S-1-5-32-544" "Administrators"
  if ((Run-Quiet "net.exe" @("user", $User)) -ne 0) {
    [void](Run "net.exe" @("user", $User, "/add", "/active:yes", "/expires:never", "/passwordchg:yes", ("/fullname:" + $User)) ("tao tai khoan khach " + $User + " (khong mat khau)"))
  } else { Log ("tai khoan khach " + $User + " da co") }
  [void](Run-Quiet "net.exe" @("user", $User, "/active:yes"))
  if (-not (Test-Member $adm $User)) { [void](Run "net.exe" @("localgroup", $adm, $User, "/add") ("cho " + $User + " vao nhom " + $adm)) }
  try {
    $u = [ADSI]("WinNT://" + $env:COMPUTERNAME + "/" + $User + ",user")
    $f = [int]$u.UserFlags.Value
    if (($f -band 0x10000) -eq 0) { $u.UserFlags.Value = ($f -bor 0x10000); $u.SetInfo() }
    Log ("ok  mat khau tai khoan " + $User + " khong het han")
  } catch { Log ("LOI dat mat khau khong het han :: " + (Short ("" + $_))) }
}

function Set-AutoLogon {
  $wl = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
  $ok = (Set-Reg $wl "AutoAdminLogon" "1") -and (Set-Reg $wl "DefaultUserName" $User) -and (Set-Reg $wl "DefaultDomainName" $env:COMPUTERNAME) -and (Set-Reg $wl "DefaultPassword" "")
  Remove-ItemProperty -LiteralPath $wl -Name "AutoLogonCount" -ErrorAction SilentlyContinue
  if ($ok) { Log ("ok  tu dang nhap tai khoan " + $User) } else { Log "LOI dat tu dang nhap" }
}

function Set-Tweaks {
  [void](Set-Reg "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" "DisableCAD" 1 "DWord")
  if (-not (Is-Server)) { return }
  [void](Set-Reg "HKLM:\SOFTWARE\Microsoft\ServerManager" "DoNotOpenServerManagerAtLogon" 1 "DWord")
  [void](Set-Reg "HKLM:\SOFTWARE\Policies\Microsoft\Windows\Server\ServerManager" "DoNotOpenAtLogon" 1 "DWord")
  [void](Set-Reg "HKLM:\SOFTWARE\Microsoft\Active Setup\Installed Components\{A509B1A7-37EF-4b3f-8CFC-4F3A74704073}" "IsInstalled" 0 "DWord")
  [void](Set-Reg "HKLM:\SOFTWARE\Microsoft\Active Setup\Installed Components\{A509B1A8-37EF-4b3f-8CFC-4F3A74704073}" "IsInstalled" 0 "DWord")
  [void](Set-Reg "HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\Reliability" "ShutdownReasonOn" 0 "DWord")
  [void](Set-Reg "HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\Reliability" "ShutdownReasonUI" 0 "DWord")
  Log "ok  Server: khong tu mo Server Manager, tat IE ESC, tat hop hoi ly do tat may"
}

function Register-Step2 {
  $start = (Get-Date).AddMinutes(4).ToString("yyyy-MM-ddTHH:mm:ss")
  $arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " + (Join-Path $VmDir "maymau.ps1") + " -Buoc 2"
  $x = @(
    '<?xml version="1.0" encoding="UTF-16"?>',
    '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">',
    '  <RegistrationInfo><Description>CloudBlue - hoan tat may mau VPS ao hoa (tu go khi xong)</Description></RegistrationInfo>',
    '  <Triggers>',
    '    <LogonTrigger><Enabled>true</Enabled></LogonTrigger>',
    '    <BootTrigger><Enabled>true</Enabled><Delay>PT1M</Delay></BootTrigger>',
    ('    <TimeTrigger><StartBoundary>' + $start + '</StartBoundary><Enabled>true</Enabled></TimeTrigger>'),
    '  </Triggers>',
    '  <Principals><Principal id="Author"><UserId>S-1-5-18</UserId><RunLevel>HighestAvailable</RunLevel></Principal></Principals>',
    '  <Settings>',
    '    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>',
    '    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>',
    '    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>',
    '    <AllowHardTerminate>true</AllowHardTerminate>',
    '    <StartWhenAvailable>true</StartWhenAvailable>',
    '    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>',
    '    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>',
    '    <AllowStartOnDemand>true</AllowStartOnDemand>',
    '    <Enabled>true</Enabled>',
    '    <Hidden>false</Hidden>',
    '    <RunOnlyIfIdle>false</RunOnlyIfIdle>',
    '    <WakeToRun>false</WakeToRun>',
    '    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>',
    '    <Priority>7</Priority>',
    '  </Settings>',
    '  <Actions Context="Author">',
    ('    <Exec><Command>' + $Ps + '</Command><Arguments>' + $arg + '</Arguments></Exec>'),
    '  </Actions>',
    '</Task>')
  $xf = Join-Path $VmDir "maymau-task.xml"
  try { [IO.File]::WriteAllText($xf, ($x -join "`r`n"), [Text.Encoding]::Unicode) } catch { Log ("LOI ghi " + $xf) }
  $rc = Run "schtasks.exe" @("/create", "/tn", $TaskName, "/xml", $xf, "/f") ("tac vu '" + $TaskName + "' (buoc 2: luc dang nhap / bat may / 4 phut sau)")
  if ($rc -ne 0) {
    [void](Run "schtasks.exe" @("/create", "/tn", $TaskName, "/sc", "onlogon", "/ru", "SYSTEM", "/rl", "highest", "/tr", ($Ps + " " + $arg), "/f") ("tac vu '" + $TaskName + "' (du phong: luc dang nhap)"))
  }
}

function Do-Buoc1 {
  Log ("=== buoc 1 (ban " + $VER + ") - may mau " + (Get-Tag) + ", tai khoan khach " + $User)
  Install-Drivers
  Install-Ga
  Install-Ucrt
  if (Is-Server) { Set-PwPolicy }
  Ensure-User
  Set-AutoLogon
  [void](Run "tzutil.exe" @("/s", "SE Asia Standard Time") "mui gio UTC+7 (SE Asia Standard Time)")
  Set-Tweaks
  Register-Step2
  Touch-Mark "maymau.buoc1"
  Log "xong buoc 1 - cho tai khoan khach tu dang nhap (buoc 2)"
}

# ------------------------------------------------------------------------------------------------ buoc 2
function Test-Py {
  if (-not (Test-Path -LiteralPath $Py)) { Log "LOI thieu C:\CloudBluePC\py\python.exe"; return $false }
  if (-not (Test-Path -LiteralPath (Join-Path $env:SystemRoot "System32\ucrtbase.dll"))) { Log "chua co ucrtbase.dll (Universal C Runtime)"; return $false }
  $tmp = Join-Path $env:TEMP "cb-pytest.txt"
  Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
  try {
    $p = Start-Process -FilePath $Py -ArgumentList '-I -B -c "import ssl, json, ctypes; print(''py-ok'')"' -RedirectStandardOutput $tmp -PassThru
    [void]$p.Handle
    if (-not $p.WaitForExit(90000)) { try { $p.Kill() } catch { }; Log "python treo qua 90 giay"; return $false }
    $o = ""
    if (Test-Path -LiteralPath $tmp) { $o = "" + (Get-Content -Raw -LiteralPath $tmp) }
    if ($o -match "py-ok") { return $true }
    Log ("python chua chay (ma " + $p.ExitCode + ") " + (Short $o))
  } catch { Log ("python chua chay :: " + (Short ("" + $_))) }
  return $false
}

function Get-BootTime {
  try { $o = Get-WmiObject -Class Win32_OperatingSystem; return $o.ConvertToDateTime($o.LastBootUpTime) } catch { return (Get-Date) }
}

function Prov([string]$phase) {
  Log ("cb_provision " + $phase + " ... (chi tiet: C:\CloudBluePC\logs\provision.log)")
  $o = ""
  try { $o = (& $Py -I -B (Join-Path $Base "os\cb_provision.py") $phase 2>&1 | Out-String) } catch { $o = "" + $_ }
  foreach ($ln in ($o -split "`r?`n")) { if (("" + $ln).Trim()) { Log ("   " + ("" + $ln).Trim()) } }
}

function Lock-Others {
  # Moi tai khoan khac (Administrator co san + tai khoan nguoi dung bo cai / nguoi dung tao) -> mat khau ngau nhien khong ai biet + tat:
  # moi VPS nhan ban tu may mau nay KHONG con chung 1 mat khau quan tri nao (khach VPS nay khong vao duoc VPS khac).
  $list = @()
  try { $list = @(Get-WmiObject -Class Win32_UserAccount -Filter "LocalAccount=True" -ErrorAction Stop) } catch { Log ("LOI doc danh sach tai khoan :: " + (Short ("" + $_))); return }
  foreach ($a in $list) {
    $rid = 0
    try { $rid = [int64](("" + $a.SID).Split("-")[-1]) } catch { $rid = 0 }
    if (("" + $a.Name) -eq $User) { continue }
    if (@(501, 503, 504) -contains $rid) { continue }
    if (($rid -ne 500) -and $a.Disabled) { continue }
    $ok = $true
    try { $u = [ADSI]("WinNT://" + $env:COMPUTERNAME + "/" + $a.Name + ",user"); $pw = New-RandomPw; $u.SetPassword($pw); $pw = $null } catch { $ok = $false; Log ("LOI doi mat khau tai khoan '" + $a.Name + "' :: " + (Short ("" + $_))) }
    $rc = Run-Quiet "net.exe" @("user", $a.Name, "/active:no")
    if ($ok -and ($rc -eq 0)) { Log ("ok  tai khoan '" + $a.Name + "': mat khau ngau nhien (khong luu o dau) + tat") } else { Log ("LOI khoa tai khoan '" + $a.Name + "' (ma " + $rc + ")") }
  }
}

function Check-All {
  $bad = @()
  foreach ($t in @("CloudBluePC Agent", "CloudBluePC Watch")) { if ((Run-Quiet "schtasks.exe" @("/query", "/tn", $t)) -ne 0) { $bad += ("thieu tac vu " + $t) } }
  if (-not (Get-Service -Name "QEMU-GA" -ErrorAction SilentlyContinue)) {
    if ($Thu) { Log "(che do thu) chua co dich vu QEMU-GA - bo qua" } else { $bad += "chua cai QEMU guest agent" }
  }
  if ((Run-Quiet "net.exe" @("user", $User)) -ne 0) { $bad += ("chua co tai khoan " + $User) }
  elseif (-not (Test-Member (Get-GroupName "S-1-5-32-544" "Administrators") $User)) { $bad += ("tai khoan " + $User + " chua co quyen Admin") }
  $wl = Get-ItemProperty -LiteralPath "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" -ErrorAction SilentlyContinue
  if ((-not $wl) -or (("" + $wl.AutoAdminLogon) -ne "1") -or (("" + $wl.DefaultUserName) -ne $User)) { $bad += "chua dat tu dang nhap" }
  return $bad
}

function Clean-Up {
  foreach ($p in @("C:\Windows\Panther\unattend.xml", "C:\Windows\Panther\autounattend.xml", "C:\Windows\Panther\Unattend\unattend.xml",
                   "C:\Windows\Panther\Unattend\autounattend.xml", "C:\Windows\Setup\Scripts\SetupComplete.cmd")) {
    Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue
  }
  foreach ($n in @("ucrt.msu", "qemu-ga-x86_64.msi", "drivers", "reboot.at", "maymau.loi")) { Remove-Item -LiteralPath (Join-Path $VmDir $n) -Recurse -Force -ErrorAction SilentlyContinue }
  # KHONG xoa seed.json / identity.json: dung bang bang dieu khien may mau tren web thi may chu dua ve dang ky vao day (agent dang ky de admin dieu khien);
  # luc "Luu thanh may mau" may chu tu xoa ma may truoc khi chuyen thanh mau.
  Log "ok  don file cai dat (file tra loi, goi cai, driver da nap)"
}

function Remove-Step2 { [void](Run-Quiet "schtasks.exe" @("/delete", "/tn", $TaskName, "/f")) }

function Fail([string]$why) {
  Log ("LOI: " + $why)
  try { [IO.File]::WriteAllText((Join-Path $VmDir "maymau.loi"), ((Get-Date -Format "yyyy-MM-dd HH:mm:ss") + " " + $why)) } catch { }
  Tell ("CloudBlue: MAY MAU CHUA XONG - " + $why + ". Xem C:\CloudBluePC\logs\maymau.log") 86400
}

function Do-Buoc2 {
  if (Test-Path -LiteralPath $DoneF) { Log "may mau da xong tu truoc - go tac vu"; Remove-Step2; return }
  $ra = Join-Path $VmDir "reboot.at"
  if (Test-Path -LiteralPath $ra) {
    # vua hen khoi dong lai ma may CHUA khoi dong lai (tac vu chay lan nua trong luc dem nguoc) -> thoi
    $at = $null
    try { $at = [DateTime]::FromBinary([int64](("" + (Get-Content -LiteralPath $ra -TotalCount 1)).Trim())) } catch { $at = $null }
    if ($at -and ((Get-BootTime) -lt $at)) { Log "dang cho khoi dong lai"; return }
  }
  Log ("=== buoc 2 (ban " + $VER + ") - may mau " + (Get-Tag))
  if (-not (Test-Path -LiteralPath (Join-Path $LogDir "maymau.buoc1"))) { Log "buoc 1 chua chay (SetupComplete.cmd?) - chay bu"; Do-Buoc1 }
  Tell "CloudBlue: dang cai phan mem CloudBlue cho may mau (vai phut). KHONG tat may." 900
  if (-not (Test-Py)) {
    Install-Ucrt
    $rf = Join-Path $VmDir "reboot.n"
    $n = 0
    if (Test-Path -LiteralPath $rf) { try { $n = [int](("" + (Get-Content -LiteralPath $rf -TotalCount 1)).Trim()) } catch { $n = 0 } }
    if ($n -lt 3) {
      try { [IO.File]::WriteAllText($rf, ("" + ($n + 1))); [IO.File]::WriteAllText($ra, ("" + (Get-Date).ToBinary())) } catch { }
      Log ("Python chua chay duoc - khoi dong lai lan " + ($n + 1) + " / 3 de ban va Windows co hieu luc")
      [void](Run "shutdown.exe" @("/r", "/t", "20", "/c", "CloudBlue: khoi dong lai 1 lan de hoan tat cai dat may mau") "hen khoi dong lai sau 20 giay")
      return
    }
    Fail "Python khong chay duoc sau 3 lan khoi dong lai (thieu ban va Universal C Runtime?)"
    return
  }
  Log "ok  Python chay duoc"
  Prov "specialize"
  Touch-Mark "firstlogon.start"
  Touch-Mark "firstlogon.done"
  Prov "system"
  if ($Thu) { Log "(che do thu) KHONG khoa tai khoan khac" } else { Lock-Others }
  $bad = @(Check-All)
  if ($bad.Count -gt 0) { Fail ($bad -join "; "); return }
  Clean-Up
  Remove-Item -LiteralPath (Join-Path $VmDir "reboot.n") -Force -ErrorAction SilentlyContinue
  try { [IO.File]::WriteAllText($DoneF, ("ok " + $VER + " " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))) } catch { }
  Remove-Step2
  if (-not $Thu) { [void](Run "schtasks.exe" @("/run", "/tn", "CloudBluePC Agent") "bat agent CloudBlue (chua dang ky - cho may chu dua ve dang ky)") }
  $tag = Get-Tag
  Log ("XONG may mau " + $tag)
  Tell ("CloudBlue: MAY MAU DA XONG (" + $tag + "). Web > VPS ao hoa > Ban Windows: dieu khien / luu thanh may mau. Hoac: Shutdown, go ISO khoi o CD, Convert to template, ten tpl-" + $tag + ".") 86400
}

# ------------------------------------------------------------------------------------------------ chay
try {
  if (-not (Test-Path -LiteralPath $LogDir)) { New-Item -ItemType Directory -Force $LogDir | Out-Null }
  Read-Info
  if ($Buoc -eq 2) { Do-Buoc2 } else { Do-Buoc1 }
} catch {
  Log ("LOI KHONG NGO: " + (Short ("" + $_) 600))
}
exit 0
