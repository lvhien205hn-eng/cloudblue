# cloudblue-may-chu-iso
# =====================================================================================================
#  may-chu-iso.ps1 - TU CAI MAY CHU CLOUD PHONE sau khi cai Windows tu "ISO may chu CloudBlue"   (ban 23.11j)
#  Tac vu "CloudBlue cai may chu" goi script nay moi lan dang nhap, cho toi khi XONG: tu lam tiep cho dang do, tu khoi dong lai khi can.
#  Cau hinh: C:\blue\iso\may-chu.conf (bo tao ISO ghi - CO KHOA BI MAT: khong gui ai, khong dua len mang):
#     DOMAIN  SUPABASE_URL  SUPABASE_SERVICE_KEY  CF_API_TOKEN (tuy chon)  CF_DNS_TOKEN (tuy chon)  LE_AGREE  EMU (mumu | ld)  NODE (tuy chon)
#  Lam lan luot (phan nao xong roi thi tu bo qua):
#     1. cho bo cai Windows lam xong + cho mang          2. TEN MAY CHU (ten go luc cai Windows: win9 hoac 9; khong co thi hoi, goi y so ke tiep)
#     3. gia lap (MuMu / LDPlayer 9: chay bo cai kem trong ISO - im lang neu bo cai ho tro, khong thi hien bo cai de bam)
#     4. setup.ps1 (Python, Node, adb, cloudflared, chuong trinh CloudBlue, cloudphone.conf)      5. khoa Supabase -> cloudphone.conf
#     6. may mau MuMu (tpl_a12 / tpl_a15)                 7. duong ham Cloudflare phoneN + streamN (tu tao bang API neu co CF_API_TOKEN)
#     8. bang CloudBlue tu chay quyen Admin, khong ngu, toi uu Windows        9. mo bang -> bat dich vu
#    10. duong thang web (neu co ma) + lenh A + kiem RAM + cong modem        11. kiem may chu da len web
#  KHONG in khoa bi mat nao ra man hinh / nhat ky. Nhat ky: C:\blue\logs\iso-cai.log
#  -Lib : chi nap cac ham (de kiem thu), khong chay.
# =====================================================================================================
param([string]$Conf = '', [switch]$Lib)
$MC_VER = '23.11j'
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
$B = 'C:\blue'
$ISO = 'C:\blue\iso'
$CBPC = 'C:\CloudBluePC'
$SRC = 'C:\CloudBluePC\os\firstboot.d\maychu'
$PROV = 'C:\CloudBluePC\logs'
$PY = 'C:\Program Files\Python312\python.exe'
$PYW = 'C:\Program Files\Python312\pythonw.exe'
$TASK = 'CloudBlue cai may chu'
$RAWB = 'https://raw.githubusercontent.com/lvhien205hn-eng/cloudblue/main'
$CFAPI = 'https://api.cloudflare.com/client/v4'
$SELF_REL = 'winpc/maychu/may-chu-iso.ps1'
$SECRETS = New-Object System.Collections.ArrayList
$WAIT_NAME = 300
$MAX_REBOOT = 4
$POLL = 20                     # giay giua 2 lan kiem khi dang cho (kiem thu dat nho lai)
$SETTLE = 120                  # giay cho gia lap vua cai tu mo lan dau roi moi dong

function Hide-Secret([string]$s) {
  foreach ($x in @($SECRETS)) { if ($x -and ("" + $x).Length -ge 8) { $s = $s.Replace(("" + $x), '***') } }
  return $s
}

function Say([string]$m, [string]$c = 'Gray') {
  $m = Hide-Secret $m
  Write-Host $m -ForegroundColor $c
  try { Add-Content -LiteralPath (Join-Path $B 'logs\iso-cai.log') -Value ((Get-Date -Format 'dd/MM HH:mm:ss') + ' ' + $m) -Encoding UTF8 -ErrorAction Stop } catch {}
}

function Step([string]$m) { Say ''; Say ('== ' + $m + ' ==') 'Cyan' }

# ----------------------------------------------------------------------------------------------------- tep KHOA=gia tri
function Read-KV([string]$path) {
  $h = @{}
  if (-not $path -or -not (Test-Path -LiteralPath $path)) { return $h }
  foreach ($ln in [IO.File]::ReadAllLines($path)) {
    $t = ("" + $ln).Trim()
    if (-not $t -or $t.StartsWith('#')) { continue }
    $i = $t.IndexOf('=')
    if ($i -lt 1) { continue }
    $h[$t.Substring(0, $i).Trim()] = $t.Substring($i + 1).Trim()
  }
  return $h
}

function Set-KV([string]$path, [string]$key, [string]$val) {
  $lines = @()
  if (Test-Path -LiteralPath $path) { $lines = @([IO.File]::ReadAllLines($path)) }
  $hit = $false
  $out = New-Object System.Collections.ArrayList
  foreach ($ln in $lines) {
    if (("" + $ln) -match ('^\s*' + [regex]::Escape($key) + '\s*=')) {
      if (-not $hit) { $hit = $true; [void]$out.Add($key + '=' + $val) }
    } else { [void]$out.Add("" + $ln) }
  }
  if (-not $hit) { [void]$out.Add($key + '=' + $val) }
  [IO.File]::WriteAllLines($path, [string[]]$out.ToArray(), (New-Object Text.UTF8Encoding($false)))
}

function Find-Payload([string]$name) {
  # Tep kem trong ISO (bo cai gia lap, may mau): C:\blue\iso truoc, roi thu muc bo cai Windows da chep vao may. Khong co -> ''.
  foreach ($d in @($ISO, $SRC)) { if ($d) { $c = Join-Path $d $name; if (Test-Path -LiteralPath $c) { return $c } } }
  return ''
}

function Get-State {
  $h = @{}
  try {
    $j = Get-Content -Raw -LiteralPath (Join-Path $B 'logs\iso-cai.json') -ErrorAction Stop | ConvertFrom-Json
    foreach ($p in $j.PSObject.Properties) { $h[$p.Name] = $p.Value }
  } catch {}
  return $h
}

function Save-State($st) {
  try {
    New-Item -ItemType Directory -Force (Join-Path $B 'logs') | Out-Null
    [IO.File]::WriteAllText((Join-Path $B 'logs\iso-cai.json'), ($st | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding($false)))
  } catch {}
}

# ----------------------------------------------------------------------------------------------------- ten may chu
function Get-NodeNum([string]$s) {
  # 'win9' / '9' / 'WIN 09' / 'may chu 12' / 'win-12' -> 9 / 9 / 9 / 12 / 12 ; khong doc duoc -> 0
  $t = ("" + $s).Trim().ToLower()
  if ($t -match '^(?:win|may\s*chu|maychu|server|sv|may)?[\s\-_\.]*0*(\d{1,2})$') { return [int]$Matches[1] }
  return 0
}

function Get-SeedNum([string]$seedPath) {
  # Ten go o bo cai Windows nam trong seed.json ("label"); ten tu sinh (CB-3FA2C1) thi KHONG lay.
  try {
    $j = Get-Content -Raw -LiteralPath $seedPath -ErrorAction Stop | ConvertFrom-Json
    $n = Get-NodeNum ("" + $j.label)
    if ($n -gt 0) { return $n }
    $nm = "" + $j.name
    if ($nm -and ($nm -notmatch '-[0-9A-Fa-f]{6}$')) { return (Get-NodeNum $nm) }
  } catch {}
  return 0
}

function Get-FreeNum($rows) {
  # so may chu ke tiep = so lon nhat dang co tren web + 1 (khong dung lai so cu); chua co may nao -> 2 (win1 la may chinh)
  $mx = 1
  foreach ($r in @($rows)) { if (("" + $r.id) -match '^win(\d{1,2})$') { $v = [int]$Matches[1]; if ($v -gt $mx) { $mx = $v } } }
  return ($mx + 1)
}

function Test-NodeLive($rows, [int]$n, [int]$secs = 300) {
  # may chu winN dang bao ve web trong $secs giay gan day? (= dang co 1 may KHAC mang ten nay)
  foreach ($r in @($rows)) {
    if (("" + $r.id) -ne ('win' + $n)) { continue }
    try {
      $t = [DateTimeOffset]::Parse(("" + $r.updated_at), [Globalization.CultureInfo]::InvariantCulture)
      if (([DateTimeOffset]::UtcNow - $t).TotalSeconds -lt $secs) { return $true }
    } catch {}
  }
  return $false
}

function Read-LineWait([string]$prompt, [int]$secs) {
  # Doc 1 dong tu ban phim, het $secs giay ma chua ai go phim nao -> $null. Khong co ban phim (chay tu dong) -> $null.
  Write-Host ($prompt + ': ') -NoNewline -ForegroundColor White
  $sb = New-Object Text.StringBuilder
  $t0 = Get-Date
  try {
    while ($true) {
      if ([Console]::KeyAvailable) {
        $k = [Console]::ReadKey($true)
        if ($k.Key -eq 'Enter') { Write-Host ''; return $sb.ToString() }
        if ($k.Key -eq 'Backspace') { if ($sb.Length -gt 0) { [void]$sb.Remove($sb.Length - 1, 1); Write-Host "`b `b" -NoNewline } ; continue }
        if ($k.KeyChar -and ([int][char]$k.KeyChar -ge 32)) { [void]$sb.Append($k.KeyChar); Write-Host $k.KeyChar -NoNewline }
        $t0 = Get-Date
      } else {
        if (((Get-Date) - $t0).TotalSeconds -ge $secs) { Write-Host ''; if ($sb.Length -gt 0) { return $sb.ToString() }; return $null }
        Start-Sleep -Milliseconds 150
      }
    }
  } catch { Write-Host ''; return $null }
}

# ----------------------------------------------------------------------------------------------------- mang / API
function Invoke-Api([string]$method, [string]$url, $headers, $body = $null, [int]$timeout = 30) {
  # Tra @{ ok; code; data; err } - khong nem loi. err da che khoa bi mat.
  try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}
  try {
    # UserAgent rieng: PowerShell mac dinh tu xung "Mozilla/5.0 ..." -> Supabase coi la trinh duyet, tu choi khoa sb_secret_... (401) du khoa dung
    $p = @{ Method = $method; Uri = $url; Headers = $headers; TimeoutSec = $timeout; UseBasicParsing = $true; ErrorAction = 'Stop'; UserAgent = ('cloudblue-may-chu/' + $MC_VER) }
    if ($null -ne $body) { $p.Body = [Text.Encoding]::UTF8.GetBytes(($body | ConvertTo-Json -Depth 8 -Compress)); $p.ContentType = 'application/json' }
    $r = Invoke-WebRequest @p
    $d = $null
    if ($r.Content) { try { $d = ("" + $r.Content) | ConvertFrom-Json } catch { $d = "" + $r.Content } }
    return @{ ok = $true; code = [int]$r.StatusCode; data = $d; err = '' }
  } catch {
    $code = 0; $txt = ''
    try { $code = [int]$_.Exception.Response.StatusCode } catch {}
    try { $sr = New-Object IO.StreamReader($_.Exception.Response.GetResponseStream()); $txt = $sr.ReadToEnd(); $sr.Close() } catch {}
    if (-not $txt) { $txt = "" + $_.Exception.Message }
    $txt = ($txt -replace '\s+', ' ')
    if ($txt.Length -gt 240) { $txt = $txt.Substring(0, 240) }
    return @{ ok = $false; code = $code; data = $null; err = (Hide-Secret ('HTTP ' + $code + ' ' + $txt)) }
  }
}

function Test-Net {
  foreach ($h in 'raw.githubusercontent.com', 'www.google.com') {
    try {
      $c = New-Object Net.Sockets.TcpClient
      $ar = $c.BeginConnect($h, 443, $null, $null)
      $ok = $ar.AsyncWaitHandle.WaitOne(6000) -and $c.Connected
      $c.Close()
      if ($ok) { return $true }
    } catch {}
  }
  return $false
}

function Get-Url([string]$url, [string]$dst) {
  Remove-Item -LiteralPath $dst -Force -ErrorAction SilentlyContinue
  $curl = Join-Path $env:SystemRoot 'System32\curl.exe'
  if (Test-Path -LiteralPath $curl) { & $curl -fsSL --retry 2 --connect-timeout 20 -o $dst $url 2>$null | Out-Null }
  if (-not (Test-Path -LiteralPath $dst) -or ((Get-Item -LiteralPath $dst).Length -lt 1)) {
    try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -UserAgent ('cloudblue-may-chu/' + $MC_VER) -Uri $url -OutFile $dst -TimeoutSec 180 -ErrorAction Stop } catch {}
  }
  return ((Test-Path -LiteralPath $dst) -and ((Get-Item -LiteralPath $dst).Length -gt 0))
}

function Test-Marker([string]$path, [string]$mark, [int]$minLen = 2000) {
  try {
    if ((Get-Item -LiteralPath $path -ErrorAction Stop).Length -lt $minLen) { return $false }
    return [bool](Select-String -LiteralPath $path -Pattern $mark -SimpleMatch -Quiet)
  } catch { return $false }
}

function Test-Ps1([string]$path) {
  try {
    $tok = $null; $perr = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tok, [ref]$perr)
    return (@($perr).Count -eq 0)
  } catch { return $false }
}

function Sb-Headers([string]$key) { return @{ apikey = $key; Authorization = ('Bearer ' + $key); Accept = 'application/json' } }

function Get-NodeRows([string]$sbUrl, [string]$key) {
  # @{ ok; rows; code; err }
  $r = Invoke-Api 'GET' ($sbUrl.TrimEnd('/') + '/rest/v1/cloud_nodes?select=id,updated_at') (Sb-Headers $key)
  if (-not $r.ok) { return @{ ok = $false; rows = @(); code = $r.code; err = $r.err } }
  return @{ ok = $true; rows = @($r.data | Where-Object { $_ -and $_.id }); code = $r.code; err = '' }
}

function Get-NodePhones([string]$sbUrl, [string]$key, [int]$num) {
  # So may khach DANG THUE o may chu win<num> tren web (dang tao / dang chay / tam dung cho gia han / dang huy). Khong hoi duoc -> -1.
  $q = '/rest/v1/cloud_phones?node=eq.win' + $num + '&status=in.(pending,active,expired,cancelling)&select=status'
  $r = Invoke-Api 'GET' ($sbUrl.TrimEnd('/') + $q) (Sb-Headers $key)
  if (-not $r.ok) { return -1 }
  return @($r.data | Where-Object { $_ -and $_.status }).Count
}

# ----------------------------------------------------------------------------------------------------- Cloudflare (duong ham + ten mien)
function Cf-Call([string]$method, [string]$path, [string]$tok, $body = $null) {
  $r = Invoke-Api $method ($CFAPI + $path) @{ Authorization = ('Bearer ' + $tok) } $body
  if ($r.ok -and $r.data -and ($r.data.success -eq $false)) { $r.ok = $false; $r.err = Hide-Secret ('Cloudflare: ' + (($r.data.errors | ForEach-Object { "" + $_.message }) -join '; ')) }
  return $r
}

function Set-CfDns([string]$tok, [string]$zone, [string]$name, [string]$target) {
  # CNAME <name> -> <target> (may cam). Da dung thi thoi. Tra '' = xong, khac '' = loi.
  $g = Cf-Call 'GET' ('/zones/' + $zone + '/dns_records?name=' + [uri]::EscapeDataString($name)) $tok
  if (-not $g.ok) { return $g.err }
  $body = @{ type = 'CNAME'; name = $name; content = $target; proxied = $true; ttl = 1 }
  $cur = @($g.data.result)
  if ($cur.Count -and $cur[0]) {
    $c0 = $cur[0]
    if ((("" + $c0.type) -eq 'CNAME') -and ((("" + $c0.content).TrimEnd('.')) -eq $target) -and ($c0.proxied -eq $true)) { return '' }
    $u = Cf-Call 'PUT' ('/zones/' + $zone + '/dns_records/' + $c0.id) $tok $body
    if ($u.ok) { return '' } else { return $u.err }
  }
  $p = Cf-Call 'POST' ('/zones/' + $zone + '/dns_records') $tok $body
  if ($p.ok) { return '' } else { return $p.err }
}

function New-CfTunnel([string]$tok, [string]$domain, [string]$sub, [string]$ssub) {
  # Tao (hoac dung lai) duong ham ten $sub, dat 2 dia chi $sub.$domain -> 8010 va $ssub.$domain -> 8020, tao 2 ban ghi CNAME.
  # Tra @{ ok; token; id; err } - token = ma chay cloudflared (bi mat, da dua vao danh sach che).
  $z = Cf-Call 'GET' ('/zones?name=' + [uri]::EscapeDataString($domain)) $tok
  if (-not $z.ok) { return @{ ok = $false; err = ('doc ten mien: ' + $z.err) } }
  $zr = @($z.data.result)
  if (-not $zr.Count -or -not $zr[0]) { return @{ ok = $false; err = ('ma Cloudflare khong thay ten mien ' + $domain) } }
  $zone = "" + $zr[0].id; $acc = "" + $zr[0].account.id
  if (-not $zone -or -not $acc) { return @{ ok = $false; err = 'khong doc duoc ma tai khoan Cloudflare' } }
  $l = Cf-Call 'GET' ('/accounts/' + $acc + '/cfd_tunnel?name=' + [uri]::EscapeDataString($sub) + '&is_deleted=false') $tok
  if (-not $l.ok) { return @{ ok = $false; err = ('doc duong ham (ma can quyen Account > Cloudflare Tunnel > Edit): ' + $l.err) } }
  $id = ''
  $lr = @($l.data.result | Where-Object { $_ -and (("" + $_.name) -eq $sub) })
  if ($lr.Count) { $id = "" + $lr[0].id }
  if (-not $id) {
    $c = Cf-Call 'POST' ('/accounts/' + $acc + '/cfd_tunnel') $tok @{ name = $sub; config_src = 'cloudflare' }
    if (-not $c.ok) { return @{ ok = $false; err = ('tao duong ham: ' + $c.err) } }
    $id = "" + $c.data.result.id
  }
  if (-not $id) { return @{ ok = $false; err = 'Cloudflare khong tra ma duong ham' } }
  $ing = @(@{ hostname = ($sub + '.' + $domain); service = 'http://localhost:8010' }, @{ hostname = ($ssub + '.' + $domain); service = 'http://localhost:8020' }, @{ service = 'http_status:404' })
  $u = Cf-Call 'PUT' ('/accounts/' + $acc + '/cfd_tunnel/' + $id + '/configurations') $tok @{ config = @{ ingress = $ing } }
  if (-not $u.ok) { return @{ ok = $false; err = ('dat dia chi cho duong ham: ' + $u.err) } }
  foreach ($h in ($sub + '.' + $domain), ($ssub + '.' + $domain)) {
    $e = Set-CfDns $tok $zone $h ($id + '.cfargotunnel.com')
    if ($e) { return @{ ok = $false; err = ('ban ghi ten mien ' + $h + ' (ma can quyen Zone > DNS > Edit): ' + $e) } }
  }
  $t = Cf-Call 'GET' ('/accounts/' + $acc + '/cfd_tunnel/' + $id + '/token') $tok
  if (-not $t.ok) { return @{ ok = $false; err = ('lay ma chay duong ham: ' + $t.err) } }
  $tt = "" + $t.data.result
  if ($tt.Length -lt 40) { return @{ ok = $false; err = 'ma chay duong ham khong hop le' } }
  [void]$SECRETS.Add($tt)
  return @{ ok = $true; token = $tt; id = $id; err = '' }
}

function Get-Cloudflared {
  $c = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
  if (-not $c) { $c = 'C:\Program Files (x86)\cloudflared\cloudflared.exe' }
  if (Test-Path -LiteralPath $c) { return $c }
  return ''
}

function Test-CfService { return [bool]((& sc.exe query cloudflared 2>$null | Out-String) -match 'RUNNING') }

function Install-CfService([string]$token) {
  $cf = Get-Cloudflared
  if (-not $cf) { return 'chua co cloudflared.exe' }
  if ((& sc.exe query cloudflared 2>$null | Out-String) -match 'SERVICE_NAME') { & $cf service uninstall 2>$null | Out-Null; Start-Sleep 2 }
  & $cf service install $token 2>$null | Out-Null
  Start-Sleep 4
  if (-not (Test-CfService)) { & sc.exe start cloudflared 2>$null | Out-Null; Start-Sleep 5 }
  if (Test-CfService) { return '' }
  return 'dich vu cloudflared chua chay'
}

# ----------------------------------------------------------------------------------------------------- gia lap
function Find-Mumu {
  $cand = @('C:\Program Files\Netease\MuMuPlayer', 'D:\Program Files\Netease\MuMuPlayer', 'C:\Program Files\Netease\MuMuPlayer-12.0', 'D:\Program Files\Netease\MuMuPlayer-12.0',
            'C:\Program Files\Netease\MuMuPlayerGlobal-12.0', 'C:\Program Files\MuMuPlayerGlobal-12.0', 'D:\Program Files\MuMuPlayerGlobal-12.0')
  try {
    $cand += @(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*', 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
               Where-Object { "$($_.DisplayName)" -match 'mumu' } | ForEach-Object { "$($_.InstallLocation)".TrimEnd('\') })
  } catch {}
  foreach ($d in $cand) {
    if (-not $d) { continue }
    foreach ($r in 'nx_main\mumu-cli.exe', 'nx_main\MuMuManager.exe', 'shell\MuMuManager.exe') { if (Test-Path -LiteralPath (Join-Path $d $r)) { return $d } }
  }
  return ''
}

function Get-MumuCli([string]$d) {
  foreach ($r in 'nx_main\mumu-cli.exe', 'nx_main\MuMuManager.exe', 'shell\MuMuManager.exe') { if ($d -and (Test-Path -LiteralPath (Join-Path $d $r))) { return (Join-Path $d $r) } }
  return ''
}

function Find-Ld {
  foreach ($d in 'C:\LDPlayer\LDPlayer9', 'D:\LDPlayer\LDPlayer9', 'C:\Program Files\LDPlayer\LDPlayer9', 'C:\leidian\LDPlayer9', 'D:\leidian\LDPlayer9') {
    if (Test-Path -LiteralPath (Join-Path $d 'ldconsole.exe')) { return $d }
  }
  return ''
}

function Find-Emu {
  # @{ kind = 'ld' | 'mumu' | ''; dir }  (co ca hai -> LDPlayer, giong setup.ps1)
  $l = Find-Ld; if ($l) { return @{ kind = 'ld'; dir = $l } }
  $m = Find-Mumu; if ($m) { return @{ kind = 'mumu'; dir = $m } }
  return @{ kind = ''; dir = '' }
}

function Stop-EmuUi {
  # CHI goi ngay sau khi vua cai gia lap tren may MOI (chua co may khach nao): dong cua so gia lap de setup.ps1 thay duoc adb.
  foreach ($n in 'MuMuNxMain', 'MuMuNxDevice', 'MuMuPlayer', 'MuMuMultiPlayer', 'MuMuVMMHeadless', 'dnplayer', 'dnmultiplayer', 'dnmultiplayerex', 'Ld9BoxHeadless') {
    Get-Process -Name $n -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  }
  Get-Process adb -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

function Get-SetupKind([string]$exe) {
  # Doan cong cu da dong goi bo cai (de biet tham so cai im lang): 'inno' (Inno Setup) | 'nsis' (Nullsoft) | '' (khong ro). Chi doc 8 MB dau tep.
  try {
    $fs = [IO.File]::OpenRead($exe)
    try {
      $len = [int][Math]::Min($fs.Length, 8MB)
      $buf = New-Object byte[] $len
      $got = 0
      while ($got -lt $len) { $r = $fs.Read($buf, $got, $len - $got); if ($r -le 0) { break }; $got += $r }
    } finally { $fs.Close() }
    $t = [Text.Encoding]::GetEncoding(28591).GetString($buf, 0, $got)
    if ($t.Contains('JR.Inno.Setup') -or $t.Contains('Inno Setup Setup Data')) { return 'inno' }
    if ($t.Contains('Nullsoft.NSIS') -or $t.Contains('NullsoftInst')) { return 'nsis' }
  } catch {}
  return ''
}

function Get-SetupArgs([string]$kind, [string]$exe) {
  # Tham so cai im lang: theo kieu dong goi doan duoc (ban dong goi lai cung dung duoc); khong ro thi theo bo cai chinh hang cua tung gia lap.
  $sk = Get-SetupKind $exe
  if ($sk -eq 'inno') { return '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-' }
  if ($sk -eq 'nsis') { return '/S' }
  if ($kind -eq 'ld') { return '-silence -language=en -path="C:\LDPlayer\LDPlayer9\"' }
  return '/S'
}

function Install-Emu([string]$kind, [string]$exe) {
  # Chay bo cai kem trong ISO kieu im lang. Bo cai khong ho tro im lang thi cua so bo cai hien len -> nguoi cai bam; script tu lam tiep khi thay gia lap.
  $name = 'MuMu Player'
  if ($kind -eq 'ld') { $name = 'LDPlayer 9' }
  $silent = Get-SetupArgs $kind $exe
  Say ('   Dang cai ' + $name + ' (3 den 15 phut, dung tat may).') 'White'
  Say ('   >>> Neu CUA SO BO CAI hien len: bam Cai dat / Install (de thu muc mac dinh). Khong hien gi thi cu cho.') 'Yellow'
  $p = $null; $again = $false; $gone = $null; $cnt = 0
  try { $p = Start-Process -FilePath $exe -ArgumentList $silent -PassThru -ErrorAction Stop } catch { Say ('   (!) khong chay duoc bo cai: ' + $_.Exception.Message) 'Yellow' }
  while (-not (Find-Emu).kind) {
    if ((-not $p) -or $p.HasExited) {
      if (-not $gone) { $gone = Get-Date }
      if ((-not $again) -and (((Get-Date) - $gone).TotalSeconds -gt 90)) {
        $again = $true
        Say ('   Bo cai da dong ma chua thay ' + $name + ' -> mo lai bo cai binh thuong: BAM CAI tren man hinh.') 'Yellow'
        try { $p = Start-Process -FilePath $exe -PassThru -ErrorAction Stop; $gone = $null } catch { Say ('   (!) khong mo duoc bo cai: ' + $_.Exception.Message) 'Yellow' }
      }
    }
    Start-Sleep 5; $cnt++
    if (($cnt % 60) -eq 0) { Say ('   ... van cho cai ' + $name + ' (cua so bo cai hien thi bam cai; hoac tu cai tay - script tu lam tiep)') 'Yellow' }
  }
  Say ('   Da thay ' + $name + ' - cho bo cai lam not (toi da 20 phut) roi dong cua so gia lap...') 'DarkGray'
  $t1 = Get-Date
  while ($p -and (-not $p.HasExited) -and (((Get-Date) - $t1).TotalMinutes -lt 20)) { Start-Sleep 5 }
  Start-Sleep $SETTLE                                         # gia lap vua cai tu mo lan dau (tao may goc) -> de no lam xong
  Stop-EmuUi
  Start-Sleep 3
  Say ('   OK - da cai ' + $name + ': ' + (Find-Emu).dir) 'Green'
}

function Get-Engine {
  try {
    $o = & $PY (Join-Path $B 'phonectl.py') engine 2>$null | Select-Object -Last 1
    return (("" + $o) | ConvertFrom-Json)
  } catch { return $null }
}

function Get-VmRows {
  $rows = @()
  foreach ($ln in @(& $PY (Join-Path $B 'phonectl.py') vmlist 2>$null)) {
    if (("" + $ln) -match '^(\d+),([^,]+),') { $rows += [pscustomobject]@{ Idx = [int]$Matches[1]; Name = $Matches[2] } }
  }
  return $rows
}

function Add-Templates([string]$mumuDir) {
  # May mau MuMu con thieu: (1) nhap tep tpl_aNN.mumudata kem trong ISO  (2) phonectl mktpl NN. Khong duoc thi BAO va di tiep (may chu van ban cac ban da co).
  $e = Get-Engine
  $miss = @(); if ($e) { $miss = @($e.missing_tpl | Where-Object { $_ }) }
  if (-not $miss.Count) { return @() }
  $cli = Get-MumuCli $mumuDir
  foreach ($t in $miss) {
    $v = ("" + $t) -replace '\D', ''
    $f = Find-Payload ($t + '.mumudata')
    if ($cli -and $f) {
      Say ('   Nhap may mau ' + $t + ' tu tep kem trong ISO (vai phut)...') 'White'
      $before = @(Get-VmRows | ForEach-Object { $_.Idx })
      try { $pp = Start-Process -FilePath $cli -ArgumentList ('import --path "' + $f + '"') -PassThru -WindowStyle Hidden -ErrorAction Stop; [void]$pp.WaitForExit(1500000) } catch { Say ('   (!) nhap may mau loi: ' + $_.Exception.Message) 'Yellow' }
      $new = @(Get-VmRows | Where-Object { $before -notcontains $_.Idx })
      if ($new.Count -eq 1) {
        try { $pr = Start-Process -FilePath $cli -ArgumentList ('rename --vmindex ' + $new[0].Idx + ' --name ' + $t) -PassThru -WindowStyle Hidden -ErrorAction Stop; [void]$pr.WaitForExit(120000) } catch {}
        try { $ps = Start-Process -FilePath $cli -ArgumentList ('control --vmindex ' + $new[0].Idx + ' shutdown') -PassThru -WindowStyle Hidden -ErrorAction Stop; [void]$ps.WaitForExit(120000) } catch {}
      }
    }
    $e2 = Get-Engine
    if ($e2 -and (@($e2.missing_tpl) -contains $t)) {
      Say ('   Thu tao may mau ' + $t + ' bang lenh (phonectl mktpl ' + $v + ')...') 'White'
      & $PY -u (Join-Path $B 'phonectl.py') mktpl $v 2>&1 | ForEach-Object { Say ('      ' + $_) 'DarkGray' }
    }
  }
  $e3 = Get-Engine
  if ($e3) { return @($e3.missing_tpl | Where-Object { $_ }) }
  return $miss
}

# ----------------------------------------------------------------------------------------------------- bang CloudBlue + dich vu
function Get-PyProcs { return @(Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue | ForEach-Object { "$($_.CommandLine)" }) }

function Test-Services {
  $pr = Get-PyProcs
  $c = @($pr | Where-Object { $_ -match 'cloudphoned\.py' }).Count
  $s = @($pr | Where-Object { $_ -match 'bluestream\.py' -and $_ -notmatch '--(netcheck|upnp|captest|selftest|webdirect)' }).Count
  return (($c -gt 0) -and ($s -gt 0))
}

function Register-Panel {
  # Giong nut "Tu dang nhap + tu chay" cua bang (phan tac vu): bang CloudBlue tu mo quyen Admin khi dang nhap, may khong ngu.
  $who = $env:USERDOMAIN + '\' + $env:USERNAME
  $a = New-ScheduledTaskAction -Execute $PYW -Argument ('"' + (Join-Path $B 'panel.py') + '" --auto') -WorkingDirectory $B
  $t = New-ScheduledTaskTrigger -AtLogOn -User $who
  $pr = New-ScheduledTaskPrincipal -UserId $who -LogonType Interactive -RunLevel Highest
  $st = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -Priority 4
  Register-ScheduledTask -TaskName 'BlueRoblox' -Action $a -Trigger $t -Principal $pr -Settings $st -Force | Out-Null
  Remove-Item "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp\BlueRoblox.lnk" -ErrorAction SilentlyContinue
  New-Item 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\PasswordLess\Device' -Force | Out-Null
  Set-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\PasswordLess\Device' DevicePasswordLessBuildVersion 0 -Type DWord
  & powercfg.exe /change standby-timeout-ac 0 | Out-Null; & powercfg.exe /change hibernate-timeout-ac 0 | Out-Null; & powercfg.exe /change monitor-timeout-ac 0 | Out-Null
  return [bool](Get-ScheduledTask -TaskName 'BlueRoblox' -ErrorAction SilentlyContinue)
}

function Optimize-Windows([string]$emuDir) {
  & powercfg.exe -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61 2>$null | Out-Null
  $u = (& powercfg.exe -list | Select-String 'Ultimate' | Select-Object -First 1)
  if ($u) { & powercfg.exe -setactive ((("" + $u) -split '\s+')[3]) | Out-Null } else { & powercfg.exe -setactive SCHEME_MIN | Out-Null }
  & powercfg.exe /hibernate off 2>$null | Out-Null
  foreach ($d in @($B, $emuDir)) { if ($d -and (Test-Path -LiteralPath $d)) { Add-MpPreference -ExclusionPath $d -ErrorAction SilentlyContinue } }
  foreach ($x in 'adb.exe', 'node.exe', 'MuMuVMMHeadless.exe', 'MuMuNxDevice.exe', 'dnplayer.exe', 'Ld9BoxHeadless.exe') { Add-MpPreference -ExclusionProcess $x -ErrorAction SilentlyContinue }
  & reg.exe add HKCU\System\GameConfigStore /v GameDVR_Enabled /t REG_DWORD /d 0 /f | Out-Null
  & reg.exe add HKLM\SOFTWARE\Policies\Microsoft\Windows\GameDVR /v AllowGameDVR /t REG_DWORD /d 0 /f | Out-Null
}

function Get-PanelProcs {
  return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { "$($_.Name)" -match '^pythonw?\.exe$' -and "$($_.CommandLine)" -match 'panel\.py' })
}

function Start-Panel([switch]$Restart) {
  # Dich vu DANG chay (may chu dang phuc vu) -> khong dung toi. Bang dang mo -> chi dong + mo lai khi -Restart (de bang doc khoa moi + tu bat A->Z).
  if (Test-Services) { return }
  $pp = Get-PanelProcs
  if ($pp.Count -and -not $Restart) { return }
  $pp | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  if ($pp.Count) { Start-Sleep 2 }
  Start-Process -FilePath $PYW -ArgumentList ('"' + (Join-Path $B 'panel.py') + '" --auto') -WorkingDirectory $B
}

function Restart-Now($st, [string]$why) {
  $rb = 0; try { $rb = [int]$st.reboots } catch {}
  if ($rb -ge $MAX_REBOOT) { Say ('!! Da tu khoi dong lai ' + $rb + ' lan ma van can khoi dong lai (' + $why + ') - xem C:\blue\logs\viec-lam-tay.txt') 'Red'; return $false }
  $st.reboots = $rb + 1; Save-State $st
  if ($env:CB_ISO_TEST -eq '1') { return $true }                # kiem thu: khong khoi dong lai may that
  Say ('>>> Tu KHOI DONG LAI sau 20 giay (' + $why + ') - bat len script tu lam tiep.') 'Yellow'
  & shutdown.exe /r /t 20 /c "CloudBlue: cai may chu - tu khoi dong lai, bat len tu lam tiep" | Out-Null
  return $true
}

function Set-AutoStart([switch]$Remove) {
  # Tu chay lai script nay moi lan co nguoi dang nhap, cho toi khi cai xong (-Remove = go het khi xong).
  # 2 duong, KHONG gan voi ten may / ten tai khoan (may doi ten giua chung thi tac vu gan kieu "TENMAY\taikhoan" khong chay lai):
  #   khoa Run cua may  +  tac vu theo NHOM Administrators. Goi lai nhieu lan khong sao.
  $runKey = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run'
  $lnkOld = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\StartUp\CloudBlue-cai-may-chu.lnk'
  if ($Remove) {
    try { Remove-ItemProperty -Path $runKey -Name 'CloudBlueMayChu' -ErrorAction SilentlyContinue } catch {}
    try { Unregister-ScheduledTask -TaskName $TASK -Confirm:$false -ErrorAction SilentlyContinue } catch {}
    Remove-Item -LiteralPath $lnkOld -Force -ErrorAction SilentlyContinue
    return 0
  }
  $selfPath = Join-Path $ISO 'may-chu-iso.ps1'
  if ((-not (Test-Path -LiteralPath $selfPath)) -and $PSCommandPath) { $selfPath = $PSCommandPath }
  $argLine = '-NoProfile -ExecutionPolicy Bypass -File "' + $selfPath + '"'
  $ways = 0
  try {
    New-ItemProperty -Path $runKey -Name 'CloudBlueMayChu' -Value ('powershell.exe ' + $argLine) -PropertyType String -Force -ErrorAction Stop | Out-Null
    $ways++
  } catch {}
  try {
    $a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argLine -WorkingDirectory $B
    $t = New-ScheduledTaskTrigger -AtLogOn
    $st = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
    $made = $false
    foreach ($grp in @('S-1-5-32-544', 'BUILTIN\Administrators')) {
      if ($made) { break }
      try {
        $pr = New-ScheduledTaskPrincipal -GroupId $grp -RunLevel Highest
        Register-ScheduledTask -TaskName $TASK -Action $a -Trigger $t -Principal $pr -Settings $st -Force -ErrorAction Stop | Out-Null
        $made = $true
      } catch { $made = $false }
    }
    if ($made) { $ways++ }
  } catch {}
  Remove-Item -LiteralPath $lnkOld -Force -ErrorAction SilentlyContinue
  return $ways
}

function Update-Self([string]$self) {
  # Lay ban moi nhat cua script nay tren GitHub (sua loi ma khong phai tao lai ISO). Tra ve true khi da thay tep (can chay lai).
  if ($env:CB_ISO_SELF -eq '1') { return $false }
  $new = Join-Path $ISO 'may-chu-iso.moi.ps1'
  if (-not (Get-Url ($RAWB + '/' + $SELF_REL + '?t=' + (Get-Random)) $new)) { return $false }
  if (-not ((Test-Marker $new 'cloudblue-may-chu-iso' 8000) -and (Test-Ps1 $new))) { Remove-Item -LiteralPath $new -Force -ErrorAction SilentlyContinue; return $false }
  $same = $false
  try { $same = ((Get-FileHash -Algorithm SHA256 -LiteralPath $new).Hash -eq (Get-FileHash -Algorithm SHA256 -LiteralPath $self).Hash) } catch {}
  if ($same) { Remove-Item -LiteralPath $new -Force -ErrorAction SilentlyContinue; return $false }
  try { Copy-Item -LiteralPath $new -Destination $self -Force -ErrorAction Stop; Remove-Item -LiteralPath $new -Force -ErrorAction SilentlyContinue; return $true } catch { return $false }
}

function Write-MumuConf([int]$n, [string]$domain, [string]$sbUrl, [string]$mu) {
  # setup.ps1 khong nhan ra MuMu (ban MuMu moi dat tep lenh cho khac) -> tu ghi cau hinh nhu may-moi.ps1
  $port = 8188 + $n
  @('# CloudBlue - cau hinh may chu (KHONG dua file nay len GitHub)', ('SUPABASE_URL=' + $sbUrl), 'SUPABASE_SERVICE_KEY=DAN_SERVICE_ROLE_KEY_VAO_DAY',
    ('PUBLIC_BASE=https://phone' + $n + '.' + $domain), ('STREAM_WS=wss://stream' + $n + '.' + $domain + '/v2/stream'), ('CPAPI_ORIGINS=https://' + $domain + ',https://www.' + $domain),
    ('NOTIFY_URL=https://' + $domain + '/api/notify-admin'), ('NODE_ID=win' + $n), 'PRIMARY=0', 'LIMIT_PCT=90', 'RAM_OVER=1', 'CPU_OVER=1.8', 'WIN_VCPU_OVER=1.8', 'WIN_RAM_RESERVE=3',
    'RAM_BUSY_PCT=98', 'EMU=mumu', 'ANDROIDS=12,15', 'CAPTURE=scrcpy', 'MEMU_MAX_RAM=16', 'MEMU_MAX_CPU=32', 'MEMU_RENDER=1', 'MEMU_GMEM_OPT=1', 'POOL_SIZE=0',
    ('STREAM_PORT=' + $port), ('MUMU_DIR=' + $mu)) | Set-Content -Encoding utf8 (Join-Path $B 'cloudphone.conf')
}

# ===================================================================================================== CHAY
# Ma tra ve ($script:RC): 0 = XONG | 2 = chua xong, thu lai tu dau (vong lap ben duoi) | 3 = dang khoi dong lai | 9 = da tai ban moi cua script, chay lai
function Main {
  $script:RC = 1
  New-Item -ItemType Directory -Force $B, (Join-Path $B 'logs'), $ISO | Out-Null
  Set-Location $B
  Say ''
  Say ('#################### CloudBlue - TU CAI MAY CHU CLOUD PHONE (ban ' + $MC_VER + ') ####################') 'Cyan'
  Say '   Dung tat may / dong cua so nay. May co the tu khoi dong lai vai lan - bat len tu lam tiep.' 'DarkGray'

  # cau hinh (bo tao ISO ghi) - chep 1 lan tu thu muc bo cai sang C:\blue\iso
  foreach ($f in @(Get-ChildItem -LiteralPath $SRC -File -ErrorAction SilentlyContinue | Where-Object { $_.Length -lt 20MB })) {
    $dst = Join-Path $ISO $f.Name
    if (-not (Test-Path -LiteralPath $dst)) { try { Copy-Item -LiteralPath $f.FullName -Destination $dst -Force } catch {} }
  }
  $cfp = $Conf
  if (-not $cfp) { $cfp = Join-Path $ISO 'may-chu.conf' }
  $cfg = Read-KV $cfp
  foreach ($k in 'SUPABASE_SERVICE_KEY', 'CF_API_TOKEN', 'CF_DNS_TOKEN') { if ($cfg[$k]) { [void]$SECRETS.Add("" + $cfg[$k]) } }
  $domain = ("" + $cfg['DOMAIN']).Trim().ToLower(); if (-not $domain) { $domain = 'cloudblue.vn' }
  $sbUrl = ("" + $cfg['SUPABASE_URL']).Trim().TrimEnd('/'); if (-not $sbUrl) { $sbUrl = 'https://nprftgodswlpzomcttal.supabase.co' }
  $sbKey = ("" + $cfg['SUPABASE_SERVICE_KEY']).Trim()
  $cfTok = ("" + $cfg['CF_API_TOKEN']).Trim()
  $dnsTok = ("" + $cfg['CF_DNS_TOKEN']).Trim(); if (-not $dnsTok) { $dnsTok = $cfTok }
  $st = Get-State
  $confPath = Join-Path $B 'cloudphone.conf'

  # ------------------------------------------------------------------ 1. bo cai Windows lam xong + mang
  Step '1/11 Cho bo cai Windows lam xong + cho mang'
  $t0 = Get-Date
  while ((Test-Path (Join-Path $PROV 'firstlogon.start')) -and (-not (Test-Path (Join-Path $PROV 'firstlogon.done'))) -and (((Get-Date) - $t0).TotalMinutes -lt 45)) { Start-Sleep 10 }
  $fd = Join-Path $PROV 'firstlogon.done'
  if (Test-Path -LiteralPath $fd) {                                       # bo cai Windows vua xong co the hen khoi dong lai sau 20 giay -> de no khoi dong lai truoc
    $age = ((Get-Date) - (Get-Item -LiteralPath $fd).LastWriteTime).TotalSeconds
    if (($age -ge 0) -and ($age -lt 100)) { Say '   Bo cai Windows vua xong - cho 1-2 phut (may co the tu khoi dong lai 1 lan)...' 'DarkGray'; Start-Sleep ([int](105 - $age)) }
  }
  $cnt = 0
  while (-not (Test-Net)) {
    if (($cnt % 12) -eq 0) { Say '   Chua co mang - cam day mang LAN (kiem driver card mang). Script tu lam tiep khi co mang.' 'Yellow' }
    $cnt++; Start-Sleep 10
  }
  Say '   OK - da co mang' 'Green'
  if (-not (Test-Path -LiteralPath (Join-Path $env:SystemRoot 'System32\curl.exe'))) { Say '   (Windows ban cu khong co curl.exe - tai bang PowerShell, khong sao)' 'DarkGray' }
  if ($PSCommandPath -and (Update-Self $PSCommandPath)) {
    Say '   Co ban moi cua script cai may chu tren GitHub -> chay ban moi.' 'DarkGray'
    $script:RC = 9; return
  }

  # ------------------------------------------------------------------ 2. ten may chu
  Step '2/11 Ten may chu'
  $Num = 0
  $cur = (Read-KV $confPath)['NODE_ID']
  if ($cur) { $Num = Get-NodeNum $cur; if ($Num) { Say ('   May nay da la win' + $Num + ' (cloudphone.conf)') 'Green' } }
  if (-not $Num -and $st.n) { $Num = [int]$st.n }
  if (-not $Num) {
    $want = Get-NodeNum ("" + $cfg['NODE'])
    $from = 'cau hinh ISO'
    if (-not $want) { $want = Get-SeedNum (Join-Path $ISO 'seed.json'); $from = 'ten go luc cai Windows' }
    if (-not $want) { $want = Get-SeedNum (Join-Path $CBPC 'seed.json') }
    $warned = $false
    while (-not $Num) {
      $rows = @(); $rowsOk = $false
      if ($sbKey.Length -ge 30) {
        $nr = Get-NodeRows $sbUrl $sbKey
        if ($nr.ok) { $rows = $nr.rows; $rowsOk = $true }
        elseif (-not $warned) {
          $warned = $true
          if ($nr.code -eq 401 -or $nr.code -eq 403) { Say '   (!) Khoa Supabase trong ISO KHONG con dung duoc - se phai dan khoa moi trong bang CloudBlue (nut 2).' 'Red' }
          else { Say ('   (chua doc duoc danh sach may chu tren web: ' + $nr.err + ')') 'DarkGray' }
        }
      }
      if ($want -ge 2 -and $want -le 99) {
        $busy = 0
        if ($rowsOk) { $busy = Get-NodePhones $sbUrl $sbKey $want }
        if ($rowsOk -and (Test-NodeLive $rows $want)) { Say ('   (!) win' + $want + ' DANG CHAY o 1 may chu khac (vua bao ve web) - khong dung trung ten duoc.') 'Red' }
        elseif ($busy -gt 0) {
          Say ('   (!) Web con ' + $busy + ' may khach dang thue o win' + $want + ' - KHONG dung ten nay cho may moi cai (may khach do se mat).') 'Red'
          Say ('       Muon cai lai DUNG may chu win' + $want + ': chuyen / huy het may khach cua no tren web truoc.') 'Yellow'
        }
        elseif ($busy -lt 0) { Say ('   (chua kiem duoc may khach cua win' + $want + ' tren web - thu lai)') 'DarkGray'; Start-Sleep $POLL; continue }
        else { $Num = $want; Say ('   Ten may chu: win' + $Num + ' (' + $from + ')') 'Green'; break }
      } elseif ($want -eq 1) { Say '   (!) win1 la may chu CHINH - may cai tu ISO dung so tu 2 tro len.' 'Yellow' }
      $sug = 0
      if ($rowsOk) { $sug = Get-FreeNum $rows }
      if ($sug) {
        Say ('   Go SO MAY CHU roi Enter (vi du 9 = win9). Enter trong / cho ' + [int]($WAIT_NAME / 60) + ' phut = lay so ke tiep: ' + $sug) 'White'
        $ans = Read-LineWait '   So may chu' $WAIT_NAME
      } else {
        Say '   Go SO MAY CHU roi Enter (vi du 9 = win9).' 'White'
        $ans = Read-LineWait '   So may chu' 600
      }
      $from = 'vua go'
      if (($null -eq $ans) -or (-not ("" + $ans).Trim())) {
        if ($sug) { $want = $sug; $from = 'so ke tiep - tu chon' } else { $want = 0; Start-Sleep $POLL }
      } else {
        $want = Get-NodeNum $ans
        if (-not $want) { Say '   (!) Chi go so tu 2 den 99 (hoac win9).' 'Yellow' }
      }
    }
    $st.n = $Num; Save-State $st
  }
  $sub = 'phone' + $Num; $ssub = 'stream' + $Num; $port = 8188 + $Num
  Say ('   win' + $Num + '  |  ' + $sub + '.' + $domain + '  |  ' + $ssub + '.' + $domain + '  |  cong phat hinh TCP ' + $port) 'White'

  # ------------------------------------------------------------------ 3. gia lap
  Step '3/11 Gia lap Android'
  $em = Find-Emu
  if (-not $em.kind) {
    $ek = ("" + $cfg['EMU']).Trim().ToLower(); if ($ek -ne 'ld') { $ek = 'mumu' }
    $exe = ''
    foreach ($k in @($ek, 'mumu', 'ld')) { $c = Find-Payload ($k + '-setup.exe'); if ((-not $exe) -and $c) { $exe = $c; $ek = $k } }
    if ($exe) { Install-Emu $ek $exe; $st.emu_new = 1; Save-State $st }
    else {
      Say '   ISO nay KHONG kem bo cai gia lap.' 'Yellow'
      Say '   >>> Cai MuMu Player (mumuplayer.com) hoac LDPlayer 9 (ldplayer.net) - de thu muc mac dinh. Cai xong script TU LAM TIEP.' 'Yellow'
      $cnt = 0
      while (-not (Find-Emu).kind) { Start-Sleep 15; $cnt++; if (($cnt % 20) -eq 0) { Say '   ... van cho cai gia lap' 'Yellow' } }
      Say '   Da thay gia lap. DONG HAN gia lap (bieu tuong goc phai man hinh > Exit) - cho 60 giay roi lam tiep.' 'Yellow'
      Start-Sleep 60
    }
    $em = Find-Emu
  }
  $emuName = 'MuMu'; if ($em.kind -eq 'ld') { $emuName = 'LDPlayer 9' }
  Say ('   OK - ' + $emuName + ': ' + $em.dir) 'Green'

  # ------------------------------------------------------------------ 4. setup.ps1
  Step '4/11 Cai dat CloudBlue (setup.ps1 - lan dau 10-15 phut)'
  $sp = Join-Path $B 'setup.ps1'
  if (-not ((Get-Url ($RAWB + '/windows/setup.ps1?t=' + (Get-Random)) $sp) -and ((Get-Item -LiteralPath $sp).Length -gt 5000))) {
    Say '!! Chua tai duoc setup.ps1 tu GitHub (mang?) - 2 phut nua thu lai.' 'Red'; Start-Sleep 120; $script:RC = 2; return
  }
  for ($try = 1; $try -le 2; $try++) {
    try { & $sp -Node ('win' + $Num) -PubHost ($sub + '.' + $domain) *>&1 | ForEach-Object { Say ('   ' + $_) 'DarkGray' } } catch { Say ('   (!) setup.ps1 dung giua chung: ' + $_.Exception.Message) 'Yellow' }
    Set-Location $B
    if (Test-Path -LiteralPath $confPath) { break }
    if (($try -eq 1) -and ($em.kind -eq 'mumu') -and (Test-Path -LiteralPath (Join-Path $B 'platform-tools\adb.exe'))) {
      Say '   Bo cai chua nhan MuMu -> tu tao cau hinh roi chay lai.' 'Yellow'
      Write-MumuConf $Num $domain $sbUrl $em.dir
    }
  }
  $todo = @(Get-Content (Join-Path $B 'logs\viec-lam-tay.txt') -ErrorAction SilentlyContinue)
  if ([regex]::IsMatch(($todo -join "`n"), 'KHOI DONG LAI')) { if (Restart-Now $st 'Windows vua tat Hyper-V / can khoi dong lai') { $script:RC = 3; return } }
  if ((-not (Test-Path -LiteralPath $confPath)) -or (-not (Test-Path -LiteralPath $PY))) {
    Say '!! Cai dat chua xong (xem cac dong [!] o tren + C:\blue\logs\viec-lam-tay.txt). 3 phut nua script thu lai.' 'Red'
    Start-Sleep 180; $script:RC = 2; return
  }

  # ------------------------------------------------------------------ 5. khoa Supabase
  Step '5/11 Khoa Supabase'
  $have = "" + (Read-KV $confPath)['SUPABASE_SERVICE_KEY']
  if ((($have.Length -lt 30) -or ($have -match 'DAN_')) -and ($sbKey.Length -ge 30)) { Set-KV $confPath 'SUPABASE_SERVICE_KEY' $sbKey; $have = $sbKey }
  $keyOk = $false
  if (($have.Length -ge 30) -and ($have -notmatch 'DAN_')) {
    [void]$SECRETS.Add($have)
    $kr = Get-NodeRows $sbUrl $have
    if ($kr.ok) { $keyOk = $true; Say '   OK - khoa Supabase dung duoc' 'Green' }
    elseif ($kr.code -eq 401 -or $kr.code -eq 403) { Say '   (!) Khoa Supabase KHONG con dung duoc -> trong bang CloudBlue bam "2 Dan khoa Supabase" (khoa service_role hien tai - KHONG gui ai).' 'Red' }
    else { $keyOk = $true; Say ('   (chua thu duoc khoa: ' + $kr.err + ' - di tiep)') 'DarkGray' }
  } else { Say '   (!) ISO khong kem khoa Supabase -> trong bang CloudBlue bam "2 Dan khoa Supabase" (KHONG gui ai).' 'Yellow' }
  if ($dnsTok -and (-not (Read-KV $confPath)['CF_DNS_TOKEN'])) { Set-KV $confPath 'CF_DNS_TOKEN' $dnsTok }
  if ((("" + $cfg['LE_AGREE']) -eq '1') -and ((Read-KV $confPath)['LE_AGREE'] -ne '1')) { Set-KV $confPath 'LE_AGREE' '1' }

  # ------------------------------------------------------------------ 6. may mau MuMu
  $missTpl = @()
  if ($em.kind -eq 'mumu') {
    Step '6/11 May mau MuMu (tpl_a12 / tpl_a15)'
    $missTpl = @(Add-Templates $em.dir)
    if ($missTpl.Count) {
      Say ('   (!) Con thieu may mau: ' + ($missTpl -join ', ') + ' -> may chu VAN chay va ban cac ban Android da co.') 'Yellow'
      Say '       Tao sau (2 phut): MuMu > Multi-instance > tao may dung ban Android > doi ten thanh ten may mau > de TAT. 2 phut sau web tu ban them.' 'Yellow'
    } else { Say '   OK - du may mau' 'Green' }
    if ($st.emu_new -eq 1) { Stop-EmuUi; $st.emu_new = 0; Save-State $st }
  } else { Step '6/11 May mau: LDPlayer khong can'; if ($st.emu_new -eq 1) { $st.emu_new = 0; Save-State $st } }

  # ------------------------------------------------------------------ 7. Cloudflare
  Step ('7/11 Duong ham Cloudflare ' + $sub + ' + ' + $ssub)
  if (Test-CfService) { Say '   OK - cloudflared dang chay' 'Green' }
  elseif ($cfTok) {
    $tn = New-CfTunnel $cfTok $domain $sub $ssub
    if ($tn.ok) {
      $e = Install-CfService $tn.token
      if ($e) { Say ('   (!) ' + $e) 'Yellow' } else { Say ('   OK - da tao / noi duong ham ' + $sub + ' + 2 dia chi ' + $sub + '.' + $domain + ', ' + $ssub + '.' + $domain) 'Green' }
    } else { Say ('   (!) Chua tu tao duoc duong ham: ' + $tn.err) 'Red' }
  }
  if (-not (Test-CfService)) {
    Say ('   >>> Lam tay: Cloudflare > Zero Trust > Networks > Tunnels > tao tunnel ' + $sub + ' > copy lenh eyJ... > bang CloudBlue bam "3 Noi Cloudflare" (KHONG gui ai);') 'Yellow'
    Say ('       them 2 dia chi: ' + $sub + '.' + $domain + ' -> http://localhost:8010  va  ' + $ssub + '.' + $domain + ' -> http://localhost:8020') 'Yellow'
  }

  # ------------------------------------------------------------------ 8. tu chay + toi uu
  Step '8/11 Bang CloudBlue tu chay quyen Admin + khong ngu + toi uu Windows'
  try { if (Register-Panel) { Say '   OK - bang CloudBlue tu mo quyen Admin khi dang nhap' 'Green' } } catch { Say ('   (!) chua tao duoc tac vu tu chay: ' + $_.Exception.Message) 'Yellow' }
  try { Optimize-Windows $em.dir; Say '   OK - che do hieu nang cao, Defender bo qua thu muc gia lap + CloudBlue' 'Green' } catch {}
  $al = "" + (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon' -ErrorAction SilentlyContinue).AutoAdminLogon
  if ($al -ne '1') { Say '   (!) Windows CHUA tu dang nhap -> trong bang bam "Tu dang nhap + tu chay" (go mat khau Windows NGAY TRONG BANG).' 'Yellow' }

  # ------------------------------------------------------------------ 9. bat dich vu
  Step '9/11 Mo bang CloudBlue -> bat dich vu'
  Start-Panel -Restart
  $t0 = Get-Date; $last = ''
  while (-not ((Test-Services) -and (Test-CfService))) {
    $need = @()
    $k = "" + (Read-KV $confPath)['SUPABASE_SERVICE_KEY']
    if (($k.Length -ge 30) -and ($k -notmatch 'DAN_') -and ($k -ne $have)) { $have = $k; [void]$SECRETS.Add($k); $keyOk = $true }      # vua dan khoa moi trong bang
    if (($k.Length -lt 30) -or ($k -match 'DAN_') -or (-not $keyOk)) { $need += 'bang CloudBlue: bam "2 Dan khoa Supabase" (KHONG gui ai)' }
    if (-not (Test-CfService)) { $need += ('Cloudflare: bang CloudBlue bam "3 Noi Cloudflare" (tunnel ' + $sub + ')') }
    if (-not (Test-Services)) { $need += 'dich vu dang bat (1-3 phut); qua 5 phut chua len: bang CloudBlue bam "TU DONG A->Z"' }
    $txt = $need -join "`n      - "
    if (($txt -ne $last) -or (((Get-Date) - $t0).TotalMinutes -gt 10)) { Say ('   Con cho:' + "`n      - " + $txt) 'Yellow'; $last = $txt; $t0 = Get-Date }
    if ($keyOk) { Start-Panel }
    Start-Sleep $POLL
  }
  Say '   OK - dich vu dang chay (nhan don + phat hinh), cloudflared dang chay' 'Green'
  try { & $PY (Join-Path $B 'phonectl.py') hide 2>$null | Out-Null } catch {}

  # ------------------------------------------------------------------ 10. duong thang web + lenh A + RAM + modem
  Step '10/11 Duong thang web + lenh A + kiem RAM + cong modem'
  $c2 = Read-KV $confPath
  if ($c2['CF_DNS_TOKEN'] -and ($c2['LE_AGREE'] -eq '1')) {
    & $PY (Join-Path $B 'bluestream.py') --webdirect 2>&1 | ForEach-Object { Say ('   ' + $_) 'DarkGray' }
    if ($LASTEXITCODE -eq 0) { Say '   OK - duong thang web' 'Green' } else { Say ('   Duong thang web CHUA bat (ma ' + $LASTEXITCODE + ') - web van di Cloudflare; lam lai sau: bluestream.py --webdirect') 'Yellow' }
  } else { Say '   (bo qua duong thang web: ISO khong kem ma Cloudflare DNS / chua dong y Let''s Encrypt - web van chay qua Cloudflare; bat sau: bluestream.py --webdirect)' 'DarkGray' }
  $sa = Join-Path $B 'sua-tat-ca.py'
  if ((Get-Url ($RAWB + '/windows/sua-tat-ca.py?t=' + (Get-Random)) $sa) -and (Test-Marker $sa 'cloudblue-sua-tat-ca' 20000)) {
    & $PY -u $sa 2>&1 | ForEach-Object { Say ('   ' + $_) 'Gray' }
  } else { Say '   (!) Chua tai duoc sua-tat-ca.py - chay lenh A sau.' 'Yellow' }
  $whea = @(Get-WinEvent -FilterHashtable @{ LogName = 'System'; ProviderName = 'Microsoft-Windows-WHEA-Logger'; Id = 47 } -MaxEvents 200 -ErrorAction SilentlyContinue).Count
  if ($whea) { Say ('   CANH BAO: loi RAM WHEA 47 = ' + $whea + ' lan -> xu ly RAM TRUOC khi ban may') 'Red' } else { Say '   OK - khong thay loi RAM (WHEA 47)' 'Green' }
  & $PY (Join-Path $B 'bluestream.py') --netcheck 2>&1 | ForEach-Object { Say ('   ' + $_) 'DarkGray' }

  # ------------------------------------------------------------------ 11. len web chua
  Step '11/11 Kiem may chu da len web'
  $live = $false
  $kk = "" + (Read-KV $confPath)['SUPABASE_SERVICE_KEY']
  for ($i = 0; ($i -lt 18) -and (-not $live); $i++) {
    $nr = Get-NodeRows $sbUrl $kk
    if ($nr.ok -and (Test-NodeLive $nr.rows $Num 180)) { $live = $true } else { Start-Sleep ([Math]::Min(10, $POLL)) }
  }
  $sum = New-Object System.Collections.ArrayList
  [void]$sum.Add('CloudBlue - may chu win' + $Num + ' (cai tu ISO, ' + (Get-Date -Format 'dd/MM/yyyy HH:mm') + ')')
  [void]$sum.Add('Gia lap: ' + $emuName + ' | ' + $sub + '.' + $domain + ' | ' + $ssub + '.' + $domain)
  if ($live) { [void]$sum.Add('DA LEN WEB: Bang quan tri > May chu > win' + $Num + ' (nut ghi "Nhan may lai" thi bam de bat dau nhan don).') }
  else { [void]$sum.Add('CHUA thay tren web sau 3 phut - xem bang CloudBlue (tab cloudphoned).') }
  if ($missTpl.Count) { [void]$sum.Add('CON THIEU may mau MuMu: ' + ($missTpl -join ', ') + ' (tao trong MuMu Multi-instance, doi ten, de TAT).') }
  [void]$sum.Add('VIEC TAY CON LAI: modem / router mo cong TCP ' + $port + ' -> IP LAN cua may nay (gan IP co dinh theo MAC). CHI mo dung cong nay.')
  [void]$sum.Add('Ban sau tu cap nhat theo cac may chu khac; quan ly tu web: Bang quan tri > May chu > Quan ly.')
  Say ''
  Say ('#################### XONG win' + $Num + ' ####################') 'Green'
  foreach ($ln in $sum) { Say ('  ' + $ln) 'Green' }
  try { $sum | Set-Content -Encoding UTF8 (Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'CloudBlue-may-chu.txt') } catch {}

  # xong: go tac vu + xoa khoa bi mat khoi tep cau hinh ISO (khoa da nam trong cloudphone.conf)
  foreach ($p in @($cfp, (Join-Path $SRC 'may-chu.conf'))) {
    if (Test-Path -LiteralPath $p) { foreach ($k in 'SUPABASE_SERVICE_KEY', 'CF_API_TOKEN', 'CF_DNS_TOKEN') { try { Set-KV $p $k '' } catch {} } }
  }
  $st.done = 1; Save-State $st
  # May cai tu ISO may chu (cb.json role = server): tat 2 tac vu cua phan mem "may PC cho thue" - may chu khong bao gio duoc vao danh sach may PC cho thue.
  $isSrv = $false
  try { $isSrv = (("" + (Get-Content -Raw -LiteralPath (Join-Path $CBPC 'cb.json') -ErrorAction Stop | ConvertFrom-Json).role) -eq 'server') } catch {}
  if ($isSrv) {
    foreach ($tn in 'CloudBluePC Agent', 'CloudBluePC Watch') { try { Disable-ScheduledTask -TaskName $tn -ErrorAction SilentlyContinue | Out-Null } catch {} }
    Say '   Da tat phan mem quan ly "may PC cho thue" tren may chu nay (may chu khong vao danh sach may PC).' 'DarkGray'
  }
  [void](Set-AutoStart -Remove)
  $script:RC = 0
}

if (-not $Lib) {
  $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
  if (-not $isAdmin) {
    # chay tu loi tat (khong qua tac vu) -> tu mo lai bang quyen Admin (may chu cai tu ISO khong hien hop hoi quyen)
    try { Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '"') -ErrorAction Stop; exit 0 } catch {}
    Write-Host 'Can quyen Admin: chuot phai PowerShell > Run as administrator roi chay lai tep nay.' -ForegroundColor Red; Start-Sleep 30; exit 1
  }
  $created = $false
  $mx = New-Object Threading.Mutex($true, 'Global\CloudBlueMayChuIso', [ref]$created)
  if (-not $created) { exit 0 }                                # dang co 1 ban khac chay
  $autoWays = Set-AutoStart                                    # moi lan chay deu dat lai duong tu chay (may vua doi ten / tac vu cu hong van tu chay lai sau khi khoi dong lai)
  try { $Host.UI.RawUI.WindowTitle = 'CloudBlue - tu cai may chu (dung dong cua so nay)' } catch {}
  try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
  $env:PYTHONUTF8 = '1'; $env:PYTHONIOENCODING = 'utf-8'
  $script:RC = 1
  for ($round = 1; $round -le 500; $round++) {
    try { Main | Out-Null }
    catch { Say ('!! LOI KHONG NGO: ' + $_.Exception.Message + '  (dong ' + $_.InvocationInfo.ScriptLineNumber + ') - 1 phut nua thu lai') 'Red'; $script:RC = 2; Start-Sleep 60 }
    if ($script:RC -ne 2) { break }
  }
  try { $mx.ReleaseMutex() } catch {}
  try { $mx.Close() } catch {}
  if ($script:RC -eq 9) {
    $env:CB_ISO_SELF = '1'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath -Conf $Conf
    exit $LASTEXITCODE
  }
  if ($script:RC -eq 0) { Write-Host ''; Write-Host 'Co the dong cua so nay (tu dong sau 15 phut).' -ForegroundColor DarkGray; Start-Sleep 900 }
  exit ([int]$script:RC)
}
