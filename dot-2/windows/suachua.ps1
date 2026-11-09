# =====================================================================
#  suachua.ps1 — SỬA TOÀN BỘ khi MEmu kẹt / máy đen màn / kẹt 99% / adb offline
#  Chạy (PowerShell quyền Admin):
#     Set-ExecutionPolicy -Scope Process Bypass -Force; & C:\blue\suachua.ps1
#  Làm: tắt dịch vụ BlueRoblox → tắt hẳn MEmu → trả mọi máy về cài đặt đồ hoạ an toàn
#        → gỡ khoá kẹt → KHỞI ĐỘNG LẠI WINDOWS (để driver card & ảo hoá sạch hẳn)
# =====================================================================
$B = "C:\blue"
$MEMU = @("C:\Program Files\Microvirt\MEmu", "D:\Program Files\Microvirt\MEmu", "C:\Microvirt\MEmu", "D:\Microvirt\MEmu") | Where-Object { Test-Path "$_\memuc.exe" } | Select-Object -First 1
$mc = "$MEMU\memuc.exe"
function Ok($m) { Write-Host "  [OK] $m" -ForegroundColor Green }
function Step($m) { Write-Host "`n== $m ==" -ForegroundColor Cyan }

Step "1/6 Tat dich vu BlueRoblox (bang dieu khien, cloudphoned, cpapi, ws-scrcpy)"
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*$B*" -and $_.ProcessId -ne $PID -and $_.Name -notlike "powershell*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host "   tat $($_.Name) #$($_.ProcessId)" }
Ok "da tat"

Step "2/6 Tat het may MEmu dang chay"
& $mc stopall 2>$null | Out-Null; Start-Sleep 5
Ok "stopall"

Step "3/6 Tat han tien trinh MEmu bi ket + adb"
foreach ($n in "MEmuConsole", "MEmuHeadless", "MEmu", "MemuService", "MEmuSVC", "memuc", "adb") {
  Get-Process -Name $n -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue }
Start-Sleep 3
Ok "da tat"

Step "4/6 Go khoa ket"
Remove-Item "$B\redroid\*.lock", "$B\*.lock" -Force -ErrorAction SilentlyContinue
Ok "da go"

Step "5/6 Dat moi may ve cai dat do hoa CHUAN (DirectX + GPU memory optimization: muot nhat)"
$vms = (& $mc listvms) | Where-Object { $_ -match '^\d+,' }
foreach ($l in $vms) {
  $i = ($l -split ',')[0]; $nm = ($l -split ',')[1]
  & $mc setconfigex -i $i graphics_render_mode 1 | Out-Null
  & $mc setconfigex -i $i gmem_opt 1 | Out-Null
  Write-Host "   #$i $nm -> DirectX, gmem_opt 1" }
# máy mới cũng dùng cài đặt an toàn cho tới khi thử xong; bỏ chép cài đặt từ máy mẫu
$cf = "$B\cloudphone.conf"
if (Test-Path $cf) {
  $t = Get-Content $cf -Encoding UTF8 | Where-Object { $_ -notmatch '^\s*(MEMU_GMEM_OPT|MEMU_RENDER)\s*=' } |
       ForEach-Object { if ($_ -match '^\s*MEMU_TEMPLATE\s*=') { "#" + $_ } else { $_ } }
  $t += "MEMU_GMEM_OPT=1"; $t += "MEMU_RENDER=1"
  $t | Set-Content -Encoding utf8 $cf }
Ok "xong ($($vms.Count) may)"

Step "6/6 Khoi dong lai Windows"
Write-Host "Can khoi dong lai de driver card NVIDIA va phan ao hoa cua MEmu sach han." -ForegroundColor Yellow
Write-Host "Sau khi bat lai, bang BlueRoblox tu chay va tu bat may khach." -ForegroundColor Yellow
$a = Read-Host "Go Y roi Enter de khoi dong lai NGAY (Enter khong de huy)"
if ($a -match '^[Yy]') { Restart-Computer -Force } else { Write-Host "Chua khoi dong lai. Nho khoi dong lai may tinh truoc khi dung." -ForegroundColor Red }
