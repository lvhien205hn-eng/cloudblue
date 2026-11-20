@echo off
rem =====================================================================================
rem  CloudBlue PC - CAI LAI MAY NAY ngay tu trong Windows (khong can USB).
rem  Cach dung: mo file ISO CloudBlue (bam dup), roi bam dup file CAI-DAT.cmd nay.
rem  Viec lam: tao phan vung cuu ho, chep bo cai vao, khoi dong lai vao bo cai -> XOA va cai Windows moi.
rem =====================================================================================
setlocal
fltmc >nul 2>&1
if not errorlevel 1 goto admin
echo  Dang xin quyen Admin...
powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
exit /b
:admin
if not exist "%~dp0cb\py\python.exe" goto thieu
"%~dp0cb\py\python.exe" -I -B "%~dp0cb\os\cb_stage.py" "%~dp0."
echo.
pause
exit /b
:thieu
echo.
echo  !! Thieu %~dp0cb\py\python.exe - day khong phai bo cai CloudBlue day du.
pause
exit /b 1
