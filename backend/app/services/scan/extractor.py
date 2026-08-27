"""
Tầng 1 — Extractor (FR-01.5, BR-01-9)

Trích xuất thực thể (URL, PHONE, BANK_ACCOUNT) từ normalized_text.
Đầu vào PHẢI là normalized_text (đã qua Normalizer ở Tầng 0),
không dùng raw_content trực tiếp để tránh lỗi encoding trên dấu tổ hợp.
"""
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from app.models.db_models import EntityType


@dataclass
class ExtractedEntity:
    entity_type: EntityType
    raw_value: str
    normalized_value: str


# Bắt URL có scheme (http/https) HOẶC domain trần kèm path/query
# (VD: "bit.ly/vcb-xacminh" — đúng ví dụ mẫu trong BR-01-1 và R_SHORT_URL)
URL_PATTERN = re.compile(
    r"(?:https?://[^\s<>\"']+"
    r"|(?:www\.)?[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z]{2,})+(?:/[^\s<>\"']*)?)",
)

# Số điện thoại VN: 0xxxxxxxxx | +84xxxxxxxxx | 84xxxxxxxxx
# Cho phép khoảng trắng/chấm/gạch xen giữa các chữ số (BR-01-9)
PHONE_PATTERN = re.compile(
    r"(?:\+84|84|0)(?:[\s.\-]?\d){9}"
)

BANK_ACCOUNT_PATTERN = re.compile(
    r"(?:stk|số tài khoản|tk số)\s*[:\-]?\s*(\d{6,20})",
    re.IGNORECASE,
)


def normalize_phone_to_e164(raw: str) -> str | None:
    """
    Chuẩn hóa số điện thoại VN về E.164 theo BR-01-9.
    Chấp nhận: 0912345678, +84912345678, 84912345678, có dấu cách/chấm/gạch.
    Trả về None nếu không hợp lệ (không tạo entity, không làm hỏng cả lượt quét).
    """
    digits = re.sub(r"[\s.\-]", "", raw)

    if digits.startswith("+84"):
        digits = digits[3:]
    elif digits.startswith("84"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = digits[1:]
    else:
        return None

    if len(digits) != 9 or not digits.isdigit():
        return None

    return f"+84{digits}"


def extract_domain(url: str) -> str:
    """Trích domain (netloc) từ URL, lowercase để dùng làm normalized_value."""
    candidate = url
    if not candidate.startswith(("http://", "https://")):
        candidate = "http://" + candidate

    parsed = urlparse(candidate)
    domain = parsed.netloc.lower()

    # Loại bỏ "www." đầu domain để chuẩn hóa nhất quán khi so khớp blacklist
    if domain.startswith("www."):
        domain = domain[4:]

    return domain


def _is_false_positive_url(raw_match: str) -> bool:
    """
    Loại các match giả do regex domain-trần quá rộng bắt nhầm,
    ví dụ số điện thoại có dấu chấm, hoặc từ có dấu chấm câu ngẫu nhiên.
    Điều kiện tối thiểu: phải có ít nhất 1 dấu chấm và phần sau dấu chấm cuối
    là chữ cái (TLD hợp lệ, không phải số).
    """
    if "." not in raw_match:
        return True
    tld_candidate = raw_match.rsplit(".", 1)[-1]
    tld_candidate = re.split(r"[/?#]", tld_candidate)[0]
    return not tld_candidate.isalpha()


def extract_entities(normalized_text: str) -> list[ExtractedEntity]:
    """
    Tầng 1 — trích xuất URL, PHONE, BANK_ACCOUNT từ normalized_text.

    Lưu ý thứ tự trích xuất: PHONE và BANK_ACCOUNT trích trước để tránh
    URL_PATTERN (domain trần) bắt nhầm chuỗi số thành domain.
    """
    entities: list[ExtractedEntity] = []
    consumed_spans: list[tuple[int, int]] = []

    # 1. BANK_ACCOUNT trước (có từ khóa rõ ràng "stk", "số tài khoản")
    for match in BANK_ACCOUNT_PATTERN.finditer(normalized_text):
        entities.append(
            ExtractedEntity(
                entity_type=EntityType.BANK_ACCOUNT,
                raw_value=match.group(),
                normalized_value=match.group(1),
            )
        )
        consumed_spans.append(match.span())

    # 2. PHONE
    for match in PHONE_PATTERN.finditer(normalized_text):
        if any(s <= match.start() < e for s, e in consumed_spans):
            continue  # tránh trích trùng nếu đã nằm trong BANK_ACCOUNT match
        e164 = normalize_phone_to_e164(match.group())
        if e164:
            entities.append(
                ExtractedEntity(
                    entity_type=EntityType.PHONE,
                    raw_value=match.group(),
                    normalized_value=e164,
                )
            )
            consumed_spans.append(match.span())

    # 3. URL (sau cùng, để không bắt nhầm số điện thoại thành domain)
    for match in URL_PATTERN.finditer(normalized_text):
        raw = match.group()
        if any(s <= match.start() < e for s, e in consumed_spans):
            continue
        if _is_false_positive_url(raw):
            continue
        entities.append(
            ExtractedEntity(
                entity_type=EntityType.URL,
                raw_value=raw,
                normalized_value=extract_domain(raw),
            )
        )

    return entities