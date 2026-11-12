# =====================================================================
#  capnhat-ngu.ps1 - cap nhat 12/11/2026 cho may chu DANG CHAY:
#   * may ranh tu ngu, khach mo may tu bat lai
#   * DUONG THANG cho web + iPhone (wss://dN.<mien>:cong cua app) - hoi ma Cloudflare + dong y dieu khoan Let's Encrypt lan dau
#   Tai 3 file tu GitHub: windows/phonectl.py, windows/bluestream.py (phat hinh 11/12b), cloudphoned.py
#   -> giu ban cu (*.truoc-ngu) -> thay -> bat duong thang web -> tat phat hinh + nhan don (bang CloudBlue tu bat lai)
#   -> kiem tra -> in thu may ngu (khong tat may nao)
#   Chay:     & C:\blue\capnhat-ngu.ps1
#   Quay lai: & C:\blue\capnhat-ngu.ps1 -QuayLai     (tra 3 file cu; may dang ngu se duoc ban cu tu bat lai)
#  File nay chi dung chu khong dau (PowerShell 5 doc .ps1 khong BOM theo bang ma ANSI).
# =====================================================================
param([switch]$QuayLai)
$ErrorActionPreference = 'Continue'
Set-Location C:\blue
$n = (Select-String -Path cloudphone.conf -Pattern '^NODE_ID=' | Select-Object -First 1).Line -replace '^NODE_ID=', ''
$P = 'C:\Program Files\Python312\python.exe'; if (-not (Test-Path $P)) { $P = 'python' }

function Stop-Svc([string]$which) {
    if ($which -eq 'phat-hinh') {
        Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'bluestream\.py' -and $_.CommandLine -notmatch '--(netcheck|upnp|captest|selftest)' -and $_.Name -notmatch '^(powershell|pwsh|cmd)' } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    } else {
        # dang tao may cho khach -> cho xong (toi da 10 phut) roi moi tat phan nhan don
        for ($i = 0; $i -lt 120; $i++) {
            $busy = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'phonectl\.py\S*\s+(create|resize)\s' }
            if (-not $busy) { break }
            if ($i -eq 0) { Write-Host "$n - dang tao / doi cau hinh may cho khach, cho xong roi moi bat lai phan nhan don..." -ForegroundColor Cyan }
            Start-Sleep 5
        }
        Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'cloudphoned\.py' -and $_.Name -match '^python' } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    }
}

if ($QuayLai) {
    $back = @()
    foreach ($x in 'phonectl.py', 'bluestream.py', 'cloudphoned.py') {
        if (Test-Path "$x.truoc-ngu") { Copy-Item "$x.truoc-ngu" $x -Force; $back += $x }
    }
    if (-not $back) { Write-Host "$n - khong co ban cu (*.truoc-ngu) de quay lai" -ForegroundColor Yellow; return }
    if ($back -contains 'bluestream.py') { Stop-Svc 'phat-hinh' }
    if ($back -contains 'cloudphoned.py') { Stop-Svc 'nhan-don' }
    Write-Host "$n - da tra ban cu: $($back -join ', '). Bang CloudBlue tu bat lai dich vu; may dang ngu se duoc bat lai trong vai phut." -ForegroundColor Green
    return
}

$R = 'https://api.github.com/repos/lvhien205hn-eng/cloudblue/contents'
$W = 'https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main'
$F = @(
    @('windows/phonectl.py', 'phonectl.py', 'def cmd_wake'),
    @('windows/bluestream.py', 'bluestream.py', 'BS_VER = "11/12b"'),
    @('cloudphoned.py', 'cloudphoned.py', 'def idle_job')
)
$new = @(); $bad = 0
foreach ($f in $F) {
    $src = $f[0]; $dst = $f[1]; $mark = $f[2]; $tmp = "$dst.new"
    if (Select-String -Path $dst -Pattern $mark -SimpleMatch -Quiet -ErrorAction SilentlyContinue) { continue }
    curl.exe -sSL -H "Accept: application/vnd.github.raw" -o $tmp "$R/$src`?ref=main"
    if (-not (Select-String -Path $tmp -Pattern $mark -SimpleMatch -Quiet -ErrorAction SilentlyContinue)) {
        curl.exe -sSL -o $tmp "$W/$src`?t=$(Get-Random)"
    }
    if (Select-String -Path $tmp -Pattern $mark -SimpleMatch -Quiet -ErrorAction SilentlyContinue) { $new += $dst }
    else { $bad++; Write-Host "$n - CHUA TAI DUOC $dst (GitHub chua co ban moi?)" -ForegroundColor Yellow }
}
if ($bad) {
    Remove-Item *.py.new -ErrorAction SilentlyContinue
    Write-Host "$n - KHONG thay file nao (can du 3 file moi tren GitHub). May chu van chay ban cu." -ForegroundColor Yellow
    return
}
foreach ($x in $new) { Copy-Item $x "$x.truoc-ngu" -Force -ErrorAction SilentlyContinue; Move-Item "$x.new" $x -Force }

Write-Host "`n== Duong thang cho web + iPhone (lan dau hoi ma Cloudflare + dong y dieu khoan Let's Encrypt) ==" -ForegroundColor Cyan
& $P bluestream.py --webdirect
if ($LASTEXITCODE -eq 0) { Write-Host "$n - duong thang web: OK" -ForegroundColor Green }
else { Write-Host "$n - duong thang web CHUA bat (ma $LASTEXITCODE) - web van di Cloudflare nhu cu; xem dong loi o tren" -ForegroundColor Yellow }
if ($new -contains 'bluestream.py') { Stop-Svc 'phat-hinh' }
if ($new -contains 'cloudphoned.py') { Stop-Svc 'nhan-don' }
if ($new) { Write-Host "$n - da thay: $($new -join ', ') - cho bang CloudBlue bat lai dich vu (toi da 2 phut)..." -ForegroundColor Cyan }
else { Write-Host "$n - 3 file da la ban moi tu truoc - kiem tra dich vu..." -ForegroundColor Cyan }

$a = $null; $b = $null
for ($i = 0; $i -lt 40 -and -not ($a -and $b); $i++) {
    Start-Sleep 3
    $a = Get-Content logs\phat-hinh.log -Tail 400 -Encoding UTF8 -ErrorAction SilentlyContinue | Select-String '11/12b' | Select-Object -Last 1
    $b = Get-Content logs\cloudphoned.log -Tail 400 -Encoding UTF8 -ErrorAction SilentlyContinue | Select-String 'IDLE_STOP_MIN=' | Select-Object -Last 1
}
if ($a -and $b) { Write-Host "OK - $n - phat hinh 11/12b + may ranh tu ngu dang chay" -ForegroundColor Green }
else { Write-Host "$n - chua thay ban moi chay (phat hinh: $([bool]$a), nhan don: $([bool]$b)) -> trong bang CloudBlue bam Bat tat ca roi chay lai lenh nay" -ForegroundColor Yellow }

Write-Host "`n== Thu (KHONG tat may nao): may nao dang ranh / vi sao chua ranh ==" -ForegroundColor Cyan
& $P phonectl.py idle --dry -v
