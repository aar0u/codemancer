@echo off
setlocal enabledelayedexpansion
set "logfile=%~1"
if "%logfile%"=="" set "logfile=%cd%\sample.log"
:loop
set /a rnd=%random%
echo [%date% %time%] Random log entry: !rnd! >> "%logfile%"
timeout /t 1 >nul
goto loop