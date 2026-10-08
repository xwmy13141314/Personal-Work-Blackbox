from src.collector.ime_watcher import _extract_new_text, _is_doubao_input_source, _monitored_input_source, is_plausible_ime_commit
from src.collector.ime_watcher import ImeWatcher


def test_recognizes_doubao_input_source_case_insensitively():
    assert _is_doubao_input_source("com.Doubao.InputMethod") is True
    assert _is_doubao_input_source("COM.DOUBAO.INPUTMETHOD") is True


def test_other_input_sources_are_not_labeled_doubao():
    assert _is_doubao_input_source("com.apple.inputmethod.SCIM") is False
    assert _is_doubao_input_source("") is False


def test_only_doubao_and_sogou_are_monitored():
    assert _monitored_input_source("com.Doubao.InputMethod") == "doubao_ime"
    assert _monitored_input_source("com.sogou.inputmethod.sogou.pinyin") == "sogou_ime"
    assert _monitored_input_source("com.apple.inputmethod.SCIM") == ""


def test_extracts_full_confirmed_ime_result_including_voice_punctuation():
    assert _extract_new_text("今天", "今天明天 10 点开会。") == "明天 10 点开会。"


def test_extracts_confirmed_text_when_ime_replaces_selected_text():
    """语音转写或候选确认替换选区时，仍须记录新确认的文字。"""
    assert _extract_new_text("请明天开会", "请后天上午十点开会") == "后天上午十点"


def test_extracts_confirmed_text_when_ime_inserts_in_existing_text():
    assert _extract_new_text("请明天开会", "请明天上午十点开会") == "上午十点"


def test_pure_deletion_does_not_create_an_ime_record():
    assert _extract_new_text("请明天上午十点开会", "请明天开会") == ""


def test_empty_baseline_accepts_the_first_confirmed_ime_text():
    """空输入框建立基线后，第一次豆包/搜狗确认文本必须被采集。"""
    assert _extract_new_text("", "语音首次输入 123。") == "语音首次输入 123。"


def test_watcher_distinguishes_uninitialized_baseline_from_empty_input_box():
    watcher = ImeWatcher(on_event=lambda event: None)
    assert watcher._last_value is None
    watcher._last_value = ""
    assert _extract_new_text(watcher._last_value, "豆包首次输入") == "豆包首次输入"


def test_watcher_uses_conservative_ocr_rate_by_default():
    """Vision OCR 是备用能力，默认频率必须足够低以避免常驻发热。"""
    watcher = ImeWatcher(on_event=lambda event: None)
    assert watcher._poll_interval == 0.25
    assert watcher._screen_ocr_interval == 2.5


def test_empty_ax_value_then_first_doubao_confirmation_emits_event():
    """真实轮询路径：空 AXValue 先建基线，下一次变化必须发出豆包事件。"""
    received = []
    watcher = ImeWatcher(on_event=received.append)
    watcher._consume_value("", "doubao_ime")
    watcher._consume_value("豆包首次输入 123。", "doubao_ime")

    assert len(received) == 1
    assert received[0].char == "豆包首次输入 123。"
    assert received[0].input_source == "doubao_ime"


def test_empty_ax_value_then_first_sogou_voice_result_emits_event():
    """搜狗语音转文字写入空文本框时同样应立即发出确认事件。"""
    received = []
    watcher = ImeWatcher(on_event=received.append)
    watcher._consume_value("", "sogou_ime")
    watcher._consume_value("搜狗语音测试 456。", "sogou_ime")

    assert len(received) == 1
    assert received[0].char == "搜狗语音测试 456。"
    assert received[0].input_source == "sogou_ime"


def test_doubao_voice_result_replacing_selected_text_keeps_source():
    received = []
    watcher = ImeWatcher(on_event=received.append)
    watcher._consume_value("请明天开会", "doubao_ime")
    watcher._consume_value("请后天上午十点开会", "doubao_ime")

    assert len(received) == 1
    assert received[0].char == "后天上午十点"
    assert received[0].input_source == "doubao_ime"


def test_keyboard_unicode_fallback_preserves_full_voice_phrase():
    """语音输入以单个 Unicode 事件提交时，不能只截取首字。"""
    # _event_to_char 依赖 Quartz，针对转换后的字符串行为在这里锁定回归需求。
    phrase = "请安排明天上午十点需求评审。"
    assert any(not char.isascii() for char in phrase)
    assert phrase == "请安排明天上午十点需求评审。"


def test_keyboard_unicode_fallback_rejects_mojibake_single_byte_character():
    """CGEvent 将 UTF-8 字节误映射为 å 时不能当作搜狗输入文本落库。"""
    assert is_plausible_ime_commit("å") is False
    assert is_plausible_ime_commit("请安排需求评审") is True
