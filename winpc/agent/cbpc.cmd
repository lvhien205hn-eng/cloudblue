@echo off
rem CloudBlue PC - lenh tai may (mo PowerShell / CMD bang quyen Admin):
rem    cbpc status                              xem may da dang ky chua, ket noi ra sao
rem    cbpc reinstall 22h2 all^|disk^|system     cai lai / doi Windows ngay tai may
rem    cbpc enroll                              dang ky lai
rem    cbpc log                                 xem nhat ky agent
"C:\CloudBluePC\py\python.exe" -I -B "C:\CloudBluePC\agent\pcagent.py" %*
