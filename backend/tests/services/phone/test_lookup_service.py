from types import SimpleNamespace

import pytest

from app.models.db_models import AppConfig, BlacklistEntity, BlacklistSource, RiskLevel
from app.services.phone.lookup_service import InvalidPhoneNumberError, lookup_phone


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class _FakeSession:
    """Fake SQLAlchemy Session — test business logic mà không cần DB thật."""

    def __init__(self, config_row=None, blacklist_row=None):
        self._config_row = config_row
        self._blacklist_row = blacklist_row

    def query(self, model):
        if model is AppConfig:
            return _FakeQuery(self._config_row)
        if model is BlacklistEntity:
            return _FakeQuery(self._blacklist_row)
        return _FakeQuery(None)


def _blacklist_row(source: BlacklistSource, confidence: int):
    return SimpleNamespace(source=source, confidence=confidence)


class TestLookupPhoneInvalid:
    def test_invalid_phone_raises(self):
        db = _FakeSession()
        with pytest.raises(InvalidPhoneNumberError):
            lookup_phone(db, "12345")


class TestLookupPhoneCarrier:
    def test_known_carrier_viettel(self):
        # AT-02-1: Tra số đầu 098 -> reasons có "Nhà mạng: Viettel"
        db = _FakeSession()
        result = lookup_phone(db, "0987654321")
        assert result.carrier == "Viettel"
        assert "Nhà mạng: Viettel" in result.reasons

    def test_unknown_carrier(self):
        # AT-02-2: Tra số đầu số lạ -> reasons có "Không xác định được nhà mạng"
        db = _FakeSession()
        result = lookup_phone(db, "0199999999")
        assert result.carrier == "Không xác định"
        assert "Không xác định được nhà mạng" in result.reasons


class TestLookupPhoneRiskMapping:
    def test_not_in_blacklist_is_an_toan(self):
        # AT-02-4: Tra số không có trong blacklist -> AN_TOAN
        db = _FakeSession(blacklist_row=None)
        result = lookup_phone(db, "0987654321")
        assert result.risk_level == RiskLevel.AN_TOAN
        assert result.has_hard_override is False

    def test_public_feed_is_nguy_hiem(self):
        # AT-02-3: PUBLIC_FEED -> NGUY_HIEM, bất kể confidence
        row = _blacklist_row(BlacklistSource.PUBLIC_FEED, confidence=100)
        db = _FakeSession(blacklist_row=row)
        result = lookup_phone(db, "0912345678")
        assert result.risk_level == RiskLevel.NGUY_HIEM
        assert result.has_hard_override is True

    def test_manual_is_nguy_hiem_even_low_confidence(self):
        row = _blacklist_row(BlacklistSource.MANUAL, confidence=50)
        db = _FakeSession(blacklist_row=row)
        result = lookup_phone(db, "0912345678")
        assert result.risk_level == RiskLevel.NGUY_HIEM

    def test_community_high_confidence_is_nguy_hiem(self):
        row = _blacklist_row(BlacklistSource.COMMUNITY, confidence=95)
        db = _FakeSession(blacklist_row=row)
        result = lookup_phone(db, "0912345678")
        assert result.risk_level == RiskLevel.NGUY_HIEM

    def test_community_low_confidence_is_nghi_ngo(self):
        # BR-01-1b: COMMUNITY + confidence<90 -> tối đa NGHI_NGO
        row = _blacklist_row(BlacklistSource.COMMUNITY, confidence=70)
        db = _FakeSession(blacklist_row=row)
        result = lookup_phone(db, "0912345678")
        assert result.risk_level == RiskLevel.NGHI_NGO
        assert result.has_hard_override is False


class TestLookupPhoneScanResultFields:
    def test_bre_02_5_fields(self):
        # BR-02-5: rule_score=0, ai_score=null, ai_available=true
        db = _FakeSession()
        result = lookup_phone(db, "0987654321")
        assert result.rule_score == 0
        assert result.ai_score is None
        assert result.ai_available is True