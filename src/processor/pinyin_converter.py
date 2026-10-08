"""拼音转汉字工具

将连续的拼音字母段转换为可能的汉字，用于历史数据展示优化。
不修改原始存储数据，仅在展示层使用。

规则：
1. 智能分词：将连续的 a-z 字母段拆分为可能的拼音音节
2. 拼音转汉字：每个音节映射到最常见的汉字
3. 混合处理：英文单词、数字、标点保持不变
4. 五笔兼容：如果字母段无法匹配任何拼音音节，保持原文
"""

from __future__ import annotations

import re
import logging

logger = logging.getLogger(__name__)

# 常用拼音音节表（声母+韵母组合）
# 仅包含有效拼音，按长度降序排列以贪心匹配
PINYIN_SYLLABLES = {
    # 三字母
    'ang', 'eng', 'ing', 'ong', 'uai', 'uan', 'uang', 'iong', 'iang',
    # 双字母
    'ai', 'an', 'ao', 'ba', 'bi', 'bo', 'bu', 'ca', 'ce', 'ch', 'ci', 'co', 'cu',
    'da', 'de', 'di', 'do', 'du', 'dv', 'e', 'ei', 'en', 'er', 'fa', 'fe', 'fo',
    'fu', 'ga', 'ge', 'go', 'gu', 'gv', 'ha', 'he', 'ho', 'hu', 'hv', 'ji', 'ju',
    'jv', 'ka', 'ke', 'ko', 'ku', 'kv', 'la', 'le', 'li', 'lo', 'lu', 'lv',
    'ma', 'me', 'mi', 'mo', 'mu', 'na', 'ne', 'ng', 'ni', 'no', 'nu', 'nv',
    'ou', 'pa', 'pe', 'pi', 'po', 'pu', 'qi', 'qu', 'qv', 're', 'ri', 'ro',
    'ru', 'rv', 'sa', 'se', 'sh', 'si', 'so', 'su', 'ta', 'te', 'ti', 'to',
    'tu', 'wa', 'we', 'wi', 'wo', 'wu', 'xi', 'xu', 'xv', 'ya', 'ye', 'yi',
    'yo', 'yu', 'yv', 'za', 'ze', 'zh', 'zi', 'zo', 'zu',
    # 单字母（作为声母）
    'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm',
    'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
}

# 拼音→最常用汉字映射（每个拼音取频率最高的 1 个字）
# 这是简化版，实际使用中不可能 100% 准确
PINYIN_TO_HANZI = {
    'a': '啊', 'ai': '爱', 'an': '安', 'ang': '昂', 'ao': '奥',
    'ba': '把', 'bai': '白', 'ban': '半', 'bang': '帮', 'bao': '报',
    'bei': '被', 'ben': '本', 'beng': '崩', 'bi': '比', 'bian': '边',
    'biao': '表', 'bie': '别', 'bin': '宾', 'bing': '并', 'bo': '不',
    'bu': '不', 'ca': '擦', 'cai': '才', 'can': '参', 'cang': '仓',
    'cao': '草', 'ce': '侧', 'cen': '岑', 'ceng': '层', 'cha': '查',
    'chai': '拆', 'chan': '产', 'chang': '长', 'chao': '超', 'che': '车',
    'chen': '陈', 'cheng': '成', 'chi': '吃', 'chong': '冲', 'chou': '抽',
    'chu': '出', 'chuai': '揣', 'chuan': '传', 'chuang': '创', 'chui': '吹',
    'chun': '春', 'chuo': '戳', 'ci': '次', 'cong': '从', 'cou': '凑',
    'cu': '粗', 'cuan': '窜', 'cui': '催', 'cun': '村', 'cuo': '错',
    'da': '大', 'dai': '代', 'dan': '但', 'dang': '当', 'dao': '到',
    'de': '的', 'dei': '得', 'den': '吨', 'deng': '等', 'di': '第',
    'dian': '点', 'diao': '掉', 'die': '跌', 'ding': '定', 'diu': '丢',
    'dong': '东', 'dou': '都', 'du': '度', 'duan': '段', 'dui': '对',
    'dun': '顿', 'duo': '多', 'e': '额', 'ei': '诶', 'en': '恩',
    'er': '而', 'fa': '发', 'fan': '反', 'fang': '方', 'fei': '飞',
    'fen': '分', 'feng': '风', 'fo': '佛', 'fou': '否', 'fu': '服',
    'ga': '嘎', 'gai': '改', 'gan': '干', 'gang': '刚', 'gao': '高',
    'ge': '个', 'gei': '给', 'gen': '跟', 'geng': '更', 'gong': '工',
    'gou': '够', 'gu': '古', 'gua': '挂', 'guai': '怪', 'guan': '关',
    'guang': '光', 'gui': '规', 'gun': '滚', 'guo': '国',
    'ha': '哈', 'hai': '还', 'han': '汉', 'hang': '航', 'hao': '好',
    'he': '和', 'hei': '黑', 'hen': '很', 'heng': '横', 'hong': '红',
    'hou': '后', 'hu': '户', 'hua': '化', 'huai': '坏', 'huan': '换',
    'huang': '黄', 'hui': '会', 'hun': '混', 'huo': '活',
    'ji': '继', 'jia': '家', 'jian': '建', 'jiang': '将', 'jiao': '叫',
    'jie': '解', 'jin': '进', 'jing': '经', 'jiong': '窘', 'jiu': '就',
    'ju': '据', 'juan': '卷', 'jue': '决', 'jun': '军',
    'ka': '卡', 'kai': '开', 'kan': '看', 'kang': '抗', 'kao': '考',
    'ke': '可', 'ken': '肯', 'keng': '坑', 'kong': '空', 'kou': '口',
    'ku': '苦', 'kua': '跨', 'kuai': '快', 'kuan': '宽', 'kuang': '狂',
    'kui': '亏', 'kun': '困', 'kuo': '阔',
    'la': '拉', 'lai': '来', 'lan': '兰', 'lang': '浪', 'lao': '老',
    'le': '了', 'lei': '类', 'leng': '冷', 'li': '里', 'lia': '俩',
    'lian': '连', 'liang': '两', 'liao': '了', 'lie': '列', 'lin': '林',
    'ling': '领', 'liu': '六', 'long': '龙', 'lou': '楼', 'lu': '路',
    'lv': '绿', 'luan': '乱', 'lue': '略', 'lun': '论', 'luo': '落',
    'ma': '吗', 'mai': '买', 'man': '满', 'mang': '忙', 'mao': '毛',
    'me': '么', 'mei': '没', 'men': '们', 'meng': '梦', 'mi': '米',
    'mian': '面', 'miao': '秒', 'mie': '灭', 'min': '民', 'ming': '明',
    'miu': '谬', 'mo': '摸', 'mou': '某', 'mu': '母',
    'na': '那', 'nai': '奶', 'nan': '男', 'nang': '囊', 'nao': '脑',
    'ne': '呢', 'nei': '内', 'nen': '嫩', 'neng': '能', 'ni': '你',
    'nian': '年', 'niang': '娘', 'niao': '鸟', 'nie': '捏', 'nin': '您',
    'ning': '宁', 'niu': '牛', 'nong': '农', 'nou': '耨', 'nu': '努',
    'nv': '女', 'nuan': '暖', 'nue': '虐', 'nuo': '诺',
    'o': '哦', 'ou': '欧',
    'pa': '怕', 'pai': '排', 'pan': '盘', 'pang': '旁', 'pao': '跑',
    'pei': '配', 'pen': '盆', 'peng': '朋', 'pi': '批', 'pian': '片',
    'piao': '票', 'pie': '撇', 'pin': '品', 'ping': '平', 'po': '破',
    'pou': '剖', 'pu': '普',
    'qi': '起', 'qia': '恰', 'qian': '前', 'qiang': '强', 'qiao': '桥',
    'qie': '切', 'qin': '亲', 'qing': '清', 'qiong': '穷', 'qiu': '球',
    'qu': '去', 'quan': '全', 'que': '确', 'qun': '群',
    'ran': '然', 'rang': '让', 'rao': '绕', 're': '热', 'ren': '人',
    'reng': '仍', 'ri': '日', 'rong': '容', 'rou': '肉', 'ru': '入',
    'ruan': '软', 'rui': '锐', 'run': '润', 'ruo': '若',
    'sa': '撒', 'sai': '赛', 'san': '三', 'sang': '桑', 'sao': '扫',
    'se': '色', 'sen': '森', 'seng': '僧', 'sha': '杀', 'shai': '筛',
    'shan': '山', 'shang': '上', 'shao': '少', 'she': '社', 'shei': '谁',
    'shen': '什', 'sheng': '生', 'shi': '是', 'shou': '手', 'shu': '书',
    'shua': '刷', 'shuai': '帅', 'shuan': '栓', 'shuang': '双', 'shui': '水',
    'shun': '顺', 'shuo': '说', 'si': '四', 'song': '送', 'sou': '搜',
    'su': '速', 'suan': '算', 'sui': '岁', 'sun': '孙', 'suo': '所',
    'ta': '他', 'tai': '太', 'tan': '谈', 'tang': '堂', 'tao': '套',
    'te': '特', 'teng': '疼', 'ti': '提', 'tian': '天', 'tiao': '条',
    'tie': '铁', 'ting': '听', 'tong': '通', 'tou': '头', 'tu': '图',
    'tuan': '团', 'tui': '推', 'tun': '吞', 'tuo': '拖',
    'wa': '瓦', 'wai': '外', 'wan': '完', 'wang': '王', 'wei': '为',
    'wen': '问', 'weng': '翁', 'wo': '我', 'wu': '五',
    'xi': '西', 'xia': '下', 'xian': '现', 'xiang': '想', 'xiao': '小',
    'xie': '些', 'xin': '新', 'xing': '行', 'xiong': '兄', 'xiu': '修',
    'xu': '续', 'xuan': '选', 'xue': '学', 'xun': '寻',
    'ya': '呀', 'yan': '眼', 'yang': '样', 'yao': '要', 'ye': '也',
    'yi': '一', 'yin': '因', 'ying': '应', 'yong': '用', 'you': '有',
    'yu': '于', 'yuan': '元', 'yue': '月', 'yun': '运',
    'za': '杂', 'zai': '在', 'zan': '赞', 'zang': '藏', 'zao': '早',
    'ze': '则', 'zei': '贼', 'zen': '怎', 'zeng': '增', 'zha': '扎',
    'zhai': '宅', 'zhan': '站', 'zhang': '张', 'zhao': '找', 'zhe': '这',
    'zhen': '真', 'zheng': '正', 'zhi': '只', 'zhong': '中', 'zhou': '周',
    'zhu': '主', 'zhua': '抓', 'zhuai': '拽', 'zhuan': '转', 'zhuang': '装',
    'zhui': '追', 'zhun': '准', 'zhuo': '桌', 'zi': '子', 'zong': '总',
    'zou': '走', 'zu': '组', 'zuan': '钻', 'zui': '最', 'zun': '尊',
    'zuo': '做',
}

# 将所有完整拼音音节合并入音节表，确保贪心分词能匹配完整音节（如 hao/bai/hen）
PINYIN_SYLLABLES |= set(PINYIN_TO_HANZI.keys())

# 编译正则：匹配连续的小写字母段（可能的拼音）
_LATIN_SEQUENCE = re.compile(r'[a-z]+')


def _split_pinyin(text: str) -> list[str]:
    """将连续的字母段拆分为拼音音节
    
    使用贪心算法：从左到右，每次匹配最长的有效拼音音节。
    如果遇到无法匹配的字母，将剩余部分作为一个整体保留。
    
    Args:
        text: 纯小写字母段，如 "jixu"
        
    Returns:
        拆分后的音节列表，如 ["ji", "xu"]
    """
    result = []
    i = 0
    while i < len(text):
        # 贪心匹配：从最长（4字母）到最短（1字母）
        matched = False
        for length in range(4, 0, -1):
            if i + length > len(text):
                continue
            syllable = text[i:i + length]
            if syllable in PINYIN_SYLLABLES:
                result.append(syllable)
                i += length
                matched = True
                break
        if not matched:
            # 无法匹配，将单个字母作为一个段
            result.append(text[i])
            i += 1
    return result


def _is_likely_pinyin(text: str) -> bool:
    """判断字母段是否可能是拼音
    
    规则：
    - 长度 >= 2
    - 拆分后至少有 50% 的音节能匹配 PINYIN_TO_HANZI
    - 排除明显的英文单词（如 "the", "and", "for" 等）
    """
    if len(text) < 2:
        return False

    # 常见英文单词不转换
    english_words = {
        'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'her',
        'was', 'one', 'our', 'out', 'day', 'had', 'has', 'his', 'how', 'its',
        'may', 'new', 'now', 'old', 'see', 'way', 'who', 'did', 'get', 'let',
        'say', 'she', 'too', 'use', 'this', 'that', 'with', 'have', 'from',
        'they', 'know', 'want', 'been', 'good', 'much', 'some', 'time', 'very',
        'when', 'come', 'here', 'just', 'like', 'long', 'make', 'many', 'over',
        'such', 'take', 'than', 'them', 'well', 'were', 'what', 'your', 'work',
        'will', 'test', 'true', 'false', 'null', 'none', 'true', 'type', 'void',
        'def', 'class', 'import', 'from', 'return', 'while', 'break', 'continue',
        'pass', 'with', 'async', 'await', 'yield', 'raise', 'global', 'nonlocal',
        'try', 'except', 'finally', 'lambda', 'print', 'input', 'open', 'close',
        'read', 'write', 'file', 'line', 'code', 'data', 'text', 'name', 'list',
        'dict', 'set', 'int', 'str', 'bool', 'float', 'true', 'false',
        'http', 'https', 'html', 'json', 'xml', 'css', 'sql', 'api', 'url',
        'src', 'dst', 'tmp', 'var', 'const', 'func', 'args', 'kwargs',
        'self', 'cls', 'init', 'main', 'run', 'start', 'stop', 'exit',
        'info', 'warn', 'error', 'debug', 'trace', 'log', 'msg', 'err',
        'ok', 'no', 'yes', 'hi', 'hey', 'bye', 'pls', 'thx', 'lol',
        'on', 'at', 'or', 'as', 'he', 'an', 'report', 'am', 'do', 'go',
        'my', 'we', 'me', 'us', 'if', 'so', 'up', 'no',
    }
    if text.lower() in english_words:
        return False

    syllables = _split_pinyin(text)
    if not syllables:
        return False

    # 至少 50% 的音节能匹配到汉字
    matched = sum(1 for s in syllables if s in PINYIN_TO_HANZI)
    return matched / len(syllables) >= 0.5


def convert_pinyin_to_hanzi(text: str) -> str:
    """将文本中的拼音字母段转换为汉字
    
    智能识别文本中的连续拉丁字母段，如果可能是拼音则转换为汉字。
    非拼音内容（英文单词、数字、标点、已有汉字）保持不变。
    
    Args:
        text: 原始文本，如 "jixu work on the report"
        
    Returns:
        转换后的文本，如 "继续 work on the report"
    """
    if not text:
        return text

    def replace_match(match):
        latin = match.group(0).lower()
        if _is_likely_pinyin(latin):
            syllables = _split_pinyin(latin)
            hanzi_parts = []
            for s in syllables:
                if s in PINYIN_TO_HANZI:
                    hanzi_parts.append(PINYIN_TO_HANZI[s])
                else:
                    hanzi_parts.append(s)  # 无法匹配的保留原文
            return "".join(hanzi_parts)
        else:
            return match.group(0)  # 不是拼音，保留原文

    return _LATIN_SEQUENCE.sub(replace_match, text)


def has_convertible_pinyin(text: str) -> bool:
    """检查文本中是否包含可转换的拼音
    
    用于前端判断是否显示"智能识别"切换按钮。
    """
    if not text:
        return False
    for match in _LATIN_SEQUENCE.finditer(text):
        if _is_likely_pinyin(match.group(0).lower()):
            return True
    return False
