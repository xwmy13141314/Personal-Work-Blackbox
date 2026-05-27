@echo off
chcp 65001 >nul 2>&1
title Personal Work Blackbox - 开机自启设置

echo ============================================================
echo   Personal Work Blackbox - 开机自启注册
echo ============================================================
echo.

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

:: 检测启动方式
if exist "%PROJECT_DIR%\dist\blackbox.exe" (
    set "TARGET=%PROJECT_DIR%\dist\blackbox.exe"
    echo 检测到打包版本: %TARGET%
) else (
    set "TARGET=pythonw"
    set "ARGS=%PROJECT_DIR%\src\main.py"
    echo 检测到源码版本，使用 pythonw 启动
)

:: 创建启动脚本
set "STARTUP_SCRIPT=%STARTUP_FOLDER%\start_blackbox.bat"

echo @echo off > "%STARTUP_SCRIPT%"
echo start "" /B "%TARGET%" %ARGS% >> "%STARTUP_SCRIPT%"

echo.
echo [OK] 已创建启动脚本: %STARTUP_SCRIPT%
echo.
echo Personal Work Blackbox 将在下次开机时自动启动。
echo.
echo 如需取消自启，删除以下文件即可：
echo   %STARTUP_SCRIPT%
echo.
pause
