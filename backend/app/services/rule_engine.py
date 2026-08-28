import re
from sqlalchemy.orm import Session
from app.models.db_models import ScoringRule


def _match_keyword_list(normalized_text: str, pattern: str) -> bool:
    if not pattern:
        return False
    text_lower = normalized_text.lower()
    for kw in pattern.split(","):
        kw = kw.strip()
        if not kw:
            continue
        if kw.lower() in text_lower:
            return True
    return False


def _match_regex(normalized_text: str, pattern: str) -> bool:
    if not pattern:
        return False
    try:
        return re.search(pattern, normalized_text, re.IGNORECASE | re.MULTILINE) is not None
    except re.error:
        return pattern.lower() in normalized_text.lower()


def _match_tld_list(normalized_text: str, pattern: str) -> bool:
    if not pattern:
        return False
    tlds = [t.strip().lstrip(".").lower() for t in pattern.split(",") if t.strip()]
    if not tlds:
        return False
    tld_group = "|".join(re.escape(t) for t in tlds)
    tld_regex = r"\." + tld_group + r"(?:[\s/!?.,;:]|$)"
    try:
        return re.search(tld_regex, normalized_text, re.IGNORECASE) is not None
    except re.error:
        return False


def run_rule_engine(normalized_text: str, db: Session) -> dict:
    """
    Tầng 3: Nạp scoring_rule từ DB và đối soát pattern để cộng điểm (BR-01-10).
    Hỗ trợ 3 pattern_type: keyword_list | regex | tld_list.
    Điểm cộng dồn và áp trần 100 điểm.
    """
    rules = db.query(ScoringRule).filter(ScoringRule.is_active == True).order_by(ScoringRule.score.desc()).all()

    raw_rule_score = 0
    matched_reasons = []

    for rule in rules:
        pattern = rule.pattern or ""
        score_val = int(rule.score or 0)
        ptype = (rule.pattern_type or "keyword_list").strip().lower()
        matched = False

        if ptype == "keyword_list":
            matched = _match_keyword_list(normalized_text, pattern)
        elif ptype == "regex":
            matched = _match_regex(normalized_text, pattern)
        elif ptype == "tld_list":
            matched = _match_tld_list(normalized_text, pattern)
        else:
            matched = _match_keyword_list(normalized_text, pattern)

        if matched:
            raw_rule_score += score_val
            reason_text = (rule.reason_text or rule.description or f"Phát hiện dấu hiệu {rule.rule_code}").strip()
            matched_reasons.append({
                "source": "RULE",
                "text": reason_text,
                "rule_code": rule.rule_code,
                "score": score_val,
            })

    final_rule_score = min(100, raw_rule_score)
    return {"rule_score": final_rule_score, "reasons": matched_reasons}
