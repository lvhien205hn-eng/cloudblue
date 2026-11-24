@echo off
rem CloudBlue - MAY MAU VPS ao hoa: Windows vua cai xong (chay bang SYSTEM, truoc man hinh dang nhap) -> buoc 1 cua maymau.ps1:
rem   driver virtio, QEMU guest agent, (2012 R2) ban va Universal C Runtime, tai khoan khach + tu dang nhap, tac vu chay buoc 2.
rem Luon thoat ma 0 de khong lam hong buoc cai Windows. Nhat ky: C:\CloudBluePC\logs\maymau.log
if not exist "C:\CloudBluePC\logs" mkdir "C:\CloudBluePC\logs" >nul 2>&1
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "C:\CloudBluePC\vm\maymau.ps1" -Buoc 1 >> "C:\CloudBluePC\logs\maymau.out" 2>&1
exit /b 0
