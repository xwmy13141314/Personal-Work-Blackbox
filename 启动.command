#!/bin/bash
# 职迹 WorkTrace macOS 启动脚本
# 双击本文件即可启动（需先赋予执行权限：chmod +x 启动.command）

# 切换到脚本所在目录（项目根）
cd "$(dirname "$0")" || exit 1

# 选择 Python（优先 python3）
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "未找到 Python，请先安装 Python 3.11+（推荐 brew install python）"
    echo "按回车键退出..."
    read
    exit 1
fi

# 检查关键依赖，缺失则自动安装
if ! "$PYTHON" -c "import pywebview, AppKit, Quartz" >/dev/null 2>&1; then
    echo "检测到依赖缺失，正在安装依赖（requirements-mac.txt）..."
    "$PYTHON" -m pip install -r requirements-mac.txt
fi

# 启动 Web GUI（默认）
echo "启动职迹 WorkTrace..."
"$PYTHON" -m src.main
