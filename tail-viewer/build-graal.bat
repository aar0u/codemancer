@echo off
echo ========================================
echo IMPORTANT: Run meta.bat first to create ni_config folder!
echo ========================================
echo.

if not exist "dist\TailViewer.jar" call gen-jar.bat

set graalvm=D:\dev\_sdks\graalvm-community-openjdk-25+37.1

if not exist "dist\lib" mkdir dist\lib
copy /Y "%graalvm%\lib\fontconfig.bfc" dist\lib\fontconfig.bfc

call %graalvm%\bin\native-image.cmd -Djava.awt.headless=false -H:ConfigurationFileDirectories=ni-config ^
--initialize-at-run-time=sun.awt.Win32FontManager ^
-o dist\TailViewer ^
-jar dist\TailViewer.jar

if errorlevel 1 (
    echo native-image failed, exiting...
    pause
    exit /b 1
)
