@echo off
rem CloudBlue PC - cai dat lan dau trong Windows moi. Goi boi unattend.xml:  provision.cmd specialize | firstlogon
rem Luon thoat ma 0 de khong bao gio lam hong buoc cai Windows. Nhat ky: C:\CloudBluePC\logs\provision.log
rem Thu muc C:\CloudBluePC bi khoa quyen (chi SYSTEM + Administrators): neu nguoi goi khong ghi duoc vao logs thi ghi nhat ky vao ho so cua ho.
set "CBLOG=C:\CloudBluePC\logs"
if not exist "%CBLOG%" mkdir "%CBLOG%" >nul 2>&1
(echo.>>"%CBLOG%\provision.out") 2>nul || set "CBLOG=%LOCALAPPDATA%\CloudBluePC"
if not exist "%CBLOG%" mkdir "%CBLOG%" >nul 2>&1
"C:\CloudBluePC\py\python.exe" -I -B "C:\CloudBluePC\os\cb_provision.py" %* >> "%CBLOG%\provision.out" 2>&1
exit /b 0
