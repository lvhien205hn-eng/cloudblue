@echo off
rem keep.bat - chay lai chuong trinh neu bi tat
:a
%*
echo [%date% %time%] chuong trinh dung, chay lai sau 5 giay...
timeout /t 5 /nobreak >nul
goto a
