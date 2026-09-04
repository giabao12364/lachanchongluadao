import uuid
from types import SimpleNamespace

from app.models.db_models import EntityType
from app.services.reports.report_service import create_report
from app.services.reports.report_validator import ValidatedReportEntity


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class _FakeSession:
    def __init__(self, existing_report=None):
        self._existing = existing_report
        self.added = []
        self.committed = False

    def query(self, model):
        return _FakeQuery(self._existing)

    def add(self, obj):
        self.added.append(obj)
        # Giả lập DB tự sinh id sau khi add
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = uuid.uuid4()

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        pass

    def rollback(self):
        pass


def _entity(entity_type=EntityType.PHONE, value="+84987000111"):
    return ValidatedReportEntity(entity_type=entity_type, normalized_value=value)


class TestCreateReportFirstTime:
    def test_creates_new_report_when_not_exists(self):
        db = _FakeSession(existing_report=None)
        user_id = uuid.uuid4()

        result = create_report(db, user_id, _entity())

        assert result.is_duplicate is False
        assert result.status == "PENDING"
        assert len(db.added) == 1
        assert db.committed is True


class TestCreateReportDuplicate:
    def test_returns_existing_when_already_reported(self):
        # Đúng ví dụ BR-04-2: User A report 1 thực thể 2 lần
        existing_id = uuid.uuid4()
        existing = SimpleNamespace(id=existing_id, status=SimpleNamespace(value="PENDING"))
        db = _FakeSession(existing_report=existing)
        user_id = uuid.uuid4()

        result = create_report(db, user_id, _entity())

        assert result.is_duplicate is True
        assert result.report_id == existing_id
        assert len(db.added) == 0  # KHÔNG tạo bản ghi mới (BR-04-2)
        assert db.committed is False