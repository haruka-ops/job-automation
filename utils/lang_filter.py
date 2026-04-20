"""
职位语言检测与过滤
使用 langdetect 本地检测，无需 API，完全免费
支持语言代码：en=英语, zh-cn/zh-tw=中文, sv=瑞典语, de=德语, fr=法语, es=西班牙语
"""

from langdetect import detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException

# 固定随机种子，保证检测结果稳定
DetectorFactory.seed = 42

# 语言显示名称
LANG_NAMES = {
    "en":    "English",
    "zh-cn": "中文（简体）",
    "zh-tw": "中文（繁体）",
    "zh":    "中文",
    "sv":    "Svenska",
    "de":    "Deutsch",
    "fr":    "Français",
    "es":    "Español",
    "da":    "Dansk",
    "nl":    "Nederlands",
    "no":    "Norsk",
    "fi":    "Suomi",
}

# 语言分组：用户选「中文」时同时匹配 zh / zh-cn / zh-tw
LANG_GROUPS = {
    "en":   ["en"],
    "zh":   ["zh", "zh-cn", "zh-tw"],
    "sv":   ["sv"],
    "de":   ["de"],
    "fr":   ["fr"],
    "es":   ["es"],
}

ALL_LANGUAGES = list(LANG_NAMES.keys())


def detect_language(text: str) -> str:
    """
    检测文本语言，返回语言代码
    失败时返回 'unknown'
    """
    if not text or len(text.strip()) < 20:
        return "unknown"
    try:
        return detect(text[:1000])   # 只取前1000字符，足够判断
    except LangDetectException:
        return "unknown"


def is_allowed(text: str, allowed_langs: list[str]) -> tuple[bool, str]:
    """
    检测文本语言是否在允许列表中
    allowed_langs: 用户选择的语言，如 ["en", "zh"]
    返回 (是否允许, 检测到的语言代码)
    """
    if not allowed_langs:
        return True, "unknown"   # 没有限制则全部通过

    detected = detect_language(text)

    # 展开语言组（zh -> zh/zh-cn/zh-tw）
    expanded = set()
    for lang in allowed_langs:
        expanded.update(LANG_GROUPS.get(lang, [lang]))

    allowed = detected in expanded or detected == "unknown"
    return allowed, detected


def get_lang_display(code: str) -> str:
    """返回语言的显示名称"""
    return LANG_NAMES.get(code, code.upper())
