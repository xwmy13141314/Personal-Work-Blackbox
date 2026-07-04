#!/bin/bash
# 安装 WorkTrace：拷贝 .app 到 ~/Applications + 配置登录启动（LaunchAgent）
# 用法：bash scripts/install.sh
set -e

cd "$(dirname "$0")/.."

APP_SOURCE="dist/WorkTrace.app"
APP_DIR="$HOME/Applications"
APP_DEST="$APP_DIR/WorkTrace.app"
PLIST_LABEL="com.worktrace.mac"
PLIST_SRC="scripts/com.worktrace.mac.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"

if [ ! -d "$APP_SOURCE" ]; then
    echo "错误：未找到 $APP_SOURCE，请先执行打包（pyinstaller worktrace-mac.spec）。"
    exit 1
fi

# 1. 拷贝 .app 到 ~/Applications（用户级，无需管理员权限）
mkdir -p "$APP_DIR"
echo "[1/3] 拷贝 WorkTrace.app → $APP_DEST"
rm -rf "$APP_DEST"
cp -R "$APP_SOURCE" "$APP_DEST"

# 2. 生成 LaunchAgent plist（替换路径占位）
mkdir -p "$(dirname "$PLIST_DEST")"
echo "[2/3] 生成 LaunchAgent → $PLIST_DEST"
sed "s|__APP_PATH__|$APP_DEST|g" "$PLIST_SRC" > "$PLIST_DEST"
plutil -lint "$PLIST_DEST" >/dev/null

# 3. 加载
echo "[3/3] 加载 LaunchAgent"
launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"

echo ""
echo "✓ 安装完成。WorkTrace 将在每次登录时自动启动。"
echo "  立即启动：open '$APP_DEST'"
echo "  卸载：    bash scripts/uninstall.sh"
