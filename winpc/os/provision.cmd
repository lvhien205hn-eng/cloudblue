@echo off
rem CloudBlue PC - cai dat lan dau trong Windows moi. Goi boi unattend.xml:  provision.cmd specialize | firstlogon
rem Luon thoat ma 0 de khong bao gio lam hong buoc cai Windows. Nhat ky: C:\CloudBluePC\logs\provision.log
if not exist "C:\CloudBluePC\logs" mkdir "C:\CloudBluePC\logs" >nul 2>&1
"C:\CloudBluePC\py\python.exe" -I -B "C:\CloudBluePC\os\cb_provision.py" %* >> "C:\CloudBluePC\logs\provision.out" 2>&1
exit /b 0
