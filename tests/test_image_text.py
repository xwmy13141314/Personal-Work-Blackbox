from src.processor.image_text import ImageTextError, SUPPORTED_IMAGE_SUFFIXES


def test_supported_image_types_cover_local_import_formats():
    assert {".png", ".jpg", ".jpeg", ".heic", ".webp"}.issubset(SUPPORTED_IMAGE_SUFFIXES)


def test_image_text_error_is_a_value_error():
    assert issubclass(ImageTextError, ValueError)
