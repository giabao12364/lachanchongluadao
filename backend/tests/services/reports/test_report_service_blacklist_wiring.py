"""
Test tích hợp T-032 — xác nhận create_report() ĐÃ nối dây với
blacklist_aggregator.register_independent_report() (BR-04-1).

Bug gốc: report_service.create_report() chỉ tạo ScamReport, không hề
gọi aggregator -> dù 100 người report cùng 1 SĐT/URL, blacklist_entity
vẫn không bao giờ được tạo/auto-active. 

"""
import uuid
from typing import Generator

import pytest
from sqlalchemy.orm import Session

from app.models.db_models import AppUser, BlacklistEntity, EntityType
from app.services.reports.report_service import create_report
from app.services.reports.report_validator import ValidatedReportEntity


@pytest.fixture()
def three_users(db_session: Session) -> Generator[list[AppUser], None, None]:
    """3 user độc lập (3 số điện thoại khác nhau) để mô phỏng '3 report độc lập'."""
    users = [
        AppUser(phone_number=f"+8490{uuid.uuid4().int % 10_000_000:07d}")
        for _ in range(3)
    ]
    db_session.add_all(users)
    db_session.flush()
    yield users
    db_session.rollback()  # dọn sạch, không để lại rác trong DB thật


def _fetch_blacklist_row(db_session: Session, entity_type: EntityType, value: str):
    return (
        db_session.query(BlacklistEntity)
        .filter(
            BlacklistEntity.entity_type == entity_type,
            BlacklistEntity.normalized_value == value,
        )
        .first()
    )


class TestCreateReportWiresIntoBlacklistAggregator:
    def test_three_independent_reports_auto_activates_blacklist(
        self, db_session: Session, three_users: list[AppUser]
    ):
        """
        Đúng ví dụ BR-04-1: 3 report độc lập -> blacklist_entity mới,
        report_count=3, is_active=true, confidence=70.
        """
        entity = ValidatedReportEntity(
            entity_type=EntityType.PHONE,
            normalized_value=f"+84987{uuid.uuid4().int % 1_000_000:06d}",
        )

        for user in three_users:
            result = create_report(db_session, user.id, entity)
            assert result.is_duplicate is False

        row = _fetch_blacklist_row(db_session, entity.entity_type, entity.normalized_value)
        assert row is not None, (
            "create_report() phải tự tạo/cập nhật blacklist_entity qua "
            "register_independent_report() — nếu None nghĩa là dây nối T-032 "
            "đã bị gỡ hoặc chưa được thêm."
        )
        assert row.report_count == 3
        assert row.is_active is True
        assert row.confidence == 70

    def test_one_or_two_reports_not_enough_to_activate(
        self, db_session: Session, three_users: list[AppUser]
    ):
        """Chưa đủ 3 report độc lập -> vẫn tạo blacklist_entity nhưng is_active=False."""
        entity = ValidatedReportEntity(
            entity_type=EntityType.URL,
            normalized_value=f"unactivated-t032-{uuid.uuid4().hex[:8]}.example",
        )

        create_report(db_session, three_users[0].id, entity)
        create_report(db_session, three_users[1].id, entity)

        row = _fetch_blacklist_row(db_session, entity.entity_type, entity.normalized_value)
        assert row is not None
        assert row.report_count == 2
        assert row.is_active is False

    def test_duplicate_report_from_same_user_does_not_double_count(
        self, db_session: Session, three_users: list[AppUser]
    ):
        """
        BR-04-2: cùng 1 user report trùng thực thể chỉ tính 1 lần.
        Gọi create_report() 2 lần với CÙNG user -> report_count vẫn phải là 1,
        không phải 2 (aggregator không được gọi ở nhánh is_duplicate=True).
        """
        entity = ValidatedReportEntity(
            entity_type=EntityType.DOMAIN,
            normalized_value=f"dup-user-t032-{uuid.uuid4().hex[:8]}.example",
        )
        user = three_users[0]

        first = create_report(db_session, user.id, entity)
        second = create_report(db_session, user.id, entity)

        assert first.is_duplicate is False
        assert second.is_duplicate is True

        row = _fetch_blacklist_row(db_session, entity.entity_type, entity.normalized_value)
        assert row is not None
        assert row.report_count == 1 