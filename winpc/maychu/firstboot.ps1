# cloudblue-may-chu-firstboot
# =====================================================================================================
#  Chay 1 LAN luc Windows vua cai tu "ISO may chu CloudBlue" (bo cai Windows goi: os\firstboot.d) - co the chay bang tai khoan
#  SYSTEM (truoc khi ai dang nhap) hoac bang tai khoan cua may.
#  Viec: chep cau hinh + script cai may chu (thu muc maychu ben canh) sang C:\blue\iso, giu lai TEN MAY nguoi cai da go,
#  roi dat 2 DUONG TU CHAY may-chu-iso.ps1 moi lan co nguoi dang nhap, cho toi khi cai xong:
#     (1) khoa Run cua may (moi tai khoan)      (2) tac vu "CloudBlue cai may chu" theo NHOM Administrators (+ 3 phut nua)
#  Ca 2 KHONG gan voi ten may / ten tai khoan: bo cai Windows con DOI TEN MAY sau buoc nay, tac vu gan kieu "TENMAY\taikhoan"
#  (ban 23.11g-h) khong chay lai sau khi may doi ten -> may dung o man hinh nen, khong tu cai tiep.
#  Khong in khoa bi mat nao. Nhat ky: C:\blue\logs\iso-firstboot.log
# =====================================================================================================
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$from = Join-Path $here 'maychu'
$to = 'C:\blue\iso'
$task = 'CloudBlue cai may chu'
New-Item -ItemType Directory -Force 'C:\blue', 'C:\blue\logs', $to | Out-Null
function Note-Line([string]$m) {
  Write-Host ('  ' + $m)
  try { Add-Content -LiteralPath 'C:\blue\logs\iso-firstboot.log' -Value ((Get-Date -Format 'dd/MM HH:mm:ss') + ' ' + $m) -Encoding UTF8 -ErrorAction Stop } catch {}
}
Note-Line ('firstboot may chu: tai khoan chay = ' + $env:USERNAME + ' | ten may luc nay = ' + $env:COMPUTERNAME)
foreach ($f in @(Get-ChildItem -LiteralPath $from -File -ErrorAction SilentlyContinue | Where-Object { $_.Length -lt 20MB })) {
  try { Copy-Item -LiteralPath $f.FullName -Destination (Join-Path $to $f.Name) -Force -ErrorAction Stop } catch { Note-Line ('(!) chua chep duoc ' + $f.Name) }
}
# seed.json: chi giu TEN MAY nguoi cai da go - KHONG chep ma may chu / ve dang ky (enroll_key, ticket) sang C:\blue\iso
try {
  $sj = Get-Content -Raw -LiteralPath 'C:\CloudBluePC\seed.json' -ErrorAction Stop | ConvertFrom-Json
  $keep = @{}
  foreach ($pp in $sj.PSObject.Properties) { if (@('enroll_key', 'ticket') -notcontains $pp.Name) { $keep[$pp.Name] = $pp.Value } }
  [IO.File]::WriteAllText((Join-Path $to 'seed.json'), ($keep | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding($false)))
} catch {}
$run = Join-Path $to 'may-chu-iso.ps1'
if (-not (Test-Path -LiteralPath $run)) { Note-Line '(!) ISO thieu may-chu-iso.ps1 - khong dat duoc duong tu chay'; exit 1 }
$argLine = '-NoProfile -ExecutionPolicy Bypass -File "' + $run + '"'
$okWays = 0
try {
  New-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run' -Name 'CloudBlueMayChu' -Value ('powershell.exe ' + $argLine) -PropertyType String -Force -ErrorAction Stop | Out-Null
  $okWays++
  Note-Line 'OK - khoa Run: tu chay moi lan co nguoi dang nhap'
} catch { Note-Line ('(!) chua dat duoc khoa Run: ' + $_.Exception.Message) }
$a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argLine -WorkingDirectory 'C:\blue'
$t1 = New-ScheduledTaskTrigger -AtLogOn
$t2 = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(3))
$st = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$made = $false
foreach ($grp in @('S-1-5-32-544', 'BUILTIN\Administrators')) {
  if ($made) { break }
  try {
    $pr = New-ScheduledTaskPrincipal -GroupId $grp -RunLevel Highest
    Register-ScheduledTask -TaskName $task -Action $a -Trigger @($t1, $t2) -Principal $pr -Settings $st -Force -ErrorAction Stop | Out-Null
    $made = $true
    $okWays++
    Note-Line ('OK - tac vu "' + $task + '" (nhom Administrators, quyen cao nhat): luc dang nhap + 3 phut nua')
  } catch { Note-Line ('(!) chua tao duoc tac vu voi nhom ' + $grp + ': ' + $_.Exception.Message) }
}
if ($okWays -eq 0) {
  try {
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut((Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\StartUp\CloudBlue-cai-may-chu.lnk'))
    $lnk.TargetPath = 'powershell.exe'; $lnk.Arguments = $argLine; $lnk.WorkingDirectory = 'C:\blue'; $lnk.Save()
    Note-Line 'OK - loi tat Startup (duong du phong)'
  } catch { Note-Line ('(!) khong dat duoc duong tu chay nao: ' + $_.Exception.Message) }
}
exit 0
