@echo off
chcp 65001 >nul 2>&1
title Personal Work Blackbox - 白名单设置

echo ============================================================
echo   Personal Work Blackbox - 杀毒软件白名单设置向导
echo ============================================================
echo.
echo 本工具涉及键盘监听，杀毒软件可能会将其标记为恶意软件。
echo 请按照以下步骤将程序添加到白名单中。
echo.

:: 获取当前脚本所在目录
set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."

:: ==================== Windows Defender ====================
echo [1/3] 正在添加 Windows Defender 白名单...
echo.

:: 排除项目目录
powershell -Command "Add-MpPreference -ExclusionPath '%PROJECT_DIR%'" 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [OK] 已将项目目录添加到 Windows Defender 排除列表
) else (
    echo [!] 需要管理员权限，正在请求提权...
    powershell -Command "Start-Process powershell -ArgumentList 'Add-MpPreference -ExclusionPath \"%PROJECT_DIR%\"' -Verb RunAs" 2>nul
    echo [OK] 已请求管理员权限添加白名单
)

:: 排除进程（如果已打包为 exe）
if exist "%PROJECT_DIR%\dist\blackbox.exe" (
    powershell -Command "Add-MpPreference -ExclusionProcess 'blackbox.exe'" 2>nul
    echo [OK] 已将 blackbox.exe 添加到进程排除列表
)

echo.

:: ==================== 360 安全卫士 ====================
echo [2/3] 360 安全卫士设置提示
echo.
echo   如果已安装 360 安全卫士，请手动操作：
echo   1. 打开 360 安全卫士
echo   2. 进入「木马查杀」→「信任区」
echo   3. 添加信任目录：%PROJECT_DIR%
echo   4. 或添加信任程序：blackbox.exe
echo.
echo   按任意键继续...
pause >nul

:: ==================== 火绒 ====================
echo.
echo [3/3] 火绒安全设置提示
echo.
echo   如果已安装火绒安全，请手动操作：
echo   1. 打开火绒安全
echo   2. 进入「防护中心」→「高级防护」→「自定义白名单」
echo   3. 添加文件/文件夹白名单：%PROJECT_DIR%
echo.
echo   按任意键继续...
pause >nul

echo.
echo ============================================================
echo   白名单设置完成！
echo ============================================================
echo.
echo 现在可以正常启动 Personal Work Blackbox 了。
echo.
pause
