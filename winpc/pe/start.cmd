@echo off
rem =====================================================================================
rem  CloudBlue PC - goi bo cai tu dong (cb_pe.py) TRUOC bo cai Windows goc.
rem  Duoc goi boi:   winpeshl.ini trong boot.wim          ->  start.cmd winpeshl
rem          hoac:   autounattend.xml (RunSynchronous)     ->  start.cmd
rem  cb_pe.py thoat 0 / 10 -> khoi dong lai  ;  3 hoac loi -> chay bo cai Windows goc nhu binh thuong
rem =====================================================================================
setlocal
set "CBMODE=%~1"
if exist "%SystemDrive%\cb-ran.flag" goto fallback
echo ran> "%SystemDrive%\cb-ran.flag"
set "CBPY=%~dp0..\py\python.exe"
if not exist "%CBPY%" goto nopy
title CloudBlue PC
rem  Thay vo (shell) cua WinPE thi khong ai goi wpeinit ho: goi truoc de nap du o cung / USB / mang roi moi do o dia.
if /i "%CBMODE%"=="winpeshl" (
  echo  CloudBlue PC: dang nap thiet bi...
  wpeinit
)
"%CBPY%" -I -B -u "%~dp0cb_pe.py"
set "CBRC=%ERRORLEVEL%"
if "%CBRC%"=="0" goto reboot
if "%CBRC%"=="10" goto reboot
if "%CBRC%"=="3" goto fallback
echo.
echo  !! Bo cai CloudBlue thoat voi ma %CBRC% - co the Python khong chay duoc trong moi truong cai dat nay.
echo     Chup man hinh nay gui ho tro. Bam phim bat ky de chuyen sang bo cai Windows thuong.
pause >nul
goto fallback
:nopy
echo.
echo  !! Khong thay %CBPY%
echo     Bam phim bat ky de chuyen sang bo cai Windows thuong.
pause >nul
:fallback
if /i not "%CBMODE%"=="winpeshl" exit /b 0
if exist "%SystemDrive%\setup.exe" goto setup1
if exist "%SystemDrive%\sources\setup.exe" goto setup2
cmd.exe
exit /b 0
:setup1
"%SystemDrive%\setup.exe"
exit /b 0
:setup2
"%SystemDrive%\sources\setup.exe"
exit /b 0
:reboot
wpeutil reboot
pause >nul
exit /b 0
