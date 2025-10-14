@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "JAR=%SCRIPT_DIR%TailViewer.jar"

if not exist "%JAR%" (
  echo %JAR% not found alongside script.
  exit /b 1
)

set HAS_CLI=false
for %%A in (%*) do (
  if /I "%%~A"=="--cli" set HAS_CLI=true
)

if /I "%HAS_CLI%"=="false" (
  java -jar "%JAR%" --cli %*
) else (
  java -jar "%JAR%" %*
)

endlocal

