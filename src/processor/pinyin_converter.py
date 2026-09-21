"""拼音转汉字工具 — 分层转换引擎

将连续的拼音字母段转换为汉字，用于活动页历史数据展示优化。
不修改原始存储数据，仅在展示层使用。

分层策略（任意一层失败自动降级，永不丢失原文）：
1. Pinyin2Hanzi DAG：词库 + 动态规划，词组级转换（首选）
2. Pinyin2Hanzi HMM：维特比算法，字级上下文（补充）
3. 内置单字频率映射：无上下文兜底（最后手段）

库来源：https://github.com/letiantian/Pinyin2Hanzi (MIT)
已内置到 src/libs/Pinyin2Hanzi，数据文件 gzip 压缩（37MB -> 5.8MB）。

规则：
1. 智能分词：将连续的 a-z 字母段拆分为可能的拼音音节
2. 混合处理：英文单词、数字、标点保持不变
3. 五笔兼容：如果字母段无法匹配任何拼音音节，保持原文
"""

from __future__ import annotations

import math
import re
import logging
import threading

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
# 仅作为 Pinyin2Hanzi 引擎不可用时的兜底
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

# HMM 引擎处理的最大音节数（维特比对超长序列较慢）
_HMM_MAX_SYLLABLES = 60

# 待转换音节块的最小音节数（单音节保留原文，避免英文单词误转）
_MIN_CHUNK_SYLLABLES = 2

# ==================== 置信度门控（C3：残缺拼音不硬转）====================
# 引擎返回 score 为路径概率（DAG：短语概率乘积；HMM：转移×发射概率乘积）。
# 每音节平均 log 概率（avg_log = ln(score)/音节数）衡量整条路径的可靠程度：
#   接近 0（如 '公司' -0.10）→ 词库强命中，置信
#   接近 ln(0.2)≈-1.61（默认概率）→ 词库弱信号，路径不可靠
# 两档阈值：
#   _SHORT_SEQ_CONFIDENCE（2 音节）≥ -0.9 用 DAG，否则逐字映射
#     —— 修复 'gongsi'→'工四'（DAG 实为 '公司' 0.83 分）等短序列误转
#   _LONG_SEQ_CONFIDENCE（≥3 音节）≥ -1.0 用 DAG，否则改试 HMM 上下文
#     —— 修复 'yudaole'→'于到了'（DAG 弱信号，HMM '遇到了' 更自然）
_SHORT_SEQ_CONFIDENCE = -0.9
_LONG_SEQ_CONFIDENCE = -1.0

# ==================== 不完整拼音前缀 → 汉字（输入法的简拼匹配）===================
# 样本1验证：jint→今天, wanc→完成, xiangm→项目
# 当用户用搜狗/微软拼音的"简拼"或"前几字母"输入时触发
# 最小长度 3 字母，避免误伤英文短词（如 'it', 'no'）
PINYIN_PREFIX_HANZI = {
    # 时间
    'jint': '今天', 'jintian': '今天', 'jinr': '今儿', 'jinri': '今日',
    'mingr': '明儿', 'mingri': '明日', 'mingt': '明天', 'mingtian': '明天',
    'xianz': '现在', 'xianzai': '现在',
    # 项目/工作
    'xiangm': '项目', 'wanc': '完成', 'wancheng': '完成',
    'guanl': '管理', 'guanli': '管理',
    'cesh': '测试', 'ceshi': '测试',
    'kaif': '开发', 'kaifa': '开发',
    'shej': '设计', 'sheji': '设计',
    'baog': '报告', 'baogao': '报告',
    'tuand': '团队', 'tuandui': '团队',
    'chanp': '产品', 'chanpin': '产品',
    'jingl': '经理', 'jingli': '经理',
    'zhug': '主管', 'zhuguan': '主管',
    # 城市
    'beij': '北京', 'beijing': '北京',
    'shangh': '上海', 'shanghai': '上海',
    'guangz': '广州', 'guangzhou': '广州',
    'shenzh': '深圳', 'shenzhen': '深圳',
    # 疑问
    'shenm': '什么', 'shenme': '什么',
    'zenm': '怎么', 'zenme': '怎么',
    'weish': '为什么', 'weishenme': '为什么',
    'zenya': '怎样', 'zenyang': '怎样',
    # 常用
    'bangz': '帮助', 'bangzhu': '帮助',
    'guonei': '国内', 'guowai': '国外',
    'fuwu': '服务', 'xianzhuang': '现状',
    'fangan': '方案', 'fangan': '方案',
    'mubia': '目标', 'mubiao': '目标',
    'went': '问题', 'wenti': '问题',
    'jindu': '进度', 'jiedu': '进度',
    'jieguo': '结果', 'shijian': '时间',
}


# ==================== 分层引擎（懒加载单例） ====================

_engine_lock = threading.Lock()
_dag_params = None
_hmm_params = None
_engine_failed = False  # 引擎不可用（数据文件缺失等），永久降级到单字映射


def _load_engine():
    """懒加载 Pinyin2Hanzi 引擎参数（首次约 0.5s，进程内共享）"""
    global _dag_params, _hmm_params, _engine_failed
    if _engine_failed:
        return False
    if _dag_params is not None:
        return True
    with _engine_lock:
        if _engine_failed:
            return False
        if _dag_params is not None:
            return True
        try:
            from src.libs.Pinyin2Hanzi import DefaultDagParams, DefaultHmmParams
            _dag_params = DefaultDagParams()
            _hmm_params = DefaultHmmParams()
            logger.info("Pinyin2Hanzi 引擎已加载（DAG 词库 + HMM 模型）")
            return True
        except Exception:
            _engine_failed = True
            logger.exception("Pinyin2Hanzi 引擎加载失败，降级到单字映射")
            return False


def _norm_syllables(syllables: list[str]) -> list[str] | None:
    """音节规范化 + 合法性校验（lue→lve 等）；非法音节返回 None"""
    try:
        from src.libs.Pinyin2Hanzi import simplify_pinyin, is_pinyin
        norm = [simplify_pinyin(s) for s in syllables]
        if all(is_pinyin(s) for s in norm):
            return norm
    except Exception:
        logger.debug("音节规范化异常", exc_info=True)
    return None


def _dag_scored(syllables: list[str]) -> tuple[str, float] | None:
    """DAG 词库 + 动态规划：返回 (汉字串, 每音节平均 log 概率)；失败返回 None"""
    if not _load_engine():
        return None
    norm = _norm_syllables(syllables)
    if norm is None:
        return None
    try:
        from src.libs.Pinyin2Hanzi import dag
        result = dag(_dag_params, norm, path_num=1)
        if result:
            score = result[0].score
            avg = math.log(score) / len(norm) if score > 0 else float("-inf")
            return "".join(result[0].path), avg
    except Exception:
        logger.debug("DAG 转换异常", exc_info=True)
    return None


def _hmm_scored(syllables: list[str]) -> tuple[str, float] | None:
    """HMM 维特比：返回 (汉字串, 每音节平均 log 概率)；失败返回 None"""
    if not _load_engine():
        return None
    norm = _norm_syllables(syllables)
    if norm is None:
        return None
    if len(norm) > _HMM_MAX_SYLLABLES:
        return None
    try:
        from src.libs.Pinyin2Hanzi import viterbi
        result = viterbi(hmm_params=_hmm_params, observations=tuple(norm), path_num=1)
        if result:
            score = result[0].score
            avg = math.log(score) / len(norm) if score > 0 else float("-inf")
            return "".join(result[0].path), avg
    except Exception:
        logger.debug("HMM 转换异常", exc_info=True)
    return None


def _convert_by_engine_scored(syllables: list[str]) -> tuple[str, float] | None:
    """分层引擎打分：DAG 优先，失败降级 HMM

    Returns:
        (汉字串, 每音节平均 log 概率)；引擎不可用或非法音节返回 None
    """
    dag_res = _dag_scored(syllables)
    if dag_res:
        return dag_res
    return _hmm_scored(syllables)


def _convert_by_engine(syllables: list[str]) -> str | None:
    """用 Pinyin2Hanzi 引擎转换音节列表，失败返回 None

    层级：DAG（词组级）→ HMM（字级上下文）
    """
    scored = _convert_by_engine_scored(syllables)
    return scored[0] if scored else None


def _convert_by_fallback(syllables: list[str]) -> str:
    """Layer 3 兜底：单字频率映射（无上下文）"""
    parts = []
    for s in syllables:
        if s in PINYIN_TO_HANZI:
            parts.append(PINYIN_TO_HANZI[s])
        else:
            parts.append(s)  # 无法匹配的保留原文
    return ''.join(parts)


# ==================== 公共接口 ====================

def _split_pinyin(text: str) -> list[str]:
    """将连续的字母段拆分为拼音音节

    使用贪心算法：从左到右，每次匹配最长的有效拼音音节。
    如果遇到无法匹配的字母，将单个字母作为一个段。

    Args:
        text: 纯小写字母段，如 "jixu"

    Returns:
        拆分后的音节列表，如 ["ji", "xu"]
    """
    result = []
    i = 0
    while i < len(text):
        # 贪心匹配：最长 6 字母（zhuang/chuang/shuang/xiang 等长音节）
        matched = False
        for length in range(6, 0, -1):
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


def _normalize_syllable(s: str) -> str | None:
    """规范化音节（lue→lve 等）；非法音节（简拼声母/英文字母）返回 None"""
    try:
        from src.libs.Pinyin2Hanzi import simplify_pinyin, is_pinyin
        norm = simplify_pinyin(s)
        return norm if is_pinyin(norm) else None
    except Exception:
        return s if s in PINYIN_TO_HANZI else None


def _is_likely_pinyin(text: str) -> bool:
    """判断字母段是否可能是拼音

    规则：
    - 长度 >= 2
    - 拆分后至少有 50% 的音节能匹配 PINYIN_TO_HANZI
    - 排除明显的英文单词（如 "the", "and", "for" 等）
    - 包含已知拼音前缀（如 jint/wanc/xiangm）也视为拼音（v1.1 新增）
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

    # 包含已知拼音前缀（样本1: jint/wanc/xiangm）→ 视为拼音交给 v2 处理
    for prefix in PINYIN_PREFIX_HANZI:
        if prefix in text:
            return True

    syllables = _split_pinyin(text)
    if not syllables:
        return False

    # 至少 50% 的音节能匹配到汉字
    matched = sum(1 for s in syllables if s in PINYIN_TO_HANZI)
    return matched / len(syllables) >= 0.5


def _convert_chunk(syllables: list[str]) -> str:
    """转换一个连续合法音节块：引擎优先，单字映射兜底"""
    converted = _convert_by_engine(syllables)
    if converted:
        return converted
    return _convert_by_fallback(syllables)


def _convert_latin_run(latin: str) -> str:
    """转换单个字母段（部分转换策略）

    将音节序列分组：连续合法音节（≥ _MIN_CHUNK_SYLLABLES 个）作为块交给
    引擎转换；非法音节（简拼声母、英文字母等）与不足长度的块保留原字母。
    实现"能识别的转汉字，识别不了的保留原文"。

    例: "xiangmdewaiguanjianmopinggu" → "xiangm" + "的外观建模评估"
    """
    syllables = _split_pinyin(latin)
    parts: list[str] = []
    buf: list[str] = []

    def flush():
        if len(buf) >= _MIN_CHUNK_SYLLABLES:
            parts.append(_convert_chunk(list(buf)))
        elif buf:
            parts.append(''.join(buf))
        buf.clear()

    for s in syllables:
        norm = _normalize_syllable(s)
        if norm is not None:
            buf.append(norm)
        else:
            flush()
            parts.append(s)
    flush()
    return ''.join(parts)


# ==================== v1.1 增强版：前缀匹配 + 错拼容错 + 编号保护 ====================

# 单音节错拼容错占位符
_PREFIX_TOKEN = '__PREFIX_MATCH__'


def _fuzzy_fix_syllable(s: str) -> str | None:
    """单音节错拼容错：编辑距离 1 替换使其成为合法音节

    适用：样本2 中 'haou' → 'hao'（漏字母）/ 'jian' → 'jiam' 等
    局限：跨多字符错拼（如 'hiayou'）无法在此层修复,需后续整段错拼方案
    """
    if not s or s in PINYIN_SYLLABLES or len(s) < 2 or len(s) > 6:
        return None
    for i in range(len(s)):
        for c in 'abcdefghijklmnopqrstuvwxyz':
            if c == s[i]:
                continue
            variant = s[:i] + c + s[i+1:]
            if variant in PINYIN_SYLLABLES:
                return variant
    return None


def _split_pinyin_v2(text: str) -> tuple[list[str], dict[int, str]]:
    """增强版分词：完整音节与前缀音节视为同一候选池,贪心选最长

    关键设计：把"完整音节"和"拼音前缀"放在同一候选池中按长度匹配,
    这样 'jintyaowanc' 会在 i=0 优先匹配 4 字符前缀 'jint'(→"今天"),
    而不是退化为 3 字符完整音节 'jin'(→"今")。如果不合并池子,
    完整音节优先级高会"吃"掉前缀,导致 jint 这种高频简拼永远识别不到。

    Returns:
        (syllables, replacements) —— syllables 含占位符 _PREFIX_TOKEN
        replacements[i] 表示第 i 个音节应替换的汉字
    """
    syllables: list[str] = []
    replacements: dict[int, str] = {}
    i = 0
    while i < len(text):
        matched = False
        # 完整音节 + 前缀音节 同池贪心（最长优先，8→1）
        # 前缀上限 8：覆盖 'jintian'/'wancheng'/'xianzai' 等 7 字母高频前缀
        # 整体命中，否则 'jintian' 会被拆成 'jint'+'ian' 产生乱码
        for length in range(min(8, len(text) - i), 0, -1):
            candidate = text[i:i + length]
            if candidate in PINYIN_SYLLABLES:
                syllables.append(candidate)
                i += length
                matched = True
                break
            if length >= 4 and candidate in PINYIN_PREFIX_HANZI:
                # 仅长度 >= 4 的前缀（避免误伤英文 2~3 字母短词）
                syllables.append(_PREFIX_TOKEN)
                replacements[len(syllables) - 1] = PINYIN_PREFIX_HANZI[candidate]
                i += length
                matched = True
                break
        if not matched:
            syllables.append(text[i])
            i += 1
    return syllables, replacements


def _convert_chunk_with_fuzzy(syllables: list[str]) -> str | None:
    """带错拼容错 + 置信度仲裁的转换

    按音节数分层（C3 置信度门控）：
    - 1 音节：单字映射（最常用字，无上下文可依）
    - 2 音节：DAG 置信（avg_log ≥ -0.9）用 DAG 结果，否则单字映射
      —— 修复 'gongsi'→'工四'（DAG 高分 '公司' 被单字映射吃掉）
    - ≥3 音节：DAG 置信（avg_log ≥ -1.0）用 DAG；DAG 弱信号改试 HMM
      上下文；HMM 仍不可用时退回 DAG/单字映射
      —— 修复 'yudaole'→'于到了'（DAG 弱信号，HMM '遇到了' 更自然）
    """
    if not syllables:
        return None
    if len(syllables) == 1:
        return _convert_by_fallback(syllables)

    dag_res = _dag_scored(syllables)
    if dag_res:
        text, avg_log = dag_res
        if len(syllables) == 2:
            if avg_log >= _SHORT_SEQ_CONFIDENCE:
                return text
            return _convert_by_fallback(syllables)
        # 长序列：DAG 置信直接用，弱信号试 HMM
        if avg_log >= _LONG_SEQ_CONFIDENCE:
            return text
        hmm_res = _hmm_scored(syllables)
        if hmm_res:
            return hmm_res[0]
        return text  # HMM 不可用，退回 DAG 结果（至少是词级）

    # 引擎完全不可用（数据缺失等），逐字映射兜底
    return _convert_by_fallback(syllables)


def _convert_pure_latin(latin: str) -> str:
    """纯字母段转换：前缀匹配 + 错拼容错 + 引擎/兜底"""
    if not latin:
        return latin
    # 1. 整体前缀匹配（整段恰好是某高频前缀）
    if latin in PINYIN_PREFIX_HANZI:
        return PINYIN_PREFIX_HANZI[latin]

    # 2. 增强分词
    syllables, prefix_map = _split_pinyin_v2(latin)
    parts: list[str] = []
    buf: list[str] = []

    def flush():
        if not buf:
            return
        # 单合法音节（如 'yao'）直接转 —— _MIN_CHUNK_SYLLABLES=2 会保留它为原文
        if len(buf) == 1 and buf[0] in PINYIN_TO_HANZI:
            parts.append(PINYIN_TO_HANZI[buf[0]])
        elif len(buf) >= _MIN_CHUNK_SYLLABLES:
            converted = _convert_chunk_with_fuzzy(list(buf))
            parts.append(converted if converted else ''.join(buf))
        else:
            parts.append(''.join(buf))
        buf.clear()

    for idx, s in enumerate(syllables):
        if s == _PREFIX_TOKEN:
            # 前缀匹配：先 flush 累积的 buf,再插入汉字
            flush()
            parts.append(prefix_map.get(idx, ''))
            continue
        norm = _normalize_syllable(s)
        if norm is not None:
            buf.append(norm)
            continue
        # 错拼容错
        fixed = _fuzzy_fix_syllable(s)
        if fixed is not None:
            buf.append(fixed)
            continue
        # 无法处理,原样保留
        flush()
        parts.append(s)
    flush()
    return ''.join(parts)


def _convert_latin_run_v2(latin: str) -> str:
    """增强版 latin 段转换

    新增能力：
    1. 数字边界拆分（保护编号如 gr1003、v2.0 中的数字）
    2. 拼音前缀匹配（jint→今天, wanc→完成, xiangm→项目 等）
    3. 单音节错拼容错（编辑距离 1）
    """
    if not latin:
        return latin
    # 整体前缀匹配（不拆分）
    if latin in PINYIN_PREFIX_HANZI:
        return PINYIN_PREFIX_HANZI[latin]
    # 数字边界拆分
    result: list[str] = []
    last_end = 0
    for m in re.finditer(r'\d+', latin):
        if m.start() > last_end:
            result.append(_convert_pure_latin(latin[last_end:m.start()]))
        result.append(m.group(0))  # 数字段原样保留
        last_end = m.end()
    if last_end < len(latin):
        result.append(_convert_pure_latin(latin[last_end:]))
    return ''.join(result)


def convert_pinyin_to_hanzi(text: str) -> str:
    """将文本中的拼音字母段转换为汉字

    智能识别文本中的连续拉丁字母段，如果可能是拼音则转换为汉字。
    非拼音内容（英文单词、数字、标点、已有汉字）保持不变；
    拼音段内部无法识别的部分（简拼声母等）也保留原字母。

    Args:
        text: 原始文本，如 "jixu work on the report"

    Returns:
        转换后的文本，如 "继续 work on the report"

    样本1（v1.1 增强后）:
        "nihao,jintyaowancgr1003xiangmdewaiguanjianmopinggu"
        → "你好,今天要完成gr1003项目的外观建模评估"
        （注: gr 与 1003 之间的编号天然保留,字母段被前缀匹配识别）
    """
    if not text:
        return text

    def replace_match(match):
        latin = match.group(0).lower()
        if not _is_likely_pinyin(latin):
            return match.group(0)  # 不是拼音，保留原文
        return _convert_latin_run_v2(latin)

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


def engine_status() -> dict:
    """引擎状态诊断（用于日志/调试）"""
    return {
        "engine_loaded": _dag_params is not None,
        "engine_failed": _engine_failed,
        "fallback": "single-char",
    }
