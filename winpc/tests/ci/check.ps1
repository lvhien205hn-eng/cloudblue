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
#  Khong dua gi len web, khong dung toi may that nao. Luon thoat ma 0; ket qua nam o trang tom tat cua lan chay.
# =====================================================================================================
param([string]$WorkRoot = "")
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
  $wantVars = @('$OSC_SHA', '$PACKEXT', '$Notes', '$OscInfo', '$OscWhy', '$GetFileErr', '$VER')
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
    $a1 = @{ Iso = @($iso1, $iso2); Work = $work; Out = $outIso; Nguon = $RepoDir; MaDangKy = $key; KhongHoi = $true; GiuWork = $true; Driver = $drv }
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
    Ck "co file ISO moi" (Test-Path $outIso)
    Ck "khung tom tat: ma dang ky tu tham so + dong oscdimg + goi hong bi bo" (($txt -match "Ma dang ky: CO \(tham so\)") -and ($txt -match "oscdimg: ") -and ($txt -match "Goi driver bad.exe: khong lay ra duoc"))
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
        Ck "goi VGA NVIDIA cua ISO thu 2 -> firstboot.d\<ban 2> + file lenh cai im lang" ((Test-Path (Join-Path $fbd (Split-Path -Leaf $nvPack))) -and (Test-Path (Join-Path $fbd "50-vga-nvidia.cmd")) -and ((Get-Content -Raw (Join-Path $fbd "50-vga-nvidia.cmd")) -match "-s -noreboot"))
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

    # ---------------------------------------------------------------------------------------- 4. chay lai: dung lai ma dang ky, cac loi nhap
    Out-Line "== 4. Chay lai khong dua ma dang ky + cac kieu nhap sai"
    $log2 = Join-Path $Wk "run2.log"
    $a2 = @{ Iso = @($iso1); Work = $work; KhongHoi = $true; KhongIso = $true }     # khong -Nguon: tai phan mem tu GitHub + kiem manifest nhu nguoi dung
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
      Ck "bo thu chep tep chay het" ($nSys -ge 14) ("" + $nSys + " phep thu, " + $sysOut.Count + " dong")
    } else {
      Info ("BO QUA buoc 6: khong co cay bo cai / python (" + $cbDir + ")")
    }
  }
} catch {
  $script:FailN++
  Out-Line ("  XX  LOI KHI CHAY THU: " + $_.Exception.Message + "   (dong " + $_.InvocationInfo.ScriptLineNumber + ": " + ("" + $_.InvocationInfo.Line).Trim() + ")")
} finally {
  try { Write-Summary } catch { Write-Host ("khong ghi duoc tom tat: " + $_) }
}
exit 0
