import pytest

from app.services.scan.normalizer import normalize_content


class TestNormalizeContent:
    def test_trims_leading_and_trailing_whitespace(self):
        raw = "  Xin chào  "
        result = normalize_content(raw)
        assert result == "Xin chào"

    def test_keeps_internal_whitespace(self):
        raw = "  Xin  chào  bạn  "
        result = normalize_content(raw)
        assert result == "Xin  chào  bạn"

    def test_keeps_vietnamese_diacritics(self):
        raw = "Tài khoản của bạn sẽ bị khóa trong 24h"
        result = normalize_content(raw)
        assert "à" in result
        assert "ạ" in result
        assert "ả" in result
        assert result == raw

    def test_does_not_lowercase(self):
        raw = "VIETCOMBANK: Tài khoản của bạn sẽ bị khóa"
        result = normalize_content(raw)
        assert result == raw
        assert result != result.lower()

    def test_normalizes_unicode_nfd_to_nfc(self):
        # "à" viết dưới dạng tổ hợp NFD: 'a' + dấu huyền kết hợp (U+0300)
        nfd_text = "a\u0300"
        result = normalize_content(nfd_text)
        # "à" viết dưới dạng NFC: 1 ký tự duy nhất (U+00E0)
        nfc_text = "\u00e0"
        assert result == nfc_text
        assert len(result) == 1

    def test_empty_string_raises_no_error_here(self):
        # Việc chặn EMPTY_CONTENT (422) thuộc tầng validation ở ScanService,
        # không phải trách nhiệm của Normalizer.
        result = normalize_content("")
        assert result == ""

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            normalize_content(None)