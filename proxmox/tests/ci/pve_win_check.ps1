# =====================================================================================================
#  CI (windows-2022, Windows PowerShell 5.1): ISO PROXMOX TU CAI - proxmox/tao-iso-proxmox.ps1 chay THAT tren Windows
#    1. cu phap script
#    2. chay lenh (-KhongHoi -Nguon <kho nay>): tu tai Python nhung (python.org), tu tai ISO Proxmox VE chinh thuc (khong co san tren may),
#       ghep voi 2 "ISO may mau" gia noi dung co dinh -> ra file ISO
#    3. ghi ma SHA-256 cua file ISO -> job ket-qua so voi ma cua file ghep tren Linux (cung dau vao) : phai GIONG TUNG BYTE
#       (file ghep tren Linux la file da duoc cai that trong may ao o job pve).
#  Ket qua: -KetQua <file .txt>, ma kiem: <thu muc ket qua>\pve-sha-win.txt. Khong dua gi len web.
# =====================================================================================================
param([string]$KetQua = "")

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
$Lines = New-Object System.Collections.ArrayList
$Pass = 0
$Fail = 0

function Out-Line([string]$t) { [void]$Lines.Add($t); Write-Host $t }
function Ck([string]$name, $cond, [string]$extra = "") {
  if ($cond) { $script:Pass++; Out-Line ("OK  " + $name) }
  else { $script:Fail++; Out-Line ("XX  " + $name + $(if ($extra) { "  -> " + $extra } else { "" })) }
}

$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$Wk = Join-Path $env:RUNNER_TEMP "cbw"
New-Item -ItemType Directory -Force $Wk | Out-Null

try {
  $f = "proxmox\tao-iso-proxmox.ps1"
  $errs = $null; $tok = $null
  [void][System.Management.Automation.Language.Parser]::ParseFile((Join-Path $Repo $f), [ref]$tok, [ref]$errs)
  Ck ("Windows: cu phap " + $f) ($errs.Count -eq 0) ((@($errs) | ForEach-Object { "" + $_.Extent.StartLineNumber + ": " + $_.Message }) -join " | ")

  $mau = Join-Path $Wk "mau"
  & python (Join-Path $Repo "proxmox\tests\ci\pve_det.py") $mau | Out-Null
  $m1 = Join-Path $mau "CloudBlue-MayMau-det1.iso"
  $m2 = Join-Path $mau "CloudBlue-MayMau-det2.iso"
  $out = Join-Path $Wk "det.iso"
  $log = Join-Path $Wk "chay.txt"
  $env:CB_PVE_PW_HASH = '$6$cbthu2611$f/E0E88wcetQEiEUYlTyWFTUy6Z7TbfRVRumzXvH6Y7PrcDqL/zDnnrZbu/Y3U6C2jgRc7NYkg2APNr17bDyX1'
  $env:CB_PVE_KHO_ID = "0123456789abcdef01234567"
  $t0 = Get-Date
  $pa = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $Repo $f), "-Nguon", $Repo, "-Work", $Wk, "-MayMau", ($m1 + "," + $m2), "-Out", $out, "-KhongHoi")
  & powershell.exe @pa *> $log
  $rc = $LASTEXITCODE
  $txt = ""
  if (Test-Path -LiteralPath $log) { $txt = (Get-Content -LiteralPath $log) -join "`n" }
  $mins = [math]::Round(((Get-Date) - $t0).TotalMinutes, 1)
  $tail = ""
  if ($txt.Length -gt 0) { $tail = $txt.Substring([Math]::Max(0, $txt.Length - 500)) -replace "`n", " | " }
  Ck ("Windows: tao-iso-proxmox.ps1 chay het (" + $mins + " phut): tu tai Python nhung + ISO Proxmox VE chinh thuc, ghep ra file ISO, khong DUNG / LOI") ((Test-Path -LiteralPath $out) -and ($txt -match "XONG \(") -and ($txt -notmatch "!! DUNG") -and ($txt -notmatch "LOI KHONG NGO")) $tail
  Ck "Windows: python.exe nhung co chu ky Python Software Foundation; ISO Proxmox tai ve khop ma kiem ban da thu (khong ghi chu 'chua thu')" (($txt -match "chu ky Python Software Foundation hop le") -and ($txt -match "tu tai ban") -and ($txt -notmatch "chua duoc CloudBlue cai thu")) $tail
  Ck "Windows: chu in ra chi co ASCII, khong in ma bam mat khau" (($txt -notmatch '[^\x00-\x7F]') -and ($txt -notmatch 'cbthu2611'))
  if (Test-Path -LiteralPath $out) {
    $sha = (Get-FileHash -Algorithm SHA256 -LiteralPath $out).Hash.ToLower()
    $len = (Get-Item -LiteralPath $out).Length
    Out-Line ("..  Windows: det.iso " + $len + " byte, sha256 " + $sha)
    if ($KetQua) { Set-Content -LiteralPath (Join-Path (Split-Path -Parent $KetQua) "pve-sha-win.txt") -Value ($sha + " " + $len) -Encoding ASCII }
  }
  if ($txt) { Set-Content -LiteralPath (Join-Path (Split-Path -Parent $KetQua) "pve-win-chay.txt") -Value $txt -Encoding UTF8 }
} catch {
  $Fail++
  Out-Line ("XX  Windows: LOI KHONG NGO: " + $_ + " @ " + $_.InvocationInfo.PositionMessage)
} finally {
  if ($KetQua) { $Lines | Set-Content -LiteralPath $KetQua -Encoding UTF8 }
}
if ($Fail -gt 0) { exit 1 }
exit 0
