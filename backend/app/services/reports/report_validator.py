"""
T-030 — Validate & chuẩn hóa thực thể cho FR-04 (Báo cáo lừa đảo cộng đồng)
Theo BR-04-4: PHONE dùng BR-01-9 (E.164); URL/DOMAIN trích domain;
BANK_ACCOUNT chỉ strip khoảng trắng, giữ nguyên số.
"""
from dataclasses import dataclass

from app.models.db_models import EntityType
from app.services.scan.extractor import normalize_phone_to_e164, extract_domain


@dataclass
class ValidatedReportEntity:
    entity_type: EntityType
    normalized_value: str


class InvalidEntityError(Exception):
    """Raise khi entity_type/giá trị không hợp lệ (EX-04-2, EX-04-3)."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def validate_and_normalize_entity(entity_type: str, raw_value: str) -> ValidatedReportEntity:
    """
    Validate + chuẩn hóa 1 thực thể do người dùng khai báo khi report (EP-06).

    Raises:
        InvalidEntityError với code EMPTY_VALUE hoặc INVALID_ENTITY
    """
    if raw_value is None or raw_value.strip() == "":
        raise InvalidEntityError("EMPTY_VALUE", "Vui lòng nhập giá trị cần báo cáo.")

    raw_value = raw_value.strip()

    try:
        entity_type_enum = EntityType(entity_type)
    except ValueError:
        raise InvalidEntityError(
            "INVALID_ENTITY",
            f"Loại thực thể '{entity_type}' không hợp lệ. Chỉ chấp nhận: URL, PHONE, BANK_ACCOUNT, DOMAIN.",
        )

    if entity_type_enum == EntityType.PHONE:
        normalized = normalize_phone_to_e164(raw_value)
        if normalized is None:
            raise InvalidEntityError("INVALID_ENTITY", "Số điện thoại không hợp lệ.")
        return ValidatedReportEntity(entity_type=EntityType.PHONE, normalized_value=normalized)

    if entity_type_enum in (EntityType.URL, EntityType.DOMAIN):
        domain = extract_domain(raw_value)
        if not domain:
            raise InvalidEntityError("INVALID_ENTITY", "Đường link/tên miền không hợp lệ.")
        # BR-04-4: dù người dùng khai báo URL hay DOMAIN, đều lưu dưới dạng DOMAIN
        # để gộp đúng theo entity_type+normalized_value (tránh trùng lặp URL khác path, cùng domain)
        return ValidatedReportEntity(entity_type=EntityType.DOMAIN, normalized_value=domain)

    if entity_type_enum == EntityType.BANK_ACCOUNT:
        normalized = "".join(raw_value.split())  # chỉ bỏ khoảng trắng, giữ nguyên số
        if not normalized.isdigit():
            raise InvalidEntityError("INVALID_ENTITY", "Số tài khoản ngân hàng không hợp lệ.")
        return ValidatedReportEntity(entity_type=EntityType.BANK_ACCOUNT, normalized_value=normalized)

    raise InvalidEntityError("INVALID_ENTITY", "Loại thực thể không được hỗ trợ.")