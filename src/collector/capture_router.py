"""采集路由 — 三路融合 + 择优仲裁

为什么需要路由
--------------
单一采集手段覆盖不了所有应用（实测结论）：

| 应用类型          | UIA | COM | 说明                              |
|-------------------|-----|-----|-----------------------------------|
| 记事本/标准控件   | ✅  | —   | UIA 三路全通                      |
| Chromium 系       | ✅  | —   | UIA EditControl 逐字可读          |
| WPS 表格          | ❌  | ✅  | UIA 无单元格节点，必须走 COM      |
| 自绘/DirectX      | ❌  | ❌  | 只能靠拼音引擎兜底                |

所以需要一层"择优"：谁能拿到更接近真实的文本，就用谁。

仲裁规则
--------
    ① COM 命中（前台是 WPS/Office）→ 用 COM（单元格级最精准）
    ② 否则 UIA 有编辑控件文本      → 用 UIA
    ③ 都没有                        → 交回键盘文本（由拼音引擎兜底）

两条路径在进程层面互斥（COM 只在办公进程工作，UIA 在其他应用工作），
因此不会出现"同一时刻两路都产出"的冲突。

对外契约
--------
与 UiaTextCapture 完全一致，便于 main.py 无缝替换：
    start() / stop() / request_snapshot() / get_typed_text(text) / is_available

可通过 accurate_mode=False 整体关闭增强，行为回到"纯键盘 + 拼音引擎"。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class CaptureRouter:
    """三路采集路由（UIA + WPS/Office COM + 键盘兜底）"""

    def __init__(
        self,
        uia=None,
        com=None,
        accurate_mode: bool = True,
    ):
        """
        Args:
            uia: UiaTextCapture 实例（可为 None）
            com: WpsComCapture 实例（可为 None）
            accurate_mode: 总开关；False 时完全不介入，直接返回键盘文本
        """
        self._uia = uia
        self._com = com
        self._accurate_mode = accurate_mode
        self._last_source = "keyboard"

    # ==================== 生命周期（透传）====================

    def start(self):
        if not self._accurate_mode:
            logger.info("采集增强已关闭（accurate_mode=false），使用纯键盘链路")
            return
        for name, cap in (("UIA", self._uia), ("COM", self._com)):
            if cap is not None:
                try:
                    cap.start()
                except Exception:
                    logger.warning("%s 采集启动失败（已跳过）", name, exc_info=True)

    def stop(self):
        for cap in (self._com, self._uia):
            if cap is not None:
                try:
                    cap.stop()
                except Exception:
                    logger.debug("采集停止异常", exc_info=True)

    def request_snapshot(self):
        """IME 上屏时触发立即快照（两条路径都唤醒，谁命中谁产出）"""
        if not self._accurate_mode:
            return
        for cap in (self._com, self._uia):
            if cap is not None:
                try:
                    cap.request_snapshot()
                except Exception:
                    pass

    # ==================== 核心仲裁 ====================

    def get_typed_text(self, keyboard_text: str) -> str:
        """提交片段时调用：按优先级择优返回

        Returns:
            更接近真实输入的文本；无增强数据时原样返回 keyboard_text
        """
        if not self._accurate_mode:
            self._last_source = "keyboard"
            return keyboard_text

        # ① COM 优先（WPS/Office 表格场景最精准，单元格级）
        if self._com is not None:
            try:
                t = self._com.get_typed_text(keyboard_text)
                if t and t != keyboard_text:
                    self._last_source = "com"
                    return t
            except Exception:
                logger.debug("COM 采集取值异常", exc_info=True)

        # ② UIA
        if self._uia is not None:
            try:
                t = self._uia.get_typed_text(keyboard_text)
                if t and t != keyboard_text:
                    self._last_source = "uia"
                    return t
            except Exception:
                logger.debug("UIA 采集取值异常", exc_info=True)

        # ③ 兜底：交回键盘文本（拼音引擎在展示层处理）
        self._last_source = "keyboard"
        return keyboard_text

    # ==================== 状态查询 ====================

    @property
    def is_available(self) -> bool:
        """是否至少有一条增强路径可用"""
        if not self._accurate_mode:
            return False
        return any(
            cap is not None and getattr(cap, "is_available", False)
            for cap in (self._uia, self._com)
        )

    @property
    def last_source(self) -> str:
        """最近一次实际采用的来源：com / uia / keyboard"""
        return self._last_source

    @property
    def accurate_mode(self) -> bool:
        return self._accurate_mode

    def status(self) -> dict:
        """诊断信息（供 /api/capture/quality 等使用）"""
        return {
            "accurate_mode": self._accurate_mode,
            "last_source": self._last_source,
            "uia": {
                "available": bool(self._uia and getattr(self._uia, "is_available", False)),
                "last_way": getattr(self._uia, "last_way", ""),
            } if self._uia is not None else None,
            "com": {
                "available": bool(self._com and getattr(self._com, "is_available", False)),
            } if self._com is not None else None,
        }
