#!/bin/bash
# 卸载 WorkTrace LaunchAgent（保留 .app 与数据，仅取消登录启动）
# 用法：bash scripts/uninstall.sh
PLIST_LABEL="com.worktrace.mac"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"

echo "卸载 LaunchAgent ..."
if [ -f "$PLIST_DEST" ]; then
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
    rm -f "$PLIST_DEST"
    echo "✓ 已取消登录启动（删除 $PLIST_DEST）"
else
    echo "未找到 LaunchAgent plist，无需卸载。"
fi

echo ""
echo "  .app 保留：    ~/Applications/WorkTrace.app"
echo "  数据保留：     ~/Library/Application Support/WorkTrace/"
echo "  彻底删除：     rm -rf ~/Applications/WorkTrace.app ~/Library/Application\\ Support/WorkTrace"
