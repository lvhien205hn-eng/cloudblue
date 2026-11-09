@echo off
rem start-blue.bat - bat toan bo BlueRoblox tren Windows
cd /d C:\blue
set PY="C:\Program Files\Python312\python.exe"
set PATH=C:\blue\platform-tools;%PATH%
C:\blue\platform-tools\adb.exe start-server
start "BR ws-scrcpy" /min /d C:\blue\ws-scrcpy\dist cmd /c C:\blue\keep.bat node index.js
timeout /t 3 /nobreak >nul
start "BR cpapi" /min /d C:\blue cmd /c C:\blue\keep.bat %PY% run.py cpapi.py
start "BR cloudphoned" /min /d C:\blue cmd /c C:\blue\keep.bat %PY% run.py cloudphoned.py
echo BlueRoblox da chay: 3 cua so thu nho (ws-scrcpy, cpapi, cloudphoned).
