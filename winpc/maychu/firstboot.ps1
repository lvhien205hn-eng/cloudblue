# cloudblue-may-chu-firstboot
# =====================================================================================================
#  Chay 1 LAN o lan dang nhap dau cua Windows vua cai tu "ISO may chu CloudBlue" (bo cai Windows goi: os\firstboot.d).
#  Viec: chep cau hinh + script cai may chu (thu muc maychu ben canh) sang C:\blue\iso, giu lai TEN MAY nguoi cai da go,
#  dung tac vu "CloudBlue cai may chu": chay may-chu-iso.ps1 quyen Admin moi lan dang nhap (va 3 phut nua) cho toi khi cai xong.
#  Khong in khoa bi mat nao.
# =====================================================================================================
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$from = Join-Path $here 'maychu'
$to = 'C:\blue\iso'
$task = 'CloudBlue cai may chu'
New-Item -ItemType Directory -Force 'C:\blue', 'C:\blue\logs', $to | Out-Null
foreach ($f in @(Get-ChildItem -LiteralPath $from -File -ErrorAction SilentlyContinue | Where-Object { $_.Length -lt 20MB })) {
  try { Copy-Item -LiteralPath $f.FullName -Destination (Join-Path $to $f.Name) -Force -ErrorAction Stop } catch { Write-Host ('  (!) chua chep duoc ' + $f.Name) }
}
try { Copy-Item -LiteralPath 'C:\CloudBluePC\seed.json' -Destination (Join-Path $to 'seed.json') -Force -ErrorAction Stop } catch {}
$run = Join-Path $to 'may-chu-iso.ps1'
if (-not (Test-Path -LiteralPath $run)) { Write-Host '  (!) ISO thieu may-chu-iso.ps1 - khong dung duoc tac vu cai may chu'; exit 1 }
$user = ''
try { $user = "" + (Get-Content -Raw -LiteralPath 'C:\CloudBluePC\cb.json' -ErrorAction Stop | ConvertFrom-Json).user } catch {}
if (-not $user) { $user = $env:USERNAME }
$who = $env:COMPUTERNAME + '\' + $user
try {
  $a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -ExecutionPolicy Bypass -File "' + $run + '"') -WorkingDirectory 'C:\blue'
  $t1 = New-ScheduledTaskTrigger -AtLogOn -User $who
  $t2 = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(3))
  $pr = New-ScheduledTaskPrincipal -UserId $who -LogonType Interactive -RunLevel Highest
  $st = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
  Register-ScheduledTask -TaskName $task -Action $a -Trigger @($t1, $t2) -Principal $pr -Settings $st -Force -ErrorAction Stop | Out-Null
  Write-Host ('  OK - tac vu "' + $task + '" (tai khoan ' + $who + '): tu cai may chu Cloud Phone sau khi Windows cai xong')
} catch {
  Write-Host ('  (!) chua tao duoc tac vu (' + $_.Exception.Message + ') -> dung loi tat tu chay thay the')
  try {
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut((Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\StartUp\CloudBlue-cai-may-chu.lnk'))
    $lnk.TargetPath = 'powershell.exe'; $lnk.Arguments = ('-NoProfile -ExecutionPolicy Bypass -File "' + $run + '"'); $lnk.WorkingDirectory = 'C:\blue'; $lnk.Save()
  } catch {}
}
exit 0
