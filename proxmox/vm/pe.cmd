@echo off
rem CloudBlue - ISO MAY MAU VPS ao hoa: chia o dia 0 TRUOC khi bo cai Windows chep file (chay trong WinPE: autounattend.xml > windowsPE > RunSynchronous).
rem   BIOS (SeaBIOS) : phan vung 1 = System 100 MB (active), phan vung 2 = Windows
rem   UEFI (OVMF)    : phan vung 1 = EFI 100 MB,             phan vung 2 = Windows
rem   File tra loi cai Windows vao O 0 - PHAN VUNG 2 (ca 2 kieu). Phan vung Windows nam CUOI o (sau nay noi o duoc).
rem   XOA SACH o dia 0 - chi dung cho may ao mau moi tao.
rem   Nhat ky: X:\cbvm-pe.log (o RAM cua bo cai) + ban chep W:\cbvm-pe.log (o Windows moi, sau khi cai la C:\cbvm-pe.log)
setlocal
set "D=%~d0"
set "L=X:\cbvm-pe.log"
echo CloudBlue may mau (pe.cmd 26.11a): nap driver o dia VirtIO + chia o dia 0 > "%L%"
for %%f in ("%D%\$WinPEDriver$\vioscsi\*.inf" "%D%\$WinPEDriver$\viostor\*.inf") do drvload "%%~f" >> "%L%" 2>&1

rem --- driver vua nap: Windows can vai giay moi thay o dia, nen cho o dia 0 hien ra (toi da ~2 phut) roi moi chia
> X:\cbvm-ls.txt echo rescan
>> X:\cbvm-ls.txt echo list disk
set N=0
:cho
diskpart /s X:\cbvm-ls.txt > X:\cbvm-ls.out 2>&1
find /i "Disk 0" X:\cbvm-ls.out > nul 2>&1
if not errorlevel 1 goto co
set /a N+=1
if %N% geq 40 goto co
call :ngu
goto cho
:co
echo cho o dia 0: %N% lan >> "%L%"
type X:\cbvm-ls.out >> "%L%" 2>&1
wpeutil UpdateBootInfo >> "%L%" 2>&1
set "FW=0x1"
for /f "tokens=3" %%a in ('reg query HKLM\System\CurrentControlSet\Control /v PEFirmwareType 2^>nul ^| find /i "PEFirmwareType"') do set "FW=%%a"
set "DP=%D%\cbvm\bios.txt"
if /i "%FW%"=="0x2" set "DP=%D%\cbvm\uefi.txt"

rem --- chia o (loi thi thu lai toi da 3 lan)
set T=1
:chia
echo firmware %FW% - diskpart /s %DP% - lan %T% >> "%L%"
diskpart /s "%DP%" >> "%L%" 2>&1
if not errorlevel 1 goto xong
echo diskpart bao loi >> "%L%"
set /a T+=1
if %T% gtr 3 goto xong
call :ngu
call :ngu
goto chia
:xong
> X:\cbvm-ls.txt echo list disk
>> X:\cbvm-ls.txt echo list volume
>> X:\cbvm-ls.txt echo select disk 0
>> X:\cbvm-ls.txt echo list partition
diskpart /s X:\cbvm-ls.txt >> "%L%" 2>&1
if exist W:\ copy /y "%L%" W:\cbvm-pe.log > nul 2>&1
exit /b 0

rem --- nghi 1-2 giay (WinPE khong co timeout.exe; ping co the chua co mang): cho so giay cua dong ho doi 2 lan
:ngu
set "S=%time:~6,2%"
:ngu1
if "%time:~6,2%"=="%S%" goto ngu1
set "S=%time:~6,2%"
:ngu2
if "%time:~6,2%"=="%S%" goto ngu2
exit /b 0
