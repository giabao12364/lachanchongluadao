import threading
import uuid

from app.core.database import SessionLocal
from app.models.db_models import BlacklistEntity, BlacklistSource, EntityType
from app.services.reports.blacklist_aggregator import register_independent_report


def _unique_value(prefix: str) -> str:
    """Giá trị test luôn khác nhau giữa các lần chạy — tránh trùng dữ liệu
    thật/seed, và giúp các test không cần commit vẫn không lo đụng nhau
    nếu lỡ chạy song song (pytest -n auto)."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class TestFirstReport:
    def test_creates_new_entity_inactive(self, db_session):
        phone = _unique_value("+84900")
        entity = register_independent_report(db_session, EntityType.PHONE, phone)

        assert entity.report_count == 1
        assert entity.is_active is False
        # KHÔNG gọi db_session.commit() -> fixture tự rollback khi đóng
        # session (session.close() sau khối try/finally trong conftest),
        # không để lại rác trong DB test.


class TestAutoActive:
    def test_reaches_threshold_becomes_active(self, db_session):
        domain = _unique_value("vn-scam-test")

        register_independent_report(db_session, EntityType.DOMAIN, domain)
        register_independent_report(db_session, EntityType.DOMAIN, domain)
        entity = register_independent_report(db_session, EntityType.DOMAIN, domain)

        # Không insert AppConfig tay — dùng đúng giá trị đã seed theo L4.4
        # (report.auto_active_threshold=3, report.community_confidence=70),
        # hoặc nếu DB test chưa seed, hàm tự fallback default cũng = 3/70.
        assert entity.report_count == 3
        assert entity.is_active is True
        assert entity.confidence == 70
        assert entity.source == BlacklistSource.COMMUNITY

    def test_below_threshold_stays_inactive(self, db_session):
        domain = _unique_value("vn-scam-test")

        register_independent_report(db_session, EntityType.DOMAIN, domain)
        entity = register_independent_report(db_session, EntityType.DOMAIN, domain)

        assert entity.report_count == 2
        assert entity.is_active is False

    def test_already_active_not_recomputed(self, db_session):
        domain = _unique_value("vn-scam-test")

        for _ in range(3):
            register_independent_report(db_session, EntityType.DOMAIN, domain)
        entity = register_independent_report(db_session, EntityType.DOMAIN, domain)

        assert entity.report_count == 4
        assert entity.is_active is True
        assert entity.confidence == 70  # không bị tính lại/đổi giá trị khác


class TestConcurrency:
    """
    Test riêng cho đúng bug đã sửa (race condition khi 2 request cùng lúc
    report 1 entity HOÀN TOÀN MỚI). Cần 2 session độc lập + commit thật,
    nên KHÔNG dùng chung fixture db_session (chỉ 1 session, không đại diện
    2 transaction song song) — tự tạo session riêng, tự dọn dẹp sau test.
    """

    def test_concurrent_new_entity_no_lost_update(self):
        phone = _unique_value("+84901")
        results: list[int] = []
        errors: list[Exception] = []

        def _report():
            session = SessionLocal()
            try:
                entity = register_independent_report(session, EntityType.PHONE, phone)
                session.commit()
                results.append(entity.report_count)
            except Exception as e:
                session.rollback()
                errors.append(e)
            finally:
                session.close()

        t1 = threading.Thread(target=_report)
        t2 = threading.Thread(target=_report)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        cleanup = SessionLocal()
        try:
            cleanup.query(BlacklistEntity).filter(
                BlacklistEntity.entity_type == EntityType.PHONE,
                BlacklistEntity.normalized_value == phone,
            ).delete()
            cleanup.commit()
        finally:
            cleanup.close()

        assert errors == [], f"Không được có lỗi văng ra: {errors}"
        assert sorted(results) == [1, 2], (
            f"2 report cùng lúc 1 entity mới phải ra đúng report_count=1 và =2 "
            f"(không lost-update, không trùng), thực tế: {results}"
        )