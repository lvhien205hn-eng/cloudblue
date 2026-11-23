# =====================================================================================================
#  winpc/tests/ci/check.ps1
#  Chay tren may Windows cua GitHub Actions (Windows PowerShell 5.1, quyen Admin) moi khi thu muc winpc doi:
#    1. soat cu phap tao-iso.ps1 bang chinh Windows PowerShell
#    2. thu tung ham: tach duong dan keo tha, nhan / tu choi driver, giai nen goi driver, tai + kiem oscdimg, dong ISO thu
#    3. chay CA tao-iso.ps1 tu dau toi luc ra file ISO, voi 2 "ISO Windows" gia lap dung tu anh WinRE cua may chay thu
#       (co driver rieng tung ban, goi VGA NVIDIA gia, goi driver hong), roi mo ISO ra kiem
#    4. chay lai khong dua ma dang ky -> phai dung lai ma cua lan truoc
#    5. bao mat: khoa quyen that bang icacls + thu bang 1 tai khoan thuong that (sec_check.py)
#    6. chep tep that cua bo cai: tep lon khong duoc ngon RAM (sys_check.py)
#    7. soat ten chua khai bao trong moi file Python (lint.py) + thu tren Windows that cac ham goi thang vao Windows cua ban 21.11a:
#       thu mang, tim card NVIDIA, provision.cmd in tien do, dat dong ho, huy hen tat may, DRIVER: doc thiet bi that + kho driver + do lai phan cung (os_check.py)
#    8. dieu khien tu xa (ban 21.11d): tai ffmpeg + kiem ma da ghim, quay man hinh that + nen, chuot / phim / bo nho copy that, mo chuong trinh bang SYSTEM
#       vao phien man hinh, va thu dau-cuoi may chu phat hinh (windows/bluestream.py + pcrelay.py) <-> pcremote <-> nguoi xem (remote_check.py)
#    3b. (23.11g) ISO MAY CHU CLOUD PHONE: chay tao-iso.ps1 -MayChu voi tep cau hinh + bo cai gia lap gia, mo ISO ra kiem
#  -ChiIso : chi thu phan tao ISO (buoc 1-4) - dung khi thu tren nhanh rieng cho nhanh.   -KetQua <tep> : ghi them ket qua ra tep.
#  Khong dua gi len web, khong dung toi may that nao. Luon thoat ma 0; ket qua nam o trang tom tat cua lan chay.
# =====================================================================================================
param([string]$WorkRoot = "", [switch]$ChiIso, [string]$KetQua = "")
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$RepoDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Ps1 = Join-Path $RepoDir "tao-iso.ps1"
$Pass = 0
$FailN = 0
$Lines = New-Object System.Collections.ArrayList

function Out-Line([string]$t) { [void]$Lines.Add($t); Write-Host $t }
function Ck([string]$name, $cond, [string]$extra = "") {
  if ($cond) { $script:Pass++; Out-Line ("  OK  " + $name) }
  else { $script:FailN++; Out-Line ("  XX  " + $name + "   -> " + $extra) }
}
function Info([string]$t) { Out-Line ("  ..  " + $t) }
function New-Dir([string]$p) { New-Item -ItemType Directory -Force $p | Out-Null; return $p }
function Write-Summary {
  $verdict = "CHUA DAT"
  if ($FailN -eq 0) { $verdict = "DAT" }
  $head = "winpc check: " + $verdict + " (" + $Pass + " OK, " + $FailN + " XX)"
  Write-Host ""
  Write-Host ("::notice title=winpc check::" + $head)
  if ($env:GITHUB_STEP_SUMMARY) {
    $md = @(("### " + $head), "", '```') + @($Lines) + @('```')
    Add-Content -Path $env:GITHUB_STEP_SUMMARY -Value $md -Encoding UTF8
  }
  if ($KetQua) { try { Set-Content -Path $KetQua -Value (@($head) + @($Lines)) -Encoding UTF8 } catch { Write-Host ("khong ghi duoc tep ket qua: " + $_) } }
}

try {
  if (-not $WorkRoot) {
    $best = Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Free -gt 0 } | Sort-Object Free -Descending | Select-Object -First 1
    $WorkRoot = "" + $best.Name + ":\"
  }
  $Wk = Join-Path $WorkRoot "cbci"
  if (Test-Path $Wk) { Remove-Item -Recurse -Force $Wk }
  New-Dir $Wk | Out-Null
  $os = Get-CimInstance Win32_OperatingSystem
  Info ("may chay thu: " + $os.Caption + " " + $os.Version + " ; PowerShell " + $PSVersionTable.PSVersion + " ; thu muc lam viec " + $Wk + " (trong " + [math]::Round((Get-PSDrive ($Wk.Substring(0, 1))).Free / 1GB, 1) + " GB)")

  # ------------------------------------------------------------------------------------------- 1. cu phap
  Out-Line "== 1. Cu phap tao-iso.ps1"
  $tok = $null
  $perr = $null
  $ast = [System.Management.Automation.Language.Parser]::ParseFile($Ps1, [ref]$tok, [ref]$perr)
  Ck "tao-iso.ps1 khong co loi cu phap" (@($perr).Count -eq 0) ((@($perr) | ForEach-Object { "dong " + $_.Extent.StartLineNumber + ": " + $_.Message }) -join " | ")
  if (@($perr).Count -gt 0) { throw "loi cu phap - dung" }

  # nap cac ham + vai bien dau file cua tao-iso.ps1 vao phien nay (KHONG chay phan than)
  $fdefs = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false)
  foreach ($fd in $fdefs) { . ([scriptblock]::Create($fd.Extent.Text)) }
  $wantVars = @('$OSC_SHA', '$PACKEXT', '$Notes', '$OscInfo', '$OscWhy', '$GetFileErr', '$VER', '$CFAPI')
  foreach ($st in $ast.EndBlock.Statements) {
    if ($st -is [System.Management.Automation.Language.AssignmentStatementAst]) {
      if ($wantVars -contains ("" + $st.Left.Extent.Text)) { . ([scriptblock]::Create($st.Extent.Text)) }
    }
  }
  Ck "nap duoc cac ham cua tao-iso.ps1" ((@($fdefs).Count -ge 20) -and ($OSC_SHA.Length -eq 64) -and (@($PACKEXT).Count -ge 4)) ("" + @($fdefs).Count + " ham")
  Info ("ban tao-iso: " + $VER)

  # ------------------------------------------------------------------------------------------- 2. tung ham
  Out-Line "== 2. Tung ham"
  $td = New-Dir (Join-Path $Wk "t")
  $f1 = Join-Path $td "Win 10 (22H2).iso"
  $f2 = Join-Path $td "b.iso"
  $f3 = Join-Path $td "vga [moi].exe"
  foreach ($x in @($f1, $f2, $f3)) { [IO.File]::WriteAllBytes($x, (New-Object byte[] 16)) }
  $q = [string][char]34
  Ck "Split-Paths: 1 duong dan co dau cach, trong nhay kep" ((@(Split-Paths ($q + $f1 + $q)) -join "|") -eq $f1)
  Ck "Split-Paths: 1 duong dan co dau cach, khong nhay" ((@(Split-Paths $f1) -join "|") -eq $f1)
  Ck "Split-Paths: keo 2 file 1 luc" ((@(Split-Paths ($q + $f1 + $q + " " + $f2)) -join "|") -eq ($f1 + "|" + $f2))
  Ck "Split-Paths: ten co ngoac vuong" ((@(Split-Paths $f3) -join "|") -eq $f3)
  Ck "Split-Paths: dong trong" (@(Split-Paths "   ").Count -eq 0)
  Ck "Test-There: duong dan co ky tu la khong lam hong script" ((-not (Test-There ("C:\a" + $q + "b|c<d"))) -and (-not (Test-There "")) -and (Test-There $f3))
  Ck "Test-IsoPath: file .iso / thu muc duoc, file .exe khong" ((Test-IsoPath $f1) -and (Test-IsoPath $td) -and (-not (Test-IsoPath $f3)))
  Ck "Get-OsTag" (((Get-OsTag "10.0.19045.4291") -eq "22H2") -and ((Get-OsTag "10.0.10586.0") -eq "1511") -and ((Get-OsTag "10.0.99999.1") -eq "build 99999"))
  Ck "Test-NvidiaName" ((Test-NvidiaName "466.77-notebook-win10-64bit-international-whql.exe") -and (Test-NvidiaName "nvidia-vga-x.exe") -and (-not (Test-NvidiaName "Driver WLAN.exe")))
  $fn1 = Free-Name $td "Driver WLAN (moi).exe"
  [IO.File]::WriteAllBytes($fn1, (New-Object byte[] 4))
  $fn2 = Free-Name $td "Driver WLAN (moi).exe"
  Ck "Free-Name: ten sach + khong trung" (((Split-Path -Leaf $fn1) -eq "Driver_WLAN__moi_.exe") -and ((Split-Path -Leaf $fn2) -eq "Driver_WLAN__moi__2.exe")) ($fn1 + " | " + $fn2)
  $rc9 = Run-Exe (Join-Path $td "khong-co.exe") @("x")
  $rc3 = Run-Exe "cmd.exe" @("/c", "exit 3")
  Ck "Run-Exe: chuong trinh khong co -> 9009, ma thoat that -> 3" (($rc9 -eq 9009) -and ($rc3 -eq 3)) ("" + $rc9 + " / " + $rc3)

  # goi driver mau
  $seven = "C:\Program Files\7-Zip\7z.exe"
  $has7 = Test-Path $seven
  Info ("7-Zip tren may chay thu: " + $has7)
  $drvSrc = New-Dir (Join-Path $Wk "drvsrc\Net Driver")
  Set-Content -Path (Join-Path $drvSrc "netx.inf") -Value "[Version]" -Encoding ASCII
  Set-Content -Path (Join-Path $drvSrc "netx.sys") -Value "sys" -Encoding ASCII
  $pk = New-Dir (Join-Path $Wk "packs")
  $zipPack = Join-Path $pk "pack one.zip"
  Compress-Archive -Path $drvSrc -DestinationPath $zipPack
  $cabPack = Join-Path $pk "pack2.cab"
  & makecab.exe (Join-Path $drvSrc "netx.inf") $cabPack | Out-Null
  $badPack = Join-Path $pk "bad.exe"
  Copy-Item "C:\Windows\System32\notepad.exe" $badPack
  $nvPack = Join-Path $pk "466.77-notebook-win10-64bit-international-whql.exe"
  [IO.File]::WriteAllBytes($nvPack, (New-Object byte[] 2097152))
  $sfxPack = Join-Path $pk "Driver WLAN.exe"
  $szPack = Join-Path $pk "pack4.7z"
  if ($has7) {
    & $seven a -sfx $sfxPack $drvSrc | Out-Null
    & $seven a $szPack $drvSrc | Out-Null
  }
  $lanDir = New-Dir (Join-Path $Wk "drvsrc\lan folder")
  Set-Content -Path (Join-Path $lanDir "e1.inf") -Value "[Version]" -Encoding ASCII
  $emptyDir = New-Dir (Join-Path $Wk "drvsrc\rong")
  Set-Content -Path (Join-Path $emptyDir "readme.txt") -Value "x" -Encoding ASCII

  Ck "Test-DriverDrop: nhan file .exe / .zip / .cab va thu muc co .inf" (((Test-DriverDrop $badPack) -eq "") -and ((Test-DriverDrop $zipPack) -eq "") -and ((Test-DriverDrop $cabPack) -eq "") -and ((Test-DriverDrop $lanDir) -eq ""))
  Ck "Test-DriverDrop: tu choi file .iso, file .inf le, thu muc khong co driver, o dia, duong dan khong co" (((Test-DriverDrop $f1) -ne "") -and ((Test-DriverDrop (Join-Path $lanDir "e1.inf")) -ne "") -and ((Test-DriverDrop $emptyDir) -ne "") -and ((Test-DriverDrop "C:\") -ne "") -and ((Test-DriverDrop (Join-Path $td "khong-co")) -ne ""))
  Ck "Get-DropName: file .exe thuong giu nguyen ten" ((Get-DropName (Get-Item $badPack)) -eq "bad.exe")
  Info ("Get-DropText: " + (Get-DropText $lanDir) + "   |   " + (Get-DropText $nvPack))

  $x1 = Join-Path $Wk "x1"
  Ck "Expand-One .zip" ((Expand-One $zipPack $x1 "") -eq 1)
  $x2 = Join-Path $Wk "x2"
  Ck "Expand-One .cab (expand.exe)" ((Expand-One $cabPack $x2 "") -eq 1)
  $x3 = Join-Path $Wk "x3"
  Ck "Expand-One file .exe khong phai goi nen -> 0" ((Expand-One $badPack $x3 $(if ($has7) { $seven } else { "" })) -eq 0)
  if ($has7) {
    $x4 = Join-Path $Wk "x4"
    Ck "Expand-One .exe tu giai nen (7-Zip)" ((Expand-One $sfxPack $x4 $seven) -eq 1)
    $x5 = Join-Path $Wk "x5"
    $n5 = Expand-One $sfxPack $x5 ""
    Info ("KHONG co 7-Zip, chi tar.exe cua Windows: .exe tu giai nen (7z) -> " + $n5 + " file .inf")
    $x6 = Join-Path $Wk "x6"
    $n6 = Expand-One $szPack $x6 ""
    Info ("KHONG co 7-Zip, chi tar.exe cua Windows: file .7z -> " + $n6 + " file .inf")
  }

  # Expand-DriverPacks tren 1 cay drivers giong luc tao ISO
  $dtree = New-Dir (Join-Path $Wk "tree\cb\drivers")
  $st1 = New-Dir (Join-Path $dtree "_img1")
  $st2 = New-Dir (Join-Path $dtree "1511")
  Copy-Item $zipPack (Join-Path $st1 "pack_one.zip")
  Copy-Item $badPack (Join-Path $st1 "bad.exe")
  Copy-Item $nvPack (Join-Path $st1 (Split-Path -Leaf $nvPack))
  if ($has7) { Copy-Item $sfxPack (Join-Path $st1 "Driver_WLAN.exe") }
  Copy-Item $cabPack (Join-Path $st2 "pack2.cab")
  $notes0 = $Notes.Count
  Expand-DriverPacks $dtree
  Ck "Expand-DriverPacks: goi .zip trong _img1 -> thu muc co .inf, xoa file goi" ((Test-Path (Join-Path $st1 "pack_one\Net Driver\netx.inf")) -and (-not (Test-Path (Join-Path $st1 "pack_one.zip")))) ((Get-ChildItem $st1 -Recurse | ForEach-Object { $_.FullName }) -join " ; ")
  Ck "Expand-DriverPacks: goi .cab trong drivers\1511" ((Count-Inf $st2) -eq 1)
  Ck "Expand-DriverPacks: goi hong trong _img1 -> bo ra + ghi chu" ((-not (Test-Path (Join-Path $st1 "bad.exe"))) -and ($Notes.Count -eq ($notes0 + 1)) -and (("" + $Notes[$Notes.Count - 1]) -match "bad.exe")) ("" + $Notes.Count)
  Ck "Expand-DriverPacks: goi VGA NVIDIA de nguyen" (Test-Path (Join-Path $st1 (Split-Path -Leaf $nvPack)))
  if ($has7) { Ck "Expand-DriverPacks: goi .exe tu giai nen trong _img1" (Test-Path (Join-Path $st1 "Driver_WLAN\Net Driver\netx.inf")) }

  # oscdimg: tai + kiem ma kiem, roi dong thu 1 ISO khoi dong duoc 2 kieu
  $dlDir = New-Dir (Join-Path $Wk "dl")
  $osc = Find-Oscdimg $dlDir @()
  Info ("oscdimg lan 1: " + $OscInfo + "   ly do loi: " + ((@($OscWhy) | ForEach-Object { "" + $_ }) -join " ; "))
  Ck "Find-Oscdimg: tai duoc tu may chu Microsoft, khop ma kiem da ghim" (($osc -ne "") -and ($OscInfo -match "KHOP ban da ghim")) $OscInfo
  $osc2 = Find-Oscdimg $dlDir @()
  Ck "Find-Oscdimg lan 2: dung lai ban da tai" (($osc2 -eq $osc) -and ($OscInfo -match "ban da tai lan truoc")) $OscInfo
  $bootSdi = "C:\Windows\Boot\DVD\PCAT\boot.sdi"
  $etfs = "C:\Windows\Boot\DVD\PCAT\etfsboot.com"
  $efisys = "C:\Windows\Boot\DVD\EFI\en-US\efisys.bin"
  $haveBoot = ((Test-Path $bootSdi) -and (Test-Path $etfs) -and (Test-Path $efisys))
  Info ("file khoi dong DVD tren may chay thu (boot.sdi / etfsboot.com / efisys.bin): " + $haveBoot)

  # file ISO dich dang bi chuong trinh khac giu (may ao Hyper-V dang gan file do) -> Test-FileLocked / Get-FreeOut
  $lk = Join-Path $td "CloudBlue-PC.iso"
  [IO.File]::WriteAllBytes($lk, (New-Object byte[] 64))
  Ck "Test-FileLocked: file khong ai giu -> false ; file khong ton tai -> false ; chuoi rong -> false" ((-not (Test-FileLocked $lk)) -and (-not (Test-FileLocked ($lk + ".khong-co"))) -and (-not (Test-FileLocked "")))
  Ck "Get-FreeOut: file khong bi giu -> giu nguyen ten" ((Get-FreeOut $lk) -eq $lk)
  $hold = [System.IO.File]::Open($lk, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
  try {
    Ck "Test-FileLocked: file dang bi chuong trinh khac mo (nhu may ao gan ISO) -> true" (Test-FileLocked $lk)
    $alt = Get-FreeOut $lk
    Ck "Get-FreeOut: file bi giu -> ten ben canh CloudBlue-PC-2.iso" ($alt -eq (Join-Path $td "CloudBlue-PC-2.iso")) $alt
    [IO.File]::WriteAllBytes((Join-Path $td "CloudBlue-PC-2.iso"), (New-Object byte[] 8))
    $hold2 = [System.IO.File]::Open((Join-Path $td "CloudBlue-PC-2.iso"), [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
    try { $alt3 = Get-FreeOut $lk } finally { $hold2.Close() }
    Ck "Get-FreeOut: ca -2.iso cung bi giu -> sang -3.iso" ($alt3 -eq (Join-Path $td "CloudBlue-PC-3.iso")) $alt3
  } finally { $hold.Close() }
  Ck "Test-FileLocked: tha ra roi -> false" (-not (Test-FileLocked $lk))
  Set-ItemProperty -LiteralPath $lk -Name IsReadOnly -Value $true
  Ck "Test-FileLocked: file chi-doc (khong ai giu) -> false (Remove-Item -Force van xoa duoc)" (-not (Test-FileLocked $lk))
  Set-ItemProperty -LiteralPath $lk -Name IsReadOnly -Value $false

  # ham cua ISO may chu Cloud Phone (23.11g)
  function ConvertTo-B64Url([string]$t) { return ([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($t))).TrimEnd("=").Replace("+", "-").Replace("/", "_") }
  $jwtSvc = "eyJhbGciOiJIUzI1NiJ9." + (ConvertTo-B64Url '{"iss":"supabase","ref":"abc","role":"service_role","iat":1}') + ".chu-ky-gia"
  $jwtAnon = "eyJhbGciOiJIUzI1NiJ9." + (ConvertTo-B64Url '{"iss":"supabase","ref":"abc","role":"anon","iat":1}') + ".chu-ky-gia"
  Ck "Get-JwtRole: doc muc role cua khoa eyJ..." (((Get-JwtRole $jwtSvc) -eq "service_role") -and ((Get-JwtRole $jwtAnon) -eq "anon") -and ((Get-JwtRole "rac") -eq "")) ((Get-JwtRole $jwtSvc) + " / " + (Get-JwtRole $jwtAnon))
  Ck "Test-SbKeyShape: nhan khoa service_role (eyJ... / sb_secret_...), tu choi khoa anon / publishable / chuoi ngan" (((Test-SbKeyShape $jwtSvc) -eq "") -and ((Test-SbKeyShape ("sb_secret_" + ("a" * 30))) -eq "") -and ((Test-SbKeyShape $jwtAnon) -match "anon") -and ((Test-SbKeyShape ("sb_publishable_" + ("a" * 30))) -match "CONG KHAI") -and ((Test-SbKeyShape "abc") -ne "") -and ((Test-SbKeyShape ("x" * 40)) -ne ""))
  Ck "Test-SbService: may chu khong toi duoc -> rong (khong nem loi)" ((Test-SbService "https://127.0.0.1:9" ("sb_secret_" + ("a" * 30))) -eq "")
  $oldCf = $CFAPI
  $CFAPI = "https://127.0.0.1:9/client/v4"
  $ctx = Test-CfToken "ma-gia" "example.test"
  $CFAPI = $oldCf
  Ck "Test-CfToken: khong goi duoc Cloudflare -> zone = false, co ly do, khong nem loi" ((-not $ctx.zone) -and (-not $ctx.tunnel) -and ($ctx.err -ne ""))
  $gd1 = Get-EmuDrop "D:\tai ve\MuMuInstaller_3.1.7.0_gw-overseas12_all_1699.exe"
  $gd2 = Get-EmuDrop "D:\LDPlayer9_ens_1001_ld.exe"
  $gd3 = Get-EmuDrop "D:\x\tpl_a15.mumudata"
  $gd4 = Get-EmuDrop "D:\x\Android 12 mau.mumudata"
  $gd5 = Get-EmuDrop "D:\x\may-mau.mumudata"
  $gd6 = Get-EmuDrop "D:\x\chrome_setup.exe"
  $gd7 = Get-EmuDrop "D:\x\ghi-chu.txt"
  Ck "Get-EmuDrop: nhan bo cai MuMu / LDPlayer + tep may mau (12 / 15); tep la thi noi ro ly do" (($gd1.name -eq "mumu-setup.exe") -and ($gd2.name -eq "ld-setup.exe") -and ($gd3.name -eq "tpl_a15.mumudata") -and ($gd4.name -eq "tpl_a12.mumudata") -and ($gd5.why -match "so ban Android") -and ($gd6.why -match "khong nhan ra bo cai") -and ($gd7.why -ne "")) (@($gd1.name, $gd2.name, $gd3.name, $gd4.name, $gd5.why, $gd6.why) -join " | ")
  $cfT = Join-Path $td "mc.conf"
  @("# ghi chu", "SUPABASE_SERVICE_KEY=abc=def", " EMU = ld ", "", "DOMAIN=example.test") | Set-Content -Path $cfT -Encoding UTF8
  $rcf = Read-ConfFile $cfT
  Ck "Read-ConfFile: tep KHOA=gia tri (co BOM, ghi chu, gia tri co dau =)" (($rcf["SUPABASE_SERVICE_KEY"] -eq "abc=def") -and ($rcf["EMU"] -eq "ld") -and ($rcf["DOMAIN"] -eq "example.test") -and ($rcf.Count -eq 3))

  # ------------------------------------------------------------------------------------------- 3. chay ca tao-iso.ps1
  Out-Line "== 3. Chay ca tao-iso.ps1 voi 2 ISO Windows gia lap"
  $wim = ""
  foreach ($c in @("C:\Windows\System32\Recovery\Winre.wim", "C:\Recovery\WindowsRE\Winre.wim")) { if ((-not $wim) -and (Test-Path -LiteralPath $c)) { $wim = $c } }
  if (-not $wim) {
    $ri = ""
    try { $ri = (& reagentc.exe /info 2>&1 | Out-String) } catch { $ri = "" + $_ }
    Info ("khong thay Winre.wim o cho quen; reagentc: " + ($ri -replace "\s+", " "))
    if ($ri -match '(\\\\\?\\GLOBALROOT\\device\\harddisk\d+\\partition\d+\\Recovery\\WindowsRE)') {
      $cand = $Matches[1] + "\Winre.wim"
      $tmpWim = Join-Path $Wk "winre-copy.wim"
      & cmd.exe /c copy /y $cand $tmpWim | Out-Null
      if (Test-Path $tmpWim) { $wim = $tmpWim }
    }
  }
  if (-not $wim) {
    try {
      $fk = New-Dir (Join-Path $Wk "fakewin")
      New-Dir (Join-Path $fk "Windows\System32\config") | Out-Null
      foreach ($sf in @("ntoskrnl.exe", "ntdll.dll", "kernel32.dll", "hal.dll")) { Copy-Item (Join-Path $env:SystemRoot ("System32\" + $sf)) (Join-Path $fk ("Windows\System32\" + $sf)) }
      & reg.exe save HKLM\SOFTWARE (Join-Path $fk "Windows\System32\config\SOFTWARE") /y | Out-Null
      & reg.exe save HKLM\SYSTEM (Join-Path $fk "Windows\System32\config\SYSTEM") /y | Out-Null
      $capWim = Join-Path $Wk "cap.wim"
      & dism.exe /English /Capture-Image "/ImageFile:$capWim" "/CaptureDir:$fk" "/Name:Windows 10 Pro" /Compress:fast | Out-Null
      if (Test-Path $capWim) { $wim = $capWim; Info "khong co WinRE -> dung anh tu chup (vai file he thong that)" }
      Remove-Item -Recurse -Force $fk
    } catch { Info ("tu chup anh loi: " + $_) }
  }
  $ok3 = $false
  if ($wim -and $osc -and $haveBoot) {
    $baseWim = Join-Path $Wk "base.wim"
    Copy-Item -LiteralPath $wim -Destination $baseWim -Force
    & attrib.exe -h -s -r $baseWim | Out-Null
    $wi = Get-WindowsImage -ImagePath $baseWim -Index 1
    Info ("anh Windows dung de thu: " + $wim + " (" + [math]::Round((Get-Item $baseWim).Length / 1MB) + " MB) - " + $wi.ImageName + " " + $wi.Version + " kien truc " + $wi.Architecture)
    if ([int]$wi.Architecture -eq 9) { $ok3 = $true }
  } else {
    Info ("BO QUA buoc 3: wim=" + $wim + " osc=" + $osc + " boot=" + $haveBoot)
  }
  if ($ok3) {
    # ISO gia 1: bo cai chuan (khoi dong duoc) ; ISO gia 2: chi co sources\install.wim
    $s1 = New-Dir (Join-Path $Wk "src1")
    New-Dir (Join-Path $s1 "sources") | Out-Null
    New-Dir (Join-Path $s1 "boot") | Out-Null
    New-Dir (Join-Path $s1 "efi\microsoft\boot") | Out-Null
    Copy-Item $baseWim (Join-Path $s1 "sources\boot.wim")
    Copy-Item $baseWim (Join-Path $s1 "sources\install.wim")
    Copy-Item $bootSdi (Join-Path $s1 "boot\boot.sdi")
    Copy-Item $etfs (Join-Path $s1 "boot\etfsboot.com")
    Copy-Item $efisys (Join-Path $s1 "efi\microsoft\boot\efisys.bin")
    Set-Content -Path (Join-Path $s1 "sources\lang.ini") -Value @("[Available UI Languages]", "en-US = 3", "", "[Fallback Languages]", "en-US = en-us") -Encoding ASCII
    Set-Content -Path (Join-Path $s1 "setup.exe") -Value "gia" -Encoding ASCII
    $s2 = New-Dir (Join-Path $Wk "src2")
    New-Dir (Join-Path $s2 "sources") | Out-Null
    Copy-Item $baseWim (Join-Path $s2 "sources\install.wim")
    $iso1 = Join-Path $Wk "Win10 gia 1.iso"
    $iso2 = Join-Path $Wk "Win10-gia-2.iso"
    $bd = "-bootdata:2#p0,e,b" + (Join-Path $s1 "boot\etfsboot.com") + "#pEF,e,b" + (Join-Path $s1 "efi\microsoft\boot\efisys.bin")
    $r1 = Run-Exe $osc @("-m", "-o", "-u2", "-udfver102", $bd, "-lSRC1", $s1, $iso1)
    $r2 = Run-Exe $osc @("-m", "-o", "-u2", "-udfver102", "-lSRC2", $s2, $iso2)
    Ck "oscdimg dong duoc 2 ISO nguon (1 cai khoi dong 2 kieu BIOS + UEFI)" (($r1 -eq 0) -and ($r2 -eq 0) -and (Test-Path -LiteralPath $iso1) -and (Test-Path -LiteralPath $iso2)) ("" + $r1 + " / " + $r2)
    Remove-Item -Recurse -Force $s1, $s2
    Remove-Item -Force $baseWim

    $work = Join-Path $Wk "w"
    $outIso = Join-Path $Wk "out\CloudBlue-PC.iso"
    New-Dir (Join-Path $Wk "out") | Out-Null
    $key = "cbpc_" + ("ab" * 20)
    $drv = @(("1=" + $lanDir), ("2=" + $nvPack), ("2=" + $badPack), ("2=" + $zipPack))
    if ($has7) { $drv += ("2=" + $sfxPack) }
    $log1 = Join-Path $Wk "run1.log"
    # gia lap: file ISO cua lan chay truoc DANG BI MAY AO GIU -> script phai tu ghi ra CloudBlue-PC-2.iso (khong lam xong het moi loi o buoc cuoi)
    Set-Content -LiteralPath $outIso -Value "ISO cu dang gan trong may ao" -Encoding ASCII
    $holdIso = [System.IO.File]::Open($outIso, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
    $a1 = @{ Iso = @($iso1, $iso2); Work = $work; Out = $outIso; Nguon = $RepoDir; MaDangKy = $key; KhongHoi = $true; GiuWork = $true; Driver = $drv; KhongKiemMa = $true }     # ma gia -> khong hoi may chu
    & $Ps1 @a1 *>&1 | ForEach-Object { $ln = "" + $_; Write-Host $ln; Add-Content -Path $log1 -Value $ln -Encoding UTF8 }
    $txt = ""
    if (Test-Path $log1) { $txt = Get-Content -Raw -Path $log1 }
    Ck "chay toi khung TOM TAT, khong dung giua chung" (($txt -match "TOM TAT") -and (-not ($txt -match "!! DUNG")) -and (-not ($txt -match "!! LOI"))) (($txt -split "`n" | Where-Object { $_ -match "!! " }) -join " | ")
    $inSum = $false
    foreach ($ln in ($txt -split "`r?`n")) {
      if ($ln -match "TOM TAT \(chep") { $inSum = $true; continue }
      if ($inSum -and ($ln -match "^=====")) { $inSum = $false }
      if ($inSum) { Info ("TOM TAT> " + $ln.Trim()) }
    }
    if (-not ($txt -match "TOM TAT \(chep")) { foreach ($ln in @($txt -split "`r?`n" | Select-Object -Last 40)) { Info ("CUOI LOG> " + $ln) } }
    $holdIso.Close()
    $outIso2 = Join-Path $Wk "out\CloudBlue-PC-2.iso"
    Ck "file ISO cu dang bi giu (may ao gan) -> script bao ngay tu dau + ghi ISO moi ra CloudBlue-PC-2.iso, khong dung giua chung" ((Test-Path $outIso2) -and ($txt -match "dang bi chuong trinh khac giu") -and ($txt -match "CloudBlue-PC-2\.iso") -and ((Get-Item $outIso).Length -lt 100))
    $outIso = $outIso2
    Ck "co file ISO moi" (Test-Path $outIso)
    Ck "khung tom tat: ma dang ky tu tham so + dong oscdimg + goi hong bi bo" (($txt -match "Ma dang ky: CO \(tham so\)") -and ($txt -match "oscdimg: ") -and ($txt -match "Goi driver bad.exe: khong lay ra duoc"))
    # kiem ma dang ky voi may chu: ham Test-EnrollKey (ma GIA -> may chu khong bao gio tra "ok"; may chu chua co SQL v42 thi tra rong = bo qua)
    Ck "Test-EnrollKey: may chu khong toi duoc -> tra rong (bo qua buoc kiem, khong nem loi)" ((Test-EnrollKey "https://127.0.0.1:9" "x" $key) -eq "")
    $cjs = Join-Path $work "dl\config.js"
    if (Test-Path $cjs) {
      $cjt = Get-Content -Raw -Encoding UTF8 $cjs
      $u9 = ""; $k9 = ""
      if ($cjt -match 'supabaseUrl\s*:\s*"([^"]+)"') { $u9 = $Matches[1] }
      if ($cjt -match 'supabaseAnonKey\s*:\s*"([^"]+)"') { $k9 = $Matches[1] }
      $ks = "?"
      if ($u9 -and $k9) { $ks = Test-EnrollKey $u9 $k9 $key }
      Ck "Test-EnrollKey voi may chu that + ma GIA: 'bad' / 'nokey' (may chu da co SQL v42) hoac rong (chua co) - khong bao gio 'ok'" (@("bad", "nokey", "") -contains $ks) ("tra: " + $ks)
      Info ("may chu tra loi ma gia: '" + $ks + "'")
    } else { Info "khong thay dl\config.js - bo qua phep thu Test-EnrollKey voi may chu that" }
    if (Test-Path $outIso) {
      $mi = Mount-DiskImage -ImagePath $outIso -PassThru
      Start-Sleep -Seconds 2
      $vol = $mi | Get-Volume
      $dr = "" + $vol.DriveLetter + ":\"
      try {
        $cfg = Get-Content -Raw (Join-Path $dr "cb\cb.json") | ConvertFrom-Json
        $ids = @($cfg.images | ForEach-Object { "" + $_.id })
        Info ("ISO moi: nhan " + $vol.FileSystemLabel + ", he file " + $vol.FileSystem + ", " + [math]::Round((Get-Item $outIso).Length / 1GB, 2) + " GB ; cac ban: " + ($ids -join ", ") + " ; ban bo cai " + $cfg.ver)
        Ck "ISO moi co 2 ban Windows, ban thu 2 nam o cb\images" (($ids.Count -eq 2) -and (Test-Path (Join-Path $dr ("cb\images\" + $ids[1] + ".wim"))) -and (Test-Path (Join-Path $dr "sources\install.wim")))
        Ck "driver rieng ISO thu 1 (thu muc co .inf) -> cb\drivers\<ban 1>" (Test-Path (Join-Path $dr ("cb\drivers\" + $ids[0] + "\lan_folder\e1.inf"))) ((Get-ChildItem (Join-Path $dr "cb\drivers") -Recurse -File | ForEach-Object { $_.FullName }) -join " ; ")
        Ck "driver rieng ISO thu 2 (goi .zip) -> cb\drivers\<ban 2>, da giai nen" (Test-Path (Join-Path $dr ("cb\drivers\" + $ids[1] + "\pack_one\Net Driver\netx.inf")))
        if ($has7) { Ck "driver rieng ISO thu 2 (goi .exe tu giai nen) -> da giai nen" (Test-Path (Join-Path $dr ("cb\drivers\" + $ids[1] + "\Driver_WLAN\Net Driver\netx.inf"))) }
        $fbd = Join-Path $dr ("cb\os\firstboot.d\" + $ids[1])
        Ck "goi VGA NVIDIA cua ISO thu 2 -> firstboot.d\<ban 2>; KHONG con file lenh 50-vga-nvidia.cmd (cb_provision tu cai sau khi may co mang)" ((Test-Path (Join-Path $fbd (Split-Path -Leaf $nvPack))) -and (-not (Test-Path (Join-Path $fbd "50-vga-nvidia.cmd"))))
        Ck "khong con thu muc _img, khong co goi hong trong ISO" ((@(Get-ChildItem (Join-Path $dr "cb\drivers") -Directory | Where-Object { $_.Name -match "^_img" }).Count -eq 0) -and (@(Get-ChildItem (Join-Path $dr "cb") -Recurse -File -Filter "bad.exe").Count -eq 0))
        Ck "ma dang ky nam trong cb\enroll.key" ((("" + (Get-Content (Join-Path $dr "cb\enroll.key") -TotalCount 1)).Trim()) -eq $key)
        Ck "anh nen + file tra loi + CAI-DAT.cmd co trong ISO" ((Test-Path (Join-Path $dr "cb\os\wallpaper.jpg")) -and (Test-Path (Join-Path $dr "autounattend.xml")) -and (Test-Path (Join-Path $dr "CAI-DAT.cmd")))
        # boot.wim: chep ra cho ghi duoc roi moi doc danh sach file (doc thang tren dia ISO chi-doc bi tu choi)
        $bwLocal = Join-Path $Wk "bootwim-check.wim"
        Copy-Item (Join-Path $dr "sources\boot.wim") $bwLocal -Force
        & attrib.exe -r $bwLocal | Out-Null
        $bw = @(Get-WindowsImage -ImagePath $bwLocal)
        $bidx = 1
        if ($bw.Count -ge 2) { $bidx = 2 }
        $inside = @(Get-WindowsImageContent -ImagePath $bwLocal -Index $bidx | Where-Object { $_ -match '^\\cb\\(pe\\cb_pe\.py|py\\python\.exe|lib\\cbsys\.py)$|^\\Windows\\System32\\winpeshl\.ini$' })
        Ck "boot.wim trong ISO da duoc chen bo cai CloudBlue + winpeshl.ini" ($inside.Count -eq 4) ($inside -join " ; ")
        Remove-Item -Force $bwLocal -ErrorAction SilentlyContinue
      } catch {
        Ck "kiem noi dung ISO moi" $false ($_.Exception.Message + " (dong " + $_.InvocationInfo.ScriptLineNumber + ")")
      } finally {
        Dismount-DiskImage -ImagePath $outIso | Out-Null
      }
    }

    # ---------------------------------------------------------------------------------------- 3b. ISO may chu Cloud Phone (23.11g)
    Out-Line "== 3b. ISO MAY CHU CLOUD PHONE: tao-iso.ps1 -MayChu (tep cau hinh + bo cai gia lap gia + may mau gia)"
    $mcDir = New-Dir (Join-Path $Wk "mc")
    $mcKey = "sb_secret_ci_" + ("m" * 32)
    $mcTok = "cf_ci_token_" + ("t" * 32)
    $mcConf = Join-Path $mcDir "may-chu.conf"
    @("# cau hinh thu", "DOMAIN=example.test", ("SUPABASE_SERVICE_KEY=" + $mcKey), ("CF_API_TOKEN=" + $mcTok), "LE_AGREE=1", "EMU=mumu") | Set-Content -Path $mcConf -Encoding ASCII
    $mcSetup = Join-Path $mcDir "MuMuInstaller_gia.exe"
    $mcTpl = Join-Path $mcDir "tpl_a15.mumudata"
    [IO.File]::WriteAllBytes($mcSetup, (New-Object byte[] 4096))
    [IO.File]::WriteAllBytes($mcTpl, (New-Object byte[] 2048))
    $workM = Join-Path $Wk "wm"
    $outM = Join-Path $Wk "out\CloudBlue-MayChu.iso"
    $logM = Join-Path $Wk "run-mc.log"
    $aM = @{ Iso = @($iso1, $iso2); Work = $workM; Out = $outM; Nguon = $RepoDir; KhongHoi = $true; MayChu = $true; MayChuConf = $mcConf; BoCai = @($mcSetup, $mcTpl); MaDangKy = $key; KhongKiemMa = $true }
    & $Ps1 @aM *>&1 | ForEach-Object { $ln = "" + $_; Write-Host $ln; Add-Content -Path $logM -Value $ln -Encoding UTF8 }
    $txtM = ""
    if (Test-Path $logM) { $txtM = Get-Content -Raw -Path $logM }
    Ck "ISO may chu: chay toi khung TOM TAT, khong dung giua chung" (($txtM -match "TOM TAT") -and (-not ($txtM -match "!! DUNG")) -and (-not ($txtM -match "!! LOI"))) (($txtM -split "`n" | Where-Object { $_ -match "!! " }) -join " | ")
    Ck "ISO may chu: tom tat ghi ro may chu + canh bao ISO chua khoa bi mat; KHONG in khoa ra man hinh; khong dung ma dang ky may PC (du co dua -MaDangKy)" (($txtM -match "MAY CHU CLOUD PHONE: gia lap mumu") -and ($txtM -match "mumu-setup.exe, tpl_a15.mumudata") -and ($txtM -match "ISO NAY CHUA KHOA BI MAT") -and ($txtM -match "khoa Supabase: CO") -and ($txtM -match "Ma dang ky: KHONG") -and (-not $txtM.Contains($mcKey)) -and (-not $txtM.Contains($mcTok)))
    Ck "ISO may chu: buoc ke nhac go TEN MAY (win9 / 9)" ($txtM -match "bo cai hoi TEN MAY")
    if (Test-Path $outM) {
      $miM = Mount-DiskImage -ImagePath $outM -PassThru
      Start-Sleep -Seconds 2
      $drM = "" + ($miM | Get-Volume).DriveLetter + ":\"
      try {
        $cfgM = Get-Content -Raw (Join-Path $drM "cb\cb.json") | ConvertFrom-Json
        Ck "ISO may chu: cb.json role = server, tai khoan giu quyen Admin, bo cai chi hoi ten may (khong hoi so may), ten tu sinh win-..., cho go ten 15 phut" (($cfgM.role -eq "server") -and ($cfgM.user_admin -eq $true) -and ($cfgM.ask_code -eq $false) -and ($cfgM.name_prefix -eq "win") -and ($cfgM.code_wait -eq 900))
        Ck "ISO may chu: KHONG co cb\enroll.key (may chu khong vao danh sach may PC cho thue)" (-not (Test-Path (Join-Path $drM "cb\enroll.key")))
        $fbM = Join-Path $drM "cb\os\firstboot.d"
        $mcM = Join-Path $fbM "maychu"
        Ck "ISO may chu: lenh chay lan dau 90-cloudblue-may-chu.ps1 + script cai may chu dung ban trong kho" (((Get-FileHash (Join-Path $fbM "90-cloudblue-may-chu.ps1")).Hash -eq (Get-FileHash (Join-Path $RepoDir "maychu\firstboot.ps1")).Hash) -and ((Get-FileHash (Join-Path $mcM "may-chu-iso.ps1")).Hash -eq (Get-FileHash (Join-Path $RepoDir "maychu\may-chu-iso.ps1")).Hash))
        $kvM = Read-ConfFile (Join-Path $mcM "may-chu.conf")
        Ck "ISO may chu: may-chu.conf du khoa (ten mien, dia chi Supabase, khoa service_role, ma Cloudflare, dong y Let's Encrypt, gia lap)" (($kvM["DOMAIN"] -eq "example.test") -and ($kvM["SUPABASE_URL"] -match '^https://[a-z0-9]+\.supabase\.co$') -and ($kvM["SUPABASE_SERVICE_KEY"] -eq $mcKey) -and ($kvM["CF_API_TOKEN"] -eq $mcTok) -and ($kvM["LE_AGREE"] -eq "1") -and ($kvM["EMU"] -eq "mumu")) (($kvM.Keys | Where-Object { $_ -notmatch "KEY|TOKEN" } | ForEach-Object { $_ + "=" + $kvM[$_] }) -join " | ")
        Ck "ISO may chu: bo cai gia lap + may mau + curl.exe (cho Windows cu) nam trong cb\os\firstboot.d\maychu" (((Get-Item (Join-Path $mcM "mumu-setup.exe")).Length -eq 4096) -and ((Get-Item (Join-Path $mcM "tpl_a15.mumudata")).Length -eq 2048) -and (Test-Path (Join-Path $mcM "curl.exe"))) ((Get-ChildItem $mcM | ForEach-Object { $_.Name }) -join ", ")
        Ck "ISO may chu: van du bo cai Windows nhu ISO thuong (2 ban, file tra loi, CAI-DAT.cmd)" ((@($cfgM.images).Count -eq 2) -and (Test-Path (Join-Path $drM "autounattend.xml")) -and (Test-Path (Join-Path $drM "CAI-DAT.cmd")) -and (Test-Path (Join-Path $drM "sources\install.wim")))
      } catch {
        Ck "kiem noi dung ISO may chu" $false ($_.Exception.Message + " (dong " + $_.InvocationInfo.ScriptLineNumber + ")")
      } finally {
        Dismount-DiskImage -ImagePath $outM | Out-Null
      }
    } else { Ck "co file ISO may chu" $false ("khong thay " + $outM) }
    $tM2 = (& $Ps1 -Iso $iso1 -Work $workM -Nguon $RepoDir -KhongHoi -KhongIso -MayChu -BoCai $cfT *>&1 | Out-String)
    Ck "ISO may chu: tep kem khong phai bo cai gia lap / may mau -> dung som, noi ro" (($tM2 -match "!! DUNG") -and ($tM2 -match "Tep kem cho may chu"))
    $tM3 = (& $Ps1 -Iso $iso1 -Work $workM -Nguon $RepoDir -KhongHoi -KhongIso -MayChu -GiaLap ld *>&1 | Out-String)
    Ck "ISO may chu khong kem khoa / bo cai (-KhongHoi): van dung duoc cay bo cai, ghi chu ro cac viec se phai lam tay" (($tM3 -match "TOM TAT") -and ($tM3 -match "KHONG kem khoa Supabase") -and ($tM3 -match "KHONG kem bo cai ld") -and ($tM3 -match "KHONG kem ma Cloudflare") -and ($tM3 -match "gia lap ld"))
    Remove-Item -Recurse -Force $workM -ErrorAction SilentlyContinue

    # ---------------------------------------------------------------------------------------- 4. chay lai: dung lai ma dang ky, cac loi nhap
    Out-Line "== 4. Chay lai khong dua ma dang ky + cac kieu nhap sai"
    $log2 = Join-Path $Wk "run2.log"
    $a2 = @{ Iso = @($iso1); Work = $work; KhongHoi = $true; KhongIso = $true; KhongKiemMa = $true }     # khong -Nguon: tai phan mem tu GitHub + kiem manifest nhu nguoi dung
    if ($env:GITHUB_REF_NAME) { $a2["Nhanh"] = $env:GITHUB_REF_NAME; Info ("lan 2 tai tu nhanh: " + $env:GITHUB_REF_NAME) }      # dang thu tren nhanh nao thi tai dung nhanh do
    & $Ps1 @a2 *>&1 | ForEach-Object { $ln = "" + $_; Add-Content -Path $log2 -Value $ln -Encoding UTF8 }
    $txt2 = ""
    if (Test-Path $log2) { $txt2 = Get-Content -Raw -Path $log2 }
    foreach ($ln in ($txt2 -split "`r?`n")) { if ($ln -match "khop ma kiem|manifest|!! ") { Info ("LAN 2> " + $ln.Trim()) } }
    if ($txt2 -match "khong khop ma kiem") { Info "LAN 2: GitHub raw chua cap nhat kip (khong tinh la loi cua bo cong cu) - chay lai lay tu thu muc checkout"
      $a2["Nguon"] = $RepoDir
      Remove-Item -Force $log2
      & $Ps1 @a2 *>&1 | ForEach-Object { $ln = "" + $_; Add-Content -Path $log2 -Value $ln -Encoding UTF8 }
      $txt2 = Get-Content -Raw -Path $log2
    } else { Ck "lan 2: tai phan mem tu GitHub, khop ma kiem manifest" ($txt2 -match "khop ma kiem") }
    Ck "lan 2 khong dua ma -> dung lai ma lan truoc (luu ma hoa DPAPI)" (($txt2 -match "Ma dang ky: CO \(dung lai cua lan chay truoc\)") -and ($txt2 -match "TOM TAT")) (($txt2 -split "`n" | Where-Object { $_ -match "Ma dang ky|!! " }) -join " | ")
    Ck "file luu ma KHONG chua ma dang ky dang chu thuong" ((Test-Path (Join-Path $work "dl\ma-dang-ky.dpapi")) -and (-not ((Get-Content -Raw (Join-Path $work "dl\ma-dang-ky.dpapi")) -match "cbpc_")))
    Ck "lan 2 (-KhongIso): khong dong ISO, cay bo cai van co ma" (($txt2 -match "ISO: CHUA dong") -and (Test-Path (Join-Path $work "iso\cb\enroll.key")))
    $t3 = (& $Ps1 -Iso $iso1 -Work $work -Nguon $RepoDir -KhongHoi -KhongIso -Them $nvPack *>&1 | Out-String)
    Ck "-Them tro vao 1 file -> dung som, noi ro" (($t3 -match "!! DUNG") -and ($t3 -match "Them phai la THU MUC"))
    $t4 = (& $Ps1 -Iso $nvPack -Work $work -Nguon $RepoDir -KhongHoi -KhongIso *>&1 | Out-String)
    Ck "dua file .exe vao cho ISO -> dung som, noi ro" (($t4 -match "!! DUNG") -and ($t4 -match "khong phai file .iso"))
    $t5 = (& $Ps1 -Iso $iso1 -Work $work -Nguon $RepoDir -KhongHoi -KhongIso -Driver ("3=" + $zipPack) *>&1 | Out-String)
    Ck "-Driver sai so thu tu ISO -> dung som" (($t5 -match "!! DUNG") -and ($t5 -match "khong co ISO thu 3"))

    if ($ChiIso) { Info "-ChiIso: bo qua buoc 5-8 (bao mat, chep tep, he dieu hanh, dieu khien tu xa)"; throw "cb-xong-som" }

    # ---------------------------------------------------------------------------------------- 5. bao mat tren may cho thue
    Out-Line "== 5. Bao mat tren may cho thue: khoa quyen that bang icacls + thu bang 1 tai khoan thuong that"
    $cbDir = Join-Path $work "iso\cb"
    $pyExe = Join-Path $work "py\python.exe"
    if ((Test-Path $cbDir) -and (Test-Path $pyExe)) {
      $secTmp = New-Dir (Join-Path $Wk "sec")
      $oldEap = $ErrorActionPreference
      $ErrorActionPreference = "Continue"
      $secOut = @(& $pyExe -I -B (Join-Path $PSScriptRoot "sec_check.py") $cbDir $secTmp 2>&1 | ForEach-Object { "" + $_ })
      $ErrorActionPreference = $oldEap
      $nSec = 0
      foreach ($ln in $secOut) {
        if ($ln -match '^OK  (.*)$') { $script:Pass++; $nSec++; Out-Line ("  OK  " + $Matches[1]) }
        elseif ($ln -match '^XX  (.*)$') { $script:FailN++; $nSec++; Out-Line ("  XX  " + $Matches[1]) }
        elseif ($ln -match '^\.\. (.*)$') { Info $Matches[1] }
        elseif ($ln.Trim()) { Info ("? " + $ln) }
      }
      Ck "bo thu bao mat chay het" ($nSec -ge 15) ("" + $nSec + " phep thu, " + $secOut.Count + " dong")
    } else {
      Info ("BO QUA buoc 5: khong co cay bo cai / python (" + $cbDir + ")")
    }

    Out-Line "== 6. Chep tep that (cbsys.WinSys): goi driver lon khong duoc lam het RAM trong WinPE"
    if ((Test-Path $cbDir) -and (Test-Path $pyExe)) {
      $sysTmp = New-Dir (Join-Path $Wk "syschk")
      $oldEap = $ErrorActionPreference
      $ErrorActionPreference = "Continue"
      $sysOut = @(& $pyExe -I -B (Join-Path $PSScriptRoot "sys_check.py") $cbDir $sysTmp 2>&1 | ForEach-Object { "" + $_ })
      $ErrorActionPreference = $oldEap
      $nSys = 0
      foreach ($ln in $sysOut) {
        if ($ln -match '^OK  (.*)$') { $script:Pass++; $nSys++; Out-Line ("  OK  " + $Matches[1]) }
        elseif ($ln -match '^XX  (.*)$') { $script:FailN++; $nSys++; Out-Line ("  XX  " + $Matches[1]) }
        elseif ($ln -match '^\.\. (.*)$') { Info $Matches[1] }
        elseif ($ln.Trim()) { Info ("? " + $ln) }
      }
      Ck "bo thu chep tep chay het" ($nSys -ge 25) ("" + $nSys + " phep thu, " + $sysOut.Count + " dong")
    } else {
      Info ("BO QUA buoc 6: khong co cay bo cai / python (" + $cbDir + ")")
    }

    Out-Line "== 7. Soat ten chua khai bao (lint.py) + thu tren Windows that: thu mang, card NVIDIA, provision.cmd, dat dong ho (os_check.py)"
    if ((Test-Path $cbDir) -and (Test-Path $pyExe)) {
      $oldEap = $ErrorActionPreference
      $ErrorActionPreference = "Continue"
      $lintOut = @(& $pyExe -I -B (Join-Path $RepoDir "tests\lint.py") 2>&1 | ForEach-Object { "" + $_ })
      $lintRc = $LASTEXITCODE
      $osTmp = New-Dir (Join-Path $Wk "oschk")
      $osOut = @(& $pyExe -I -B (Join-Path $PSScriptRoot "os_check.py") $cbDir $osTmp 2>&1 | ForEach-Object { "" + $_ })
      $ErrorActionPreference = $oldEap
      Ck "lint.py: moi file Python dung cu phap, khong co ten chua khai bao" (($lintRc -eq 0) -and ($lintOut.Count -ge 15)) (("ma " + $lintRc + " ; ") + (($lintOut | Select-Object -Last 4) -join " | "))
      $nOs = 0
      foreach ($ln in $osOut) {
        if ($ln -match '^OK  (.*)$') { $script:Pass++; $nOs++; Out-Line ("  OK  " + $Matches[1]) }
        elseif ($ln -match '^XX  (.*)$') { $script:FailN++; $nOs++; Out-Line ("  XX  " + $Matches[1]) }
        elseif ($ln -match '^\.\. (.*)$') { Info $Matches[1] }
        elseif ($ln.Trim()) { Info ("? " + $ln) }
      }
      Ck "bo thu os_check chay het" ($nOs -ge 36) ("" + $nOs + " phep thu, " + $osOut.Count + " dong")
    } else {
      Info ("BO QUA buoc 7: khong co cay bo cai / python (" + $cbDir + ")")
    }

    Out-Line "== 8. Dieu khien tu xa (ban 21.11d): ffmpeg da ghim ma, quay man hinh that, chuot / phim that, mo bang SYSTEM vao phien man hinh, dau-cuoi (remote_check.py)"
    if ((Test-Path $cbDir) -and (Test-Path $pyExe)) {
      Ck "bo cai co chuong trinh dieu khien tu xa (cb\agent\pcremote.py)" (Test-Path (Join-Path $cbDir "agent\pcremote.py"))
      $rmTmp = Join-Path $Wk "rmchk"
      $repoRoot = Split-Path -Parent $RepoDir
      $oldEap = $ErrorActionPreference
      $ErrorActionPreference = "Continue"
      $rmOut = @(& $pyExe -I -B (Join-Path $PSScriptRoot "remote_check.py") $cbDir $rmTmp $repoRoot 2>&1 | ForEach-Object { "" + $_ })
      $ErrorActionPreference = $oldEap
      $nRm = 0
      foreach ($ln in $rmOut) {
        if ($ln -match '^OK  (.*)$') { $script:Pass++; $nRm++; Out-Line ("  OK  " + $Matches[1]) }
        elseif ($ln -match '^XX  (.*)$') { $script:FailN++; $nRm++; Out-Line ("  XX  " + $Matches[1]) }
        elseif ($ln -match '^\.\. (.*)$') { Info $Matches[1] }
        elseif ($ln.Trim()) { Info ("? " + $ln) }
      }
      Ck "bo thu remote_check chay het" (($nRm -ge 12) -and (($rmOut -join " ") -match "xong remote_check")) ("" + $nRm + " phep thu, " + $rmOut.Count + " dong")
    } else {
      Info ("BO QUA buoc 8: khong co cay bo cai / python (" + $cbDir + ")")
    }
  }
} catch {
  if (("" + $_.Exception.Message) -ne "cb-xong-som") {
    $script:FailN++
    Out-Line ("  XX  LOI KHI CHAY THU: " + $_.Exception.Message + "   (dong " + $_.InvocationInfo.ScriptLineNumber + ": " + ("" + $_.InvocationInfo.Line).Trim() + ")")
  }
} finally {
  try { Write-Summary } catch { Write-Host ("khong ghi duoc tom tat: " + $_) }
}
exit 0
