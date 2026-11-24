@echo off
rem CloudBlue - ISO MAY MAU VPS ao hoa: chia o dia 0 TRUOC khi bo cai Windows chep file (chay trong WinPE: autounattend.xml > windowsPE > RunSynchronous).
rem   BIOS (SeaBIOS) : 1 phan vung NTFS (active)          UEFI (OVMF) : EFI 100 MB + MSR 16 MB + Windows
rem   XOA SACH o dia 0 - chi dung cho may ao mau moi tao. Nhat ky: X:\cbvm-pe.log (o RAM cua bo cai)
setlocal
set "D=%~d0"
echo CloudBlue may mau: nap driver o dia VirtIO + chia o dia 0 > X:\cbvm-pe.log
for %%f in ("%D%\$WinPEDriver$\vioscsi\*.inf" "%D%\$WinPEDriver$\viostor\*.inf") do drvload "%%~f" >> X:\cbvm-pe.log 2>&1
wpeutil UpdateBootInfo >> X:\cbvm-pe.log 2>&1
set "FW=0x1"
for /f "tokens=3" %%a in ('reg query HKLM\System\CurrentControlSet\Control /v PEFirmwareType 2^>nul ^| find /i "PEFirmwareType"') do set "FW=%%a"
set "DP=%D%\cbvm\bios.txt"
if /i "%FW%"=="0x2" set "DP=%D%\cbvm\uefi.txt"
echo firmware %FW% - diskpart /s %DP% >> X:\cbvm-pe.log
diskpart /s "%DP%" >> X:\cbvm-pe.log 2>&1
exit /b 0
