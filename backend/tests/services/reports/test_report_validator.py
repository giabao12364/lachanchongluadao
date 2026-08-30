import pytest

from app.services.reports.report_validator import (
    validate_and_normalize_entity,
    InvalidEntityError,
)


class TestPhoneValidation:
    def test_valid_phone_normalized_to_e164(self):
        result = validate_and_normalize_entity("PHONE", "0987000111")
        assert result.normalized_value == "+84987000111"

    def test_three_formats_normalize_to_same_value(self):
        # Đúng ví dụ BR-04-4: gộp 3 định dạng SĐT về 1
        r1 = validate_and_normalize_entity("PHONE", "0987000111")
        r2 = validate_and_normalize_entity("PHONE", "+84987000111")
        r3 = validate_and_normalize_entity("PHONE", "84987000111")
        assert r1.normalized_value == r2.normalized_value == r3.normalized_value

    def test_invalid_phone_raises(self):
        with pytest.raises(InvalidEntityError) as exc:
            validate_and_normalize_entity("PHONE", "123")
        assert exc.value.code == "INVALID_ENTITY"


class TestUrlDomainValidation:
    def test_url_extracts_domain(self):
        result = validate_and_normalize_entity("URL", "https://vietcombank-vn.top/nhan")
        assert result.normalized_value == "vietcombank-vn.top"
        assert result.entity_type.value == "DOMAIN"

    def test_domain_input_stays_domain(self):
        result = validate_and_normalize_entity("DOMAIN", "vietcombank-vn.top")
        assert result.normalized_value == "vietcombank-vn.top"


class TestBankAccountValidation:
    def test_valid_bank_account(self):
        result = validate_and_normalize_entity("BANK_ACCOUNT", "0123456789")
        assert result.normalized_value == "0123456789"

    def test_bank_account_strips_spaces(self):
        result = validate_and_normalize_entity("BANK_ACCOUNT", "0123 456 789")
        assert result.normalized_value == "0123456789"

    def test_non_digit_bank_account_raises(self):
        with pytest.raises(InvalidEntityError):
            validate_and_normalize_entity("BANK_ACCOUNT", "abc123")


class TestGeneralValidation:
    def test_empty_value_raises(self):
        with pytest.raises(InvalidEntityError) as exc:
            validate_and_normalize_entity("PHONE", "")
        assert exc.value.code == "EMPTY_VALUE"

    def test_invalid_entity_type_raises(self):
        with pytest.raises(InvalidEntityError) as exc:
            validate_and_normalize_entity("EMAIL", "test@test.com")
        assert exc.value.code == "INVALID_ENTITY"