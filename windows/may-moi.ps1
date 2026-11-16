# cloudblue-may-moi
# =====================================================================================================
#  may-moi.ps1 - CAI MAY CHU MOI CHI BANG 1 LENH (ban 16/11). Chay trong PowerShell (Admin) cua may chu moi:
#     $N = 8; ... & C:\blue\may-moi.ps1 -N $N        (lenh day du: so tay "cai-may-chu-moi-1-lenh")
#  Lam lan luot, phan nao xong roi thi tu bo qua (dan lai bao nhieu lan cung duoc):
#     1. Cai dat (setup.ps1 + tu nhan MuMu neu bo cai khong thay) - tai ban moi nhat tren GitHub
#     2. CHO anh lam cac buoc trong bang CloudBlue (khoa Supabase, noi Cloudflare, tu dang nhap, A->Z) - tu kiem 10 giay / lan
#     3. Duong thang cho web + iPhone (hoi ma Cloudflare DNS + anh tu go "dong y" dieu khoan Let's Encrypt - lan dau)
#     4. Lenh A (sua-tat-ca): kiem + cap nhat moi thu, tran 100 nhan / 112GB
#     5. Kiem RAM / phan cung (WHEA 47, sap 0x124)
#     6. In IP + cong de mo modem (phai mo tay tren trang modem)
#  KHONG in khoa bi mat nao. Khoa Supabase, lenh Cloudflare eyJ..., mat khau Windows: chi dan vao BANG CloudBlue.
#  Ma Cloudflare DNS (buoc 3): chi dan vao chinh cua so nay. Khong mo cong 8443.
#  -XoaSach (16/11f): may DA LA may chu (cloudphone.conf co NODE_ID) -> XOA SACH truoc roi cai lai thanh win$N:
#     xoa HAN moi may khach / du phong (cp_..., spare_...) + du lieu, danh sach may; cat cau hinh + nhat ky cu sang C:\blue\cu-...;
#     GIU MuMu + may mau (tpl_...) + may goc #0 + may rieng khong phai cp_/spare_. Web con may khach dang thue o may chu do -> DUNG.
#     Phai go dung "XOA SACH <ten may chu cu>" moi xoa. Khoa Supabase cu duoc dung lai (khoi dan lai).
# =====================================================================================================
param([int]$N = 0, [switch]$XoaSach)
$ErrorActionPreference = 'Continue'
$B = 'C:\blue'
$PY = 'C:\Program Files\Python312\python.exe'
$R = 'https://api.github.com/repos/lvhien205hn-eng/cloudblue/contents'
$W = 'https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main'

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host 'Hay mo PowerShell bang Run as administrator roi dan lai lenh.' -ForegroundColor Red; return
}
if ($N -lt 1 -or $N -gt 99) {
    try { $N = [int](Read-Host 'So may chu (VD 8)') } catch { $N = 0 }
    if ($N -lt 1 -or $N -gt 99) { Write-Host 'So may chu phai tu 1 den 99.' -ForegroundColor Red; return }
}
$Node = "win$N"; $Pub = "phone$N.cloudblue.vn"; $Strm = "stream$N.cloudblue.vn"; $Port = 8188 + $N
New-Item -ItemType Directory -Force $B | Out-Null
Set-Location $B
Write-Host "`n#################### CAI MAY CHU $Node (1 lenh - ban 16/11) ####################" -ForegroundColor Cyan

function Get-Conf([string]$key) {
    if (-not (Test-Path "$B\cloudphone.conf")) { return '' }
    $ln = Select-String -Path "$B\cloudphone.conf" -Pattern "^$key=" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($ln) { return ($ln.Line -replace "^$key=", '').Trim() } else { return '' }
}

# ------------------------------------------------------------------ 0. (tuy chon -XoaSach) xoa sach may chu cu de cai lai
function Get-VmRows {
    $vpy = $PY; if (-not (Test-Path $vpy)) { $vpy = 'python' }
    @(& $vpy "$B\phonectl.py" vmlist 2>$null) | Where-Object { "$_" -match '^\d+,[^,]+,' } | ForEach-Object {
        $vp = "$_" -split ','; [pscustomobject]@{ Idx = [int]$vp[0]; Name = $vp[1]; On = ($vp[2] -eq '1') } }
}
function Test-Ours([string]$nm) { return ($nm -like 'cp_*' -or $nm -like 'spare_*') }
function Invoke-XoaSach([string]$Was) {
    Write-Host "`n== 0/6 XOA SACH may chu $Was roi cai lai thanh $Node ==" -ForegroundColor Yellow
    $xsUrl = Get-Conf 'SUPABASE_URL'; $xsKey = Get-Conf 'SUPABASE_SERVICE_KEY'
    $xsHaveKey = [bool]($xsUrl -and $xsKey.Length -ge 30 -and $xsKey -notmatch 'DAN_')
    if ($xsHaveKey) {
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
            $xsRes = Invoke-RestMethod -Uri "$($xsUrl.TrimEnd('/'))/rest/v1/cloud_phones?node=eq.$Was&status=in.(pending,active,expired,cancelling)&select=status" `
                     -Headers @{ apikey = $xsKey; Authorization = "Bearer $xsKey" } -TimeoutSec 30 -ErrorAction Stop
        } catch {
            Write-Host "DUNG: chua doc duoc web de kiem may khach cua $Was (mang?) - thu lai sau 1 phut. Chua xoa gi." -ForegroundColor Red; return $false
        }
        $xsLive = @(@($xsRes) | Where-Object { $_ -and $_.status })
        if ($xsLive.Count) {
            $xsBy = (@($xsLive | Group-Object status | ForEach-Object { "$($_.Name) $($_.Count)" })) -join ', '
            Write-Host "DUNG: web con $($xsLive.Count) may khach dang thue o $Was ($xsBy). Chua xoa gi." -ForegroundColor Red
            Write-Host "      Chuyen / huy + hoan tien het may khach cua $Was tren web quan tri, cho het 'dang huy', roi dan lai lenh." -ForegroundColor Red
            return $false
        }
        Write-Host "  web: $Was khong con may khach nao dang thue" -ForegroundColor Green
    }
    $xsVm = @(Get-VmRows)
    if (-not $xsVm.Count) { Write-Host "DUNG: chua doc duoc danh sach may cua MuMu (MuMu dang ban / chua mo lan nao) - thu lai sau 1 phut. Chua xoa gi." -ForegroundColor Red; return $false }
    $xsDel = @($xsVm | Where-Object { Test-Ours $_.Name })
    $xsKeep = @($xsVm | Where-Object { -not (Test-Ours $_.Name) })
    if (-not $xsHaveKey -and @($xsDel | Where-Object { $_.Name -like 'cp_*' }).Count) {
        Write-Host "DUNG: cau hinh $Was khong co khoa Supabase nen khong kiem duoc web, ma MuMu con may khach (cp_...). Chua xoa gi." -ForegroundColor Red; return $false
    }
    $xsRenum = ($Was -ne $Node)
    Write-Host "  SE XOA HAN: $($xsDel.Count) may khach / du phong (cp_..., spare_...) + toan bo du lieu trong cac may do, danh sach may," -ForegroundColor Yellow
    Write-Host "              cau hinh + nhat ky cu (cat sang C:\blue\cu-...), tac vu tu chay cu" -ForegroundColor Yellow
    if ($xsRenum) { Write-Host "              + go ket noi Cloudflare cua $Was (buoc 2 se noi duong ham moi phone$N)" -ForegroundColor Yellow }
    Write-Host "  GIU: MuMu + cac may: $((@($xsKeep | ForEach-Object { $_.Name })) -join ', ')" -ForegroundColor Green
    $xsAns = Read-Host "  Go dung  XOA SACH $Was  de xac nhan (go khac = huy)"
    if ($xsAns -cne "XOA SACH $Was") { Write-Host "Da huy - chua xoa gi." -ForegroundColor Yellow; return $false }

    Write-Host "  Tat dich vu CloudBlue..." -ForegroundColor Cyan
    try { Stop-ScheduledTask -TaskName 'BlueRoblox' -ErrorAction SilentlyContinue } catch {}
    try { Unregister-ScheduledTask -TaskName 'BlueRoblox' -Confirm:$false -ErrorAction SilentlyContinue } catch {}
    @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        "$($_.Name)" -match '^(python|pythonw|node)' -and
        "$($_.CommandLine)" -match '\\blue\\|panel\.py|cloudphoned\.py|bluestream\.py|cpapi\.py|baomat\.py|phonectl\.py|run\.py' }) |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    if ($xsRenum) { & sc.exe stop cloudflared 2>$null | Out-Null; Start-Sleep 3; & sc.exe delete cloudflared 2>$null | Out-Null }
    Start-Sleep 3

    $xpy = $PY; if (-not (Test-Path $xpy)) { $xpy = 'python' }
    for ($xt = 1; $xt -le 2; $xt++) {
        if (-not @(Get-VmRows | Where-Object { Test-Ours $_.Name }).Count) { break }
        Write-Host "  Xoa may (lan $xt) - moi may 10-60 giay..." -ForegroundColor Cyan
        & $xpy -u "$B\phonectl.py" cleanup --all --yes | Out-Host
    }
    $xsAll = @(Get-VmRows)
    $xsLeft = @($xsAll | Where-Object { Test-Ours $_.Name })
    if (-not $xsAll.Count -or $xsLeft.Count) {
        $xsWho = (@($xsLeft | ForEach-Object { $_.Name })) -join ', '
        Write-Host "CHUA XOA HET: $(if ($xsAll.Count) { $xsWho } else { 'khong doc duoc danh sach may MuMu' }) - tat + xoa tay trong MuMu Multi-instance roi dan lai lenh." -ForegroundColor Red
        return $false
    }

    $xsBk = "$B\cu-$Was-$(Get-Date -Format 'yyyyMMdd-HHmm')"
    New-Item -ItemType Directory -Force $xsBk | Out-Null
    $xsMove = @('cloudphone.conf', 'redroid', 'logs'); if ($xsRenum) { $xsMove += 'le' }
    foreach ($xsItem in $xsMove) { if (Test-Path "$B\$xsItem") { Move-Item -Force "$B\$xsItem" "$xsBk\" -ErrorAction SilentlyContinue } }
    if (Test-Path "$B\cloudphone.conf") { Write-Host "DUNG: chua cat duoc cloudphone.conf cu (file dang mo?) - dan lai lenh." -ForegroundColor Red; return $false }
    Write-Host "== XOA SACH XONG: da xoa $($xsDel.Count) may + du lieu; cau hinh + nhat ky cu o $xsBk ==" -ForegroundColor Green
    if ($xsRenum) { Write-Host "   Nho: web quan tri > May chu: xoa dong $Was cu; Cloudflare > Tunnels: xoa duong ham cu cua $Was; modem: bo cong cu cua $Was." -ForegroundColor Yellow }
    return $true
}
# Cau hinh moi con cho trong khoa Supabase ma co cau hinh cu (lan xoa sach truoc) -> dung lai khoa cu (khong in khoa)
function Use-OldKey {
    $cf = "$B\cloudphone.conf"
    if (-not (Test-Path $cf)) { return }
    $ukLines = @([IO.File]::ReadAllLines($cf, [Text.Encoding]::UTF8))
    $ukGood = @($ukLines | Where-Object { $_ -match '^SUPABASE_SERVICE_KEY=(.{30,})$' -and $_ -notmatch 'DAN_' })
    if ($ukGood.Count) { return }
    $ukOld = Get-ChildItem "$B\cu-*\cloudphone.conf" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
    if (-not $ukOld) { return }
    $ukKey = @([IO.File]::ReadAllLines($ukOld.FullName, [Text.Encoding]::UTF8) | Where-Object { $_ -match '^SUPABASE_SERVICE_KEY=(.{30,})$' -and $_ -notmatch 'DAN_' }) | Select-Object -Last 1
    if (-not $ukKey) { return }
    $ukHit = $false
    $ukNew = @($ukLines | ForEach-Object { if ($_ -match '^SUPABASE_SERVICE_KEY=') { $ukHit = $true; $ukKey } else { $_ } })
    if (-not $ukHit) { $ukNew += $ukKey }
    [IO.File]::WriteAllLines($cf, [string[]]$ukNew, (New-Object Text.UTF8Encoding($false)))
    Write-Host "  Da dung lai khoa Supabase cua cau hinh cu ($($ukOld.Directory.Name)) - khoi dan lai buoc 2" -ForegroundColor Green
}

# ------------------------------------------------------------------ 1. cai dat
$cur = Get-Conf 'NODE_ID'
if ($cur -and ($XoaSach -or $cur -ne $Node)) {
    if (-not $XoaSach) {
        Write-Host "DUNG: may nay dang la $cur (C:\blue\cloudphone.conf) - kiem lai so may chu." -ForegroundColor Red
        Write-Host "      Muon XOA SACH $cur (xoa het may khach + du lieu, giu MuMu + may mau) roi cai lai: dung lenh 'xoa sach' trong so tay." -ForegroundColor Yellow
        return
    }
    if (-not ((@(Invoke-XoaSach $cur))[-1] -eq $true)) { return }      # chi tin gia tri CUOI (ham PowerShell tra ca chu da in)
}
Write-Host "`n== 1/6 Cai dat (setup.ps1 - lan dau 10-15 phut) ==" -ForegroundColor Cyan
$MU = $null
try {
    $MU = @(@("C:\Program Files\Netease\MuMuPlayer", "D:\Program Files\Netease\MuMuPlayer") +
            @(Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*", "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*" -ErrorAction SilentlyContinue |
              Where-Object { "$($_.DisplayName)" -match 'mumu' } | ForEach-Object { "$($_.InstallLocation)".TrimEnd('\') }) |
          Where-Object { $_ -and ((Test-Path "$_\nx_main\mumu-cli.exe") -or (Test-Path "$_\nx_main\MuMuManager.exe") -or (Test-Path "$_\shell\MuMuManager.exe")) })[0]
} catch {}
Remove-Item "$B\setup.ps1" -ErrorAction SilentlyContinue
curl.exe -fsSL -H "Accept: application/vnd.github.raw" -o "$B\setup.ps1" "$R/windows/setup.ps1"
if (-not (Test-Path "$B\setup.ps1") -or (Get-Item "$B\setup.ps1").Length -lt 5000) { curl.exe -fsSL -o "$B\setup.ps1" "$W/windows/setup.ps1?t=$(Get-Random)" }
if (-not (Test-Path "$B\setup.ps1") -or (Get-Item "$B\setup.ps1").Length -lt 5000) { Write-Host 'Chua tai duoc setup.ps1 tu GitHub (mang?) - thu lai sau 1 phut.' -ForegroundColor Red; return }
Set-ExecutionPolicy -Scope Process Bypass -Force
& "$B\setup.ps1" -Node $Node -PubHost $Pub
if (-not (Test-Path "$B\cloudphone.conf") -and $MU) {
    Write-Host "`n== Bo cai chua nhan MuMu -> tu tao cau hinh $Node (MuMu: $MU) roi chay lai ==" -ForegroundColor Cyan
    @("# CloudBlue - cau hinh may chu (KHONG dua file nay len GitHub)", "SUPABASE_URL=https://nprftgodswlpzomcttal.supabase.co", "SUPABASE_SERVICE_KEY=DAN_SERVICE_ROLE_KEY_VAO_DAY",
      "PUBLIC_BASE=https://$Pub", "STREAM_WS=wss://$Strm/v2/stream", "CPAPI_ORIGINS=https://cloudblue.vn,https://www.cloudblue.vn", "NOTIFY_URL=https://cloudblue.vn/api/notify-admin",
      "NODE_ID=$Node", "PRIMARY=0", "LIMIT_PCT=90", "RAM_OVER=1", "CPU_OVER=1.8", "WIN_VCPU_OVER=1.8", "WIN_RAM_RESERVE=3", "RAM_BUSY_PCT=98", "EMU=mumu", "ANDROIDS=12,15",
      "CAPTURE=scrcpy", "MEMU_MAX_RAM=16", "MEMU_MAX_CPU=32", "MEMU_RENDER=1", "MEMU_GMEM_OPT=1", "POOL_SIZE=0", "STREAM_PORT=$Port", "MUMU_DIR=$MU") |
        Set-Content -Encoding utf8 "$B\cloudphone.conf"
    Get-Process adb -ErrorAction SilentlyContinue | Stop-Process -Force
    Get-ChildItem -LiteralPath $MU -Recurse -Depth 3 -File -Filter adb.exe -ErrorAction SilentlyContinue | ForEach-Object {
        $D = $_.DirectoryName
        foreach ($f in "adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll") {
            if ((Test-Path "$D\$f") -and -not (Test-Path "$D\$f.bak")) { Copy-Item "$D\$f" "$D\$f.bak" }
            Copy-Item -Force "$B\platform-tools\$f" "$D\$f"
        }
    }
    & "$B\setup.ps1" -Node $Node -PubHost $Pub
}
Set-Location $B
if (-not (Test-Path $PY)) { $PY = 'python' }
$todo = @(Get-Content "$B\logs\viec-lam-tay.txt" -ErrorAction SilentlyContinue)
if ($todo -cmatch 'KHOI DONG LAI') {
    Write-Host "`n>>> KHOI DONG LAI may chu, mo PowerShell (Admin), dan lai DUNG lenh vua dan - lenh tu lam tiep tu cho dang do." -ForegroundColor Yellow; return
}
if (-not (Test-Path "$B\cloudphone.conf")) {
    Write-Host "`n>>> Chua cai xong: lam cac viec trong danh sach CON LAI LAM TAY o tren (cai MuMu, tao may mau tpl_a12 + tpl_a15 de TAT...)," -ForegroundColor Yellow
    Write-Host "    xong dan lai DUNG lenh vua dan." -ForegroundColor Yellow; return
}
try { Use-OldKey } catch { Write-Host "  (chua dung lai duoc khoa Supabase cu - dan khoa trong bang nhu thuong)" -ForegroundColor DarkGray }

# ------------------------------------------------------------------ 2. cho cac buoc trong bang CloudBlue
# Ten mien: hoi thang may chu ten mien cua Cloudflare (khong bi nho "chua co" cu cua modem / Windows - nho den 30 phut)
$script:NSV = ''
function Test-Host([string]$h) {
    if (-not $script:NSV) { try { $script:NSV = "$(@(Resolve-DnsName -Name 'cloudblue.vn' -Type NS -DnsOnly -ErrorAction Stop | Where-Object { $_.NameHost } | ForEach-Object { $_.NameHost })[0])" } catch {} }
    if ($script:NSV) { try { [void](Resolve-DnsName -Name $h -Server $script:NSV -DnsOnly -ErrorAction Stop); return $true } catch {} }
    try { Clear-DnsClientCache -ErrorAction SilentlyContinue } catch {}
    try { [void][System.Net.Dns]::GetHostAddresses($h); return $true } catch { return $false }
}
function Get-Need {
    $m = @()
    $k = Get-Conf 'SUPABASE_SERVICE_KEY'
    if ($k.Length -lt 30 -or $k -match 'DAN_') { $m += "bam '2 Dan khoa Supabase' (khoa service_role - KHONG gui ai)" }
    if (-not ((& sc.exe query cloudflared | Out-String) -match 'RUNNING')) { $m += "Cloudflare: tao tunnel phone$N roi bam '3 Noi Cloudflare' dan lenh eyJ... (KHONG gui ai)" }
    if (-not ((Test-Host $Pub) -and (Test-Host $Strm))) { $m += "Cloudflare: them 2 dia chi $Pub -> http://localhost:8010 va $Strm -> http://localhost:8020" }
    if (-not (Get-ScheduledTask -TaskName 'BlueRoblox' -ErrorAction SilentlyContinue)) { $m += "bam 'Tu dang nhap + tu chay' (go mat khau Windows TRONG BANG)" }
    $procs = @(Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue | ForEach-Object { "$($_.CommandLine)" })
    $okC = @($procs | Where-Object { $_ -match 'cloudphoned\.py' }).Count
    $okB = @($procs | Where-Object { $_ -match 'bluestream\.py' -and $_ -notmatch '--(netcheck|upnp|captest|selftest|webdirect)' }).Count
    if (-not $okC -or -not $okB) { $m += "bam 'Toi uu Windows' -> 'An cua so gia lap' -> 'TU DONG A->Z' (cho ra XONG)" }
    return $m
}
Write-Host "`n== 2/6 Cac buoc trong BANG CloudBlue (bang da mo san - lam lan luot, lenh tu kiem 10 giay / lan) ==" -ForegroundColor Cyan
Write-Host "   (Muon dung thi bam Ctrl+C, dan lai lenh luc nao cung duoc. Viec tay khac: C:\blue\logs\viec-lam-tay.txt)" -ForegroundColor DarkGray
$last = ''
while ($true) {
    $need = @(Get-Need)
    if (-not $need.Count) { break }
    $txt = $need -join "`n    - "
    if ($txt -ne $last) { Write-Host ("Con cho:`n    - " + $txt) -ForegroundColor Yellow; $last = $txt }
    Start-Sleep 10
}
Write-Host "OK - bang CloudBlue da xong: khoa Supabase, Cloudflare, tu chay, dich vu dang chay" -ForegroundColor Green

# ------------------------------------------------------------------ 3. duong thang web + iPhone
Set-Location $B
Write-Host "`n== 3/6 Duong thang cho web + iPhone (lan dau hoi ma Cloudflare DNS + anh tu go 'dong y'; da co thi chi kiem) ==" -ForegroundColor Cyan
Write-Host "   (Chua co ma thi bam Enter de bo qua - web van chay qua Cloudflare, lam sau bang lenh --webdirect trong so tay)" -ForegroundColor DarkGray
Start-Sleep 2; try { $Host.UI.RawUI.FlushInputBuffer() } catch {}
& $PY "$B\bluestream.py" --webdirect
$rc = $LASTEXITCODE
if ($rc -eq 0) { Write-Host "OK - duong thang web" -ForegroundColor Green } else { Write-Host "Duong thang web CHUA bat (ma $rc) - web van di Cloudflare; lam lai sau: cd C:\blue; & '$PY' bluestream.py --webdirect" -ForegroundColor Yellow }
$cert = Get-ChildItem "$B\le\*-fullchain.pem" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
if ($cert) {
    $old = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { "$($_.CommandLine)" -match 'bluestream\.py' -and "$($_.CommandLine)" -notmatch '--(netcheck|upnp|captest|selftest|webdirect)' -and "$($_.Name)" -notmatch '^(powershell|pwsh|cmd)' -and $_.CreationDate -lt $cert.LastWriteTime })
    if ($old.Count) {
        $old | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Write-Host "Bat lai phat hinh de dung chung chi moi - bang CloudBlue tu bat lai trong 1-2 phut" -ForegroundColor Cyan; Start-Sleep 90
    }
}

# ------------------------------------------------------------------ 4. lenh A
Set-Location $B
Write-Host "`n== 4/6 Lenh A (sua-tat-ca): kiem + cap nhat ban moi nhat ==" -ForegroundColor Cyan
curl.exe -sSL -H "Accept: application/vnd.github.raw" -o "$B\sua-tat-ca.py" "$R/windows/sua-tat-ca.py?ref=main"
if (-not (Select-String -Path "$B\sua-tat-ca.py" -Pattern 'cloudblue-sua-tat-ca' -SimpleMatch -Quiet -ErrorAction SilentlyContinue)) { curl.exe -sSL -o "$B\sua-tat-ca.py" "$W/windows/sua-tat-ca.py" }
if (Select-String -Path "$B\sua-tat-ca.py" -Pattern 'cloudblue-sua-tat-ca' -SimpleMatch -Quiet -ErrorAction SilentlyContinue) { & $PY -u "$B\sua-tat-ca.py" } else { Write-Host 'Chua tai duoc sua-tat-ca.py tu GitHub - chay lai lenh A sau 1 phut (so tay)' -ForegroundColor Red }

# ------------------------------------------------------------------ 5. RAM / phan cung
Write-Host "`n== 5/6 Kiem RAM / phan cung ==" -ForegroundColor Cyan
$whea = @(Get-WinEvent -FilterHashtable @{LogName = 'System'; ProviderName = 'Microsoft-Windows-WHEA-Logger'; Id = 47} -MaxEvents 200 -ErrorAction SilentlyContinue).Count
$crash = @(Get-WinEvent -FilterHashtable @{LogName = 'System'; Id = 41} -MaxEvents 50 -ErrorAction SilentlyContinue | Where-Object { try { [int64]$_.Properties[0].Value -eq 0x124 } catch { $false } }).Count
if ($whea -or $crash) { Write-Host "CANH BAO: loi RAM WHEA 47 = $whea lan, sap phan cung 0x124 = $crash lan -> chay lenh F trong so tay, xu ly RAM TRUOC khi ban may" -ForegroundColor Red } else { Write-Host "OK - khong thay loi RAM (WHEA 47) / sap phan cung (0x124)" -ForegroundColor Green }

# ------------------------------------------------------------------ 6. modem
Set-Location $B
Write-Host "`n== 6/6 Modem (lam tay - khong lam thi khach giat) ==" -ForegroundColor Cyan
& $PY "$B\bluestream.py" --netcheck
Write-Host "Trang modem FPT (thuong http://192.168.1.1): Network > LAN > gan IP co dinh cho may nay (IP LAN o tren + MAC)," -ForegroundColor Yellow
Write-Host "  roi Network > NAT > Virtual Server: TCP $Port -> IP LAN o tren, cung cong $Port. CHI mo dung cong nay, KHONG mo 8443." -ForegroundColor Yellow
Write-Host "Thu bang dien thoai 4G: https://<IP cong khai>:$Port -> 'ket noi khong rieng tu' = cong da mo." -ForegroundColor Yellow
Write-Host "`n#################### XONG $Node ####################" -ForegroundColor Green
Write-Host "Cuoi cung: web quan tri > danh sach may chu: $Node phai 'Dang chay' (nut ghi 'Nhan may lai' thi bam) -> thu tao 1 may Android 12 + 1 may Android 15." -ForegroundColor Green
