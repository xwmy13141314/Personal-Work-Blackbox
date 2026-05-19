@echo off
chcp 65001 >nul 2>&1
title Personal Work Blackbox

:: 切换到脚本所在目录
cd /d "%~dp0"

:: 检查 Python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] 未检测到 Python，请先安装 Python 3.11+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 检查依赖
python -c "import pynput" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo 正在安装依赖...
    pip install -r requirements.txt
    echo.
)

:: 启动 GUI
echo 正在启动 Personal Work Blackbox...
python -m src.main --gui
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] 程序异常退出，错误码: %ERRORLEVEL%
    echo 请检查上方错误信息，常见原因:
    echo   1. 缺少依赖 → 运行: pip install -r requirements.txt
    echo   2. 杀毒软件拦截 pynput → 将本程序加入白名单
    pause
)
