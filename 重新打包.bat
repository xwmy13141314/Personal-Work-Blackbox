@echo off
chcp 65001 >nul 2>&1
title 重新打包 WorkTrace.exe

:: 切换到脚本所在目录
cd /d "%~dp0"

echo ========================================
echo  正在重新打包 WorkTrace.exe
echo ========================================
echo.

:: 检查 PyInstaller
python -c "import PyInstaller" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo 正在安装 PyInstaller...
    pip install pyinstaller
    echo.
)

:: 清理旧的 build 目录
if exist "build" rmdir /s /q "build"

:: 执行打包
echo 开始打包...
pyinstaller blackbox.spec --noconfirm

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo  打包成功！
    echo  输出: dist\WorkTrace.exe
    echo ========================================
) else (
    echo.
    echo ========================================
    echo  打包失败，请检查上方错误信息
    echo ========================================
)
pause
