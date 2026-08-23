import unicodedata


def normalize_content(raw_content: str) -> str:
    """
    Tầng 0 — BR-01-8.
    Trim + Unicode NFC, GIỮ dấu tiếng Việt, GIỮ nguyên hoa/thường.
    KHÔNG lowercase ở đây — lowercase chỉ áp dụng lúc so khớp (RuleEngine, tầng 3).
    """
    if raw_content is None:
        raise ValueError("raw_content không được None")
    
    text = raw_content.strip()
    text = unicodedata.normalize("NFC", text)
    return text