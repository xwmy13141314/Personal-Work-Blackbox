"""macOS 本机语音输入采集。

通过系统 Speech 框架把麦克风语音转为文本；只向上游发送最终转写文本，
不落盘原始音频。首次启用会由 macOS 请求麦克风与语音识别权限。
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

logger = logging.getLogger(__name__)


class VoiceInputCollector:
    """按需语音转写采集器（仅 macOS；由用户开始/停止控制）。"""

    def __init__(self, on_text: Callable[[str], None], locale: str = "zh_CN"):
        self._on_text = on_text
        self._locale = locale
        self._running = False
        self._engine = None
        self._request = None
        self._task = None
        self._input_node = None

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """用户主动请求后才授权并启动，不可用时不影响其他采集器。"""
        if self._running:
            return
        try:
            from Speech import SFSpeechRecognizer, SFSpeechRecognizerAuthorizationStatusAuthorized
        except Exception:
            logger.warning("Speech 框架不可用，语音输入未启动")
            return

        def authorized(status):
            if status != SFSpeechRecognizerAuthorizationStatusAuthorized:
                logger.warning("语音识别未获授权，语音输入未启动")
                return
            threading.Thread(target=self._start_recognition, daemon=True, name="VoiceInputStart").start()

        SFSpeechRecognizer.requestAuthorization_(authorized)

    def _start_recognition(self) -> None:
        try:
            from AVFoundation import AVAudioEngine
            from Foundation import NSLocale
            from Speech import SFSpeechAudioBufferRecognitionRequest, SFSpeechRecognizer

            recognizer = SFSpeechRecognizer.alloc().initWithLocale_(NSLocale.localeWithLocaleIdentifier_(self._locale))
            if not recognizer or not recognizer.isAvailable():
                logger.warning("当前系统语音识别服务不可用")
                return

            self._engine = AVAudioEngine.alloc().init()
            self._request = SFSpeechAudioBufferRecognitionRequest.alloc().init()
            self._request.setShouldReportPartialResults_(False)
            self._input_node = self._engine.inputNode()
            audio_format = self._input_node.outputFormatForBus_(0)

            def on_audio(_buffer, _when):
                if self._request:
                    self._request.appendAudioPCMBuffer_(_buffer)

            def on_result(result, error):
                if error:
                    logger.warning("语音识别会话结束: %s", error)
                    return
                if result and result.isFinal():
                    text = str(result.bestTranscription().formattedString()).strip()
                    if text:
                        self._on_text(text)

            self._input_node.installTapOnBus_bufferSize_format_block_(0, 1024, audio_format, on_audio)
            self._engine.prepare()
            self._engine.startAndReturnError_(None)
            self._task = recognizer.recognitionTaskWithRequest_resultHandler_(self._request, on_result)
            self._running = True
            logger.info("语音输入已启动（仅保存转写文本，不保存录音）")
        except Exception:
            logger.exception("语音输入启动失败")
            self.stop()

    def stop(self) -> None:
        """停止麦克风与识别会话。"""
        self._running = False
        try:
            if self._input_node:
                self._input_node.removeTapOnBus_(0)
            if self._engine:
                self._engine.stop()
            if self._request:
                self._request.endAudio()
            if self._task:
                self._task.cancel()
        except Exception:
            logger.exception("停止语音输入异常")
        finally:
            self._engine = self._request = self._task = self._input_node = None
