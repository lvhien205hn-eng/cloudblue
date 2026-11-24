# =====================================================================================================
#  winpc/tests/ci/maychu_check.ps1
#  Chay tren may Windows cua GitHub Actions (Windows PowerShell 5.1, quyen Admin): thu "ISO may chu Cloud Phone" (ban 23.11g)
#    1. cu phap may-chu-iso.ps1 + firstboot.ps1 bang chinh Windows PowerShell
#    2. tung ham cua may-chu-iso.ps1: ten may chu, tep KHOA=gia tri, che khoa bi mat, doc ban phim khi khong co ai
#    3. goi API that qua 1 may chu GIA (fake_cf.py): bang cloud_nodes cua Supabase, tao duong ham Cloudflare + dia chi + ban ghi ten mien
#    4. chay CA luong cai may chu (Main) voi bo cai gia lap gia, setup.ps1 gia, phonectl gia: ten tu luc cai Windows, trung ten, ten con may khach, can khoi dong lai
#    5. firstboot.ps1 that: chep tep, dung tac vu tu chay quyen Admin (roi go ngay)
#  Khong dung toi may that nao, khong khoi dong lai may chay thu. Luon thoat ma 0; ket qua o trang tom tat + tep ketqua.
# =====================================================================================================
param([string]$WorkRoot = "", [string]$KetQua = "")
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$RepoDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$McPs1 = Join-Path $RepoDir "maychu\may-chu-iso.ps1"
$FbPs1 = Join-Path $RepoDir "maychu\firstboot.ps1"
$FakePy = Join-Path $PSScriptRoot "fake_cf.py"
$Pass = 0
$FailN = 0
$Lines = New-Object System.Collections.ArrayList
$Srv = $null

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
  $head = "may chu check: " + $verdict + " (" + $Pass + " OK, " + $FailN + " XX)"
  Write-Host ""
  Write-Host ("::notice title=may chu check::" + $head)
  if ($env:GITHUB_STEP_SUMMARY) {
    $md = @(("### " + $head), "", '```') + @($Lines) + @('```')
    Add-Content -Path $env:GITHUB_STEP_SUMMARY -Value $md -Encoding UTF8
  }
  if ($KetQua) { try { Set-Content -Path $KetQua -Value (@($head) + @($Lines)) -Encoding UTF8 } catch { Write-Host ("khong ghi duoc tep ket qua: " + $_) } }
}
function New-Exe([string]$path, [string]$code) {
  # Bien dich 1 chuong trinh C# nho thanh .exe (bo cai gia lap gia / mumu-cli gia)
  if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
  Add-Type -TypeDefinition $code -OutputAssembly $path -OutputType ConsoleApplication
  return (Test-Path -LiteralPath $path)
}
function Get-Mock([string]$path) {
  return (Invoke-RestMethod -Method Get -Uri ("http://127.0.0.1:" + $MockPort + $path) -TimeoutSec 10)
}
function Send-Mock([string]$path, $obj) {
  $js = "{}"
  if ($null -ne $obj) { $js = ConvertTo-Json -InputObject $obj -Depth 6 -Compress }
  return (Invoke-RestMethod -Method Post -Uri ("http://127.0.0.1:" + $MockPort + $path) -Body $js -ContentType "application/json" -TimeoutSec 10)
}

try {
  if (-not $WorkRoot) {
    $best = Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Free -gt 0 } | Sort-Object Free -Descending | Select-Object -First 1
    $WorkRoot = "" + $best.Name + ":\"
  }
  $Wk = Join-Path $WorkRoot "cbmc"
  if (Test-Path $Wk) { Remove-Item -Recurse -Force $Wk }
  New-Dir $Wk | Out-Null
  $os = Get-CimInstance Win32_OperatingSystem
  Info ("may chay thu: " + $os.Caption + " " + $os.Version + " ; PowerShell " + $PSVersionTable.PSVersion + " ; thu muc lam viec " + $Wk)

  # ------------------------------------------------------------------------------------------- 1. cu phap
  Out-Line "== 1. Cu phap may-chu-iso.ps1 + firstboot.ps1"
  foreach ($f in @($McPs1, $FbPs1)) {
    $tok = $null
    $perr = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($f, [ref]$tok, [ref]$perr)
    Ck ((Split-Path -Leaf $f) + " khong co loi cu phap") (@($perr).Count -eq 0) ((@($perr) | ForEach-Object { "dong " + $_.Extent.StartLineNumber + ": " + $_.Message }) -join " | ")
    if (@($perr).Count -gt 0) { throw "loi cu phap - dung" }
  }

  # ------------------------------------------------------------------------------------------- 2. tung ham
  Out-Line "== 2. Tung ham cua may-chu-iso.ps1"
  . $McPs1 -Lib
  $ErrorActionPreference = "Continue"                          # nhu luc chay that (script cai may chu dat Continue)
  Ck "nap duoc cac ham (-Lib khong chay phan than)" ((Get-Command Get-NodeNum -ErrorAction SilentlyContinue) -and (Get-Command New-CfTunnel -ErrorAction SilentlyContinue) -and (Get-Command Main -ErrorAction SilentlyContinue) -and ($MC_VER -match '^\d\d\.\d\d'))
  Info ("ban may-chu-iso: " + $MC_VER)
  # ---- 23.11n: tu cap nhat xong chay lai ban moi - ban 23.11k-m goi "-Conf" KHONG gia tri (PowerShell 5 bo chuoi rong) -> ban moi phai van chay
  $pa1 = Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ('"' + $McPs1 + '"'), "-Lib", "-Conf") -Wait -PassThru -WindowStyle Hidden
  $cmdA = ". '" + $McPs1 + "' -Lib -Conf 'D:\x\may-chu.conf'; " + 'Write-Output (''CONF='' + $Conf)'
  $cmdB = ". '" + $McPs1 + "' -Lib; " + 'Write-Output (''CONF='' + $Conf)'
  $cfA = & powershell.exe -NoProfile -ExecutionPolicy Bypass -Command $cmdA
  $cfB = & powershell.exe -NoProfile -ExecutionPolicy Bypass -Command $cmdB
  Ck "23.11n: ban cu goi lai bang '-Conf' khong gia tri -> ban moi VAN chay (ma 0) ; -Conf <tep> van doc duoc ; khong co -> rong" (($pa1.ExitCode -eq 0) -and ((@($cfA) -join "") -eq "CONF=D:\x\may-chu.conf") -and ((@($cfB) -join "") -eq "CONF=")) ("ma " + $pa1.ExitCode + " | " + (@($cfA) -join "") + " | " + (@($cfB) -join ""))
  $stubS = Join-Path $Wk "tu-goi-lai.ps1"
  $stubO = Join-Path $Wk "tu-goi-lai.txt"
  Set-Content -Path $stubS -Value ('Set-Content -Path "' + $stubO + '" -Value ("ARGS=" + ($args -join "|")) ; exit 7') -Encoding ASCII
  $Conf = ""
  $sa1 = Get-SelfArgs $stubS
  & powershell.exe @sa1
  $ex1 = $LASTEXITCODE
  $o1 = (Get-Content -Raw $stubO).Trim()
  $Conf = "D:\x y\may-chu.conf"
  $sa2 = Get-SelfArgs $stubS
  & powershell.exe @sa2
  $o2 = (Get-Content -Raw $stubO).Trim()
  $Conf = ""
  Ck "Get-SelfArgs: cau hinh rong -> KHONG truyen -Conf ; co tep (ke ca co dau cach) -> truyen dung ; ma thoat cua ban moi duoc giu" (($ex1 -eq 7) -and ($o1 -eq "ARGS=") -and ($o2 -eq "ARGS=-Conf|D:\x y\may-chu.conf") -and (-not (@($sa1) -contains "-Conf"))) ("ma " + $ex1 + " | " + $o1 + " | " + $o2)
  $B = New-Dir (Join-Path $Wk "blue0")
  $ISO = New-Dir (Join-Path $B "iso")
  $CBPC = New-Dir (Join-Path $Wk "pc0")
  $SRC = New-Dir (Join-Path $CBPC "os\firstboot.d\maychu")
  $PROV = New-Dir (Join-Path $CBPC "logs")
  New-Dir (Join-Path $B "logs") | Out-Null
  $nn = @((Get-NodeNum "win9"), (Get-NodeNum "9"), (Get-NodeNum " WIN 09 "), (Get-NodeNum "may chu 12"), (Get-NodeNum "win-12"), (Get-NodeNum "Server_7"), (Get-NodeNum "99"))
  Ck "Get-NodeNum: win9 / 9 / WIN 09 / may chu 12 / win-12 / Server_7 / 99" (($nn -join ",") -eq "9,9,9,12,12,7,99") ($nn -join ",")
  $nz = @((Get-NodeNum "CB-3FA2C1"), (Get-NodeNum "win"), (Get-NodeNum "100"), (Get-NodeNum ""), (Get-NodeNum "win9a"), (Get-NodeNum "May-01x"))
  Ck "Get-NodeNum: ten khong phai so may chu -> 0" (($nz -join ",") -eq "0,0,0,0,0,0") ($nz -join ",")
  $sj = Join-Path $Wk "seed.json"
  Set-Content -Path $sj -Value '{"name": "win9", "label": "win9", "os": "22h2"}' -Encoding ASCII
  $s1 = Get-SeedNum $sj
  Set-Content -Path $sj -Value '{"name": "win-9", "label": "9"}' -Encoding ASCII
  $s2 = Get-SeedNum $sj
  Set-Content -Path $sj -Value '{"name": "win-3FA2C1", "os": "22h2"}' -Encoding ASCII
  $s3 = Get-SeedNum $sj
  Set-Content -Path $sj -Value '{"name": "win-000012"}' -Encoding ASCII
  $s4 = Get-SeedNum $sj
  Set-Content -Path $sj -Value '{"name": "win-12"}' -Encoding ASCII
  $s5 = Get-SeedNum $sj
  $s6 = Get-SeedNum (Join-Path $Wk "khong-co.json")
  Ck "Get-SeedNum: ten nguoi cai go (label) -> so may chu; ten tu sinh win-XXXXXX thi KHONG lay; khong co tep -> 0" ((@($s1, $s2, $s3, $s4, $s5, $s6) -join ",") -eq "9,9,0,0,12,0") (@($s1, $s2, $s3, $s4, $s5, $s6) -join ",")
  $gn = @((Get-NameNum "54 cp"), (Get-NameNum "CP54"), (Get-NameNum "may 7 hn"), (Get-NameNum "win54"), (Get-NameNum " 054 "), (Get-NameNum "CB-102"), (Get-NameNum "abc"), (Get-NameNum ""), (Get-NameNum "00"))
  Ck "Get-NameNum (23.11m): so trong ten go luc cai: 54 cp / CP54 / may 7 hn / win54 / 054 -> 54,54,7,54,54 ; CB-102 / abc / rong / 00 -> 0" (($gn -join ",") -eq "54,54,7,54,54,0,0,0,0") ($gn -join ",")
  Set-Content -Path $sj -Value '{"name": "54CP", "label": "54 cp", "os": "22h2"}' -Encoding ASCII
  $t1 = Get-SeedNum $sj
  Set-Content -Path $sj -Value '{"name": "54CP"}' -Encoding ASCII
  $t2 = Get-SeedNum $sj
  Set-Content -Path $sj -Value '{"name": "CB-3FA2C1", "label": "may moi"}' -Encoding ASCII
  $t3 = Get-SeedNum $sj
  Ck "Get-SeedNum (23.11m): label '54 cp' -> 54 ; da mat label (agent bao len web roi xoa) nhung ten Windows 54CP -> 54 ; 'may moi' + ten tu sinh -> 0" ((@($t1, $t2, $t3) -join ",") -eq "54,54,0") (@($t1, $t2, $t3) -join ",")
  # 23.11l - may chu 1 o cung KHONG co o D: (ban 23.11k: Join-Path voi o khong ton tai -> script dung o buoc 3, cu 1 phut bao loi 1 lan)
  $noDrv = "" + (@(68..90 | ForEach-Object { [string][char]$_ }) | Where-Object { -not (Test-Path -LiteralPath ($_ + ":\")) } | Select-Object -First 1)
  $ldReal = New-Dir (Join-Path $Wk "ldreal\LDPlayer9")
  Set-Content -Path (Join-Path $ldReal "ldconsole.exe") -Value "x" -Encoding ASCII
  $muReal = New-Dir (Join-Path $Wk "mureal\MuMuPlayer")
  New-Dir (Join-Path $muReal "nx_main") | Out-Null
  Set-Content -Path (Join-Path $muReal "nx_main\mumu-cli.exe") -Value "x" -Encoding ASCII
  $keepLd = $LD_DIRS
  $keepMu = $MUMU_DIRS
  $dOk = (@($keepLd) -contains "D:\LDPlayer\LDPlayer9") -and (@($keepMu) -contains "D:\Program Files\Netease\MuMuPlayer")
  $LD_DIRS = @(($noDrv + ":\LDPlayer\LDPlayer9"), ($noDrv + ":\leidian\LDPlayer9"))
  $MUMU_DIRS = @(($noDrv + ":\Program Files\Netease\MuMuPlayer"))
  $nd = "chua chay"
  try { $nd = @((Find-Ld), (Find-Mumu), (Get-MumuCli ($noDrv + ":\x")), (Get-In ($noDrv + ":\a") "b.exe"), (Get-In "" "b.exe"), (Find-Emu).kind) -join "|" } catch { $nd = "NEM LOI: " + $_.Exception.Message }
  Ck "do gia lap o O DIA KHONG TON TAI (may chu 1 o cung khong co o D:) -> tra rong, KHONG nem loi" (($noDrv.Length -eq 1) -and ($nd -eq "|||||") -and $dOk) ("o thu: " + $noDrv + " -> " + $nd)
  $LD_DIRS = @(($noDrv + ":\LDPlayer\LDPlayer9"), $ldReal)
  $MUMU_DIRS = @(($noDrv + ":\Program Files\Netease\MuMuPlayer"), ($muReal + "\"))
  $fe = Find-Emu
  Ck "gia lap o thu muc co that (dung sau 1 o khong ton tai): Find-Ld / Find-Mumu tra dung thu muc, Get-MumuCli tra tep lenh, Find-Emu uu tien LDPlayer" (((Find-Ld) -eq $ldReal) -and ((Find-Mumu) -eq $muReal) -and ((Get-MumuCli $muReal) -eq (Join-Path $muReal "nx_main\mumu-cli.exe")) -and ($fe.kind -eq "ld") -and ($fe.dir -eq $ldReal)) ((Find-Ld) + " | " + (Find-Mumu) + " | " + (Get-MumuCli $muReal))
  $LD_DIRS = $keepLd
  $MUMU_DIRS = $keepMu
  $now = [DateTimeOffset]::UtcNow
  $rows = @([pscustomobject]@{ id = "win1"; updated_at = $now.AddSeconds(-20).ToString("o") }, [pscustomobject]@{ id = "win5"; updated_at = $now.AddHours(-30).ToString("o") },
            [pscustomobject]@{ id = "win8"; updated_at = $now.AddSeconds(-15).ToString("o") }, [pscustomobject]@{ id = "may-khac"; updated_at = $now.ToString("o") })
  Ck "Get-FreeNum: so ke tiep = so lon nhat + 1 (khong dung lai so cu); chua co may nao -> 2" (((Get-FreeNum $rows) -eq 9) -and ((Get-FreeNum @()) -eq 2) -and ((Get-FreeNum @([pscustomobject]@{ id = "win12" })) -eq 13))
  Ck "Test-NodeLive: win8 vua bao ve web -> dang chay; win5 bao tu hom qua -> khong; win9 chua co -> khong" ((Test-NodeLive $rows 8) -and (-not (Test-NodeLive $rows 5)) -and (-not (Test-NodeLive $rows 9)))
  $kv = Join-Path $Wk "kv.conf"
  @("# ghi chu", "A=1", "KEY=DAN_SERVICE_ROLE_KEY_VAO_DAY", "C = 2 = 3", "", "KEY=trung") | Set-Content -Path $kv -Encoding UTF8
  $h1 = Read-KV $kv
  Ck "Read-KV: tep co BOM, dong ghi chu, gia tri co dau =, khoa trung lay dong cuoi" (($h1["A"] -eq "1") -and ($h1["C"] -eq "2 = 3") -and ($h1["KEY"] -eq "trung") -and ($h1.Count -eq 3)) (($h1.Keys | ForEach-Object { $_ + "=" + $h1[$_] }) -join " | ")
  $odd = 'p$a=b"c' + "'" + 'd'
  Set-KV $kv "KEY" $odd
  Set-KV $kv "MOI" "x y"
  $h2 = Read-KV $kv
  $rawKv = [IO.File]::ReadAllBytes($kv)
  Ck "Set-KV: thay dung dong (bo dong trung), them khoa moi, giu gia tri co ky tu la, tep khong con BOM" (($h2["KEY"] -eq $odd) -and ($h2["MOI"] -eq "x y") -and ($h2["A"] -eq "1") -and (@(Get-Content $kv | Where-Object { $_ -match '^KEY=' }).Count -eq 1) -and ($rawKv[0] -ne 0xEF)) ("" + $h2["KEY"])
  [void]$SECRETS.Add("sb_secret_BIMAT_123456")
  Say "thu che khoa: sb_secret_BIMAT_123456 het"
  $lg = Get-Content -Raw (Join-Path $B "logs\iso-cai.log")
  Ck "Say: che khoa bi mat khoi man hinh + nhat ky" (($lg -match 'thu che khoa: \*\*\* het') -and (-not ($lg -match 'BIMAT')))
  Ck "Test-Ps1 + Test-Marker: tep script that -> dat; tep rac -> khong" ((Test-Ps1 $McPs1) -and (Test-Marker $McPs1 "cloudblue-may-chu-iso" 8000) -and (-not (Test-Marker $kv "cloudblue-may-chu-iso" 10)) -and (-not (Test-Marker (Join-Path $Wk "khong-co") "x" 1)))
  Set-Content -Path (Join-Path $Wk "hong.ps1") -Value 'if ($x { "thieu ngoac"' -Encoding ASCII
  Ck "Test-Ps1: script loi cu phap -> khong dat (ban tai ve hong thi khong thay ban dang chay)" (-not (Test-Ps1 (Join-Path $Wk "hong.ps1")))
  Set-Content -Path (Join-Path $SRC "a.bin") -Value "src" -Encoding ASCII
  $fp1 = Find-Payload "a.bin"
  Set-Content -Path (Join-Path $ISO "a.bin") -Value "iso" -Encoding ASCII
  $fp2 = Find-Payload "a.bin"
  Ck "Find-Payload: C:\blue\iso truoc, roi thu muc bo cai; khong co -> rong" (($fp1 -eq (Join-Path $SRC "a.bin")) -and ($fp2 -eq (Join-Path $ISO "a.bin")) -and ((Find-Payload "khong-co.exe") -eq ""))
  $t0 = Get-Date
  $rl = Read-LineWait "   thu doc ban phim" 2
  Ck "Read-LineWait: khong ai go (may chay tu dong) -> tra rong sau thoi gian cho, khong treo" (($null -eq $rl) -and (((Get-Date) - $t0).TotalSeconds -lt 15)) ("" + $rl)
  $stt = @{ reboots = 0 }
  $env:CB_ISO_TEST = "1"
  $rn = Restart-Now $stt "thu"
  $ab = (& shutdown.exe /a 2>&1 | Out-String)
  $abRc = $LASTEXITCODE
  $st9 = Get-State
  Ck "Restart-Now khi kiem thu: ghi so lan vao so, KHONG hen khoi dong lai may" ((@($rn)[-1] -eq $true) -and ($st9.reboots -eq 1) -and ($abRc -ne 0)) ("shutdown /a ma " + $abRc + " " + ($ab -replace '\s+', ' '))
  $stt.reboots = 4
  $rn2 = Restart-Now $stt "thu"
  Ck "Restart-Now: da khoi dong lai 4 lan -> thoi, de luong cai di tiep" (@($rn2)[-1] -eq $false)

  $fi = Join-Path $Wk "inno.exe"
  $fn = Join-Path $Wk "nsis.exe"
  $fx = Join-Path $Wk "la.exe"
  [IO.File]::WriteAllBytes($fi, ([byte[]](1..200) + [Text.Encoding]::ASCII.GetBytes('<assemblyIdentity name="JR.Inno.Setup" type="win32"/>') + (New-Object byte[] 5000)))
  [IO.File]::WriteAllBytes($fn, ((New-Object byte[] 70000) + [Text.Encoding]::ASCII.GetBytes('xx Nullsoft.NSIS.exehead yy')))
  [IO.File]::WriteAllBytes($fx, (New-Object byte[] 3000))
  Ck "Get-SetupKind: nhan bo cai dong goi bang Inno Setup / NSIS theo dau trong tep; tep la / khong co tep -> rong" (((Get-SetupKind $fi) -eq "inno") -and ((Get-SetupKind $fn) -eq "nsis") -and ((Get-SetupKind $fx) -eq "") -and ((Get-SetupKind (Join-Path $Wk "khong-co.exe")) -eq ""))
  Ck "Get-SetupArgs: Inno -> /VERYSILENT ..., NSIS -> /S (ke ca ban LDPlayer dong goi lai); khong ro: LDPlayer chinh hang -silence, MuMu /S" (((Get-SetupArgs "ld" $fi) -match '^/VERYSILENT ') -and ((Get-SetupArgs "ld" $fn) -eq "/S") -and ((Get-SetupArgs "ld" $fx) -match '^-silence .*-path="C:\\LDPlayer\\LDPlayer9\\"$') -and ((Get-SetupArgs "mumu" $fx) -eq "/S") -and ((Get-SetupArgs "mumu" $fi) -match '^/VERYSILENT '))

  # ------------------------------------------------------------------------------------------- 3. API qua may chu gia
  Out-Line "== 3. Supabase + Cloudflare (may chu gia fake_cf.py)"
  $pyCmd = Get-Command python -ErrorAction SilentlyContinue
  if (-not $pyCmd) { throw "may chay thu khong co python" }
  $PyReal = $pyCmd.Source
  $MockPort = Get-Random -Minimum 20000 -Maximum 40000
  $SbGood = "sb_secret_ci_" + ("k" * 30)
  $Srv = Start-Process -FilePath $PyReal -ArgumentList @($FakePy, ("" + $MockPort), "example.test", $SbGood) -PassThru -WindowStyle Hidden
  $up = $false
  for ($i = 0; $i -lt 40 -and -not $up; $i++) { try { [void](Get-Mock "/_state"); $up = $true } catch { Start-Sleep -Milliseconds 300 } }
  Ck "may chu gia chay duoc" $up
  if (-not $up) { throw "may chu gia khong len" }
  $MockUrl = "http://127.0.0.1:" + $MockPort
  $CFAPI = $MockUrl + "/client/v4"
  $r1 = Get-NodeRows $MockUrl $SbGood
  $r2 = Get-NodeRows $MockUrl "sb_secret_sai_khoa_0000000000000000"
  Ck "Get-NodeRows: khoa dung -> 3 may chu; khoa sai -> ok = false, ma 401 (khong nem loi)" ($r1.ok -and (@($r1.rows).Count -eq 3) -and (-not $r2.ok) -and ($r2.code -eq 401)) ("" + $r1.err + " / " + $r2.code + " " + $r2.err)
  Ck "danh sach that: win8 dang chay, win5 khong, so ke tiep 9" ((Test-NodeLive $r1.rows 8) -and (-not (Test-NodeLive $r1.rows 5)) -and ((Get-FreeNum $r1.rows) -eq 9))
  $r3 = Invoke-Api "GET" "http://127.0.0.1:9/khong-co" @{} $null 5
  Ck "Invoke-Api: may chu khong toi duoc -> ok = false, khong nem loi" ((-not $r3.ok) -and ($r3.code -eq 0))

  # ---- 23.11m: Windows cu (1511) PowerShell loi TLS -> goi web / tai tep bang Python (OpenSSL)
  $PY = $PyReal
  $NET_PS = $false                                                                       # gia lap: PowerShell khong goi duoc mang
  $SECRETS.Clear(); [void]$SECRETS.Add($SbGood)
  $q1 = Get-NodeRows $MockUrl $SbGood
  $q2 = Get-NodeRows $MockUrl "sb_secret_sai_khoa_0000000000000000"
  $q3 = Invoke-Api "GET" "http://127.0.0.1:9/khong-co" @{} $null 5
  Ck "Python: doc danh sach may chu (3 may) ; khoa sai -> 401 ; khong toi duoc -> ma 0, khong nem loi" ($q1.ok -and (@($q1.rows).Count -eq 3) -and (-not $q2.ok) -and ($q2.code -eq 401) -and (-not $q3.ok) -and ($q3.code -eq 0)) ("" + $q1.err + " / " + $q2.code + " / " + $q3.code + " " + $q3.err)
  [void](Send-Mock "/_reset" $null)
  $q4 = Invoke-Api "POST" ($CFAPI + "/zones/z1/dns_records") @{ Authorization = "Bearer tok-ok" } @{ type = "A"; name = "py9.example.test"; content = "1.2.3.4"; proxied = $false }
  $msq = Get-Mock "/_state"
  Ck "Python: POST kem ma + noi dung JSON toi Cloudflare (gia) -> tao ban ghi py9" ($q4.ok -and (@($msq.dns | Where-Object { $_.name -eq "py9.example.test" -and $_.content -eq "1.2.3.4" }).Count -eq 1)) ("" + $q4.code + " " + $q4.err)
  $pdst = Join-Path $Wk "py-tai.json"
  $q5 = Get-Url ($MockUrl + "/_state") $pdst
  Ck "Python: Get-Url tai tep khi PowerShell loi (vd tu cap nhat script)" ($q5 -and (Test-Path $pdst) -and ((Get-Content -Raw $pdst) -match '"dns"'))
  $hpf = Join-Path $ISO "cbhttp.py"
  Ck "Python: khoa khong nam tren dia (tep cbhttp.py) / bien moi truong da xoa sau khi goi" ((Test-Path $hpf) -and (-not (Get-Content -Raw $hpf).Contains($SbGood)) -and ($null -eq [Environment]::GetEnvironmentVariable("CB_HTTP_REQ", "Process")))
  $NET_PS = $true
  $q6 = Get-NodeRows $MockUrl $SbGood
  Ck "PowerShell goi duoc thi van dung PowerShell nhu cu" ($q6.ok -and (@($q6.rows).Count -eq 3))
  $SECRETS.Clear()
  [void](Send-Mock "/_reset" $null)

  # ---- 23.11m: so may chu KHONG hoi - lay so trong ten go luc cai ; khong co so -> so ke tiep ngay
  $tSel = Get-Date
  Set-Content -Path (Join-Path $ISO "seed.json") -Value '{"name": "54CP", "label": "54 cp"}' -Encoding ASCII
  $n54 = Select-NodeNum @{} $MockUrl $SbGood
  Set-Content -Path (Join-Path $ISO "seed.json") -Value '{"name": "CB-3FA2C1", "label": "may moi"}' -Encoding ASCII
  $nmm = Select-NodeNum @{} $MockUrl $SbGood
  Set-Content -Path (Join-Path $ISO "seed.json") -Value '{"name": "CB-3FA2C1", "label": "May-01"}' -Encoding ASCII
  $nw1 = Select-NodeNum @{} $MockUrl $SbGood
  Remove-Item -LiteralPath (Join-Path $ISO "seed.json") -Force
  $logS = Get-Content -Raw (Join-Path $B "logs\iso-cai.log")
  $secSel = ((Get-Date) - $tSel).TotalSeconds
  Ck "Select-NodeNum: '54 cp' -> win54 ; 'may moi' -> so ke tiep win9 ; 'May-01' (win1 = may chu chinh) -> win9 ; KHONG hoi / khong cho (3 lan < 15 giay)" (($n54 -eq 54) -and ($nmm -eq 9) -and ($nw1 -eq 9) -and ($secSel -lt 15) -and ($logS -match "Ten may chu: win54 \(ten go luc cai Windows\)") -and ($logS -match "win9 \(so ke tiep - tu chon\)") -and (-not ($logS -match "Chua doc duoc danh sach may chu"))) ("" + $n54 + "," + $nmm + "," + $nw1 + " ; " + [int]$secSel + " giay")

  # ---- 24/11: windows/setup.ps1 (bo cai phan mem may chu) - tai tep bang Python khi PowerShell loi TLS
  $SetupPs1 = Join-Path (Split-Path -Parent $RepoDir) "windows\setup.ps1"
  $tokS = $null
  $perrS = $null
  $astS = [System.Management.Automation.Language.Parser]::ParseFile($SetupPs1, [ref]$tokS, [ref]$perrS)
  Ck "windows/setup.ps1 khong co loi cu phap" (@($perrS).Count -eq 0) ((@($perrS) | ForEach-Object { "dong " + $_.Extent.StartLineNumber + ": " + $_.Message }) -join " | ")
  $fdS = @($astS.FindAll({ param($n) ($n -is [System.Management.Automation.Language.FunctionDefinitionAst]) -and ($n.Name -eq "PyGet") }, $true))
  $okPg = $false
  if ($fdS.Count -eq 1) {
    $ftS = $fdS[0].Extent.Text.Replace('"C:\CloudBluePC\py\python.exe"', ('"' + $PyReal + '"'))
    . ([ScriptBlock]::Create($ftS))
    $pgDst = Join-Path $Wk "pyget.json"
    $okPg = (PyGet ($MockUrl + "/_state") $pgDst) -and ((Get-Content -Raw $pgDst) -match '"dns"')
    $okPg = $okPg -and (-not (PyGet "http://127.0.0.1:9/khong-co" (Join-Path $Wk "pyget2.json")))
  }
  Ck "setup.ps1 PyGet: tai duoc bang Python ; dia chi hong -> false, khong nem loi" $okPg
  $tn = New-CfTunnel "tok-ok" "example.test" "phone9" "stream9"
  $ms = Get-Mock "/_state"
  $ing = @($ms.configs."t-1".ingress)
  $dns = @($ms.dns)
  Ck "New-CfTunnel: tao duong ham phone9, tra ma chay (eyJ...) va dua ma vao danh sach che" ($tn.ok -and ($tn.id -eq "t-1") -and ($tn.token -match '^eyJ') -and ($tn.token.Length -ge 40) -and ($SECRETS -contains $tn.token) -and (@($ms.tunnels).Count -eq 1) -and ($ms.tunnels[0].name -eq "phone9") -and ($ms.tunnels[0].config_src -eq "cloudflare")) ("" + $tn.err)
  Ck "New-CfTunnel: 2 dia chi phone9 -> 8010, stream9 -> 8020 + dong chan cuoi http_status:404" (($ing.Count -eq 3) -and ($ing[0].hostname -eq "phone9.example.test") -and ($ing[0].service -eq "http://localhost:8010") -and ($ing[1].hostname -eq "stream9.example.test") -and ($ing[1].service -eq "http://localhost:8020") -and ($ing[2].service -eq "http_status:404") -and (-not $ing[2].hostname)) (ConvertTo-Json -InputObject $ing -Compress)
  Ck "New-CfTunnel: 2 ban ghi CNAME (may cam) tro ve <ma duong ham>.cfargotunnel.com" (($dns.Count -eq 2) -and (@($dns | Where-Object { ($_.type -eq "CNAME") -and ($_.content -eq "t-1.cfargotunnel.com") -and ($_.proxied -eq $true) }).Count -eq 2) -and ((@($dns | ForEach-Object { $_.name }) -join ",") -eq "phone9.example.test,stream9.example.test")) (ConvertTo-Json -InputObject $dns -Compress)
  $tn2 = New-CfTunnel "tok-ok" "example.test" "phone9" "stream9"
  $ms2 = Get-Mock "/_state"
  Ck "chay lai (cai lai may chu cung ten): dung lai duong ham cu, khong tao trung, ban ghi dung roi thi khong sua" ($tn2.ok -and ($tn2.id -eq "t-1") -and (@($ms2.tunnels).Count -eq 1) -and (@($ms2.dns).Count -eq 2) -and (@($ms2.calls | Where-Object { $_ -match '^PUT /client/v4/zones' }).Count -eq 0))
  [void](Send-Mock "/_reset" $null)
  $hd = @{ Authorization = "Bearer tok-ok" }
  $pa = Invoke-Api "POST" ($CFAPI + "/zones/z1/dns_records") $hd @{ type = "A"; name = "stream9.example.test"; content = "1.2.3.4"; proxied = $false }
  $tn3 = New-CfTunnel "tok-ok" "example.test" "phone9" "stream9"
  $ms3 = Get-Mock "/_state"
  $rec = @($ms3.dns | Where-Object { $_.name -eq "stream9.example.test" })
  Ck "ten stream9 dang la ban ghi kieu khac (A) -> sua thanh CNAME cua duong ham, khong tao trung" ($pa.ok -and $tn3.ok -and ($rec.Count -eq 1) -and ($rec[0].type -eq "CNAME") -and ($rec[0].proxied -eq $true) -and (@($ms3.dns).Count -eq 2)) (ConvertTo-Json -InputObject $ms3.dns -Compress)
  $tn4 = New-CfTunnel "tok-notunnel" "example.test" "phone9" "stream9"
  Ck "ma Cloudflare khong co quyen duong ham -> bao ro can quyen Cloudflare Tunnel, khong nem loi" ((-not $tn4.ok) -and ($tn4.err -match "Cloudflare Tunnel")) ("" + $tn4.err)
  $tn5 = New-CfTunnel "tok-ok" "khac.test" "phone9" "stream9"
  $tn6 = New-CfTunnel "tok-sai-0000000000" "example.test" "phone9" "stream9"
  Ck "ten mien khong thuoc ma / ma sai -> bao loi, khong nem loi" ((-not $tn5.ok) -and ($tn5.err -match "khong thay ten mien") -and (-not $tn6.ok)) ("" + $tn5.err + " / " + $tn6.err)

  # ---- 23.11k: DIEU KHIEN TU XA - may nay da hien o web chua (phan mem CloudBlue PC tren may tu dang ky bang ma may chu trong ISO)
  [void](Send-Mock "/_reset" $null)
  $SECRETS.Clear()
  $rmKey = "cbsv_" + ("0123456789abcdef" * 3).Substring(0, 40)
  $rs0 = Get-RemoteState $MockUrl $SbGood
  New-Dir (Join-Path $CBPC "agent") | Out-Null
  Set-Content -Path (Join-Path $CBPC "agent\pcagent.py") -Value "# gia" -Encoding ASCII
  $rs1 = Get-RemoteState $MockUrl $SbGood                                              # chua co seed.json -> khong ket luan
  Set-Content -Path (Join-Path $CBPC "seed.json") -Value "day khong phai json {" -Encoding ASCII
  $rs2 = Get-RemoteState $MockUrl $SbGood
  Set-Content -Path (Join-Path $CBPC "seed.json") -Value '{"name": "win9", "label": "win9"}' -Encoding ASCII
  $rs3 = Get-RemoteState $MockUrl $SbGood
  Ck "Get-RemoteState: may khong co phan mem CloudBlue PC -> noagent ; khong doc duoc seed.json -> err (KHONG ket luan la ISO cu) ; ISO cu khong kem ma -> none" (($rs0 -eq "noagent") -and ($rs1 -eq "err") -and ($rs2 -eq "err") -and ($rs3 -eq "none")) (@($rs0, $rs1, $rs2, $rs3) -join ",")
  Set-Content -Path (Join-Path $CBPC "seed.json") -Value ('{"name": "win9", "label": "win9", "enroll_key": "' + $rmKey + '"}') -Encoding ASCII
  $rs4 = Get-RemoteState $MockUrl ""
  $rs5 = Get-RemoteState $MockUrl "sb_secret_sai_khoa_0000000000000000"
  [void](Send-Mock "/_sql53" @{ on = $false })
  $rs6 = Get-RemoteState $MockUrl $SbGood
  [void](Send-Mock "/_sql53" @{ on = $true })
  $rs7 = Get-RemoteState $MockUrl $SbGood
  $msR = Get-Mock "/_state"
  $msRtxt = $msR | ConvertTo-Json -Depth 6 -Compress
  Ck "Get-RemoteState: ISO co ma may chu -> khong khoa: nokey ; khoa sai: err ; web chua chay SQL v53: nosql ; binh thuong: wait" (($rs4 -eq "nokey") -and ($rs5 -eq "err") -and ($rs6 -eq "nosql") -and ($rs7 -eq "wait")) (@($rs4, $rs5, $rs6, $rs7) -join ",")
  Ck "... web chi nhan DAU BAM cua ma (sha256), khong nhan ma ; ma duoc dua vao danh sach che" ((@($msR.srv_keys).Count -eq 1) -and ($msR.srv_keys[0].hash -eq (Get-TextSha $rmKey)) -and (-not $msRtxt.Contains($rmKey)) -and ($SECRETS -contains $rmKey) -and ((Hide-Secret ("x " + $rmKey)) -notmatch "0123456789abcdef0123")) ($msRtxt)
  Set-Content -Path (Join-Path $CBPC "identity.json") -Value '{"id": "11111111-2222-3333-4444-555555555555", "token": "0123456789abcdef0123456789abcdef", "name": "win9"}' -Encoding ASCII
  [void](Send-Mock "/_reset" $null)
  $rs8 = Get-RemoteState $MockUrl $SbGood
  $msR2 = Get-Mock "/_state"
  Ck "Get-RemoteState: phan mem da dang ky xong (identity.json co ma rieng) -> on, khong goi web nua" (($rs8 -eq "on") -and (@($msR2.srv_keys).Count -eq 0)) ($rs8)
  Ck "Get-TextSha: dung sha256 chuan" ((Get-TextSha "abc") -eq "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

  # ------------------------------------------------------------------------------------------- 4. ca luong cai may chu
  Out-Line "== 4. Ca luong cai may chu (Main) voi bo cai gia lap gia, setup.ps1 gia, phonectl gia"
  New-Dir (Join-Path $Wk "emu") | Out-Null
  $EmuDir = Join-Path $Wk "emu\MuMuPlayer"
  $FakeCli = Join-Path $Wk "fake-mumu-cli.exe"
  $FakeSetup = Join-Path $Wk "fake-mumu-setup.exe"
  $cliCode = @'
using System; using System.IO; using System.Collections.Generic;
public class FakeCli { public static int Main(string[] a) {
  string st = Environment.GetEnvironmentVariable("CB_FAKE_VMS");
  File.AppendAllText(st + ".log", string.Join(" ", a) + "\n");
  List<string> L = new List<string>();
  if (File.Exists(st)) { foreach (string x in File.ReadAllLines(st)) { if (x.Trim() != "") { L.Add(x.Trim()); } } }
  if (a.Length > 0 && a[0] == "import") { int mx = -1; foreach (string x in L) { mx = Math.Max(mx, int.Parse(x.Split('|')[0])); } L.Add((mx + 1) + "|MuMu-nhap|15"); File.WriteAllLines(st, L.ToArray()); }
  if (a.Length > 0 && a[0] == "rename") { string i = a[Array.IndexOf(a, "--vmindex") + 1]; string n = a[Array.IndexOf(a, "--name") + 1];
    for (int k = 0; k < L.Count; k++) { string[] p = L[k].Split('|'); if (p[0] == i) { L[k] = p[0] + "|" + n + "|" + p[2]; } } File.WriteAllLines(st, L.ToArray()); }
  return 0; } }
'@
  $setupCode = @'
using System; using System.IO;
public class FakeSetup { public static int Main(string[] a) {
  string d = Environment.GetEnvironmentVariable("CB_FAKE_EMU");
  File.WriteAllText(d + ".args.txt", string.Join(" ", a));
  System.Threading.Thread.Sleep(1500);
  Directory.CreateDirectory(Path.Combine(d, "nx_main"));
  File.Copy(Environment.GetEnvironmentVariable("CB_FAKE_CLI"), Path.Combine(d, "nx_main", "mumu-cli.exe"), true);
  return 0; } }
'@
  $okExe = (New-Exe $FakeCli $cliCode) -and (New-Exe $FakeSetup $setupCode)
  Ck "dung duoc bo cai gia lap gia + mumu-cli gia (.exe)" $okExe
  if (-not $okExe) { throw "khong bien dich duoc chuong trinh gia" }
  $StubSetup = Join-Path $Wk "stub-setup.ps1"
  @('param([string]$Node = "", [string]$PubHost = "")',
    'Write-Host ("STUB setup " + $Node + " " + $PubHost)',
    'New-Item -ItemType Directory -Force (Join-Path $B "platform-tools"), (Join-Path $B "logs") | Out-Null',
    'Set-Content -Path (Join-Path $B "platform-tools\adb.exe") -Value "x"',
    'if ($env:CB_STUB_REBOOT -eq "1") { Set-Content -Path (Join-Path $B "logs\viec-lam-tay.txt") -Value "KHOI DONG LAI may - xong mo PowerShell Admin, chay lai lenh cai" -Encoding UTF8; return }',
    'Remove-Item (Join-Path $B "logs\viec-lam-tay.txt") -ErrorAction SilentlyContinue',
    'if (-not (Test-Path (Join-Path $B "cloudphone.conf"))) {',
    '  @("# stub", "SUPABASE_URL=x", "SUPABASE_SERVICE_KEY=DAN_SERVICE_ROLE_KEY_VAO_DAY", ("PUBLIC_BASE=https://" + $PubHost), ("NODE_ID=" + $Node), "EMU=mumu") | Set-Content -Encoding utf8 (Join-Path $B "cloudphone.conf")',
    '}', ('# ' + ('x' * 6000))) | Set-Content -Path $StubSetup -Encoding ASCII
  $StubSua = Join-Path $Wk "stub-sua.py"
  @('# cloudblue-sua-tat-ca (ban gia de kiem thu)', 'print("== TOM TAT gia ==")', 'print("-> XONG, may chu on.")', ('# ' + ("x" * 21000))) | Set-Content -Path $StubSua -Encoding ASCII
  $phonectl = @'
import os, sys
st = os.environ["CB_FAKE_VMS"]
def load():
    if not os.path.exists(st): return [("0", "MuMu-0", "12")]
    return [tuple(x.strip().split("|")) for x in open(st) if x.strip()]
a = sys.argv[1:]
vms = load()
if a[:1] == ["engine"]:
    names = dict((v[1], v[2]) for v in vms)
    miss = [] if names.get("tpl_a15") == "15" else ["tpl_a15"]
    import json
    print(json.dumps({"emu": "mumu", "androids": ["12"] + ([] if miss else ["15"]), "default": "12", "found": True, "missing_tpl": miss}))
elif a[:1] == ["vmlist"]:
    for v in vms: print("%s,%s,0,2" % (v[0], v[1]))
elif a[:1] == ["mktpl"]:
    print("LOI: ban gia khong tao duoc may mau"); sys.exit(1)
elif a[:1] == ["hide"]:
    print("da an")
'@
  $bluestream = @'
import sys
if "--webdirect" in sys.argv: print("webdirect gia: OK"); sys.exit(0)
if "--netcheck" in sys.argv: print("netcheck gia: IP LAN 192.168.1.50"); sys.exit(0)
'@
  $env:CB_FAKE_CLI = $FakeCli
  $env:CB_FAKE_EMU = $EmuDir
  $CfSecret = "tok-ok"
  # ---- cac ham thay the (khong dung toi may chay thu)
  function Test-Net { return $true }
  function Update-Self([string]$self) { return $false }
  function Stop-EmuUi { $script:StopUi++ }
  function Find-Ld { return "" }
  function Find-Mumu { if (Test-Path -LiteralPath (Join-Path $EmuDir "nx_main\mumu-cli.exe")) { return $EmuDir }; return "" }
  function Get-Url([string]$url, [string]$dst) {
    if ($url -match 'setup\.ps1') { Copy-Item -LiteralPath $StubSetup -Destination $dst -Force; return $true }
    if ($url -match 'sua-tat-ca\.py') { Copy-Item -LiteralPath $StubSua -Destination $dst -Force; return $true }
    return $false
  }
  function Test-CfService {
    $script:CfAsk++
    if (($script:CfAutoAt -gt 0) -and ($script:CfAsk -ge $script:CfAutoAt)) { $script:CfUp = $true }      # gia lap: nguoi cai tu noi Cloudflare trong bang
    return [bool]$script:CfUp
  }
  function Install-CfService([string]$token) {
    $script:CfTok = $token; $script:CfUp = $true
    [void](Send-Mock "/_nodes" @(@{ id = "win1"; age = 20 }, @{ id = "win8"; age = 15 }, @{ id = $script:WantNode; age = 3 }))      # dich vu len -> may chu bao ve web
    return ""
  }
  function Test-Services { $script:SvcAsk++; return ($script:SvcAsk -ge 4) }
  function Start-Panel([switch]$Restart) { $script:PanelStarts++ }
  function Restart-Now($st, [string]$why) { $script:Reboots++; return $true }
  $PY = $PyReal
  $PYW = $PyReal
  $POLL = 1
  $SETTLE = 1
  $WAIT_NAME = 2
  function New-Case([string]$name, [string]$label, [bool]$withKey) {
    # Dung 1 "may moi cai Windows xong": thu muc C:\blue gia + thu muc bo cai gia co cau hinh, bo cai gia lap, may mau
    $script:B = New-Dir (Join-Path $Wk ("blue-" + $name))
    $script:ISO = New-Dir (Join-Path $B "iso")
    $script:CBPC = New-Dir (Join-Path $Wk ("pc-" + $name))
    $script:SRC = New-Dir (Join-Path $CBPC "os\firstboot.d\maychu")
    $script:PROV = New-Dir (Join-Path $CBPC "logs")
    New-Dir (Join-Path $B "logs") | Out-Null
    $env:CB_FAKE_VMS = Join-Path $B "fake-vms.txt"
    Set-Content -Path $env:CB_FAKE_VMS -Value "0|MuMu-0|12" -Encoding ASCII
    Set-Content -Path (Join-Path $B "phonectl.py") -Value $phonectl -Encoding ASCII
    Set-Content -Path (Join-Path $B "bluestream.py") -Value $bluestream -Encoding ASCII
    $kline = "SUPABASE_SERVICE_KEY="
    $cline = "CF_API_TOKEN="
    if ($withKey) { $kline += $SbGood; $cline += $CfSecret }
    @("# cau hinh ISO may chu (kiem thu)", "DOMAIN=example.test", ("SUPABASE_URL=" + $MockUrl), $kline, $cline, "LE_AGREE=1", "EMU=mumu") | Set-Content -Path (Join-Path $SRC "may-chu.conf") -Encoding ASCII
    Copy-Item -LiteralPath $FakeSetup -Destination (Join-Path $SRC "mumu-setup.exe") -Force
    Set-Content -Path (Join-Path $SRC "tpl_a15.mumudata") -Value "may mau gia" -Encoding ASCII
    if ($label) { Set-Content -Path (Join-Path $ISO "seed.json") -Value ('{"name": "x", "label": "' + $label + '", "os": "22h2"}') -Encoding ASCII }
    $script:CfUp = $false; $script:CfTok = ""; $script:SvcAsk = 0; $script:PanelStarts = 0; $script:Reboots = 0; $script:StopUi = 0; $script:RC = -1
    $script:CfAsk = 0; $script:CfAutoAt = 0
    $SECRETS.Clear()
    [void](Send-Mock "/_reset" $null)
  }

  # ---- A. ten go luc cai Windows = win9, ISO kem du khoa + bo cai + may mau
  if (Test-Path $EmuDir) { Remove-Item -Recurse -Force $EmuDir }
  New-Case "a" "win9" $true
  $WantNode = "win9"
  $Conf = ""
  Set-Content -Path (Join-Path $CBPC "cb.json") -Value '{"user": "PC", "role": "server", "user_admin": true}' -Encoding ASCII
  $srvA = "cbsv_" + ("fedcba9876543210" * 3).Substring(0, 40)                # ISO 23.11k: bo cai Windows ghi ma may chu vao seed.json cua phan mem CloudBlue PC
  New-Dir (Join-Path $CBPC "agent") | Out-Null
  Set-Content -Path (Join-Path $CBPC "agent\pcagent.py") -Value "# gia" -Encoding ASCII
  Set-Content -Path (Join-Path $CBPC "seed.json") -Value ('{"name": "x", "label": "win9", "enroll_key": "' + $srvA + '"}') -Encoding ASCII
  foreach ($tn in @("CloudBluePC Agent", "CloudBluePC Watch")) {            # 2 tac vu gia cua phan mem may PC cho thue (bo cai Windows dung)
    $ta = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c exit 0"
    $tt = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddDays(30))
    Register-ScheduledTask -TaskName $tn -Action $ta -Trigger $tt -Force | Out-Null
  }
  Main | Out-Null
  $pcT = @(@("CloudBluePC Agent", "CloudBluePC Watch") | ForEach-Object { "" + (Get-ScheduledTask -TaskName $_ -ErrorAction SilentlyContinue).State })
  $cA = Read-KV (Join-Path $B "cloudphone.conf")
  $logA = Get-Content -Raw (Join-Path $B "logs\iso-cai.log")
  $msA = Get-Mock "/_state"
  $stA = Get-State
  Ck "A: chay het luong, ma tra ve 0 (XONG)" ($RC -eq 0) ("RC=" + $RC + " ; cuoi nhat ky: " + ((($logA -split "`n") | Select-Object -Last 6) -join " | "))
  Ck "A: ten may chu lay tu ten go luc cai Windows (win9) -> setup.ps1 nhan -Node win9 -PubHost phone9.example.test" (($cA["NODE_ID"] -eq "win9") -and ($cA["PUBLIC_BASE"] -eq "https://phone9.example.test") -and ($logA -match "Ten may chu: win9 \(ten go luc cai Windows\)") -and ($logA -match "STUB setup win9 phone9.example.test"))
  $argsA = ""
  if (Test-Path ($EmuDir + ".args.txt")) { $argsA = Get-Content -Raw ($EmuDir + ".args.txt") }
  Ck "A: chay bo cai gia lap kem trong ISO kieu im lang (/S), thay gia lap thi lam tiep, dong cua so gia lap" ((Test-Path (Join-Path $EmuDir "nx_main\mumu-cli.exe")) -and ($argsA.Trim() -eq "/S") -and ($StopUi -ge 1) -and ($logA -match "OK - da cai MuMu Player")) ("args=" + $argsA + " stop=" + $StopUi)
  Ck "A: khoa Supabase tu ISO vao cloudphone.conf (thay dong mau), kem ma Cloudflare DNS + dong y Let's Encrypt" (($cA["SUPABASE_SERVICE_KEY"] -eq $SbGood) -and ($cA["CF_DNS_TOKEN"] -eq $CfSecret) -and ($cA["LE_AGREE"] -eq "1") -and ($logA -match "khoa Supabase dung duoc"))
  $vmA = @(Get-Content $env:CB_FAKE_VMS)
  $cliA = Get-Content -Raw ($env:CB_FAKE_VMS + ".log")
  Ck "A: may mau tpl_a15 nhap tu tep kem trong ISO (import -> rename), khong con thieu may mau" (($vmA -contains "1|tpl_a15|15") -and ($cliA -match 'import --path ') -and ($cliA -match 'rename --vmindex 1 --name tpl_a15') -and ($logA -match "OK - du may mau")) (($vmA -join " ; ") + " // " + ($cliA -replace '\s+', ' '))
  Ck "A: tu tao duong ham phone9 + 2 dia chi + 2 ban ghi, cai dich vu cloudflared bang ma chay" ((@($msA.tunnels).Count -eq 1) -and ($msA.tunnels[0].name -eq "phone9") -and (@($msA.dns).Count -eq 2) -and ($CfTok -match '^eyJ') -and ($logA -match "da tao / noi duong ham phone9"))
  $tk = Get-ScheduledTask -TaskName "BlueRoblox" -ErrorAction SilentlyContinue
  $tkArg = ""
  if ($tk) { $tkArg = "" + $tk.Actions[0].Arguments }
  Ck "A: tac vu BlueRoblox (bang CloudBlue tu mo quyen Admin khi dang nhap) da dung" ($tk -and ("" + $tk.Principal.RunLevel -eq "Highest") -and ($tkArg -match 'panel\.py" --auto') -and ($tkArg.Contains($B))) ($tkArg)
  Ck "A: mo bang, cho dich vu len, chay duong thang web + lenh A (ban gia)" (($PanelStarts -ge 1) -and ($logA -match "dich vu dang chay") -and ($logA -match "webdirect gia: OK") -and ($logA -match "XONG, may chu on") -and ($logA -match "netcheck gia"))
  $sumF = Join-Path ([Environment]::GetFolderPath("CommonDesktopDirectory")) "CloudBlue-may-chu.txt"
  $sumT = ""
  if (Test-Path $sumF) { $sumT = Get-Content -Raw $sumF }
  Ck "A: thay may chu tren web -> tom tat ghi DA LEN WEB + cong modem TCP 8197 (tep CloudBlue-may-chu.txt tren Desktop)" (($sumT -match "win9") -and ($sumT -match "DA LEN WEB") -and ($sumT -match "TCP 8197") -and ($logA -match "XONG win9")) ($sumT -replace '\s+', ' ')
  $kA = Read-KV (Join-Path $ISO "may-chu.conf")
  $kS = Read-KV (Join-Path $SRC "may-chu.conf")
  Ck "A: xong thi xoa khoa bi mat khoi tep cau hinh ISO (ca ban trong thu muc bo cai); so ghi done" (($kA["SUPABASE_SERVICE_KEY"] -eq "") -and ($kA["CF_API_TOKEN"] -eq "") -and ($kS["SUPABASE_SERVICE_KEY"] -eq "") -and ($kS["CF_API_TOKEN"] -eq "") -and ($stA.done -eq 1) -and ($stA.n -eq 9) -and ($stA.emu_new -eq 0))
  Ck "A: nhat ky KHONG chua khoa Supabase / ma Cloudflare / ma chay duong ham" ((-not $logA.Contains($SbGood)) -and (-not $logA.Contains($CfTok)) -and (-not ($logA -match 'T0KEN')))

  Ck "A (23.11k): ISO co ma may chu -> GIU 2 tac vu cua phan mem CloudBlue PC (de dieu khien may chu tu xa), bao dau bam cua ma len web, nhat ky khong lo ma" ((($pcT -join ",") -eq "Ready,Ready") -and (@($msA.srv_keys).Count -eq 1) -and ($msA.srv_keys[0].hash -eq (Get-TextSha $srvA)) -and ($logA -match "da bao ma may chu len web") -and (-not $logA.Contains($srvA))) (($pcT -join ",") + " | khoa web: " + @($msA.srv_keys).Count)

  # ---- B. ten go trung may chu dang chay (win8) + khong ai tra loi -> tu lay so ke tiep
  New-Case "b" "win8" $true
  $WantNode = "win9"
  foreach ($tn in @("CloudBluePC Agent", "CloudBluePC Watch")) { Enable-ScheduledTask -TaskName $tn -ErrorAction SilentlyContinue | Out-Null }
  Main | Out-Null
  $pcT2 = @(@("CloudBluePC Agent", "CloudBluePC Watch") | ForEach-Object { "" + (Get-ScheduledTask -TaskName $_ -ErrorAction SilentlyContinue).State })
  Ck "B: may KHONG phai cai tu ISO may chu (khong co role) -> khong dung toi tac vu cua phan mem may PC" (($pcT2 -join ",") -eq "Ready,Ready") ($pcT2 -join ",")
  $cB = Read-KV (Join-Path $B "cloudphone.conf")
  $logB = Get-Content -Raw (Join-Path $B "logs\iso-cai.log")
  Ck "B: win8 dang chay o may khac -> KHONG dung trung; khong ai go -> tu lay so ke tiep win9; gia lap da co thi khong cai lai" (($RC -eq 0) -and ($cB["NODE_ID"] -eq "win9") -and ($logB -match "win8 DANG CHAY o 1 may chu khac") -and ($logB -match "so ke tiep - tu chon") -and (-not ($logB -match "Dang cai MuMu"))) ("RC=" + $RC + " node=" + $cB["NODE_ID"])

  # ---- C. setup.ps1 bao can khoi dong lai -> tu khoi dong lai (ban gia), chua lam cac buoc sau
  New-Case "c" "12" $true
  $WantNode = "win12"
  $env:CB_STUB_REBOOT = "1"
  Main | Out-Null
  $env:CB_STUB_REBOOT = ""
  $cC = Read-KV (Join-Path $B "cloudphone.conf")
  $logC = Get-Content -Raw (Join-Path $B "logs\iso-cai.log")
  Ck "C: go 12 -> win12; setup bao KHOI DONG LAI -> goi khoi dong lai 1 lan, ma tra ve 3, chua dung toi Cloudflare" (($RC -eq 3) -and ($Reboots -eq 1) -and ($logC -match "Ten may chu: win12") -and (-not ($logC -match "7/11 Duong ham"))) ("RC=" + $RC + " reboots=" + $Reboots)
  Ck "C: setup.ps1 khong nhan ra MuMu -> tu ghi cau hinh nhu may-moi.ps1 (win12, phone12 / stream12, cong 8200, thu muc MuMu)" (($cC["NODE_ID"] -eq "win12") -and ($cC["PUBLIC_BASE"] -eq "https://phone12.example.test") -and ($cC["STREAM_WS"] -eq "wss://stream12.example.test/v2/stream") -and ($cC["STREAM_PORT"] -eq "8200") -and ($cC["MUMU_DIR"] -eq $EmuDir) -and ($cC["EMU"] -eq "mumu") -and ($cC["ANDROIDS"] -eq "12,15")) (($cC.Keys | ForEach-Object { $_ + "=" + $cC[$_] }) -join " | ")

  # ---- E. ten go la may chu DANG TAT nhung web con may khach dang thue o do (win5) -> khong cho dung ten do
  New-Case "e" "5" $true
  $WantNode = "win9"
  # ISO may chu BAN CU (truoc 23.11k): co phan mem CloudBlue PC nhung seed.json KHONG kem ma may chu -> cai xong tat 2 tac vu nhu truoc
  Set-Content -Path (Join-Path $CBPC "cb.json") -Value '{"user": "PC", "role": "server", "user_admin": true}' -Encoding ASCII
  New-Dir (Join-Path $CBPC "agent") | Out-Null
  Set-Content -Path (Join-Path $CBPC "agent\pcagent.py") -Value "# gia" -Encoding ASCII
  Set-Content -Path (Join-Path $CBPC "seed.json") -Value '{"name": "x", "label": "5"}' -Encoding ASCII
  foreach ($tn in @("CloudBluePC Agent", "CloudBluePC Watch")) { Enable-ScheduledTask -TaskName $tn -ErrorAction SilentlyContinue | Out-Null }
  Main | Out-Null
  $pcT3 = @(@("CloudBluePC Agent", "CloudBluePC Watch") | ForEach-Object { "" + (Get-ScheduledTask -TaskName $_ -ErrorAction SilentlyContinue).State })
  foreach ($tn in @("CloudBluePC Agent", "CloudBluePC Watch")) { try { Unregister-ScheduledTask -TaskName $tn -Confirm:$false -ErrorAction SilentlyContinue } catch { } }
  $cE = Read-KV (Join-Path $B "cloudphone.conf")
  $logE = Get-Content -Raw (Join-Path $B "logs\iso-cai.log")
  $msE = Get-Mock "/_state"
  Ck "E: ISO may chu ban cu (khong kem ma may chu) -> noi ro khong co dieu khien tu xa, cai xong tat 2 tac vu cua phan mem may PC nhu truoc, khong bao gi len web" ((($pcT3 -join ",") -eq "Disabled,Disabled") -and ($logE -match "ISO nay ban cu, khong kem ma may chu") -and ($logE -match "ISO ban cu, khong co dieu khien tu xa") -and (@($msE.srv_keys).Count -eq 0)) (($pcT3 -join ",") + " | " + @($msE.srv_keys).Count)
  Ck "E: go 5 ma web con 2 may khach dang thue o win5 (may chu do dang tat) -> KHONG dung ten do; khong ai go -> so ke tiep win9" (($RC -eq 0) -and ($cE["NODE_ID"] -eq "win9") -and ($logE -match "Web con 2 may khach dang thue o win5") -and ($logE -match "so ke tiep - tu chon")) ("RC=" + $RC + " node=" + $cE["NODE_ID"])
  $np = @((Get-NodePhones $MockUrl $SbGood 5), (Get-NodePhones $MockUrl $SbGood 8), (Get-NodePhones $MockUrl $SbGood 9), (Get-NodePhones $MockUrl "khoa-sai-000000000000000000000000" 5))
  Ck "Get-NodePhones: dem may khach dang thue theo may chu (khong tinh may da huy); khoa sai -> -1" (($np -join ",") -eq "2,1,0,-1") ($np -join ",")

  # ---- D. ISO khong kem khoa + khong ai go ten -> khong tu chon bua; cho nguoi go (thu: het gio thi dung o do)
  New-Case "d" "" $false
  $WantNode = "win7"
  $script:CfAutoAt = 5
  $script:NameAsk = 0
  function Read-LineWait([string]$prompt, [int]$secs) { $script:NameAsk++; if ($script:NameAsk -ge 3) { return "7" }; return $null }
  Main | Out-Null
  $logD = Get-Content -Raw (Join-Path $B "logs\iso-cai.log")
  $cD = Read-KV (Join-Path $B "cloudphone.conf")
  Ck "D: khong co khoa -> khong biet so ke tiep -> KHONG tu chon, hoi lai cho toi khi co nguoi go (go 7 -> win7)" (($NameAsk -ge 3) -and ($cD["NODE_ID"] -eq "win7") -and ($logD -match "Ten may chu: win7 \(vua go\)") -and (-not ($logD -match "tu chon"))) ("hoi " + $NameAsk + " lan ; node=" + $cD["NODE_ID"])
  Ck "D: ISO khong kem khoa Supabase / ma Cloudflare -> noi ro viec phai lam tay trong bang CloudBlue, cho nguoi cai lam roi di tiep toi XONG" (($RC -eq 0) -and ($logD -match "ISO khong kem khoa Supabase") -and ($logD -match "Noi Cloudflare") -and ($logD -match "Con cho:") -and ($logD -match "XONG win7") -and ($logD -match "bo qua duong thang web")) ("RC=" + $RC)

  # ------------------------------------------------------------------------------------------- 5. firstboot.ps1 that
  Out-Line "== 5. firstboot.ps1 (lenh chay lan dau cua bo cai Windows): chep tep + dung tac vu tu chay quyen Admin"
  $fbRoot = New-Dir (Join-Path $Wk "fb\firstboot.d")
  $fbMc = New-Dir (Join-Path $fbRoot "maychu")
  Copy-Item -LiteralPath $FbPs1 -Destination (Join-Path $fbRoot "90-cloudblue-may-chu.ps1") -Force
  Copy-Item -LiteralPath $McPs1 -Destination (Join-Path $fbMc "may-chu-iso.ps1") -Force
  Set-Content -Path (Join-Path $fbMc "may-chu.conf") -Value @("DOMAIN=example.test", "EMU=mumu") -Encoding ASCII
  $big = [IO.File]::Create((Join-Path $fbMc "mumu-setup.exe")); $big.SetLength(21MB); $big.Close()
  $hadPc = Test-Path "C:\CloudBluePC"
  $hadBlue = Test-Path "C:\blue"
  New-Dir "C:\CloudBluePC" | Out-Null
  Set-Content -Path "C:\CloudBluePC\cb.json" -Value ('{"user": "' + $env:USERNAME + '", "role": "server"}') -Encoding ASCII
  Set-Content -Path "C:\CloudBluePC\seed.json" -Value '{"name": "win9", "label": "win9", "os": "1511", "enroll_key": "cbsv_0123456789abcdef0123456789abcdef01234567", "ticket": "ve-bi-mat-0123456789"}' -Encoding ASCII
  $fbOut = ""
  $fbRc = -1
  try {
    $fbOut = (& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $fbRoot "90-cloudblue-may-chu.ps1") 2>&1 | Out-String)
    $fbRc = $LASTEXITCODE
    $t5 = Get-ScheduledTask -TaskName "CloudBlue cai may chu" -ErrorAction SilentlyContinue
    $t5Arg = ""; $t5Trig = 0; $t5Run = ""; $t5Grp = ""; $t5Usr = ""
    if ($t5) { $t5Arg = "" + $t5.Actions[0].Arguments; $t5Trig = @($t5.Triggers).Count; $t5Run = "" + $t5.Principal.RunLevel; $t5Grp = "" + $t5.Principal.GroupId; $t5Usr = "" + $t5.Principal.UserId + "|" + (@($t5.Triggers | ForEach-Object { "" + $_.UserId }) -join ",") }
    $run5 = "" + (Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name "CloudBlueMayChu" -ErrorAction SilentlyContinue).CloudBlueMayChu
    $fbLog = ""
    try { $fbLog = "" + (Get-Content -Raw -LiteralPath "C:\blue\logs\iso-firstboot.log" -ErrorAction Stop) } catch { $fbLog = "" }
  } finally {
    try { Unregister-ScheduledTask -TaskName "CloudBlue cai may chu" -Confirm:$false -ErrorAction SilentlyContinue } catch { }
    try { Remove-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name "CloudBlueMayChu" -ErrorAction SilentlyContinue } catch { }
  }
  Ck "firstboot.ps1 chay xong ma 0" ($fbRc -eq 0) ("ma " + $fbRc + " : " + ($fbOut -replace '\s+', ' '))
  Ck "chep script + cau hinh + ten may nguoi cai go sang C:\blue\iso; tep lon (bo cai gia lap) KHONG chep" ((Test-Path "C:\blue\iso\may-chu-iso.ps1") -and (Test-Path "C:\blue\iso\may-chu.conf") -and (Test-Path "C:\blue\iso\seed.json") -and (-not (Test-Path "C:\blue\iso\mumu-setup.exe")))
  Ck "tac vu 'CloudBlue cai may chu': quyen cao nhat, theo NHOM Administrators (khong gan ten may / ten tai khoan), 2 moc (luc dang nhap + 3 phut nua), goi may-chu-iso.ps1" (($t5Run -eq "Highest") -and ($t5Grp -match "Administrators|S-1-5-32-544") -and ($t5Trig -eq 2) -and ($t5Arg -match '-File "C:\\blue\\iso\\may-chu-iso\.ps1"') -and (-not $t5Usr.Contains($env:COMPUTERNAME))) ("run=" + $t5Run + " grp=" + $t5Grp + " trig=" + $t5Trig + " usr=" + $t5Usr + " arg=" + $t5Arg)
  Ck "khoa Run cua may (duong tu chay thu 2, moi tai khoan): goi may-chu-iso.ps1 ; co nhat ky iso-firstboot.log" (($run5 -match 'powershell\.exe -NoProfile -ExecutionPolicy Bypass -File "C:\\blue\\iso\\may-chu-iso\.ps1"') -and ($fbLog -match "OK - khoa Run") -and ($fbLog -match "OK - tac vu")) ("run=" + $run5 + " | log=" + ($fbLog -replace '\s+', ' '))
  # Set-AutoStart cua may-chu-iso.ps1: dat lai 2 duong tu chay ; -Remove go sach
  $as1 = Set-AutoStart
  $asT = Get-ScheduledTask -TaskName "CloudBlue cai may chu" -ErrorAction SilentlyContinue
  $asR = "" + (Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name "CloudBlueMayChu" -ErrorAction SilentlyContinue).CloudBlueMayChu
  $asGrp = ""
  if ($asT) { $asGrp = "" + $asT.Principal.GroupId }
  [void](Set-AutoStart -Remove)
  $asT2 = Get-ScheduledTask -TaskName "CloudBlue cai may chu" -ErrorAction SilentlyContinue
  $asR2 = "" + (Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name "CloudBlueMayChu" -ErrorAction SilentlyContinue).CloudBlueMayChu
  Ck "Set-AutoStart: dat du 2 duong tu chay (khoa Run + tac vu nhom Administrators) ; -Remove go sach ca 2" (($as1 -eq 2) -and $asT -and ($asGrp -match "Administrators|S-1-5-32-544") -and ($asR -match "may-chu-iso\.ps1") -and (-not $asT2) -and (-not $asR2)) ("ways=" + $as1 + " grp=" + $asGrp + " run=" + $asR + " sau: " + [bool]$asT2 + "/" + $asR2)
  $num5 = Get-SeedNum "C:\blue\iso\seed.json"
  Ck "ten may nguoi cai go (win9) doc lai duoc tu ban chep" ($num5 -eq 9)
  $seed5 = ""
  try { $seed5 = "" + (Get-Content -Raw -LiteralPath "C:\blue\iso\seed.json" -ErrorAction Stop) } catch { $seed5 = "" }
  $seed5src = "" + (Get-Content -Raw -LiteralPath "C:\CloudBluePC\seed.json")
  Ck "ban chep seed.json sang C:\blue\iso KHONG mang ma may chu / ve dang ky (enroll_key, ticket) ; ban goc cua phan mem CloudBlue PC giu nguyen" (($seed5 -match '"label"') -and ($seed5 -match '"os"') -and (-not ($seed5 -match "cbsv_")) -and (-not ($seed5 -match "enroll_key")) -and (-not ($seed5 -match "ve-bi-mat")) -and ($seed5src -match "cbsv_0123456789abcdef")) ($seed5)
  try { Unregister-ScheduledTask -TaskName "BlueRoblox" -Confirm:$false -ErrorAction SilentlyContinue } catch { }
  if (-not $hadPc) { Remove-Item -Recurse -Force "C:\CloudBluePC" -ErrorAction SilentlyContinue }
  if (-not $hadBlue) { Remove-Item -Recurse -Force "C:\blue" -ErrorAction SilentlyContinue }
} catch {
  $script:FailN++
  Out-Line ("  XX  LOI KHI CHAY THU: " + $_.Exception.Message + "   (dong " + $_.InvocationInfo.ScriptLineNumber + ": " + ("" + $_.InvocationInfo.Line).Trim() + ")")
} finally {
  try { Unregister-ScheduledTask -TaskName "CloudBlue cai may chu" -Confirm:$false -ErrorAction SilentlyContinue } catch { }
  if ($Srv) { try { Stop-Process -Id $Srv.Id -Force -ErrorAction SilentlyContinue } catch { } }
  try { Write-Summary } catch { Write-Host ("khong ghi duoc tom tat: " + $_) }
}
exit 0
