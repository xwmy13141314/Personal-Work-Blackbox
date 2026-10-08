"""macOS Vision 本地 OCR：用于从用户选择或粘贴的图片提取待办文字。"""

from __future__ import annotations

from pathlib import Path


class ImageTextError(ValueError):
    """图片无法读取或无可识别文字。"""


SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".heic", ".heif", ".webp", ".tiff"}


def recognize_image_text(path: str | Path) -> str:
    """使用系统 Vision 识别图片文字；内容只在本机内存中处理。"""
    image = Path(path).expanduser().resolve()
    if not image.is_file():
        raise ImageTextError("所选图片不存在")
    if image.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        raise ImageTextError("仅支持 PNG、JPG、HEIC、WebP、TIFF 图片")
    return _recognize(image)


def _recognize(path: Path) -> str:
    try:
        from Foundation import NSURL
        from Vision import VNImageRequestHandler, VNRecognizeTextRequest
    except ImportError as exc:
        raise ImageTextError("系统文字识别组件未安装") from exc

    return _recognize_with_handler(
        VNImageRequestHandler.alloc().initWithURL_options_(NSURL.fileURLWithPath_(str(path)), None),
        VNRecognizeTextRequest,
    )


def recognize_cgimage_text(image) -> str:
    """识别内存中的 CGImage，不创建临时文件。

    供外部 App 输入框兼容模式使用：调用方只传入前台窗口底部裁剪区，整张
    截图不会写入磁盘，也不会上传。
    """
    try:
        from Vision import VNImageRequestHandler, VNRecognizeTextRequest
    except ImportError as exc:
        raise ImageTextError("系统文字识别组件未安装") from exc
    return _recognize_with_handler(
        VNImageRequestHandler.alloc().initWithCGImage_options_(image, None),
        VNRecognizeTextRequest,
    )


def _recognize_with_handler(handler, request_type) -> str:
    lines: list[str] = []
    errors: list[str] = []

    def completion_handler(request, error):
        if error:
            errors.append("系统未能识别此图片中的文字")
            return
        for observation in request.results() or []:
            candidates = observation.topCandidates_(1)
            if candidates:
                text = str(candidates[0].string()).strip()
                if text:
                    lines.append(text)

    request = request_type.alloc().initWithCompletionHandler_(completion_handler)
    request.setRecognitionLevel_(1)  # Accurate
    request.setUsesLanguageCorrection_(True)
    request.setRecognitionLanguages_(["zh-Hans", "en-US"])
    ok, error = handler.performRequests_error_([request], None)
    if not ok or error or errors:
        raise ImageTextError("系统未能识别此图片中的文字")
    text = "\n".join(lines).strip()
    if not text:
        raise ImageTextError("图片中未识别到文字")
    return text[:20_000]
