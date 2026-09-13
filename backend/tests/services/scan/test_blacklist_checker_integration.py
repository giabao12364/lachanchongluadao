"""
Test tích hợp T-012 (fix) — check_entity_against_blacklist() phải khớp
cả entity_type=URL lẫn DOMAIN cho cùng 1 địa chỉ web, và phải chọn đúng
dòng đáng tin cậy nhất khi có nhiều dòng cùng khớp.

Bug gốc: seed blacklist (T-003) lưu domain dạng entity_type=DOMAIN,
nhưng Extractor (T-011) luôn tạo scan_entity với entity_type=URL khi
quét -> filter so khớp tuyệt đối khiến domain trong blacklist không
bao giờ được phát hiện (vi phạm BR-01-1).

"""
import uuid
from typing import Generator

import pytest
from sqlalchemy.orm import Session

from app.models.db_models import BlacklistEntity, BlacklistSource, EntityType
from app.services.scan.blacklist_checker import check_entity_against_blacklist
from app.services.scan.extractor import ExtractedEntity


@pytest.fixture()
def blacklisted_domain(db_session: Session) -> Generator[BlacklistEntity, None, None]:
    """Seed 1 domain lừa đảo dạng entity_type=DOMAIN, giống style T-003."""
    domain = f"scam-t012-{uuid.uuid4().hex[:8]}.example"
    row = BlacklistEntity(
        entity_type=EntityType.DOMAIN,
        normalized_value=domain,
        source=BlacklistSource.MANUAL,
        confidence=95,
        is_active=True,
    )
    db_session.add(row)
    db_session.flush()
    yield row
    db_session.rollback()  # dọn sạch, không để lại rác trong DB thật


class TestBlacklistEntityTypeCrossMatch:
    def test_scan_url_entity_matches_domain_blacklist_row(
        self, db_session: Session, blacklisted_domain: BlacklistEntity
    ):
        """
        Đây là ca tái hiện đúng bug T-012: entity quét được gắn
        entity_type=URL (như Extractor luôn tạo), nhưng blacklist lưu
        entity_type=DOMAIN. Trước khi fix: matched=False (bug).
        Sau khi fix: phải matched=True, has_hard_override=True (MANUAL).
        """
        scanned_entity = ExtractedEntity(
            entity_type=EntityType.URL,
            raw_value=f"http://{blacklisted_domain.normalized_value}/login",
            normalized_value=blacklisted_domain.normalized_value,
        )

        result = check_entity_against_blacklist(db_session, scanned_entity)

        assert result.matched is True, (
            "Domain trong blacklist (entity_type=DOMAIN) phải được phát hiện "
            "khi quét dù scan_entity gắn entity_type=URL (bug T-012)"
        )
        assert result.has_hard_override is True  # source=MANUAL -> chốt chặn cứng

    def test_unrelated_phone_entity_does_not_match_domain_blacklist(
        self, db_session: Session, blacklisted_domain: BlacklistEntity
    ):
        """Đảm bảo fix không làm rộng match sai sang loại thực thể khác (PHONE)."""
        scanned_entity = ExtractedEntity(
            entity_type=EntityType.PHONE,
            raw_value="+84987000111",
            normalized_value="+84987000111",
        )

        result = check_entity_against_blacklist(db_session, scanned_entity)

        assert result.matched is False


class TestMultipleMatchingRowsPicksMostTrusted:
    def test_public_feed_row_wins_over_community_row_same_value(self, db_session: Session):
        """
        Cùng 1 domain có 2 dòng: 1 dòng COMMUNITY confidence thấp (entity_type=URL,
        có thể do lỡ seed nhầm hoặc report cũ), 1 dòng PUBLIC_FEED xác thực
        (entity_type=DOMAIN). Phải luôn chọn dòng PUBLIC_FEED -> hard_override=True,
        bất kể thứ tự insert.
        """
        value = f"dup-t012-{uuid.uuid4().hex[:8]}.example"

        weak = BlacklistEntity(
            entity_type=EntityType.URL,
            normalized_value=value,
            source=BlacklistSource.COMMUNITY,
            confidence=70,
            is_active=True,
        )
        strong = BlacklistEntity(
            entity_type=EntityType.DOMAIN,
            normalized_value=value,
            source=BlacklistSource.PUBLIC_FEED,
            confidence=100,
            is_active=True,
        )
        db_session.add_all([weak, strong])
        db_session.flush()

        try:
            result = check_entity_against_blacklist(
                db_session,
                ExtractedEntity(entity_type=EntityType.URL, raw_value=value, normalized_value=value),
            )
            assert result.matched is True
            assert result.has_hard_override is True  # phải chọn dòng PUBLIC_FEED, không phải COMMUNITY
        finally:
            db_session.rollback()