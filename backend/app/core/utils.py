"""
Shared utilities used across modules (rule engine, API search normalization, etc.).
"""

import re


# T-019: Map 66 ký tự Unicode tổ hợp (ă/â/đ/ê/ô/ơ/ư + 5 dấu sắc huyền hỏi ngã nặng) sang ASCII.
# Dùng chung cho rule_engine pattern matching và EP-05 search không dấu.
_DIACRITIC_MAP = {
    "á": "a", "à": "a", "ả": "a", "ã": "a", "ạ": "a",
    "ă": "a", "ắ": "a", "ằ": "a", "ẳ": "a", "ẵ": "a", "ặ": "a",
    "â": "a", "ấ": "a", "ầ": "a", "ẩ": "a", "ẫ": "a", "ậ": "a",
    "é": "e", "è": "e", "ẻ": "e", "ẽ": "e", "ẹ": "e",
    "ê": "e", "ế": "e", "ề": "e", "ể": "e", "ễ": "e", "ệ": "e",
    "í": "i", "ì": "i", "ỉ": "i", "ĩ": "i", "ị": "i",
    "ó": "o", "ò": "o", "ỏ": "o", "õ": "o", "ọ": "o",
    "ô": "o", "ố": "o", "ồ": "o", "ổ": "o", "ỗ": "o", "ộ": "o",
    "ơ": "o", "ớ": "o", "ờ": "o", "ở": "o", "ỡ": "o", "ợ": "o",
    "ú": "u", "ù": "u", "ủ": "u", "ũ": "u", "ụ": "u",
    "ư": "u", "ứ": "u", "ừ": "u", "ử": "u", "ữ": "u", "ự": "u",
    "ý": "y", "ỳ": "y", "ỷ": "y", "ỹ": "y", "ỵ": "y",
    "đ": "d",
}


def strip_diacritics(text: str) -> str:
    """
    Bỏ dấu tiếng Việt (unicode tổ hợp) -> text ASCII.
    Giữ nguyên ký tự khác (chữ cái Latin thường hoa, số, ký tự đặc biệt).
    Return '' nếu text falsy (None/'').
    """
    if not text:
        return ""
    out_chars = []
    for ch in text:
        low = ch.lower()
        mapped = _DIACRITIC_MAP.get(low)
        if mapped is not None:
            if ch.isupper():
                out_chars.append(mapped.upper())
            else:
                out_chars.append(mapped)
        else:
            out_chars.append(ch)
    return "".join(out_chars)


# Compile 1 lần duy nhất cho normalize_category
_CATEGORY_RE = re.compile(r"[-\s_]+")


def normalize_category_token(cat: str) -> str:
    """
    Normalize category cho EP-05 filter: lowercase, bỏ dấu,
    chuyển khoảng trắng / _ / - thành _ để match linh hoạt:
      "Mạo danh" / "Mao danh" / "MAO_DANH" / " mạo-danh  " đều -> "mao_danh"
    """
    if not cat:
        return ""
    base = strip_diacritics(cat).strip().lower()
    base = _CATEGORY_RE.sub("_", base)
    return base
