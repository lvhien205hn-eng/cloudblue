# =====================================================================================================
#  CI (windows-2022, Admin, Windows PowerShell 5.1): ISO MAY MAU VPS ao hoa - proxmox/tao-iso-may-mau.ps1 + proxmox/vm/maymau.ps1
#    1. cu phap 2 script (bo phan tich cua PowerShell)
#    2. ISO nguon: "ISO Windows" gia (tu chup anh tu file he thong + registry cua may CI = Windows Server co giao dien) + ISO virtio-win 0.1.271 THAT
#    3. chay CA tao-iso-may-mau.ps1 (-KhongHoi -Nguon <kho nay>) -> mo ISO ra kiem tung phan
#    4. chep C:\CloudBluePC tu ISO roi chay maymau.ps1 buoc 1 + buoc 2 that tren may CI (che do -Thu: khong khoa tai khoan, khong bat agent;
#       cb.json tro dia chi web ve 127.0.0.1 -> khong goi web that)
#  Ket qua: -KetQua <file .txt>. Khong dua gi len web.
# =====================================================================================================
param([string]$KetQua = "")

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
$Lines = New-Object System.Collections.ArrayList
$Pass = 0
$Fail = 0

function Out-Line([string]$t) { [void]$Lines.Add($t); Write-Host $t }
function Ck([string]$name, $cond, [string]$extra = "") {
  if ($cond) { $script:Pass++; Out-Line ("  OK  " + $name) }
  else { $script:Fail++; Out-Line ("  XX  " + $name + $(if ($extra) { "  -> " + $extra } else { "" })) }
}
function Info([string]$t) { Out-Line ("  ..  " + $t) }
function New-Dir([string]$p) { New-Item -ItemType Directory -Force $p | Out-Null; return $p }
function Tail([string]$p, [int]$n = 40) { if (Test-Path -LiteralPath $p) { Get-Content -LiteralPath $p -Tail $n | ForEach-Object { Out-Line ("      | " + $_) } } }

$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$Wk = New-Dir (Join-Path $env:RUNNER_TEMP "vmiso")
$Mnt = New-Object System.Collections.ArrayList
$OEM1 = 'sources\$OEM$\$1\CloudBluePC'

try {
  Out-Line "== 1. Cu phap PowerShell"
  foreach ($f in @("proxmox\tao-iso-may-mau.ps1", "proxmox\vm\maymau.ps1")) {
    $errs = $null; $tok = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile((Join-Path $Repo $f), [ref]$tok, [ref]$errs)
    Ck ("cu phap " + $f) ($errs.Count -eq 0) ((@($errs) | ForEach-Object { "" + $_.Extent.StartLineNumber + ": " + $_.Message }) -join " | ")
  }

  Out-Line "== 2. ISO nguon"
  $dl0 = New-Dir (Join-Path $Wk "dl0")
  $osc = Join-Path $dl0 "oscdimg.exe"
  $ca = @("-fsSL", "-A", "Microsoft-Symbol-Server/10.0.0.0", "-o", $osc, "https://msdl.microsoft.com/download/symbols/oscdimg.exe/688CABB065000/oscdimg.exe")
  & curl.exe @ca 2>$null
  $oscOk = (Test-Path $osc) -and ((Get-FileHash -Algorithm SHA256 $osc).Hash.ToLower() -eq "2000160b2c5044691b2f9a0ac308e5207f273d4880a572457af16d05886ba861")
  Ck "tai oscdimg.exe (khop ma kiem da ghim)" $oscOk
  $fk = New-Dir (Join-Path $Wk "fakewin")
  New-Dir (Join-Path $fk "Windows\System32\config") | Out-Null
  foreach ($sf in @("ntoskrnl.exe", "ntdll.dll", "kernel32.dll", "hal.dll")) { Copy-Item (Join-Path $env:SystemRoot ("System32\" + $sf)) (Join-Path $fk ("Windows\System32\" + $sf)) }
  & reg.exe save HKLM\SOFTWARE (Join-Path $fk "Windows\System32\config\SOFTWARE") /y | Out-Null
  & reg.exe save HKLM\SYSTEM (Join-Path $fk "Windows\System32\config\SYSTEM") /y | Out-Null
  $wim = Join-Path $Wk "cap.wim"
  & dism.exe /English /Capture-Image "/ImageFile:$wim" "/CaptureDir:$fk" "/Name:Windows Server CI SERVERDATACENTER" /Compress:fast | Out-Null
  $wi = $null
  try { $wi = Get-WindowsImage -ImagePath $wim -Index 1 } catch { }
  if ($wi) { Info ("anh chup: " + $wi.ImageName + " | " + $wi.Version + " | loai " + $wi.InstallationType + " | " + $wi.EditionId + " | kien truc " + $wi.Architecture) }
  Ck "anh Windows gia: 64-bit, loai Server (co giao dien)" ($wi -and ([int]$wi.Architecture -eq 9) -and (("" + $wi.InstallationType) -eq "Server")) ("" + $wi.InstallationType)
  $s1 = New-Dir (Join-Path $Wk "src1")
  foreach ($d in @("sources", "boot", "efi\microsoft\boot")) { New-Dir (Join-Path $s1 $d) | Out-Null }
  Copy-Item $wim (Join-Path $s1 "sources\boot.wim")
  Copy-Item $wim (Join-Path $s1 "sources\install.wim")
  Copy-Item "C:\Windows\Boot\DVD\PCAT\boot.sdi" (Join-Path $s1 "boot\boot.sdi")
  Copy-Item "C:\Windows\Boot\DVD\PCAT\etfsboot.com" (Join-Path $s1 "boot\etfsboot.com")
  Copy-Item "C:\Windows\Boot\DVD\EFI\en-US\efisys.bin" (Join-Path $s1 "efi\microsoft\boot\efisys.bin")
  if (Test-Path "C:\Windows\Boot\DVD\EFI\en-US\efisys_noprompt.bin") { Copy-Item "C:\Windows\Boot\DVD\EFI\en-US\efisys_noprompt.bin" (Join-Path $s1 "efi\microsoft\boot\efisys_noprompt.bin") }
  Set-Content -Path (Join-Path $s1 "setup.exe") -Value "gia" -Encoding ASCII
  $iso1 = Join-Path $Wk "Windows-Server-gia.iso"
  $bd = "-bootdata:2#p0,e,b" + (Join-Path $s1 "boot\etfsboot.com") + "#pEF,e,b" + (Join-Path $s1 "efi\microsoft\boot\efisys.bin")
  & $osc -m -o -u2 -udfver102 $bd "-lSRC1" $s1 $iso1 2>&1 | Out-Null
  Ck "dong ISO Windows gia" (Test-Path $iso1)
  $vio = Join-Path $Wk "virtio-win-0.1.271.iso"
  $ca = @("-fsSL", "--retry", "3", "-o", $vio, "https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/archive-virtio/virtio-win-0.1.271-1/virtio-win-0.1.271.iso")
  & curl.exe @ca 2>$null
  $vsz = 0
  if (Test-Path $vio) { $vsz = (Get-Item $vio).Length }
  Ck "tai ISO virtio-win 0.1.271 that" ($vsz -gt 300MB) ("" + [math]::Round($vsz / 1MB) + " MB")

  Out-Line "== 3. Chay tao-iso-may-mau.ps1"
  $out = Join-Path $Wk "out\CloudBlue-MayMau-ci.iso"
  New-Dir (Join-Path $Wk "out") | Out-Null
  $log1 = Join-Path $Wk "run1.log"
  $t0 = Get-Date
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Repo "proxmox\tao-iso-may-mau.ps1") -Iso $iso1 -Virtio $vio -KhongHoi -Nguon $Repo -Work (Join-Path $Wk "w") -Out $out *> $log1
  $txt = "" + (Get-Content -Raw -LiteralPath $log1)
  Info ("tao ISO mat " + [math]::Round(((Get-Date) - $t0).TotalMinutes, 1) + " phut")
  $ok1 = ($txt -match "XONG \(") -and (Test-Path $out)
  Ck "tao-iso-may-mau.ps1 chay het, ra file ISO" $ok1
  Ck "khong co DUNG / LOI KHONG NGO" (-not ($txt -match "!! DUNG|LOI KHONG NGO"))
  Ck "chu in ra sach: khong co dong 'RemoteException' (dong trong tren kenh loi cua oscdimg), van thay tien do dong ISO" ((-not ($txt -match "RemoteException")) -and ($txt -match "% complete"))
  Ck "buoc tiep: chi duong TU DONG (ghep vao ISO Proxmox tu cai) truoc cach lam tay" ($txt -match "Buoc tiep \(TU DONG\)")
  Ck "chon dung ban Server co giao dien -> may mau tpl-win2022, driver 2k22" ($txt -match "tpl-win2022")
  Ck "python.exe kiem chu ky Python Software Foundation" ($txt -match "chu ky Python Software Foundation hop le")
  Ck "ffmpeg kem san (dung ma kiem agent doi)" ($txt -match "ffmpeg: \d+ MB, dung ma kiem")
  if (-not $ok1) { Tail $log1 60 }
  if (Test-Path $out) {
    $mi = Mount-DiskImage -ImagePath $out -PassThru
    [void]$Mnt.Add($out)
    Start-Sleep 2
    $r = ""
    for ($i = 0; ($i -lt 15) -and (-not $r); $i++) {
      $v = @(Get-DiskImage -ImagePath $out | Get-Volume | Where-Object { $_.DriveLetter })
      if ($v.Count -gt 0) { $r = "" + $v[0].DriveLetter + ":\" } else { Start-Sleep 1 }
    }
    Info ("ISO may mau mo o " + $r + " (" + [math]::Round((Get-Item $out).Length / 1MB) + " MB)")
    $ux = $null
    try { [xml]$ux = Get-Content -Raw -LiteralPath (Join-Path $r "autounattend.xml") } catch { }
    Ck "ISO: autounattend.xml doc duoc (XML)" ($ux -ne $null)
    $wpd = @(Get-ChildItem -LiteralPath (Join-Path $r '$WinPEDriver$') -Directory -ErrorAction SilentlyContinue | ForEach-Object { $_.Name })
    Ck 'ISO: $WinPEDriver$ co vioscsi / viostor / NetKVM / vioserial, KHONG co driver man hinh' ((@("vioscsi", "viostor", "NetKVM", "vioserial") | Where-Object { $wpd -notcontains $_ }).Count -eq 0 -and ($wpd -notcontains "qxldod") -and ($wpd -notcontains "viogpudo")) ($wpd -join ",")
    Ck "ISO: vioscsi la driver cho 2k22 (file .inf + .sys + .cat)" ((@(Get-ChildItem -LiteralPath (Join-Path $r '$WinPEDriver$\vioscsi') -Include "*.inf", "*.sys", "*.cat" -Recurse).Count) -ge 3)
    foreach ($n in @("cbvm\pe.cmd", "cbvm\bios.txt", "cbvm\uefi.txt", 'sources\$OEM$\$$\Setup\Scripts\SetupComplete.cmd', ($OEM1 + "\py\python.exe"), ($OEM1 + "\vm\maymau.ps1"),
                     ($OEM1 + "\vm\qemu-ga-x86_64.msi"), ($OEM1 + "\agent\pcagent.py"), ($OEM1 + "\bin\ffmpeg.exe"), ($OEM1 + "\os\cacert.pem"))) {
      Ck ("ISO co " + $n) (Test-Path -LiteralPath (Join-Path $r $n))
    }
    $cj = $null
    try { $cj = Get-Content -Raw -LiteralPath (Join-Path $r ($OEM1 + "\cb.json")) | ConvertFrom-Json } catch { }
    Ck "ISO: cb.json (VPS, mat khau trong, giu quyen Admin, khong cuu ho, vai tro vm)" ($cj -and ($cj.user -eq "VPS") -and ($cj.password -eq "") -and ($cj.user_admin -eq $true) -and ($cj.recovery -eq $false) -and ($cj.role -eq "vm"))
    Ck "ISO: KHONG co identity.json / seed.json / enroll.key" (-not (@("identity.json", "seed.json", "enroll.key") | Where-Object { Test-Path -LiteralPath (Join-Path $r ($OEM1 + "\" + $_)) }))

    Out-Line "== 4. Chay maymau.ps1 tren may CI (gia lap may mau vua cai Windows xong)"
    if (Test-Path "C:\CloudBluePC") { Remove-Item "C:\CloudBluePC" -Recurse -Force }
    & robocopy.exe (Join-Path $r $OEM1) "C:\CloudBluePC" /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
    & attrib.exe -R "C:\CloudBluePC\*" /S /D 2>$null | Out-Null
    $cfgP = "C:\CloudBluePC\cb.json"
    $c = Get-Content -Raw $cfgP | ConvertFrom-Json
    $c.sb_url = "http://127.0.0.1:9"
    [IO.File]::WriteAllText($cfgP, ($c | ConvertTo-Json -Depth 5))
    $me = $env:USERNAME
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\CloudBluePC\vm\maymau.ps1" -Buoc 1 -Thu *> (Join-Path $Wk "mm1.out")
    $lg = "C:\CloudBluePC\logs\maymau.log"
    Ck "buoc 1: xong (moc maymau.buoc1)" (Test-Path "C:\CloudBluePC\logs\maymau.buoc1")
    Ck "buoc 1: tac vu 'CloudBlue May Mau' (SYSTEM) da dung" ((& schtasks.exe /query /tn "CloudBlue May Mau" 2>$null | Out-String) -match "CloudBlue May Mau")
    & schtasks.exe /delete /tn "CloudBlue May Mau" /f 2>$null | Out-Null
    $ga = Get-Service -Name "QEMU-GA" -ErrorAction SilentlyContinue
    Info ("QEMU guest agent tren may CI (khong co cong virtio-serial): " + $(if ($ga) { "da cai, trang thai " + $ga.Status } else { "CHUA cai duoc (xem qemu-ga-msi.log)" }))
    Ck "buoc 1: tai khoan VPS co, thuoc nhom Administrators" (((& net.exe localgroup Administrators 2>$null) | ForEach-Object { ("" + $_).Trim() }) -contains "VPS")
    $wlk = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
    Ck "buoc 1: tu dang nhap tai khoan VPS (mat khau trong)" ((("" + $wlk.AutoAdminLogon) -eq "1") -and (("" + $wlk.DefaultUserName) -eq "VPS") -and (("" + $wlk.DefaultPassword) -eq ""))
    Ck "buoc 1: Server khong tu mo Server Manager" ((Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\ServerManager" -ErrorAction SilentlyContinue).DoNotOpenServerManagerAtLogon -eq 1)
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\CloudBluePC\vm\maymau.ps1" -Buoc 2 -Thu *> (Join-Path $Wk "mm2.out")
    $ml = ""
    if (Test-Path $lg) { $ml = "" + (Get-Content -Raw $lg) }
    $done = Test-Path "C:\CloudBluePC\vm\maymau.done"
    Ck "buoc 2: XONG may mau (maymau.done)" ($done -and ($ml -match "XONG may mau"))
    if (-not $done) { Tail $lg 60; Tail "C:\CloudBluePC\logs\provision.log" 30 }
    Ck "buoc 2: Python nhung chay duoc" ($ml -match "Python chay duoc")
    foreach ($t in @("CloudBluePC Agent", "CloudBluePC Watch")) { Ck ("buoc 2: tac vu " + $t) ((& schtasks.exe /query /tn $t 2>$null | Out-String) -match "CloudBluePC") }
    Ck "buoc 2: cb_provision da khoa quyen thu muc (lock.done) + dat moc firstlogon" ((Test-Path "C:\CloudBluePC\logs\lock.done") -and (Test-Path "C:\CloudBluePC\logs\firstlogon.done"))
    Ck "buoc 2: thu muc C:\CloudBluePC an" (((Get-Item "C:\CloudBluePC" -Force).Attributes -band [IO.FileAttributes]::Hidden) -ne 0)
    Ck "buoc 2: don goi cai (msi, driver) + go tac vu may mau" ((-not (Test-Path "C:\CloudBluePC\vm\qemu-ga-x86_64.msi")) -and (-not (Test-Path "C:\CloudBluePC\vm\drivers")) -and (-not ((& schtasks.exe /query /tn "CloudBlue May Mau" 2>$null | Out-String) -match "May Mau")))
    Ck "buoc 2: KHONG co identity.json (may mau chua dang ky)" (-not (Test-Path "C:\CloudBluePC\identity.json"))
    Ck ("che do thu: tai khoan dang chay CI (" + $me + ") KHONG bi khoa") ((Get-WmiObject Win32_UserAccount -Filter ("LocalAccount=True and Name='" + $me + "'")).Disabled -ne $true)
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\CloudBluePC\vm\maymau.ps1" -Buoc 2 -Thu *> (Join-Path $Wk "mm3.out")
    Ck "chay lai buoc 2 khi da xong -> chi go tac vu, khong lam lai" (("" + (Get-Content -Raw $lg)) -match "da xong tu truoc")
    Out-Line "  -- maymau.log (40 dong cuoi):"
    Tail $lg 40
    foreach ($t in @("CloudBluePC Agent", "CloudBluePC Watch")) { & schtasks.exe /delete /tn $t /f 2>$null | Out-Null }
    Get-WmiObject Win32_Process -Filter "Name='pythonw.exe' or Name='python.exe'" -ErrorAction SilentlyContinue | ForEach-Object { try { $_.Terminate() | Out-Null } catch { } }
  }
} catch {
  $Fail++
  Out-Line ("  XX  LOI KHONG NGO: " + $_ + " @ " + $_.InvocationInfo.PositionMessage)
} finally {
  foreach ($m in $Mnt) { try { Dismount-DiskImage -ImagePath $m | Out-Null } catch { } }
  Out-Line ""
  Out-Line ("KET QUA: " + $Pass + " dat, " + $Fail + " loi")
  if ($KetQua) { $Lines | Set-Content -LiteralPath $KetQua -Encoding UTF8 }
}
if ($Fail -gt 0) { exit 1 }
exit 0
