# =====================================================================================================
#  CI (windows-2022, Admin, Windows PowerShell 5.1): GHEP ISO MAY MAU TU ISO WINDOWS THAT - dung lenh chu shop chay.
#    1. tai ISO Windows Server chinh chu (ban dung thu) tu link trong HUONG-DAN
#    2. chay proxmox\tao-iso-may-mau.ps1 -Iso <file> -KhongHoi (tu tai virtio dung ban, Python nhung, ffmpeg, oscdimg)
#    3. file ISO may mau -> thu muc -OutDir (workflow dua sang job Linux co KVM de CAI THAT: win_that.py)
#  Ket qua: -KetQua <file .txt> (dong OK / XX / ..). Khong dua gi len web.
# =====================================================================================================
param([string]$Tag = "win2016", [string]$Url = "", [string]$OutDir = "C:\cbw\out", [string]$KetQua = "")

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
$Lines = New-Object System.Collections.ArrayList
$Fail = 0

function Out-Line([string]$t) { [void]$Lines.Add($t); Write-Host $t }
function Ck([string]$name, $cond, [string]$extra = "") {
  if ($cond) { Out-Line ("OK  " + $name) }
  else { $script:Fail++; Out-Line ("XX  " + $name + $(if ($extra) { ": " + $extra } else { "" })) }
}
function Info([string]$t) { Out-Line ("..  " + $t) }
function Mask([string]$t) { return (("" + $t) -replace '[a-z0-9]{16,}\.supabase\.co', '<du-an>.supabase.co') }

$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$W = "C:\cbw"
foreach ($d in @($W, (Join-Path $W "dl"), $OutDir)) { New-Item -ItemType Directory -Force $d | Out-Null }
$T0 = Get-Date

try {
  Out-Line ("== Ghep ISO may mau tu ISO Windows that - " + $Tag)
  $free = @(Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Free -gt 0 } | ForEach-Object { "" + $_.Name + ": " + [math]::Round($_.Free / 1GB, 0) + " GB" }) -join ", "
  Info ("may CI: o trong " + $free)

  $iso = Join-Path $W ("dl\" + $Tag + "-goc.iso")
  $ca = @("-fL", "--retry", "5", "--retry-delay", "5", "--connect-timeout", "30", "-sS", "-o", $iso, $Url)
  & curl.exe @ca
  $len = 0
  if (Test-Path -LiteralPath $iso) { $len = (Get-Item -LiteralPath $iso).Length }
  Ck ("tai ISO Windows chinh chu (ban dung thu) tu link trong HUONG-DAN: " + [math]::Round($len / 1GB, 2) + " GB, " + [math]::Round(((Get-Date) - $T0).TotalMinutes, 1) + " phut") ($len -gt 3GB) ("curl ma " + $LASTEXITCODE)
  if ($len -le 3GB) { throw "khong co ISO Windows" }

  $out = Join-Path $OutDir ("CloudBlue-MayMau-" + $Tag + ".iso")
  $log = Join-Path $W ("ghep-" + $Tag + ".log")
  $t1 = Get-Date
  $pa = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $Repo "proxmox\tao-iso-may-mau.ps1"), "-Iso", $iso, "-KhongHoi", "-Nguon", $Repo, "-Work", (Join-Path $W "work"), "-Out", $out)
  & powershell.exe @pa *>&1 | ForEach-Object { $s = "" + $_; Add-Content -LiteralPath $log -Value $s -Encoding UTF8; Write-Host $s }
  $txt = ""
  if (Test-Path -LiteralPath $log) { $txt = Get-Content -Raw -LiteralPath $log }
  foreach ($ln in ($txt -split "`r?`n")) {
    $s = ("" + $ln).Trim()
    if ($s -match '^(== |-> ban so|ban Windows:|driver virtio|ffmpeg|XONG|May mau:|!! |\(!\)|LOI|THIEU)') { Info ("lenh ghep: " + (Mask $s)) }
  }
  $olen = 0
  if (Test-Path -LiteralPath $out) { $olen = (Get-Item -LiteralPath $out).Length }
  Ck ("tao-iso-may-mau.ps1 -KhongHoi ghep xong ISO may mau " + $Tag + ": " + [math]::Round($olen / 1GB, 2) + " GB, " + [math]::Round(((Get-Date) - $t1).TotalMinutes, 1) + " phut") ($olen -gt 3GB) "khong co file ISO - xem cac dong 'lenh ghep' o tren"
  Ck ("lenh ghep nhan dung ban Windows: may mau tpl-" + $Tag) ($txt -match ("tpl-" + [regex]::Escape($Tag) + "\b")) "ban Windows trong ISO khac ten mong doi"
  if ($olen -gt 3GB) { Info ("sha256 ISO may mau: " + (Get-FileHash -Algorithm SHA256 -LiteralPath $out).Hash.ToLower()) }
} catch {
  if (("" + $_) -ne "khong co ISO Windows") { Ck "job ghep chay toi het" $false ("" + $_) }
} finally {
  if ($KetQua) { Set-Content -LiteralPath $KetQua -Value $Lines -Encoding UTF8 }
}
exit 0
