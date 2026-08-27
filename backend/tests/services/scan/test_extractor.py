from app.models.db_models import EntityType
from app.services.scan.extractor import (
    extract_domain,
    extract_entities,
    normalize_phone_to_e164,
)


class TestNormalizePhoneToE164:
    def test_local_format(self):
        assert normalize_phone_to_e164("0912345678") == "+84912345678"

    def test_plus84_format(self):
        assert normalize_phone_to_e164("+84912345678") == "+84912345678"

    def test_84_format_no_plus(self):
        assert normalize_phone_to_e164("84912345678") == "+84912345678"

    def test_with_spaces(self):
        assert normalize_phone_to_e164("0912 345 678") == "+84912345678"

    def test_with_dots(self):
        assert normalize_phone_to_e164("0912.345.678") == "+84912345678"

    def test_invalid_returns_none(self):
        assert normalize_phone_to_e164("12345") is None

    def test_wrong_prefix_returns_none(self):
        assert normalize_phone_to_e164("1912345678") is None


class TestExtractDomain:
    def test_full_url_with_scheme(self):
        assert extract_domain("https://vietcombank-vn.top/nhan") == "vietcombank-vn.top"

    def test_bare_domain_with_path(self):
        assert extract_domain("bit.ly/vcb-xacminh") == "bit.ly"

    def test_strips_www(self):
        assert extract_domain("https://www.example.com/x") == "example.com"


class TestExtractEntities:
    def test_extracts_phone_from_message(self):
        text = "Gọi ngay số 0912345678 để nhận thưởng"
        entities = extract_entities(text)
        phones = [e for e in entities if e.entity_type == EntityType.PHONE]
        assert len(phones) == 1
        assert phones[0].normalized_value == "+84912345678"

    def test_extracts_short_url_bare_domain(self):
        # Ví dụ mẫu chính xác từ spec (trang 13, "Ví dụ tính điểm hoàn chỉnh")
        text = "VIETCOMBANK: Tài khoản của bạn sẽ bị khóa trong 24h. Xác minh ngay tại bit.ly/vcb-xacminh"
        entities = extract_entities(text)
        urls = [e for e in entities if e.entity_type == EntityType.URL]
        assert len(urls) == 1
        assert urls[0].normalized_value == "bit.ly"

    def test_extracts_lookalike_domain_with_scheme(self):
        text = "Nhận thưởng tại https://vietcombank-vn.top/nhan"
        entities = extract_entities(text)
        urls = [e for e in entities if e.entity_type == EntityType.URL]
        assert len(urls) == 1
        assert urls[0].normalized_value == "vietcombank-vn.top"

    def test_extracts_bank_account(self):
        text = "Chuyển tiền vào STK 0123456789 để nhận quà"
        entities = extract_entities(text)
        accounts = [e for e in entities if e.entity_type == EntityType.BANK_ACCOUNT]
        assert len(accounts) == 1
        assert accounts[0].normalized_value == "0123456789"

    def test_invalid_phone_not_extracted(self):
        text = "Số điện thoại của tôi là 12345 nhé"
        entities = extract_entities(text)
        phones = [e for e in entities if e.entity_type == EntityType.PHONE]
        assert len(phones) == 0

    def test_empty_text_returns_empty_list(self):
        assert extract_entities("") == []

    def test_plain_text_no_entities(self):
        text = "Xin chào, hôm nay trời đẹp quá"
        assert extract_entities(text) == []

    def test_multiple_entities_in_one_message(self):
        text = "Gọi 0912345678 hoặc vào bit.ly/xacminh, chuyển vào STK 0123456789"
        entities = extract_entities(text)
        types_found = {e.entity_type for e in entities}
        assert EntityType.PHONE in types_found
        assert EntityType.URL in types_found
        assert EntityType.BANK_ACCOUNT in types_found