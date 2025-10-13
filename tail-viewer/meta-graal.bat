@echo off
echo ========================================
echo GRAALVM NATIVE IMAGE AGENT MODE
echo ========================================
echo.
echo IMPORTANT: This will run the application with GraalVM agent
echo to collect metadata for native image compilation.
echo.
echo Please perform as many actions as possible to help GraalVM
echo gather comprehensive information about your application:
echo.
echo - Open different log files by dragging them
echo - Use all UI controls (buttons, text fields)
echo - Test different file operations
echo - Try various application features
echo - Navigate through all menus and dialogs
echo - Resize the window (minimize, maximize, restore)
echo.
echo The more actions you perform, the better the native image
echo will work. When done, close the application normally.
echo.
echo ========================================
echo.

if not exist "dist\TailViewer.jar" call gen-jar.bat

set graalvm=D:\dev\_sdks\graalvm-community-openjdk-25+37.1

echo Starting application with GraalVM agent...
echo.

%graalvm%\bin\java.exe -agentlib:native-image-agent=config-output-dir=ni-config -jar dist\TailViewer.jar

echo.
echo ========================================
echo Agent run completed!
echo Check ni-config folder for generated metadata.
echo ========================================
pause
