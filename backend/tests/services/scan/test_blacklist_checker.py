from types import SimpleNamespace

from app.models.db_models import BlacklistSource, EntityType, RiskLevel
from app.services.scan.blacklist_checker import check_entity_against_blacklist
from app.services.scan.extractor import ExtractedEntity


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class _FakeSession:
    """Giả lập đủ để check_entity_against_blacklist chạy được, không cần DB thật."""

    def __init__(self, blacklist_row=None, config_value=None):
        self._blacklist_row = blacklist_row
        self._config_value = config_value

    def query(self, model):
        if model.__name__ == "BlacklistEntity":
            return _FakeQuery(self._blacklist_row)
        if model.__name__ == "AppConfig":
            row = SimpleNamespace(value=self._config_value) if self._config_value else None
            return _FakeQuery(row)
        raise AssertionError(f"Unexpected model queried: {model}")


def _entity(entity_type, value="x"):
    return ExtractedEntity(entity_type=entity_type, raw_value=value, normalized_value=value)


class TestNoMatch:
    def test_not_in_blacklist_returns_unmatched(self):
        db = _FakeSession(blacklist_row=None)
        result = check_entity_against_blacklist(db, _entity(EntityType.URL))
        assert result.matched is False
        assert result.has_hard_override is False
        assert result.capped_risk_level is None


class TestHardOverride:
    def test_public_feed_source_triggers_hard_override(self):
        # Đúng ví dụ BR-01-1: domain trong blacklist, source=PUBLIC_FEED
        row = SimpleNamespace(source=BlacklistSource.PUBLIC_FEED, confidence=100)
        db = _FakeSession(blacklist_row=row)
        result = check_entity_against_blacklist(db, _entity(EntityType.URL))

        assert result.matched is True
        assert result.has_hard_override is True
        assert result.capped_risk_level is None
        assert result.reason_text == "Đường link này đã được xác nhận là trang lừa đảo."

    def test_manual_source_triggers_hard_override(self):
        row = SimpleNamespace(source=BlacklistSource.MANUAL, confidence=100)
        db = _FakeSession(blacklist_row=row)
        result = check_entity_against_blacklist(db, _entity(EntityType.PHONE))
        assert result.has_hard_override is True

    def test_community_source_with_high_confidence_triggers_hard_override(self):
        row = SimpleNamespace(source=BlacklistSource.COMMUNITY, confidence=90)
        db = _FakeSession(blacklist_row=row, config_value="90")
        result = check_entity_against_blacklist(db, _entity(EntityType.URL))
        assert result.has_hard_override is True

    def test_uses_custom_threshold_from_app_config(self):
        # confidence=85 không đủ ngưỡng MẶC ĐỊNH 90, nhưng đủ nếu app_config hạ xuống 80
        row = SimpleNamespace(source=BlacklistSource.COMMUNITY, confidence=85)
        db = _FakeSession(blacklist_row=row, config_value="80")
        result = check_entity_against_blacklist(db, _entity(EntityType.URL))
        assert result.has_hard_override is True


class TestCommunityCapped:
    def test_community_low_confidence_capped_at_nghi_ngo(self):
        # Đúng ví dụ BR-01-1b: SĐT bị 3 người báo cáo, source=COMMUNITY, confidence=70
        row = SimpleNamespace(source=BlacklistSource.COMMUNITY, confidence=70)
        db = _FakeSession(blacklist_row=row, config_value="90")
        result = check_entity_against_blacklist(db, _entity(EntityType.PHONE))

        assert result.matched is True
        assert result.has_hard_override is False
        assert result.capped_risk_level == RiskLevel.NGHI_NGO
        assert result.reason_text == "Số này đã bị một số người báo cáo là lừa đảo."