from types import SimpleNamespace

from app.models.db_models import BlacklistSource, EntityType
from app.services.reports.blacklist_aggregator import register_independent_report


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class _FakeSession:
    def __init__(self, existing_entity=None, threshold_value="3"):
        self._entity = existing_entity
        self._threshold_value = threshold_value
        self.committed = False

    def query(self, model):
        if model.__name__ == "BlacklistEntity":
            return _FakeQuery(self._entity)
        if model.__name__ == "AppConfig":
            row = SimpleNamespace(value=self._threshold_value) if self._threshold_value else None
            return _FakeQuery(row)
        raise AssertionError(f"Unexpected model: {model}")

    def add(self, obj):
        self._entity = obj  

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        pass


class TestFirstReport:
    def test_creates_new_entity_inactive(self):
        db = _FakeSession(existing_entity=None)
        entity = register_independent_report(db, EntityType.PHONE, "+84987000111")

        assert entity.report_count == 1
        assert entity.is_active is False


class TestAutoActive:
    def test_reaches_threshold_becomes_active(self):
   
        existing = SimpleNamespace(
            report_count=2, is_active=False, confidence=0, source=BlacklistSource.COMMUNITY
        )
        db = _FakeSession(existing_entity=existing, threshold_value="3")

        entity = register_independent_report(db, EntityType.DOMAIN, "vietcombank-vn.top")

        assert entity.report_count == 3
        assert entity.is_active is True
        assert entity.confidence == 70
        assert entity.source == BlacklistSource.COMMUNITY

    def test_below_threshold_stays_inactive(self):
        existing = SimpleNamespace(
            report_count=1, is_active=False, confidence=0, source=BlacklistSource.COMMUNITY
        )
        db = _FakeSession(existing_entity=existing, threshold_value="3")

        entity = register_independent_report(db, EntityType.DOMAIN, "vietcombank-vn.top")

        assert entity.report_count == 2
        assert entity.is_active is False

    def test_already_active_not_recomputed(self):
        
        existing = SimpleNamespace(
            report_count=3, is_active=True, confidence=70, source=BlacklistSource.COMMUNITY
        )
        db = _FakeSession(existing_entity=existing, threshold_value="3")

        entity = register_independent_report(db, EntityType.DOMAIN, "vietcombank-vn.top")

        assert entity.report_count == 4
        assert entity.is_active is True