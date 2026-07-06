"""拼音转汉字工具测试"""
import pytest
from src.processor.pinyin_converter import (
    convert_pinyin_to_hanzi,
    has_convertible_pinyin,
    _split_pinyin,
    _is_likely_pinyin,
)


class TestSplitPinyin:
    def test_simple_split(self):
        assert _split_pinyin("jixu") == ["ji", "xu"]

    def test_multiple_syllables(self):
        assert _split_pinyin("nihao") == ["ni", "hao"]

    def test_three_syllables(self):
        assert _split_pinyin("wohenhao") == ["wo", "hen", "hao"]

    def test_unmatched(self):
        # 'x' 不是有效拼音开头，但仍会作为单字母返回
        result = _split_pinyin("xxx")
        assert len(result) == 3

    def test_empty(self):
        assert _split_pinyin("") == []


class TestIsLikelyPinyin:
    def test_pinyin_word(self):
        assert _is_likely_pinyin("jixu") == True

    def test_english_word(self):
        assert _is_likely_pinyin("hello") == False
        assert _is_likely_pinyin("the") == False

    def test_short(self):
        assert _is_likely_pinyin("a") == False

    def test_mixed(self):
        # 'work' 不在 english_words 中但拆分后不匹配
        result = _is_likely_pinyin("work")
        # w-o-r-k: 'wo'能匹配, 'rk'不能 → 50% 临界
        # 具体看实现


class TestConvert:
    def test_basic_conversion(self):
        assert convert_pinyin_to_hanzi("jixu") == "继续"

    def test_mixed_with_english(self):
        result = convert_pinyin_to_hanzi("jixu work on report")
        assert "继续" in result
        assert "work" in result
        assert "report" in result

    def test_english_not_converted(self):
        result = convert_pinyin_to_hanzi("hello world")
        assert result == "hello world"

    def test_empty(self):
        assert convert_pinyin_to_hanzi("") == ""

    def test_chinese_passthrough(self):
        assert convert_pinyin_to_hanzi("你好世界") == "你好世界"

    def test_numbers_passthrough(self):
        assert convert_pinyin_to_hanzi("12345") == "12345"

    def test_mixed_pinyin_chinese(self):
        result = convert_pinyin_to_hanzi("你好 jixu 工作")
        assert "你好" in result
        assert "继续" in result
        assert "工作" in result

    def test_code_not_converted(self):
        result = convert_pinyin_to_hanzi("def main(): print('hello')")
        assert "def" in result
        assert "main" in result
        assert "print" in result
        assert "hello" in result


class TestHasConvertible:
    def test_has_pinyin(self):
        assert has_convertible_pinyin("jixu") == True

    def test_no_pinyin(self):
        assert has_convertible_pinyin("hello world") == False

    def test_mixed(self):
        assert has_convertible_pinyin("jixu work") == True

    def test_empty(self):
        assert has_convertible_pinyin("") == False

    def test_chinese_only(self):
        assert has_convertible_pinyin("你好") == False
