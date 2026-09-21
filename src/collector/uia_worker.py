"""UIA 采集工作子进程 —— 唯一允许导入 comtypes/uiautomation 的地方

为什么必须独立进程（2026-09-14 实测结论）
---------------------------------------
主进程一旦 `import comtypes`（uiautomation 的依赖），pywebview 的 WebView2
嵌入窗口就彻底失效：msedgewebview2 进程数 0、页面 loaded 事件永不触发，
窗口呈现白屏/黑屏。与导入顺序、导入时机（窗口启动前/启动后）均无关。

因此把 UIA 采集整体搬进子进程：
- 主进程（跑本地窗口）永不接触 comtypes → 界面永远正常
- 顺带好处：UIA/COM 崩溃只影响子进程，主进程可自动重启它

协议
----
stdout 每行一个 JSON（UTF-8）：

    观察: {"t": 1726300000.1, "key": {"k": "rid", "v": [42, 1]},
           "text": "今天要完成GR1003", "way": "V", "ctype": "EditControl",
           "proc": "workbuddy.exe"}
    无数据: {"t": ..., "none": true}
    致命:  {"fatal": "错误说明"}

`key` 用于父进程按控件隔离基线；`proc` 供父进程做前台进程过滤/诊断。

用法（由 uia_worker_capture.py 自动拼装，无需手工调用）：
    python -m src.collector.uia_worker --interval 0.5
    WorkTrace.exe --uia-worker --interval 0.5      # 打包版
"""

from __future__ import annotations

import json
import os
import sys
import time

from src.collector.uia_capture import UiaTextCapture, _load_uia

#: 单次读取的最大字符数（与主进程保持一致）
MAX_TEXT_LENGTH = 4000


def _ensure_stdout() -> None:
    """保证 stdout 可用

    打包版是 GUI 子系统(windowed)，无控制台时 `sys.stdout` 为 None；
    但父进程用管道启动本进程时 fd 1 是有效的，可直接接回来。
    """
    if sys.stdout is not None:
        return
    try:
        sys.stdout = os.fdopen(1, "w", encoding="utf-8", errors="replace", buffering=1)
    except Exception:
        try:
            sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
        except Exception:
            pass


def _emit(obj: dict) -> None:
    """输出一行 JSON 并立即刷新（父进程按行读取）"""
    if sys.stdout is None:
        return
    try:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    except Exception:
        pass


def _parse_interval(argv: list[str]) -> float:
    if "--interval" in argv:
        try:
            return float(argv[argv.index("--interval") + 1])
        except (IndexError, ValueError):
            pass
    return 0.5


def _serialize_key(key) -> dict | None:
    """控件键 → JSON 可序列化结构"""
    if key is None:
        return None
    try:
        kind, value = key
        return {"k": str(kind), "v": list(value) if isinstance(value, tuple) else value}
    except Exception:
        return None


def _foreground_process() -> str:
    """当前前台进程名（小写）；失败返回空串"""
    try:
        from src.collector.wps_com import get_foreground_process

        return get_foreground_process()
    except Exception:
        return ""


def main(argv: list[str] | None = None) -> int:
    _ensure_stdout()
    argv = list(sys.argv[1:] if argv is None else argv)
    interval = _parse_interval(argv)

    if not _load_uia():
        _emit({"fatal": "uiautomation 不可用"})
        return 2

    # COM 单线程初始化（本进程专用）
    try:
        import comtypes

        comtypes.CoInitialize()
    except Exception:
        pass

    cap = UiaTextCapture(interval=interval, max_text_length=MAX_TEXT_LENGTH)
    cap._interval = max(0.15, interval)

    _emit({"ready": True, "interval": interval})

    while True:
        try:
            cap._take_snapshot()
            snap = cap._last_snapshot
            if snap is None:
                _emit({"t": time.time(), "none": True})
            else:
                key, text, _ts = snap
                skey = _serialize_key(key)
                if skey is None:
                    _emit({"t": time.time(), "none": True})
                else:
                    _emit({
                        "t": time.time(),
                        "key": skey,
                        "text": text,
                        "way": cap.last_way,
                        "ctype": cap._last_control_type,
                        "proc": _foreground_process(),
                    })
        except KeyboardInterrupt:
            return 0
        except Exception as exc:  # 永不因单次异常退出，保证主进程采集连续
            _emit({"t": time.time(), "error": f"{type(exc).__name__}: {exc}"})
        time.sleep(cap._interval)

    return 0


if __name__ == "__main__":
    sys.exit(main())
